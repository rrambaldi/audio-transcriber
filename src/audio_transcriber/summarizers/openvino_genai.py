"""The engine that writes: a local model on an Intel device, via OpenVINO.

This is the half of a summary that needs a language model — the abstract, the
decisions, who agreed to do what — and on a machine with an Intel iGPU it is
where the feature stops being a list of quoted sentences and starts being a
document. An 8B at int4 is about five gigabytes and reads an hour of speech in
a couple of minutes; the same model on a CPU would take most of an afternoon.

The model runs on this machine. Nothing is uploaded, and there is no endpoint
to configure.

Three parts, in order of how often they bite:

*the device*
    ``auto`` means the iGPU, then the CPU. The **NPU is deliberately skipped**:
    its LLM pipeline works on static shapes with the prompt capped at 1024
    tokens by default and 8K at best, and an hour of transcript is fifteen
    thousand — it is the right accelerator for small, constant work and the
    wrong one for reading a meeting. Asked for by name it is still honoured,
    with a warning, because somebody summarising a five-minute note on battery
    has a case.
*the model*
    Named the way the keyword sets are: a size this machine can carry, or any
    Hugging Face id, or a directory that already holds a converted model. The
    first run converts it to OpenVINO IR at int4 and keeps it in the managed
    model directory; every run after that loads it.
*the reading*
    A transcript that fits goes in one pass. One that does not is cut into
    chunks on sentence boundaries, each summarised on its own, and the chunk
    summaries summarised together — the prompts and the parsing for both live
    in :mod:`~audio_transcriber.summarizers.prompting`, so the next runtime
    inherits them.

Everything this module says goes to stderr. Converting a model and loading it
are progress, not output, and the summary itself may be on its way to a file:
``summarize --print > notes.md`` must produce notes, not notes with a loading
message at the top.
"""
import os
import re
import sys

from .. import paths
from ..hardware import available_ram_gb, openvino_devices
from ..i18n import t
from ..summary import (
    STAGE_READING,
    STAGE_WRITING,
    SummaryError,
    language_of,
)
from . import prompting

NAME = "openvino"

#: How the page names this engine. The model is appended when it is known.
LABEL = "OpenVINO GenAI"

#: Recommended models by the memory they need once converted to int4, largest
#: first. Any Hugging Face id works; these are what ``auto`` chooses between,
#: and the numbers are the weights plus room for the KV cache of a long
#: transcript, which is the part people forget.
MODELS = (
    ("Qwen/Qwen3-8B", 9.0),
    ("Qwen/Qwen3-4B", 5.0),
    ("Qwen/Qwen3-1.7B", 2.5),
)

#: Where converted models are kept, under the managed model directory.
NAMESPACE = "summary"

#: Weight precision the first run converts to. int4 is the reason an 8B fits
#: on a laptop at all; the quality cost on a summarisation task is small and
#: the memory saving is not.
BITS = 4

#: Tokens the model may spend on one answer.
MAX_NEW_TOKENS = 1400

#: The band of a progress bar the reading passes are mapped into. Loading and
#: compiling the model own the first slice, and writing the final summary the
#: last: on a long transcript the passes really are most of the wait.
READING_BAND = (10, 85)


def resolve_device(device=None):
    """The Intel device to run on: the iGPU if there is one, else the CPU."""
    devices = openvino_devices()
    requested = str(device or "auto").strip().upper()

    def find(prefix):
        for name in devices:
            if name.upper() == prefix or name.upper().startswith(prefix + "."):
                return name
        return None

    if requested in ("", "AUTO"):
        return find("GPU") or find("CPU") or (devices[0] if devices else "CPU")

    if requested.startswith("NPU"):
        print(t("summary.npu_warning"), file=sys.stderr)

    if not devices:
        return requested
    found = requested if requested in devices else find(requested.split(".")[0])
    if found:
        return found

    fallback = find("CPU") or "CPU"
    print(t("openvino.device_unavailable", requested=requested,
            found=", ".join(devices) or "-", fallback=fallback), file=sys.stderr)
    return fallback


def recommend_model(ram=None):
    """The largest recommended model this machine can hold, by free memory.

    On an integrated GPU the model lives in system memory, so free RAM is the
    real limit whichever device runs it."""
    free = available_ram_gb() if ram is None else ram
    if free is None:
        return MODELS[-1][0]
    for name, needed in MODELS:
        if free >= needed:
            return name
    return MODELS[-1][0]


def resolve_model(model=None, ram=None):
    """What to load: a directory as given, or a name to convert and cache."""
    name = str(model or "auto").strip()
    if not name or name.lower() == "auto":
        name = recommend_model(ram)
    return name


def converted_dir(hf_id, models_dir=None):
    """Where the converted form of ``hf_id`` lives.

    Under the configured model directory when there is one, so a server that
    keeps its models on a volume keeps these there too — they are the largest
    files this program downloads after the recordings themselves."""
    root = (os.path.join(models_dir, NAMESPACE) if models_dir
            else paths.models_dir(NAMESPACE))
    return os.path.join(root, re.sub(r"[^\w.-]", "_", hf_id) + f"-ov-int{BITS}")


