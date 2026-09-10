"""What a model engine needs that is not the model: prompts in, sections out.

Every engine that actually writes prose faces the same three problems, and
none of them are about the runtime it uses:

* an hour of speech may not fit in one pass, so it is cut into chunks on
  sentence boundaries and summarised in two stages — each chunk on its own
  (*map*), then the chunk summaries together (*reduce*);
* the model has to be told what a summary of a meeting is, in the language
  that was spoken, and given the transcript with its minutes attached so it
  can cite them;
* whatever comes back is markdown written by a language model, which means it
  is *nearly* the shape that was asked for, and has to be read back into the
  same :class:`~audio_transcriber.summary.Sections` the extractive engine
  produces so both end up on the same page.

Keeping all three here rather than in an engine is what makes the next engine
cheap: a different runtime is a different way to turn a string into a string,
and nothing above.

Nothing in this module imports a model, a runtime or a network client, so the
whole of it is covered by the test suite on a machine that has none.
"""
import re

from ..formatting import format_clock
from ..summary import (
    HEADINGS,
    Point,
    Sections,
    estimate_tokens,
    language_of,
    reduce as reduce_sentences,
)

#: Tokens of transcript handed to the model in one pass. Deliberately well
#: under the context of any model worth using for this: the prompt, the
#: instructions and the answer all have to fit alongside it, and a model given
#: exactly its context window spends the last of it forgetting the beginning.
CHUNK_TOKENS = 6000

#: How many partial summaries one reduce pass may fold together. Above this,
#: the partials are reduced in groups and the groups reduced again: a star
#: reduce grows its prompt with the length of the recording, which is the one
#: thing a small model cannot absorb.
REDUCE_FANIN = 6

#: The deepest the whole tree may go, counting the map pass as the first
#: level: three means map, then two reduce passes at most. Beyond that the
#: fan-in is widened instead, because a meeting does not deserve four levels
#: of summary and every level loses information.
MAX_REDUCE_DEPTH = 3

#: Tokens a map answer may spend. A chunk summary is a bulleted list, not a
#: document, and every token here is a token the reduce prompt has to carry.
#: Intermediate reduce passes answer under the same ceiling, for the same
#: reason; only the root writes at length.
MAP_ANSWER_TOKENS = 500

#: Tokens the final answer may spend.
REDUCE_ANSWER_TOKENS = 1400

#: Tokens of original transcript handed to a reduce pass alongside the
#: partials. Merging summaries recursively amplifies whatever the model
#: invented at the level below, because from the second level on it is
#: reading its own writing with no way back to the source; a small extract of
#: what was actually said is the cheapest thing that gives it one.
EVIDENCE_TOKENS = 400

#: Bumped whenever a prompt here changes. It is part of the cache key of a
#: partial answer, and a cache that survives a prompt change is a bug that
#: accumulates rather than a saving.
PROMPT_VERSION = 1

#: What the transcript is wrapped in inside a prompt. The same two markers in
#: every language, because they are delimiters rather than prose and because
#: :func:`parse` has to be able to recognise them: a model that echoes its
#: input instead of answering — small ones do — hands back a "summary" that is
#: the transcript again, and the marker is how that is caught before it
#: reaches the page.
FENCE_START = "-----BEGIN TRANSCRIPT-----"
FENCE_END = "-----END TRANSCRIPT-----"

#: Below this many characters, what survived an echo is not a summary.
MIN_ANSWER = 40

#: Reasoning models narrate before answering. The narration is not the
#: summary, and it must not reach the page.
_THINK = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)

#: A markdown heading, at any level.
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*(.+?)\s*#*\s*$")

#: A bullet: a dash, a star, or a number.
_BULLET = re.compile(r"^\s*(?:[-*•]|\d{1,2}[.)])\s+(.*)$")

#: The clock the transcript was handed over with, coming back in an answer —
#: with or without the backticks the page puts around it.
_CLOCK = re.compile(r"^`?\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?`?[\s:—-]*")

#: A speaker in bold, as the page writes them.
_SPEAKER = re.compile(r"^\*\*(.+?)\*\*[\s:—-]*")

