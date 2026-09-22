"""Notes: one fact each, read out of what a pass wrote about one chunk.

A summary of a meeting used to be made by asking a model for a page, then
asking it to merge pages, then asking it to merge the merges. Every one of
those steps has to hold the whole recording in one window, and measuring it
showed what that costs: turn the reading up and the merging starves, leave it
down and the reading does. A note is what replaces the page as the thing
passes produce — small, typed, dated, and countable — so that nothing
downstream ever has to swallow a recording whole.

The catalogue of kinds is the one the earlier design worked out for the page's
sections, kept whole and given a different job. It stops meaning *which
headings do I print* and starts meaning *which atoms do I collect*, which is
the sentence the reading prompt already used. Its names are canonical in
English and rendered in the language being spoken, which is the mechanism that
lets an Italian recording produce an Italian page without the code having an
opinion about Italian.

Three of the old catalogue's entries are not kinds of note and are not here.
``topic`` is a section, and a section is what grouping the notes produces, not
what a model is asked for. ``date`` and ``number`` are attributes of a note,
found in its text by looking, not asked for and not trusted to a model that
would invent them.

The one addition is ``requirement``, which the catalogue lacked and the
recordings this is built for are mostly made of: somebody saying what a thing
must do is neither a decision, nor a proposal, nor a fact.
"""
import hashlib
import re
from dataclasses import dataclass, field

from ..formatting import format_clock
from ..summary import language_of

#: The kinds of note, in the order they are asked for and printed. Canonical
#: names, in English, whatever is being spoken.
TYPES = ("requirement", "fact", "decision", "proposal", "action", "problem",
         "open_question", "opinion")

#: What a pass is asked for when nothing else is said. Everything: the point
#: of a note is that deciding what matters happens later, on the whole
#: recording at once, rather than inside one chunk that cannot see the rest.
DEFAULT_TYPES = TYPES

#: The heading each kind is written under, in the language being spoken. These
#: are words on a page, so they live with the other words on a page; the model
#: is asked for them exactly and :func:`type_of` reads them back.
HEADINGS = {
    "en": {
        "requirement": "Requirements",
        "fact": "Facts",
        "decision": "Decisions",
        "proposal": "Proposals",
        "action": "Actions",
        "problem": "Problems",
        "open_question": "Open questions",
        "opinion": "Opinions",
    },
    "it": {
        "requirement": "Requisiti",
        "fact": "Fatti",
        "decision": "Decisioni",
        "proposal": "Proposte",
        "action": "Azioni",
        "problem": "Problemi",
        "open_question": "Questioni aperte",
        "opinion": "Opinioni",
    },
}

#: The line under each heading that says what belongs there. Prompt text, kept
#: beside the headings it explains rather than in the template, because which
#: of them is asked for changes from run to run.
INSTRUCTIONS = {
    "en": {
        "requirement": "something that has to be built, or work a certain way",
        "fact": "something that is the case, or that was measured or reported",
        "decision": "a choice actually taken, not one being weighed",
        "proposal": "something suggested and not yet decided",
        "action": "something somebody undertook to do",
        "problem": "a difficulty, a risk or an obstacle raised",
        "open_question": "a question left unanswered",
        "opinion": "a judgement somebody expressed as their own",
    },
    "it": {
        "requirement": "qualcosa che va costruito, o che deve funzionare in un certo modo",
        "fact": "qualcosa che e' cosi', o che e' stato misurato o riferito",
        "decision": "una scelta presa davvero, non una che si sta valutando",
        "proposal": "qualcosa di proposto e non ancora deciso",
        "action": "qualcosa che qualcuno si e' impegnato a fare",
        "problem": "una difficolta', un rischio o un ostacolo sollevato",
        "open_question": "una domanda rimasta senza risposta",
        "opinion": "un giudizio che qualcuno ha espresso come suo",
    },
}

#: A heading in the answer: ``## Requisiti``, ``**Requisiti**``, ``Requisiti:``.
_HEADING = re.compile(r"^\s{0,3}(?:#{1,6}\s*(.+?)\s*#*|\*\*(.+?)\*\*|(.+?):)\s*$")

#: A bullet, whatever the model chose to draw it with.
_BULLET = re.compile(r"^\s*(?:[-*•]|\d{1,2}[.)])\s+(.*)$")

#: A minute, anywhere on the line. A model told to put one on every row is not
#: told where, and puts it at the end as often as at the front.
_CLOCK = re.compile(r"`?[\[(]?(\d{1,3}:\d{2}(?::\d{2})?)[\])]?`?")

#: Who said it, when the answer says: ``(SPEAKER_01)`` or ``**Anna**``.
_SPEAKER = re.compile(r"[(\[]\s*(SPEAKER[ _]?\d{1,2}|[A-Z][\w'’-]{1,30})\s*[)\]]|"
                      r"\*\*(.+?)\*\*")


