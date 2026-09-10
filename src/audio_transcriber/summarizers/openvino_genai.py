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
    Any Hugging Face id, or a directory that already holds a converted model,
    or — the default — whatever :mod:`~audio_transcriber.summarizers.plan`
    works out this machine can hold. The first run converts it to OpenVINO IR
    at int4 and keeps it in the managed model directory; every run after that
    loads it. When the plan says nothing fits, nothing is loaded: the caller
    is told, and the page is written by the extractive engine instead.
*the reading*
    A transcript that fits goes in one pass. One that does not is cut into
    chunks on sentence boundaries, each summarised on its own, and the chunk
    summaries folded together in a tree rather than in a single prompt — a
    prompt holding every partial grows with the recording, which is what
    overflows a small model. The prompts and the parsing live in
    :mod:`~audio_transcriber.summarizers.prompting`, so the next runtime
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
from ..hardware import available_ram_gb, openvino_devices, total_ram_gb
from ..i18n import t
from ..summary import SummaryError
from . import plan, prompting, reading

NAME = "openvino"

#: How the page names this engine. The model is appended when it is known.
LABEL = "OpenVINO GenAI"

#: Where converted models are kept, under the managed model directory.
NAMESPACE = "summary"

#: Weight precision the first run converts to. int4 is the reason an 8B fits
#: on a laptop at all; the quality cost on a summarisation task is small and
#: the memory saving is not.
BITS = 4

#: Tokens the model may spend on one answer when nothing says otherwise. The
#: plan says otherwise: a map answer is a list and the root answer is a page,
#: and on a small model the difference between them is most of the window.
MAX_NEW_TOKENS = prompting.REDUCE_ANSWER_TOKENS

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


def resolve_model(model=None, settings=None):
    """What to load: a directory or an id as given, or whatever the plan chose.

    On an integrated GPU the model lives in system memory, so free RAM is the
    real limit whichever device runs it — which is why the choice is the
    plan's and not this module's."""
    name = str(model or "auto").strip()
    if name and name.lower() != "auto":
        return name
    chosen = plan.resolve_plan(plan.OPENVINO, settings or {})
    if chosen is None:
        return None
    return chosen.model.hf_id or chosen.model.name


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
        raise SummaryError(_conversion_error(hf_id, exc)) from exc
    print(t("openvino.model_saved", path=target), file=sys.stderr)
    return target


#: What the OpenVINO exporter says when the installed transformers is newer
#: than the architecture's converter was written for. It names the ceiling,
#: which is the one thing needed to get past it.
_TOO_NEW = re.compile(r"Maximum required is ([\d.]+), got:? ([\d.]+)")


def _conversion_error(hf_id, exc):
    """The exporter's complaint, and what to do about it where that is known.

    One failure is common enough and opaque enough to deserve translating:
    the converter for a given architecture is pinned to a maximum version of
    transformers, and an environment that installed a newer one cannot export
    that model at all. The library says so in a sentence that reads like a
    bug; it is a version pin, and the fix is one line."""
    found = _TOO_NEW.search(str(exc))
    if not found:
        return t("summary.conversion_failed", model=hf_id, error=exc)
    return t("summary.conversion_too_new", model=hf_id,
             ceiling=found.group(1), installed=found.group(2))


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
        #: Set once, the first time reasoning cannot be turned off. Saying it
        #: every prompt would bury the transcript's own progress lines.
        self.warned_about_thinking = False
        self.config = openvino_genai.GenerationConfig()
        self.config.max_new_tokens = MAX_NEW_TOKENS
        # Greedy: a summary is not a place for creativity, and two runs over
        # the same recording should not disagree with each other.
        self.config.do_sample = False

    def ask(self, system, user, max_new_tokens=None, think=False):
        """One prompt, one answer.

        ``max_new_tokens`` is per stage rather than per model: a map answer is
        a bulleted list and the final answer is a page, and on a small model
        the difference between the two is most of the window.

        ``think`` is off by default, and the reason is a failure that looks
        like an empty summary. The token budget is the *whole* budget, so a
        reasoning model that narrates for its entire allowance is truncated
        before the answer starts, the parser finds no sections, and the run
        ends in "returned nothing usable". In the map stage there is nothing
        to reason about anyway: the question is what this chunk says.

        ``ChatHistory`` is the way to give the model a system message; where
        the runtime predates it, the two halves are concatenated and the
        pipeline applies the chat template to the result on its own."""
        genai = self._genai
        config = genai.GenerationConfig()
        config.max_new_tokens = int(max_new_tokens or MAX_NEW_TOKENS)
        config.do_sample = False
        if not think and not self._no_thinking(config) and not self.warned_about_thinking:
            # Worth saying out loud, once. A reasoning model whose reasoning
            # stays on spends its allowance narrating and is cut off before
            # the answer begins; what comes back is empty, and an empty answer
            # is indistinguishable from a model too small for the job. The
            # run recovers — it asks again with room — but slowly, and the
            # person watching deserves to know why.
            print(t("summary.thinking_stays_on"), file=sys.stderr)
            self.warned_about_thinking = True

        if hasattr(genai, "ChatHistory"):
            conversation = genai.ChatHistory([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ])
        else:                                       # pragma: no cover - old runtime
            conversation = f"{system}\n\n{user}"
        return str(self.pipe.generate(conversation, config)).strip()

    def _no_thinking(self, config):
        """Turn reasoning off, by whichever means the runtime offers.

        Two of them exist and neither is universal: some builds expose the
        chat template's own switch on the generation config, and some models
        answer to a marker in the prompt. Where neither is reachable this does
        nothing and says so here rather than pretending: a switch that
        silently fails is worse than a documented absence, because the symptom
        is a truncated answer three chunks later."""
        for attribute in ("enable_thinking", "apply_chat_template_kwargs"):
            if not hasattr(config, attribute):
                continue
            if attribute == "enable_thinking":
                config.enable_thinking = False
            else:                       # pragma: no cover - runtime dependent
                kwargs = dict(getattr(config, attribute) or {})
                kwargs["enable_thinking"] = False
                setattr(config, attribute, kwargs)
            return True
        return False


def summarize(material, settings=None, progress=None):
    """Write the summary, in one pass or as a tree of them.

    Everything between having a model and having a page lives in
    :mod:`~audio_transcriber.summarizers.reading`, shared with the other
    engine that writes; what is left here is the model's life cycle, which is
    the only part that is about OpenVINO.

    Returns the sections and, when only part of the transcript reached the
    model, the note that says so."""
    settings = settings or {}
    chosen = reading.choose(plan.OPENVINO, settings, available_ram_gb(),
                            total_ram_gb())
    hf_id = (resolve_model(settings.get("summary_model"), settings)
             or chosen.model.hf_id or chosen.model.name)
    device = resolve_device(settings.get("summary_device"))

    def open_pipeline():
        return Pipeline(prepare(hf_id, settings.get("models_dir")), device)

    return reading.summarize_with(open_pipeline, chosen, material, settings,
                                  progress, model_name=hf_id)


def label(settings=None):
    """How the page should name this engine, model included."""
    settings = settings or {}
    name = resolve_model(settings.get("summary_model"), settings)
    return f"{LABEL} — {name}" if name else LABEL