#: What the model is asked to write, per language. These are prompts, not
#: messages to the user, so they live here rather than in the catalogue — and
#: they are in the language that was *spoken*, which is the language the
#: summary has to come out in.
PROMPTS = {
    "it": {
        "system":
            "Sei un assistente che riassume trascrizioni di riunioni e "
            "registrazioni parlate. Rispondi sempre in italiano.\n"
            "Regole non negoziabili:\n"
            "- usa solo quello che c'e' nella trascrizione; non aggiungere "
            "niente che non sia stato detto;\n"
            "- se una sezione non ha contenuto, lasciala vuota invece di "
            "inventarla;\n"
            "- cita il minuto fra parentesi quadre, come [12:34], copiandolo "
            "dalla trascrizione;\n"
            "- niente preamboli e niente commenti: solo il documento chiesto.",
        "map":
            "Questa e' la parte {part} di {total} di una trascrizione.\n"
            "Elenca, in italiano, solo quello che compare in QUESTA parte: i "
            "punti trattati, le decisioni prese e le cose che qualcuno si e' "
            "impegnato a fare. Un elenco puntato, ogni riga con il minuto.\n\n"
            "{fence_start}\n{transcript}\n{fence_end}",
        "evidence":
            "Questi sono passaggi della trascrizione originale, per "
            "controllo.\n\n{fence_start}\n{evidence}\n{fence_end}\n\n"
            "Verifica i riassunti qui sopra contro questi passaggi: togli "
            "quello che non ci trovi, e copia i minuti come sono scritti "
            "qui.\n\n",
        "reduce_partial":
            "Questi sono riassunti parziali consecutivi della stessa "
            "registrazione, in ordine.\n\n{partials}\n\n{evidence}"
            "Fondili in un solo elenco puntato in italiano, in ordine di "
            "tempo: togli le ripetizioni, tieni ogni riga con il suo minuto, "
            "e non scrivere ancora il documento finale con le intestazioni.",
        "reduce":
            "Questi sono i riassunti parziali di una registrazione, in "
            "ordine.\n\n{partials}\n\n{evidence}"
            "Scrivi ora il riassunto finale in italiano, con esattamente "
            "queste intestazioni e in quest'ordine, saltando quelle che non "
            "hanno contenuto:\n\n"
            "## {abstract}\nUn paragrafo di tre o quattro righe.\n\n"
            "## {points}\nUn elenco puntato, ogni riga con il minuto.\n\n"
            "## {decisions}\nSolo le decisioni effettivamente prese.\n\n"
            "## {actions}\nChi si e' impegnato a fare cosa, ed entro quando "
            "se e' stato detto.",
        "single":
            "Questa e' la trascrizione di una registrazione.\n\n"
            "{fence_start}\n{transcript}\n{fence_end}\n\n"
            "Scrivi il riassunto in italiano, con esattamente queste "
            "intestazioni e in quest'ordine, saltando quelle che non hanno "
            "contenuto:\n\n"
            "## {abstract}\nUn paragrafo di tre o quattro righe.\n\n"
            "## {points}\nUn elenco puntato, ogni riga con il minuto.\n\n"
            "## {decisions}\nSolo le decisioni effettivamente prese.\n\n"
            "## {actions}\nChi si e' impegnato a fare cosa, ed entro quando "
            "se e' stato detto.",
    },
    "en": {
        "system":
            "You summarise transcripts of meetings and recorded speech. "
            "Always answer in English.\n"
            "Rules you must not break:\n"
            "- use only what is in the transcript; add nothing that was not "
            "said;\n"
            "- leave a section out rather than inventing content for it;\n"
            "- cite the minute in square brackets, like [12:34], copied from "
            "the transcript;\n"
            "- no preamble and no commentary: only the document asked for.",
        "map":
            "This is part {part} of {total} of a transcript.\n"
            "List, in English, only what appears in THIS part: the points "
            "discussed, the decisions taken, and what somebody committed to "
            "doing. A bulleted list, every line carrying its minute.\n\n"
            "{fence_start}\n{transcript}\n{fence_end}",
        "evidence":
            "These are passages of the original transcript, to check "
            "against.\n\n{fence_start}\n{evidence}\n{fence_end}\n\n"
            "Check the summaries above against these passages: drop whatever "
            "you cannot find in them, and copy the minutes as written "
            "here.\n\n",
        "reduce_partial":
            "These are consecutive partial summaries of one recording, in "
            "order.\n\n{partials}\n\n{evidence}"
            "Merge them into a single bulleted list in English, in time "
            "order: drop the repetitions, keep every line's minute, and do "
            "not write the final document with its headings yet.",
        "reduce":
            "These are the partial summaries of one recording, in order.\n\n"
            "{partials}\n\n{evidence}"
            "Now write the final summary in English, under exactly these "
            "headings and in this order, leaving out any that would be "
            "empty:\n\n"
            "## {abstract}\nOne paragraph of three or four lines.\n\n"
            "## {points}\nA bulleted list, every line carrying its minute.\n\n"
            "## {decisions}\nOnly decisions actually taken.\n\n"
            "## {actions}\nWho committed to what, and by when if it was "
            "said.",
        "single":
            "This is the transcript of a recording.\n\n"
            "{fence_start}\n{transcript}\n{fence_end}\n\n"
            "Write the summary in English, under exactly these headings and "
            "in this order, leaving out any that would be empty:\n\n"
            "## {abstract}\nOne paragraph of three or four lines.\n\n"
            "## {points}\nA bulleted list, every line carrying its minute.\n\n"
            "## {decisions}\nOnly decisions actually taken.\n\n"
            "## {actions}\nWho committed to what, and by when if it was "
            "said.",
    },
}


