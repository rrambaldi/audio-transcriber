"""Reading a transcript with a model, without knowing which model.

Two engines now write summaries — a local model on an Intel device through
OpenVINO, and a GGUF through llama.cpp — and the only thing that differs
between them is how a string becomes an answer. Everything else is the same
work in the same order:

* ask the plan what this machine can hold, and stop if the answer is nothing;
* cut the transcript into passes, selecting it down first when reading all of
  it would take more passes than the plan allows;
* summarise each pass, then fold the answers in a tree, each fold checked
  against a small extract of what was actually said;
* read the markdown back into sections, and refuse an answer that is empty.

Keeping that here rather than in an engine is what made the second engine
cheap and what will make the third one cheaper. An engine supplies a
``Pipeline``: something with ``ask(system, user, max_new_tokens=None,
think=False)`` and a ``close()``, and nothing else is asked of it.

Like the modules it leans on, this one imports no runtime — the engines do
that, behind the factory they pass in.
"""
import sys

from ..i18n import t
from ..summary import (
    STAGE_READING,
    STAGE_WRITING,
    NotEnoughMemory,
    SummaryError,
    language_of,
    reduction_note,
)
from ..summary import (
    reduce as reduce_sentences,
)
from . import partials, plan, prompting

#: The band of a progress bar the reading passes are mapped into. Loading and
#: compiling the model own the first slice, and writing the final summary the
#: last: on a long transcript the passes really are most of the wait.
READING_BAND = (10, 85)

#: Where the map stage hands over to the folding, inside that band.
FOLDING_FROM = 2.0 / 3.0


def cut_to_fit(sentences, budget, chosen, language="it", tries=3):
    """Select down until the transcript really does fit the passes allowed.

    Aiming at ``max_passes * budget`` tokens is close but not exact: a chunk
    also carries a minute and a name per line, and the overlap repeats part of
    each one. Rather than model those, the chunker is asked and the target
    adjusted by what it answers, which converges in two rounds and cannot
    disagree with the thing it is trying to satisfy."""
    target = budget * chosen.max_passes
    kept, parts = list(sentences), prompting.chunks(
        sentences, budget, chosen.chunk_overlap, language)
    for _ in range(tries):
        if target <= 0:
            break
        kept = reduce_sentences(sentences, int(target), language)
        parts = prompting.chunks(kept, budget, chosen.chunk_overlap, language)
        if len(parts) <= chosen.max_passes:
            break
        target = int(target * chosen.max_passes / len(parts))
    return kept, parts


def ask(pipeline, system, prompt, budget, chosen, echo_prompt=None):
    """One prompt, one answer, with the one failure worth retrying.

    A model whose reasoning could not be switched off — the runtime may not
    expose the switch, and this program will not pretend it did — spends the
    whole allowance narrating and is cut off before the answer starts. What
    comes back is indistinguishable from a model too small for the job, and it
    is not the same thing: it is fixed by asking again with the room the
    narration needs, once, and never at the cost of the context."""
    raw = pipeline.ask(system, prompt, max_new_tokens=budget, think=False)
    answer = prompting.usable_answer(raw, echo_prompt)
    if answer or not prompting.thought_without_answering(raw):
        return answer

    room = max(budget, chosen.context_tokens
               - prompting.estimate_tokens(prompt) - 64)
    if room <= budget:
        return answer
    print(t("summary.still_thinking", tokens=room), file=sys.stderr)
    return prompting.usable_answer(
        pipeline.ask(system, prompt, max_new_tokens=room, think=False),
        echo_prompt)