def prepare(hf_id, models_dir=None):
    """Return a directory holding a model OpenVINO GenAI can open.

    A path that is already one is used as it is — somebody who converted a
    model by hand should not have it converted again. Otherwise the model is
    fetched and converted once, and kept.

    The tokenizer is the part worth knowing about: ``save_pretrained`` writes
    the Hugging Face tokenizer files, which the GenAI runtime cannot read. It
    needs ``openvino_tokenizer.xml`` and its detokenizer, and those come from
    a separate conversion step. Without it the model loads and the pipeline
    fails at the first prompt."""
    if os.path.isdir(hf_id) and os.path.exists(os.path.join(hf_id, "openvino_model.xml")):
        return hf_id

    target = converted_dir(hf_id, models_dir)
    if os.path.exists(os.path.join(target, "openvino_tokenizer.xml")):
        print(t("openvino.reusing_model", path=target), file=sys.stderr)
        return target

    try:
        import openvino
        from openvino_tokenizers import convert_tokenizer
        from optimum.intel import OVModelForCausalLM, OVWeightQuantizationConfig
        from transformers import AutoTokenizer
    except ImportError:
        raise SummaryError(t("summary.openvino_convert_missing")) from None

    print(t("summary.converting", model=hf_id, bits=BITS), file=sys.stderr)
    os.makedirs(target, exist_ok=True)
    try:
        model = OVModelForCausalLM.from_pretrained(
            hf_id, export=True,
            quantization_config=OVWeightQuantizationConfig(bits=BITS))
        model.save_pretrained(target)
        tokenizer = AutoTokenizer.from_pretrained(hf_id)
        tokenizer.save_pretrained(target)
        ov_tokenizer, ov_detokenizer = convert_tokenizer(tokenizer,
                                                         with_detokenizer=True)
        openvino.save_model(ov_tokenizer,
                            os.path.join(target, "openvino_tokenizer.xml"))
        openvino.save_model(ov_detokenizer,
                            os.path.join(target, "openvino_detokenizer.xml"))
    except SummaryError:
        raise
    except Exception as exc:
        raise SummaryError(t("summary.conversion_failed", model=hf_id,
                             error=exc)) from exc
    print(t("openvino.model_saved", path=target), file=sys.stderr)
    return target


class Pipeline:
    """The loaded model, and the one thing asked of it: text in, text out.

    A class rather than a function because a map/reduce over a long transcript
    is several prompts against the same model, and compiling it once per
    prompt would cost more than the prompts do."""

    def __init__(self, model_path, device):
        try:
            import openvino_genai
        except ImportError:
            raise SummaryError(t("summary.openvino_missing")) from None
        self._genai = openvino_genai
        print(t("summary.loading_model", path=os.path.basename(model_path),
                device=device), file=sys.stderr)
        try:
            self.pipe = openvino_genai.LLMPipeline(model_path, device)
        except Exception as exc:
            raise SummaryError(t("summary.load_failed", device=device,
                                 error=exc)) from exc
        self.config = openvino_genai.GenerationConfig()
        self.config.max_new_tokens = MAX_NEW_TOKENS
        # Greedy: a summary is not a place for creativity, and two runs over
        # the same recording should not disagree with each other.
        self.config.do_sample = False

    def ask(self, system, user):
        """One prompt, one answer.

        ``ChatHistory`` is the way to give the model a system message; where
        the runtime predates it, the two halves are concatenated and the
        pipeline applies the chat template to the result on its own."""
        genai = self._genai
        if hasattr(genai, "ChatHistory"):
            conversation = genai.ChatHistory([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ])
        else:                                       # pragma: no cover - old runtime
            conversation = f"{system}\n\n{user}"
        return str(self.pipe.generate(conversation, self.config)).strip()


def summarize(material, settings=None, progress=None):
    """Write the summary, in one pass or in two stages.

    Returns the sections and no caveat: unlike the extractive engine, this one
    really did write prose about the recording, and the line under the title
    already names the model that did it."""
    settings = settings or {}
    language = language_of(material.language)
    sentences = list(material.sentences)

    def report(percent, stage):
        if progress:
            progress(percent, stage)

    hf_id = resolve_model(settings.get("summary_model"))
    device = resolve_device(settings.get("summary_device"))
    report(4, "stage.loading_model")
    model_path = prepare(hf_id, settings.get("models_dir"))
    pipeline = Pipeline(model_path, device)
    system = prompting.prompts_for(language)["system"]

    budget = int(settings.get("summary_chunk_tokens") or prompting.CHUNK_TOKENS)
    parts = prompting.chunks(sentences, budget)
    if not parts:
        raise SummaryError(t("summary.empty"))

    if len(parts) == 1:
        report(READING_BAND[0], STAGE_READING)
        prompt = prompting.single_prompt(parts[0], language)
        answer = pipeline.ask(system, prompt)
    else:
        low, high = READING_BAND
        partials = []
        for index, part in enumerate(parts, start=1):
            print(t("summary.pass", part=index, total=len(parts)), file=sys.stderr)
            report(low + (high - low) * (index - 1) // len(parts), STAGE_READING)
            partials.append(pipeline.ask(
                system, prompting.map_prompt(part, language, index, len(parts))))
        print(t("summary.reducing", total=len(parts)), file=sys.stderr)
        report(high, STAGE_WRITING)
        prompt = prompting.reduce_prompt(partials, language)
        answer = pipeline.ask(system, prompt)

    sections = prompting.parse(answer, language, prompt)
    if not (sections.abstract or sections.points or sections.decisions
            or sections.actions):
        raise SummaryError(t("summary.model_said_nothing", model=hf_id))
    return sections, None


def label(settings=None):
    """How the page should name this engine, model included."""
    return f"{LABEL} — {resolve_model((settings or {}).get('summary_model'))}"