@dataclass
class Note:
    """One thing that was said, rewritten so it stands on its own."""

    id: str
    type: str
    text: str
    ts_start: float | None = None
    ts_end: float | None = None
    speaker: str | None = None
    chunk_idx: int = 0
    #: Where the text came from. ``model`` is a note the model wrote;
    #: anything else is a fallback, and the metrics are counted separately by
    #: origin so that they measure the model and not the fallback.
    origin: str = "model"
    entities: list = field(default_factory=list)
    dates: list = field(default_factory=list)
    numbers: list = field(default_factory=list)


def heading_of(kind, language="it"):
    """The heading a kind is written under, in the language being spoken."""
    words = HEADINGS.get(language_of(language), HEADINGS["en"])
    return words.get(kind) or HEADINGS["en"][kind]


def _plain(text):
    return re.sub(r"[^\w\s]", "", str(text or "")).strip().lower()


def type_of(heading, language="it"):
    """Which kind a heading the model wrote belongs to, if any.

    Both the language asked for and English are accepted: a model told to
    write "## Requisiti" writes "## Requirements" often enough, and losing a
    whole kind to that would be a poor trade for strictness."""
    wanted = _plain(heading)
    if not wanted:
        return None
    language = language_of(language)
    for words in (HEADINGS.get(language, HEADINGS["en"]), HEADINGS["en"]):
        for kind, written in words.items():
            if wanted == _plain(written):
                return kind
    return None


def clock_seconds(stamp):
    """``1:15`` or ``1:02:03`` as seconds, or None."""
    try:
        parts = [int(part) for part in str(stamp).split(":")]
    except ValueError:
        return None
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return None


def note_id(chunk_idx, start, text):
    """A name for a note that survives being written down and read back.

    Stable across runs of the same material, so two reports of the same
    recording can be compared note by note."""
    digest = hashlib.sha256()
    for part in (str(chunk_idx), str(start), str(text)[:40]):
        digest.update(part.encode("utf-8", "replace"))
        digest.update(b"\x00")
    return "n" + digest.hexdigest()[:10]


def read(answer, language="it", chunk_idx=0, span=(None, None), types=None):
    """Read one pass's markdown back into notes.

    The shape asked for is a heading per kind and a bullet per note, which is
    the shape the parser and the echo check in this package were already built
    around. Asking for JSON instead was the first design, and it was dropped:
    it would have needed a repair prompt and a parse-failure path for a
    fragility that markdown with headings does not have on a small model.

    Tolerant in the three ways a small model is untidy. A heading nobody
    recognises does not throw its bullets away — they become facts, which is
    the kind that claims least. A kind that was asked for and never appears is
    not an error, it is a chunk with none of those in it. And a bullet with no
    minute inherits the one above it, or the start of the chunk, because a
    note whose minute is missing is still a note and losing it would be the
    same silence this package spent a week taking out."""
    kinds = tuple(types or DEFAULT_TYPES)
    found, kind, last_start = [], None, None
    unknown_headings = []
    for line in str(answer or "").splitlines():
        heading = _HEADING.match(line)
        if heading and not _BULLET.match(line):
            written = next((group for group in heading.groups()
                            if group is not None), "")
            named = type_of(written, language)
            if named is None and _plain(written):
                unknown_headings.append(written.strip())
            kind = named or ("fact" if _plain(written) else kind)
            continue
        bullet = _BULLET.match(line)
        if not bullet:
            continue
        text = bullet.group(1).strip()
        if not text:
            continue
        clock = _CLOCK.search(text)
        start = clock_seconds(clock.group(1)) if clock else None
        if clock:
            text = (text[:clock.start()] + text[clock.end():]).strip()
        speaker = None
        named = _SPEAKER.search(text)
        if named:
            speaker = (named.group(1) or named.group(2) or "").strip()
            text = (text[:named.start()] + text[named.end():]).strip()
        text = text.strip(" \t-—–:•")
        if not text:
            continue
        if start is None:
            start = last_start if last_start is not None else span[0]
        last_start = start
        found.append(Note(id=note_id(chunk_idx, start, text),
                          type=kind if kind in kinds else "fact",
                          text=text, ts_start=start, ts_end=None,
                          speaker=speaker or None, chunk_idx=chunk_idx))
    return found, unknown_headings


def as_bullets(found, language="it"):
    """The notes as the flat list the rest of the pipeline still expects.

    A bridge, and it is meant to be torn down: once sections are written from
    one cluster at a time there is nothing left that wants every note of a
    chunk in one blob of text. Until then this is what keeps the page being
    written while the notes underneath it are the real product."""
    lines = []
    for note in found:
        clock = ("" if note.ts_start is None
                 else f"`[{format_clock(note.ts_start)}]` ")
        who = f"**{note.speaker}** " if note.speaker else ""
        lines.append(f"- {clock}{who}{note.text}")
    return "\n".join(lines)


def placed(found):
    """How many of these notes say when they happened."""
    return sum(1 for note in found if note.ts_start is not None)