def _map(pipeline, system, parts, language, chosen, report, band,
         cache_dir=None):
    """One answer per chunk, and the sentences behind each.

    The sentences are carried along because a fold above needs the source to
    check itself against, and only this level knows which of them went into
    which answer.

    Each answer is looked up before it is asked for. A pass is deterministic
    and independent, so on a machine where reading is minutes the second run
    over the same recording — a different length, or a job resumed after being
    interrupted — costs nothing at all."""
    low, high = band
    found, written = [], False
    for index, part in enumerate(parts, start=1):
        report(low + (high - low) * (index - 1) // len(parts), STAGE_READING)
        prompt = prompting.map_prompt(part, language, index, len(parts))
        name = partials.key(prompt, chosen.model.name, chosen.quant, "map",
                            chosen.map_answer_tokens, language)
        answer = partials.get(name, cache_dir)
        if answer is None:
            print(t("summary.pass", part=index, total=len(parts)),
                  file=sys.stderr)
            answer = ask(pipeline, system, prompt, chosen.map_answer_tokens,
                         chosen, echo_prompt=prompt)
            if not answer:
                # The model handed back the question. That happens with the
                # small ones, and left alone it poisons every level above:
                # what the fold merges would be the prompt, and the page would
                # look finished. The chunk still has to contribute something,
                # so it contributes the sentences that carry it — arithmetic
                # instead of a model, which is what this program falls back on
                # everywhere else.
                print(t("summary.pass_echoed", part=index, total=len(parts)),
                      file=sys.stderr)
                answer = prompting.evidence_for(part, chosen.map_answer_tokens,
                                                language)
            written = partials.put(name, answer, cache_dir) or written
        else:
            print(t("summary.pass_cached", part=index, total=len(parts)),
                  file=sys.stderr)
        found.append((answer, list(part)))
    if written:
        # This program has no daemon, so the only moment anything can be
        # tidied away is a moment when something was added. A cache that only
        # grows fills the disk of the small machine it was meant to help.
        partials.sweep(cache_dir)
    return found


def _fold(pipeline, system, answers, language, chosen, report, band):
    """Fold the answers in a tree until one is left.

    Every pass is handed a small extract of the transcript underneath it. What
    it is merging is the model's own writing, and by the second level it has
    no other way to tell what it invented one level down."""
    low, high = band
    # How much of the original a fold may be shown is a share of the window,
    # not a constant: four hundred tokens is nothing at sixteen thousand and a
    # fifth of two thousand, where it would come out of the material the fold
    # is there to merge.
    evidence_tokens = plan.evidence_for(chosen.context_tokens)
    fanin = prompting.fanin_for(
        len(answers), chosen.context_tokens, chosen.map_answer_tokens,
        chosen.reduce_answer_tokens, evidence_tokens)
    levels = prompting.reduce_tree(answers, fanin=fanin, max_fanin=fanin)
    prompt = ""
    for depth, level in enumerate(levels):
        report(low + (high - low) * depth // max(1, len(levels)), STAGE_WRITING)
        root = depth == len(levels) - 1
        folded = []
        for group in level:
            texts = [answers[index][0] for index in group]
            sentences = [line for index in group for line in answers[index][1]]
            evidence = prompting.evidence_for(sentences, evidence_tokens,
                                              language)
            if root:
                print(t("summary.reducing", total=len(answers)), file=sys.stderr)
                prompt = prompting.reduce_prompt(texts, language, evidence)
                # No prompt is passed to the echo check here, deliberately.
                # A reduce prompt carries the partial summaries, and those are
                # exactly the content that is supposed to come back: measured
                # against them, a good answer looks like an echo. What a fold
                # can wrongly reproduce is the scaffold, and :func:`parse`
                # recognises that on its own.
                answer = ask(pipeline, system, prompt,
                             chosen.reduce_answer_tokens, chosen)
            else:
                print(t("summary.folding", groups=len(level), level=depth + 1),
                      file=sys.stderr)
                prompt = prompting.reduce_partial_prompt(texts, language,
                                                         evidence)
                answer = ask(pipeline, system, prompt,
                             chosen.map_answer_tokens, chosen) or texts[0]
            folded.append((answer, sentences))
        answers = folded
    return answers[0][0], prompt


def warn_if_over_budget(chosen, available, total):
    """Say so when a model named by hand does not fit the estimate.

    It is still loaded: somebody who typed a model name has the right to be
    wrong about their own machine. They do not have the right to be surprised
    about it afterwards."""
    if chosen is None or chosen.est_ram_gb is None:
        return False
    usable = plan.usable_ram_gb(available, total)
    if usable is None or chosen.est_ram_gb <= usable:
        return False
    print(t("summary.over_budget", model=chosen.model.name,
            needed=f"{chosen.est_ram_gb:.1f}", free=f"{usable:.1f}"),
          file=sys.stderr)
    return True


def choose(engine, settings, available, total):
    """The plan, or a refusal carrying the two numbers the page will print."""
    chosen = plan.resolve_plan(engine, settings)
    if chosen is None:
        needed = plan.cheapest(engine)
        free = plan.usable_ram_gb(available, total)
        raise NotEnoughMemory(
            t("summary.no_room",
              needed="?" if needed is None else f"{needed:.1f}",
              free="?" if free is None else f"{free:.1f}"),
            needed=needed, free=free)
    warn_if_over_budget(chosen, available, total)
    return chosen


def summarize_with(open_pipeline, chosen, material, settings=None,
                   progress=None, model_name=None):
    """Write the summary with whatever ``open_pipeline`` returns.

    The engine has already asked the plan and knows what it is loading; this
    is everything that happens between having a model and having a page, and
    it is the same for every runtime."""
    settings = settings or {}
    language = language_of(material.language)
    sentences = list(material.sentences)

    def report(percent, stage):
        if progress:
            progress(percent, stage)

    budget = int(settings.get("summary_chunk_tokens") or chosen.chunk_tokens)
    parts = prompting.chunks(sentences, budget, chosen.chunk_overlap, language)
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
        kept, parts = cut_to_fit(sentences, budget, chosen, language)
        note = reduction_note(sentences, kept, language)
        sentences = kept

    report(4, "stage.loading_model")
    pipeline = open_pipeline()
    try:
        system = prompting.prompts_for(language)["system"]
        if len(parts) == 1:
            report(READING_BAND[0], STAGE_READING)
            prompt = prompting.single_prompt(parts[0], language)
            # No echo check against this prompt: it carries the headings the
            # answer is supposed to come back under, so measured against it a
            # well-shaped answer looks copied. What a one-pass answer can
            # wrongly reproduce is the transcript, and the fence catches that.
            answer = ask(pipeline, system, prompt,
                         chosen.reduce_answer_tokens, chosen)
        else:
            low, high = READING_BAND
            seam = int(low + (high - low) * FOLDING_FROM)
            answers = _map(pipeline, system, parts, language, chosen, report,
                           (low, seam), settings.get("cache_dir"))
            answer, prompt = _fold(pipeline, system, answers, language,
                                   chosen, report, (seam, high))
    finally:
        close = getattr(pipeline, "close", None)
        if close:
            close()

    sections = prompting.parse(answer, language, prompt)
    if not (sections.abstract or sections.points or sections.decisions
            or sections.actions):
        raise SummaryError(t("summary.model_said_nothing",
                             model=model_name or chosen.model.name))
    return sections, note