def prompts_for(language):
    """The prompt set for a spoken language, falling back to English."""
    return PROMPTS.get(language_of(language), PROMPTS["en"])


def transcript_for(sentences):
    """The transcript as the model reads it: a minute, a speaker, a sentence.

    The speaker is repeated only when it changes — in a two-person meeting
    that is half the labels gone, and those tokens are better spent on the
    words themselves."""
    lines, last_speaker = [], None
    for sentence in sentences:
        prefix = ""
        if sentence.start is not None:
            prefix = f"[{format_clock(sentence.start)}] "
        if sentence.speaker and sentence.speaker != last_speaker:
            prefix += f"{sentence.speaker}: "
        last_speaker = sentence.speaker or last_speaker
        lines.append(prefix + sentence.text)
    return "\n".join(lines)


def _cost(sentence):
    """What one sentence costs in a prompt: its words, its minute, its name."""
    return estimate_tokens(sentence.text) + 8


def _carried(chunk, tokens):
    """The tail of a chunk to repeat at the head of the next one.

    Never the whole chunk, however small the budget: a chunk made only of
    repeated sentences would make no progress through the transcript."""
    if tokens <= 0 or len(chunk) < 2:
        return []
    kept, size = [], 0
    for sentence in reversed(chunk[1:]):
        cost = _cost(sentence)
        if size + cost > tokens:
            break
        kept.append(sentence)
        size += cost
    kept.reverse()
    return kept


def chunks(sentences, budget=CHUNK_TOKENS, overlap=0.0):
    """Cut the transcript into passes that each fit, on sentence boundaries.

    A sentence longer than the whole budget still gets its own chunk: cutting
    it would produce two halves of a thought, and a model handed a truncated
    sentence summarises the truncation.

    ``overlap`` repeats a share of each chunk at the head of the next one.
    What it buys is the seam: a decision taken across a chunk boundary is
    otherwise half in one pass and half in another, and neither pass sees it
    whole. It costs that share of the reading again, so it stays off unless a
    caller asks — the plan does."""
    if not sentences:
        return []
    carry = max(0.0, min(0.5, float(overlap or 0.0))) * budget
    made, current, size = [], [], 0
    for sentence in sentences:
        cost = _cost(sentence)
        if current and size + cost > budget:
            made.append(current)
            current = _carried(current, carry)
            size = sum(_cost(item) for item in current)
        current.append(sentence)
        size += cost
    if current:
        made.append(current)
    return made


def budget_for(context_tokens, answer_tokens=REDUCE_ANSWER_TOKENS, overhead=400):
    """How much transcript fits in one pass, given the model's context.

    The default :data:`CHUNK_TOKENS` is a guess made without knowing which
    model would run; this is the same question answered by arithmetic once the
    plan has chosen one. ``overhead`` is the instructions around the material —
    measured generously, because the failure it prevents is an overflow."""
    return max(0, int(context_tokens) - int(answer_tokens) - int(overhead))


def fanin_for(count, context_tokens, partial_tokens,
              answer_tokens=REDUCE_ANSWER_TOKENS,
              evidence_tokens=EVIDENCE_TOKENS, overhead=400):
    """The widest fan-in whose reduce prompt still fits this model's context.

    Two below it and the tree is a chain; :data:`REDUCE_FANIN` above it and a
    single prompt carries more of the recording than any model chosen for a
    small machine can hold."""
    room = (budget_for(context_tokens, answer_tokens, overhead)
            - max(0, int(evidence_tokens)))
    fits = room // max(1, int(partial_tokens))
    widest = min(REDUCE_FANIN, max(2, int(count)))
    return max(2, min(widest, int(fits)))


