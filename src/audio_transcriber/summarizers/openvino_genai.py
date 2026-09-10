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
from ..summary import (
    STAGE_READING,
    STAGE_WRITING,
    NotEnoughMemory,
    SummaryError,
    language_of,
    reduce as reduce_sentences,
    reduction_note,
)
from . import plan, prompting

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
        if not think:
            self._no_thinking(config)

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


def _cut_to_fit(sentences, budget, chosen, language="it", tries=3):
    """Select down until the transcript really does fit in the passes allowed.

    Aiming at ``max_passes * budget`` tokens is close but not exact: a chunk
    also carries a minute and a name per line, and the overlap repeats part of
    each one. Rather than model those, the chunker is asked and the target
    adjusted by what it answers, which converges in two rounds and cannot
    disagree with the thing it is trying to satisfy."""
    target = budget * chosen.max_passes
    kept, parts = list(sentences), prompting.chunks(sentences, budget,
                                                    chosen.chunk_overlap)
    for _ in range(tries):
        if target <= 0:
            break
        kept = reduce_sentences(sentences, int(target), language)
        parts = prompting.chunks(kept, budget, chosen.chunk_overlap)
        if len(parts) <= chosen.max_passes:
            break
        target = int(target * chosen.max_passes / len(parts))
    return kept, parts


def _read(pipeline, system, parts, language, chosen, report, band):
    """The map stage: one answer per chunk, and the sentences behind each.

    Returns the answers with the chunk they came from, because a reduce pass
    above needs the source to check itself against and only this level knows
    which sentences went into which answer."""
    low, high = band
    partials = []
    for index, part in enumerate(parts, start=1):
        print(t("summary.pass", part=index, total=len(parts)), file=sys.stderr)
        report(low + (high - low) * (index - 1) // len(parts), STAGE_READING)
        answer = pipeline.ask(
            system, prompting.map_prompt(part, language, index, len(parts)),
            max_new_tokens=chosen.map_answer_tokens, think=False)
        partials.append((answer, list(part)))
    return partials


def _fold(pipeline, system, partials, language, chosen, report, band):
    """The reduce stage: fold the answers in a tree until one is left.

    Every pass is handed a small extract of the transcript underneath it. The
    partials it is merging are the model's own writing, and by the second
    level it has no other way to tell what it made up one level down."""
    low, high = band
    fanin = prompting.fanin_for(
        len(partials), chosen.context_tokens, chosen.map_answer_tokens,
        chosen.reduce_answer_tokens, prompting.EVIDENCE_TOKENS)
    levels = prompting.reduce_tree(partials, fanin=fanin, max_fanin=fanin)
    prompt = ""
    for depth, level in enumerate(levels):
        report(low + (high - low) * depth // max(1, len(levels)), STAGE_WRITING)
        root = depth == len(levels) - 1
        folded = []
        for group in level:
            texts = [partials[index][0] for index in group]
            sentences = [line for index in group for line in partials[index][1]]
            evidence = prompting.evidence_for(sentences, language=language)
            if root:
                print(t("summary.reducing", total=len(partials)), file=sys.stderr)
                prompt = prompting.reduce_prompt(texts, language, evidence)
                answer = pipeline.ask(system, prompt,
                                      max_new_tokens=chosen.reduce_answer_tokens)
            else:
                print(t("summary.folding", groups=len(level), level=depth + 1),
                      file=sys.stderr)
                prompt = prompting.reduce_partial_prompt(texts, language,
                                                         evidence)
                answer = pipeline.ask(system, prompt,
                                      max_new_tokens=chosen.map_answer_tokens)
            folded.append((answer, sentences))
        partials = folded
    return partials[0][0], prompt


def summarize(material, settings=None, progress=None):
    """Write the summary, in one pass or as a tree of them.

    Returns the sections and no caveat: unlike the extractive engine, this one
    really did write prose about the recording, and the line under the title
    already names the model that did it."""
    settings = settings or {}
    language = language_of(material.language)
    sentences = list(material.sentences)

    def report(percent, stage):
        if progress:
            progress(percent, stage)

    chosen = plan.resolve_plan(plan.OPENVINO, settings)
    if chosen is None:
        needed = plan.cheapest(plan.OPENVINO)
        free = plan.usable_ram_gb(available_ram_gb(), total_ram_gb())
        raise NotEnoughMemory(
            t("summary.no_room",
              needed="?" if needed is None else f"{needed:.1f}",
              free="?" if free is None else f"{free:.1f}"),
            needed=needed, free=free)
    warn_if_over_budget(chosen)

    hf_id = resolve_model(settings.get("summary_model"), settings) \
        or chosen.model.hf_id or chosen.model.name
    device = resolve_device(settings.get("summary_device"))
    system = prompting.prompts_for(language)["system"]

    budget = int(settings.get("summary_chunk_tokens") or chosen.chunk_tokens)
    parts = prompting.chunks(sentences, budget, chosen.chunk_overlap)
    if not parts:
        raise SummaryError(t("summary.empty"))

    note = None
    if chosen.prereduce and chosen.max_passes and len(parts) > chosen.max_passes:
        # More passes than this machine should spend. Rather than read all of
        # it badly, read the weightiest part of it properly: the selection is
        # one matrix multiplication and costs nothing, and every pass saved is
        # minutes on a machine with no accelerator. The page says what share
        # arrived.
        print(t("summary.prereducing", passes=len(parts),
                allowed=chosen.max_passes), file=sys.stderr)
        kept, parts = _cut_to_fit(sentences, budget, chosen, language)
        note = reduction_note(sentences, kept, language)
        sentences = kept

    report(4, "stage.loading_model")
    model_path = prepare(hf_id, settings.get("models_dir"))
    pipeline = Pipeline(model_path, device)

    if len(parts) == 1:
        report(READING_BAND[0], STAGE_READING)
        prompt = prompting.single_prompt(parts[0], language)
        answer = pipeline.ask(system, prompt,
                              max_new_tokens=chosen.reduce_answer_tokens)
    else:
        low, high = READING_BAND
        seam = low + (high - low) * 2 // 3
        partials = _read(pipeline, system, parts, language, chosen, report,
                         (low, seam))
        answer, prompt = _fold(pipeline, system, partials, language, chosen,
                               report, (seam, high))

    sections = prompting.parse(answer, language, prompt)
    if not (sections.abstract or sections.points or sections.decisions
            or sections.actions):
        raise SummaryError(t("summary.model_said_nothing", model=hf_id))
    return sections, note


def warn_if_over_budget(chosen):
    """Say so when a model named by hand does not fit the estimate.

    It is still loaded: somebody who typed a model name has the right to be
    wrong about their own machine. They do not have the right to be surprised
    about it afterwards."""
    if chosen is None or chosen.est_ram_gb is None:
        return False
    usable = plan.usable_ram_gb(available_ram_gb(), total_ram_gb())
    if usable is None or chosen.est_ram_gb <= usable:
        return False
    print(t("summary.over_budget", model=chosen.model.name,
            needed=f"{chosen.est_ram_gb:.1f}", free=f"{usable:.1f}"),
          file=sys.stderr)
    return True


def label(settings=None):
    """How the page should name this engine, model included."""
    settings = settings or {}
    name = resolve_model(settings.get("summary_model"), settings)
    return f"{LABEL} — {name}" if name else LABEL
