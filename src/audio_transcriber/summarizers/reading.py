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
import math
import sys

from ..i18n import t
from ..summary import (
    DEFAULT_STYLE,
    STAGE_READING,
    STAGE_WRITING,
    NotEnoughMemory,
    SummaryError,
    estimate_tokens,
    language_of,
    points_of,
    reduction_note,
)
from ..summary import (
    reduce as reduce_sentences,
)
from . import grouping, partials, plan, prompting, writing
from . import notes as note_reading
from . import trace as tracing

#: The band of a progress bar the reading passes are mapped into. Loading and
#: compiling the model own the first slice, and writing the final summary the
#: last: on a long transcript the passes really are most of the wait.
READING_BAND = (10, 85)

#: Where the map stage hands over to the folding, inside that band.
FOLDING_FROM = 2.0 / 3.0

#: Left free in the window whatever else is asked for: a tokeniser this
#: program does not have would count the prompt a little differently, and the
#: failure that costs is the transcript losing its tail.
CONTEXT_MARGIN = 128

#: The shape of the finished page: sections the recording produced, or the
#: five fixed headings this feature started with.
#:
#: Sections is the default, and it became one the way it said it would - the
#: day a run said it was better. The number that decided it is the distance
#: between what the passes read and what reached the page. On the same
#: twenty-two minute recording, the same model and the same passes: the old
#: shape read 41% of the minutes and printed 14% of them, and the new one
#: read 36% and printed 36%. Nothing lost in between, on two engines and
#: three runs, which is what the fold could never manage - it had the whole
#: recording to fit in one answer and dropped whatever did not fit.
SECTIONS = "sections"
HEADINGS = "headings"

#: A title is three to eight words. What this buys is a model that stops.
LABEL_TOKENS = 60

#: How much transcript one reading pass is given when the page is written in
#: sections. Not a memory figure - it is a quarter of what the window holds -
#: and not a guess either. The same twenty-two minute recording, the same
#: model, the same everything but this number:
#:
#:     4500 tokens   2 passes   21 notes    36% of the minutes    83 s
#:     2000 tokens   4 passes   58 notes    68%                  152 s
#:     1200 tokens   7 passes   82 notes    96%                  187 s
#:      700 tokens  12 passes  141 notes    96%                  326 s
#:
#: A pass does not read proportionally to what it is given: eleven minutes of
#: meeting in front of it and it writes down twelve things and stops. Halving
#: the chunk buys most of the recording back; halving it again buys nothing
#: but time, and a quarter of the extra notes are repetitions of the ones
#: already taken - 29 duplicates against 6.
READING_CHUNK_TOKENS = 1200


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
         cache_dir=None, fingerprint="", trace=None):
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
                            chosen.map_answer_tokens, language, fingerprint)
        answer = partials.get(name, cache_dir)
        status = tracing.OK
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
                # Not a summary of the chunk: the chunk's own sentences, put
                # where the summary should have been. Recorded as such, so
                # that copy_rate measures the model and not this.
                status = tracing.ECHOED
            written = partials.put(name, answer, cache_dir) or written
        else:
            print(t("summary.pass_cached", part=index, total=len(parts)),
                  file=sys.stderr)
            status = tracing.REUSED
        span = (part[0].start if part else None,
                (part[-1].end or part[-1].start) if part else None)
        written, unknown = note_reading.read(answer, language, index, span)
        if trace is not None:
            trace.chunk(index=index, total=len(parts),
                        budget=chosen.map_answer_tokens,
                        in_tokens=estimate_tokens(prompt, language),
                        out_tokens=estimate_tokens(answer, language),
                        notes=len(written),
                        placed=note_reading.placed(written),
                        unknown_headings=unknown,
                        status=status, span=span,
                        starts=[note.ts_start for note in written])
            trace.answers.append(answer)
            trace.notes.extend(written)
        # What goes up is the notes, laid out flat, and not the answer they
        # were read out of: a bridge until sections are written one cluster at
        # a time and nothing wants a chunk's worth of text in one blob. An
        # answer nothing could be read out of goes up as it came, because a
        # pass that produced prose still produced something.
        found.append((note_reading.as_bullets(written, language) if written
                      else answer, list(part)))
    if written:
        # This program has no daemon, so the only moment anything can be
        # tidied away is a moment when something was added. A cache that only
        # grows fills the disk of the small machine it was meant to help.
        partials.sweep(cache_dir)
    return found