def _depth(count, fanin):
    """How many reduce passes folding ``count`` partials this fan-in needs."""
    levels = 0
    while count > 1:
        count = -(-count // fanin)
        levels += 1
    return max(1, levels)


def reduce_tree(partials, fanin=REDUCE_FANIN, max_depth=MAX_REDUCE_DEPTH,
                max_fanin=None):
    """Group the partials into the reduce passes to run, level by level.

    Returns one list per level, each a list of groups, each group the indices
    a single prompt folds together — indices into the partials at the first
    level, and into the previous level's results after that. Indices rather
    than texts because the levels above the first fold answers that do not
    exist yet when the shape is decided.

    Pure: no model and no I/O, so the shape of the tree is testable without
    one, which is the whole reason it lives here.

    Depth counts the map pass as the first level, so the default allows two
    reduce passes. When more would be needed the fan-in is widened instead —
    a meeting does not deserve four levels of summary, and every level loses
    information. ``max_fanin`` stops that widening: on a model whose context
    cannot hold a wider prompt, an extra level is the lesser harm, and that is
    a judgement only the caller with the plan in hand can make."""
    items = list(partials)
    if not items:
        return []

    width = max(2, int(fanin))
    ceiling = max(width, int(max_fanin)) if max_fanin else None
    while _depth(len(items), width) > max(1, int(max_depth) - 1):
        if ceiling is not None and width >= ceiling:
            break
        width += 1

    levels, indices = [], list(range(len(items)))
    while True:
        if len(indices) <= width:
            levels.append([list(indices)])
            break
        levels.append([indices[at:at + width]
                       for at in range(0, len(indices), width)])
        indices = list(range(len(levels[-1])))
    return levels


def evidence_for(sentences, budget=EVIDENCE_TOKENS, language="it"):
    """A small extract of what was actually said, for a reduce pass to read.

    From the second level of the tree on, the model is summarising its own
    writing and has no way back to the recording; handing it the highest-
    weighted sentences of the material underneath that group is the cheapest
    way to give it one. It is the same selection the extractive engine makes,
    at a much smaller budget."""
    if not sentences or budget <= 0:
        return ""
    return transcript_for(reduce_sentences(list(sentences), int(budget),
                                           language_of(language)))


def _clock_seconds(text):
    """``1:15`` or ``1:02:03`` as seconds, or None."""
    parts = text.split(":")
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return None
    if len(numbers) == 2:
        return numbers[0] * 60 + numbers[1]
    if len(numbers) == 3:
        return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]
    return None


def _point(line):
    """One bullet from the model, back into a :class:`Point`."""
    start, speaker = None, None
    clock = _CLOCK.match(line)
    if clock:
        start = _clock_seconds(clock.group(1))
        line = line[clock.end():]
    named = _SPEAKER.match(line)
    if named:
        speaker = named.group(1).strip()
        line = line[named.end():]
    return Point(start, speaker, line.strip())


def _field_of(heading, language):
    """Which section a heading the model wrote belongs to, if any.

    Both the language that was asked for and English are accepted: a model
    told to write "## Decisioni" quite often writes "## Decisions" anyway, and
    losing a whole section to that would be a poor trade for strictness."""
    wanted = re.sub(r"[^\w\s]", "", heading).strip().lower()
    for words in (HEADINGS.get(language, HEADINGS["en"]), HEADINGS["en"]):
        for field in ("abstract", "points", "decisions", "actions", "keywords"):
            if wanted == re.sub(r"[^\w\s]", "", words[field]).strip().lower():
                return field
    return None


def parse(answer, language="it", prompt=None):
    """Read the model's markdown back into sections.

    The headings were asked for exactly, so most of the time this is a
    formality. When it is not — no heading the model wrote is one of ours —
    the whole answer becomes the abstract rather than being thrown away: a
    summary in the wrong shape is worth more than no summary, and the page it
    lands on is markdown either way.

    ``prompt`` is what was sent, and it is worth passing: it is the only way
    to tell an oddly-shaped summary from a model that simply repeated the
    question."""
    language = language_of(language)
    text = _THINK.sub("", str(answer or "")).strip()
    if not text:
        return Sections()

    collected = {"abstract": [], "points": [], "decisions": [], "actions": [],
                 "keywords": []}
    field, matched = None, False
    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading:
            found = _field_of(heading.group(1), language)
            field = found
            matched = matched or found is not None
            continue
        if field is None or not line.strip():
            continue
        bullet = _BULLET.match(line)
        if field == "abstract":
            collected["abstract"].append(bullet.group(1) if bullet else line.strip())
        elif bullet:
            collected[field].append(bullet.group(1))

    if not matched:
        return Sections(abstract=_not_an_echo(text, prompt))

    return Sections(
        abstract=" ".join(collected["abstract"]).strip(),
        points=[_point(line) for line in collected["points"]],
        decisions=[_point(line) for line in collected["decisions"]],
        actions=[_point(line) for line in collected["actions"]],
        keywords=[word.strip() for line in collected["keywords"]
                  for word in line.split(",") if word.strip()],
    )


def _not_an_echo(text, prompt=None):
    """What is left of an answer once the model's echo of the prompt is gone.

    A model too small for the job repeats its input instead of answering it.
    That is not a summary in an unexpected shape — the fallback this backs
    onto — it is the prompt again, and putting it on a page labelled "summary"
    would be the worst outcome available: it looks like it worked.

    Recognising it needs the prompt, because the echo is made of perfectly
    reasonable sentences — they are simply the ones that were sent. Leading
    lines that appear verbatim in what was asked are dropped, the transcript
    fence ends the answer wherever it appears, and if what survives is too
    short to be a summary there is no summary."""
    echoed = FENCE_START in text
    if echoed:
        text = text.split(FENCE_START, 1)[0].strip()
    if prompt:
        kept, dropping = [], True
        for line in text.splitlines():
            if dropping and (not line.strip() or line.strip() in prompt):
                echoed = echoed or bool(line.strip())
                continue
            dropping = False
            kept.append(line)
        text = "\n".join(kept).strip()
    return "" if echoed and len(text) < MIN_ANSWER else text


def plan(sentences, budget=CHUNK_TOKENS):
    """The passes to run: one prompt when it all fits, map/reduce when not."""
    parts = chunks(sentences, budget)
    return parts if len(parts) > 1 else [sentences] if sentences else []


def single_prompt(sentences, language):
    """The one-pass prompt: the whole transcript, and what to write about it."""
    words = HEADINGS.get(language_of(language), HEADINGS["en"])
    return prompts_for(language)["single"].format(
        transcript=transcript_for(sentences),
        fence_start=FENCE_START, fence_end=FENCE_END,
        abstract=words["abstract"], points=words["points"],
        decisions=words["decisions"], actions=words["actions"])


def map_prompt(sentences, language, part, total):
    """The prompt for one chunk of a transcript too long to read at once."""
    return prompts_for(language)["map"].format(
        part=part, total=total, transcript=transcript_for(sentences),
        fence_start=FENCE_START, fence_end=FENCE_END)


def _numbered(partials):
    """The partial summaries as one block, each under its own marker."""
    return "\n\n".join(f"--- {index} ---\n{part.strip()}"
                       for index, part in enumerate(partials, start=1))


def _evidence_block(evidence, language):
    """The extract of the transcript a reduce pass checks itself against."""
    if not evidence:
        return ""
    return prompts_for(language)["evidence"].format(
        evidence=evidence, fence_start=FENCE_START, fence_end=FENCE_END)


def reduce_partial_prompt(partials, language, evidence=None):
    """The prompt for a reduce pass that is not the last one.

    An intermediate level merges and deduplicates; it must not write the
    finished document, because a level above it still has to fold what comes
    out with the answers of its siblings, and headings would arrive there as
    material to summarise rather than as an answer."""
    return prompts_for(language)["reduce_partial"].format(
        partials=_numbered(partials),
        evidence=_evidence_block(evidence, language))


def reduce_prompt(partials, language, evidence=None):
    """The prompt that turns the chunk summaries into one summary.

    The root of the tree, and the only level that writes the page."""
    words = HEADINGS.get(language_of(language), HEADINGS["en"])
    return prompts_for(language)["reduce"].format(
        partials=_numbered(partials),
        evidence=_evidence_block(evidence, language),
        abstract=words["abstract"], points=words["points"],
        decisions=words["decisions"], actions=words["actions"])