def _fold_to_root(pipeline, system, answers, language, chosen, report, band,
                  trace=None):
    """Fold every level except the root, and return what the root has to
    write from: the partial summaries in time order, and the evidence to
    check them against.

    The root's own answer is the caller's job, because from here on there are
    two different ways to ask for it — one combined request, or one per
    section — and both need the same partials to start from."""
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
    for depth, level in enumerate(levels[:-1]):
        report(low + (high - low) * depth // max(1, len(levels)), STAGE_WRITING)
        folded = []
        for number, group in enumerate(level, start=1):
            texts = [answers[index][0] for index in group]
            sentences = [line for index in group for line in answers[index][1]]
            evidence = prompting.evidence_for(sentences, evidence_tokens,
                                              language)
            print(t("summary.folding", groups=len(level), level=depth + 1),
                  file=sys.stderr)
            prompt = prompting.reduce_partial_prompt(texts, language, evidence)
            written_answer = ask(pipeline, system, prompt,
                                 chosen.map_answer_tokens, chosen)
            # The fallback is left exactly as it was — this pass only writes
            # down what it costs. When the fold says nothing, the group keeps
            # its *first* partial and the rest are gone, which is a silence
            # this program can no longer afford.
            answer = written_answer or texts[0]
            if trace is not None:
                out_tokens = estimate_tokens(written_answer, language)
                if not written_answer:
                    status, lost = tracing.COLLAPSED, max(0, len(texts) - 1)
                elif out_tokens >= chosen.map_answer_tokens * tracing.BUDGET_MARGIN:
                    status, lost = tracing.BUDGET_EXHAUSTED, 0
                else:
                    status, lost = tracing.OK, 0
                trace.fold(level=depth + 1, group=number, groups=len(level),
                           partials_in=len(texts),
                           in_tokens=estimate_tokens("\n".join(texts), language),
                           budget=chosen.map_answer_tokens,
                           out_tokens=out_tokens, status=status, lost=lost)
            folded.append((answer, sentences))
        answers = folded
    report(low + (high - low) * (len(levels) - 1) // max(1, len(levels)),
          STAGE_WRITING)
    print(t("summary.reducing", total=len(answers)), file=sys.stderr)
    # The tree narrows to exactly one group at its top by construction of the
    # fan-in above — unpacking asserts that rather than silently keeping only
    # the first of several, the way indexing would have.
    [root_group] = levels[-1]
    texts = [answers[index][0] for index in root_group]
    sentences = [line for index in root_group for line in answers[index][1]]
    evidence = prompting.evidence_for(sentences, evidence_tokens, language)
    return texts, evidence


def _write_combined(pipeline, system, language, prompt, chosen):
    """One request for all four headings, the only way this feature has ever
    written its root. No prompt is passed to the echo check here, deliberately:
    a reduce/single prompt carries the partial summaries or the transcript,
    and those are exactly the content that is supposed to come back. What a
    fold can wrongly reproduce is the scaffold, and :func:`parse` recognises
    that on its own."""
    answer = ask(pipeline, system, prompt, chosen.reduce_answer_tokens, chosen)
    return prompting.parse(answer, language, prompt), answer


def _write_split(pipeline, system, language, chosen, prompt_for):
    """Ask for the four sections one at a time, then check them against each
    other before the page sees them.

    ``prompt_for(field)`` builds one field's question from whatever the root
    has to write from — the caller knows whether that is the transcript
    directly or the folded partials, and this function does not need to.

    Splitting the one combined request into four removes the failure
    :func:`~audio_transcriber.summarizers.prompting.parse` cannot parse its
    way around: a model that cannot keep four headings straight in a single
    answer. What it costs is the one thing a single answer had for free — a
    model that has already written the key points knows not to write the
    same thing again under decisions — and the merge pass buys that back by
    checking the four drafts against each other in one more request. Skipped
    when there is at most one draft, where a section could only be checked
    against itself."""
    drafts = {}
    for field in prompting.SECTION_FIELDS:
        prompt = prompt_for(field)
        raw = ask(pipeline, system, prompt, chosen.map_answer_tokens, chosen,
                 echo_prompt=prompt)
        content = prompting.parse_section(field, raw, language, prompt)
        if content:
            drafts[field] = content

    if len(drafts) > 1:
        merge = prompting.merge_prompt(drafts, language)
        answer = ask(pipeline, system, merge, chosen.reduce_answer_tokens, chosen)
        # Trusted no further than :func:`~prompting.has_written_headings`: a
        # merge answer that fell back to plain text is exactly the failure
        # this split, unlike the combined path, cannot afford to keep — it
        # would throw away drafts that were each individually fine.
        if prompting.has_written_headings(answer, language):
            merged = prompting.parse(answer, language, merge)
            if (merged.abstract or merged.points or merged.decisions
                    or merged.actions):
                return merged, answer

    return prompting.sections_from_drafts(drafts), prompting.draft_text(
        drafts, language)


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


def choose(engine, settings, available, total, skip=()):
    """The plan, or a refusal carrying the two numbers the page will print.

    ``skip`` leaves out models this machine has already proved it cannot use:
    a conversion its runtime refuses is not a reason to give up on summaries,
    it is a reason to take the next one down."""
    chosen = plan.resolve_plan(engine, settings, skip=skip)
    if chosen is None:
        needed = plan.cheapest(engine)
        free = plan.usable_ram_gb(available, total)
        raise NotEnoughMemory(
            t("summary.no_room",
              needed="?" if needed is None else f"{needed:.1f}",
              free="?" if free is None else f"{free:.1f}"),
            needed=needed, free=free)
    warn_if_over_budget(chosen, available, total)
    say_what_more_room_would_buy(engine, chosen, available, total)
    return chosen


def say_what_more_room_would_buy(engine, chosen, available, total):
    """Say which model this machine would use with more of itself free.

    The plan is made from memory that is *available*, not memory that is
    installed, and nothing has ever said so. A laptop with thirty-two
    gigabytes and a browser open summarises with a two-billion-parameter
    model and reports nothing unusual, because nothing unusual happened —
    it is simply a worse summary than the same machine can write, arrived at
    honestly and presented as the only one on offer.

    Said once, before the reading starts, and only when it is actionable: the
    better model has to be one this engine can load and one that would fit in
    the memory the machine actually has. Otherwise it is not advice, it is a
    remark about somebody's hardware."""
    better = plan.better_with_more(engine, available, total, None)
    if better is None:
        return False
    model, needed = better
    if chosen is not None and chosen.model.name == model.name:
        return False
    print(t("summary.more_room_would_buy", model=model.name,
            needed=f"{needed:.0f}", free=f"{(available or 0):.1f}"),
          file=sys.stderr)
    return True


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

    trace = tracing.Trace()
    grouped = None
    shape = str(settings.get("summary_shape") or SECTIONS).strip().lower()
    fingerprint = partials.settings_key(settings, chosen)
    budget = int(settings.get("summary_chunk_tokens") or chosen.chunk_tokens)
    # How much a reading pass may say. It comes from the plan, and it is worth
    # being able to override: the first real diagnosis found every pass
    # stopping on this allowance after the first fifth of its chunk, and
    # whether that is the cause or a symptom is one number away.
    answer_tokens = int(settings.get("summary_map_tokens")
                        or chosen.map_answer_tokens)
    if answer_tokens != chosen.map_answer_tokens:
        chosen = chosen._replace(map_answer_tokens=answer_tokens)
    # What is left for the transcript once the instructions, the worked
    # example and the answer have had their share. Measured, not guessed: the
    # reading prompt grew when it gained an example, and a chunk sized against
    # the old guess overflows the window by the difference — silently, because
    # what falls off the end is the end of the transcript.
    room = (int(chosen.context_tokens) - answer_tokens
            - prompting.map_overhead(language) - CONTEXT_MARGIN)
    if room > 0 and budget > room:
        print(t("summary.no_room_for_answer", chunk=budget, answer=answer_tokens,
                context=chosen.context_tokens, room=room), file=sys.stderr)
        budget = room
    if shape == SECTIONS and not settings.get("summary_chunk_tokens"):
        finer = min(budget, READING_CHUNK_TOKENS)
        if finer < budget:
            # More passes over the same words, and that must not cost words:
            # what a tier limits is how much transcript this machine should
            # read, not how finely it may read it. Reading it in smaller
            # pieces without this would hit the cap and the transcript would
            # be cut to fit - the coverage bought by the smaller chunk, spent
            # again immediately.
            if chosen.max_passes:
                # Rounded up, because the overlap repeats a tenth of every
                # chunk and rounding down would read a little less than the
                # tier already allows - which is the whole thing this is
                # here to prevent, in miniature.
                chosen = chosen._replace(max_passes=max(
                    1, math.ceil(chosen.max_passes * budget / finer)))
            budget = finer
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

    style = str(settings.get("summary_style") or DEFAULT_STYLE).strip().lower()

    report(4, "stage.loading_model")
    pipeline = open_pipeline()
    try:
        system = prompting.prompts_for(language)["system"]
        if shape == SECTIONS:
            low, high = READING_BAND
            seam = int(low + (high - low) * FOLDING_FROM)
            _map(pipeline, system, parts, language, chosen, report,
                 (low, seam), settings.get("cache_dir"), fingerprint, trace)
            sections, grouped = _write_sections(
                trace.notes, pipeline, system, language, chosen, settings,
                material, report, (seam, high))
            answer = sections.abstract
        elif len(parts) == 1:
            report(READING_BAND[0], STAGE_READING)
            if style == "split":
                sections, answer = _write_split(
                    pipeline, system, language, chosen,
                    lambda field: prompting.section_prompt(field, parts[0], language))
            else:
                # No echo check against this prompt: it carries the headings
                # the answer is supposed to come back under, so measured
                # against it a well-shaped answer looks copied. What a
                # one-pass answer can wrongly reproduce is the transcript,
                # and the fence catches that.
                prompt = prompting.single_prompt(parts[0], language)
                sections, answer = _write_combined(pipeline, system, language,
                                                   prompt, chosen)
        else:
            low, high = READING_BAND
            seam = int(low + (high - low) * FOLDING_FROM)
            answers = _map(pipeline, system, parts, language, chosen, report,
                           (low, seam), settings.get("cache_dir"),
                           fingerprint, trace)
            texts, evidence = _fold_to_root(pipeline, system, answers, language,
                                            chosen, report, (seam, high), trace)
            if style == "split":
                sections, answer = _write_split(
                    pipeline, system, language, chosen,
                    lambda field: prompting.section_reduce_prompt(
                        field, texts, language, evidence))
            else:
                prompt = prompting.reduce_prompt(texts, language, evidence)
                sections, answer = _write_combined(pipeline, system, language,
                                                   prompt, chosen)
    finally:
        close = getattr(pipeline, "close", None)
        if close:
            close()

    if not (sections.abstract or sections.points or sections.decisions
            or sections.actions or getattr(sections, "sections", ())):
        raise SummaryError(t("summary.model_said_nothing",
                             model=model_name or chosen.model.name,
                             detail=why_nothing(answer)))
    report_trace(trace, sections, material, settings, grouped)
    return sections, note


def _write_sections(found, pipeline, system, language, chosen, settings,
                    material, report, band):
    """Group the notes, then write one section at a time.

    Every question here is about one section's notes. Nothing sees the whole
    recording, which is the difference between this and the fold it replaces:
    a model answering a small question badly costs a section, where a model
    answering an enormous one badly cost two thirds of a meeting and said
    nothing about it."""
    low, high = band
    kept = grouping.dedupe(grouping.enrich(list(found), language), language)
    body, tail = grouping.assign(
        kept, settings.get("summary_sections_mode") or grouping.HYBRID,
        language)
    body = grouping.split_oversize(body, writing.NOTES_PER_SECTION, language)

    def ask_for(budget):
        return lambda prompt: ask(pipeline, system, prompt, budget, chosen)

    def advance(done, total):
        report(low + (high - low) * done // max(1, total), STAGE_WRITING)

    written = writing.write(
        body, tail, ask_for(chosen.map_answer_tokens), material, language,
        advance, label_tokens=LABEL_TOKENS,
        abstract_ask=ask_for(chosen.reduce_answer_tokens))
    return written, (body, tail)


def _section_shape(found, language, settings, grouped=None):
    """What the notes would be grouped into, as numbers and as words.

    Split in two on purpose: how many sections and how big they are is a
    measurement, and what each one is about is meeting content. They are
    written to different files."""
    empty = {"numbers": {"sections": 0, "sections_kept": 0}, "sections": []}
    if not found:
        return empty
    try:
        if grouped is not None:
            body, tail = grouped
            kept = [note for section in body for note in section.notes]
        else:
            kept = grouping.dedupe(grouping.enrich(list(found), language),
                                   language)
            body, tail = grouping.assign(
                kept, settings.get("summary_sections_mode") or grouping.HYBRID,
                language)
    except Exception:                   # noqa: BLE001 - a measurement, not the work
        return empty
    return {
        "numbers": {
            "sections": len(body),
            "sections_kept": len(kept),
            "notes_deduped": len(found) - len(kept),
            "section_sizes": [len(section.notes) for section in body],
            "tail_sizes": [len(section.notes) for section in tail],
            "orphans": sum(len(section.notes) for section in body
                           if section.kind == "other"),
        },
        "sections": [{"kind": section.kind, "origin": section.origin,
                      "ts_min": section.ts_min, "notes": len(section.notes),
                      "about": section.keywords} for section in body + tail],
    }


def report_trace(trace, sections, material, settings=None, grouped=None):
    """Say what the passes did, and how much of the recording came through.

    Coverage and copy_rate are not here: they are computed from the finished
    page, for every engine, in :func:`summary.report_metrics`. What belongs
    here is what only the passes know — which of them produced nothing, and
    what the folds threw away."""
    settings = settings or {}
    points = points_of(sections)
    counts = trace.counts()
    reading_share = trace.reading_coverage(material.duration)
    # Grouped here and not used for anything yet: the page is still written
    # the old way. What it is for now is the measurement — whether the notes
    # of a real recording fall into themes a reader would recognise — and it
    # costs one matrix multiplication to find out on every run rather than
    # only when somebody remembers to look.
    shape = _section_shape(trace.notes, language_of(material.language),
                           settings, grouped)

    if settings.get("summary_debug"):
        for line in trace.lines():
            print(line, file=sys.stderr)
    for record in trace.failures():
        print(record.line(), file=sys.stderr)
    if counts["partials_lost"]:
        print(t("summary.partials_lost", lost=counts["partials_lost"],
                folds=counts["folds_collapsed"]), file=sys.stderr)
    if counts["echoed_chunks"]:
        print(t("summary.echoed_chunks", chunks=counts["echoed_chunks"]),
              file=sys.stderr)
    page_share = tracing.coverage([point.start for point in points],
                                  material.duration)
    if (reading_share is not None and page_share is not None
            and reading_share - page_share > tracing.LOST_ON_THE_WAY):
        # Read and then lost. The passes covered the recording; the page does
        # not. Everything between them is the fold.
        print(t("summary.lost_on_the_way",
                read=int(round(reading_share * 100)),
                written=int(round(page_share * 100))), file=sys.stderr)

    where = settings.get("summary_dump_notes")
    if where:
        extra = {"metrics": dict(counts, reading_coverage=reading_share,
                                 **shape["numbers"]),
                 "sections": shape["sections"],
                 "answers": list(trace.answers),
                 "points": [{"start": point.start, "speaker": point.speaker,
                             "text": point.text} for point in points]}
        try:
            with open(where, "w", encoding="utf-8") as handle:
                handle.write(trace.as_document(extra))
        except OSError as failure:
            print(t("summary.dump_failed", path=where, error=failure),
                  file=sys.stderr)
    return counts


def why_nothing(answer):
    """Why what came back is not a summary, in one clause.

    "Returned nothing usable" is true of three different failures, and they
    are not fixed the same way: an empty answer is a model that produced
    nothing at all, an answer that is all narration is a thinking model cut
    off before it began, and anything else is a model repeating its
    instructions. What it actually said is worth a line of it."""
    text = str(answer or "").strip()
    if not text:
        return t("summary.nothing_at_all")
    if not prompting.without_thinking(text):
        return t("summary.all_thinking", chars=len(text))
    first = " ".join(prompting.without_thinking(text).split())[:120]
    return t("summary.unusable_answer", chars=len(text), first=first)
