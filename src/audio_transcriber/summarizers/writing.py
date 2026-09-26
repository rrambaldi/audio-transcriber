"""Writing the document: one question per section, and nothing that sees it all.

This is where the failure that started all of it goes away, and it goes away
by subtraction. The old shape asked a model for a page, then to merge pages,
then to merge the merges — and every one of those steps had to hold the whole
recording in one window. Measured on a twenty-two minute meeting: the reading
covered 41% of it and the page carried 14%, and turning the reading up only
moved the loss further along.

Here nothing ever sees the whole recording. A section is written from its own
notes and no others, so the question is small however long the meeting was; a
title is written from the same handful; and the opening paragraph is written
from the section titles alone, which is also what stops it repeating the
bullets underneath it — it has never seen them.

The number of questions grows with the number of sections instead of the
length of the recording, and each one is short. That is the trade, and it is
the right way round: a model answering a small question badly costs one
section, where a model answering an enormous one badly cost two thirds of a
meeting and said nothing about it.
"""
import difflib
import re
import time
from collections import namedtuple

from ..formatting import format_clock
from ..summary import DEFAULT_LENGTH, Document, Point, language_of
from . import grouping, prompting
from . import notes as note_kinds

#: How many notes a section may be written from in one go. Past it the section
#: is split — see grouping.split_oversize — rather than the notes thinned: a
#: document with one section more is a correct document, and a section that
#: quietly lost a third of its notes is the failure this package exists for.
NOTES_PER_SECTION = 24

#: What a title may run to before it is not a title.
TITLE_WORDS = 12

#: The numbers the asked length moves, beside the wording in
#: :data:`~audio_transcriber.summarizers.prompting.PAGE_DETAIL`.
#:
#: ``sections`` is the cap the grouping searches against — ``None`` meaning
#: whatever the grouping's own default is, so that "medium" is exactly the
#: page that was measured. Fewer sections is not fewer notes: the same notes
#: are grouped more coarsely, and a section that ends up too big for one
#: question is still split by :func:`grouping.split_oversize`.
#:
#: ``answer`` scales what one section may say. It has to move with the
#: wording and not instead of it: asking for a bullet per note and then
#: stopping the model at the allowance it had for a paragraph is how a page
#: ends mid-sentence.
Page = namedtuple("Page", "sections answer")

PAGES = {
    "short":  Page(sections=5, answer=0.45),
    "medium": Page(sections=None, answer=1.0),
    "long":   Page(sections=18, answer=1.6),
}


def page_for(length=None):
    """The numbers one length asks for."""
    return PAGES.get(str(length or DEFAULT_LENGTH).strip().lower(),
                     PAGES[DEFAULT_LENGTH])

#: What a title is made of when the sections have none: the date and the
#: length, which are true of every recording and invent nothing.
UNTITLED = {"it": "Riassunto della registrazione",
            "en": "Summary of the recording"}

#: Said of the leftovers, which belong to no section.
OTHER = {"it": "Altri punti", "en": "Other points"}

_QUOTED = re.compile(r"^[\"'«»“”\s*#]+|[\"'«»“”\s*#]+$")
_NUMBERED = re.compile(r"^\s*\d{1,2}[.)]\s*")

#: A minute in square brackets. The notes a section is written from carry no
#: minutes, so a minute in the answer was copied from nowhere in the
#: recording: it is the example in the system prompt, "[12:34]", written down
#: by a model told to cite the minute and given none to cite.
_CITED = re.compile(r"[ \t]*\[\d{1,3}:\d{2}(?::\d{2})?\]")

#: A title written as an identifier, "MonitoraggioUtentiCampagna": words run
#: together, each after the first starting with a capital. Three lower-case
#: letters before the capital, so "GitHub" is left as it is.
_RUN_TOGETHER = re.compile(r"(?<=[a-zà-ù]{3})(?=[A-Z][a-zà-ù]{2})")

#: A bullet on the page, and the marker in front of it.
_BULLET = re.compile(r"^\s*(?:[-*\u2022]|\d{1,2}[.)])\s+")

#: What a reviewer answers, one finding a line: the kind, then the line of the
#: page it is about, copied. Both languages' words, whichever was asked.
_FINDING = re.compile(
    r"^\s*(?:(?:[-*\u2022]|\d{1,2}[.)])\s*)?\**\s*(INVENTATA|DOPPIA|SCORRETTA|INVENTED|REPEATED"
    r"|GARBLED)\s*\**\s*[:\-\u2013\u2014]\s*(.+?)\s*$", re.IGNORECASE)
KINDS = {"inventata": "unsupported", "invented": "unsupported",
         "doppia": "repeated", "repeated": "repeated",
         "scorretta": "garbled", "garbled": "garbled"}

#: How close a quoted line has to be to one on the page to be about it. A
#: reviewer copies a line with its punctuation changed or its end missing; one
#: it paraphrases is not a quotation, and a finding that quotes nothing on
#: the page is the reviewer's own invention.
QUOTED = 0.85

#: How alike a line has to be to another for "it repeats another line" to be
#: believed. Measured on Spark reading back its own page of gold.srt: seven
#: of the ten lines it called repeats scored 0.18 to 0.35 against every other
#: line of their section - the same opening words, "Necessità di modalità
#: per", and different things after them - and the three it had grounds for
#: scored 0.50 to 0.62. Two alike past SAME_NOTE never reach the reviewer.
ALIKE = 0.5


def _lines(found, language="it", minutes=False):
    """The notes of one section, as the model is given them."""
    written = []
    for note in found:
        clock = ("" if note.ts_start is None or not minutes
                 else f"[{format_clock(note.ts_start)}] ")
        written.append(f"- {clock}{note.text}")
    return "\n".join(written)


def _uncited(written):
    """What a model wrote, less the minutes it could not have copied."""
    kept = []
    for line in written.split("\n"):
        bare = _CITED.sub("", line)
        if bare.strip() or not line.strip():
            kept.append(bare)
    return "\n".join(kept)


def _tidy_title(written, language="it"):
    """A title out of whatever came back, or nothing.

    Models answer a request for a title with a title in quotation marks, a
    title with a full stop, a numbered title, and occasionally a paragraph
    explaining the title. The first three are a title; the last is not."""
    first = str(written or "").strip().splitlines()
    if not first:
        return ""
    line = _NUMBERED.sub("", _QUOTED.sub("", first[0])).strip(" .:;—–-")
    if not line or len(line.split()) > TITLE_WORDS:
        return ""
    if " " not in line and _RUN_TOGETHER.search(line):
        first, *rest = _RUN_TOGETHER.split(line)
        line = " ".join([first] + [word.lower() for word in rest])
    return line


def label(cluster, ask, language="it", catalogue=None):
    """A title for one section, from its own notes and nothing else.

    ``ask(prompt)`` is how a question reaches whichever model is loaded; this
    module does not know or care which. When there is no usable answer the
    section is named from the words its notes have in common, which is what
    the engine with no model does for every section and is better than
    "Section 3"."""
    language = language_of(language)
    if cluster.kind and cluster.kind != "other":
        cluster.named_by = "catalogue"
        return note_kinds.heading_of(cluster.kind, language, catalogue)
    if cluster.kind == "other":
        cluster.named_by = "catalogue"
        return OTHER.get(language, OTHER["en"])
    prompt = prompting.prompts_for(language)["label"].format(
        notes=_lines(cluster.notes, language))
    written = _tidy_title(ask(prompt), language)
    cluster.named_by = "model" if written else "keywords"
    return written or from_keywords(cluster, language)


def from_keywords(cluster, language="it"):
    """A section named without a model, out of the words its notes share."""
    words = [word for word in (cluster.keywords or []) if word]
    if not words:
        return OTHER.get(language_of(language), OTHER["en"])
    return ", ".join(word.capitalize() if at == 0 else word
                     for at, word in enumerate(words[:3]))


def section(cluster, ask, language="it", detail=None):
    """The body of one section: a paragraph and the detail under it.

    The model sees this section's notes and no others, which is the whole
    point: whatever it does with them, it cannot lose a part of the recording
    it was never shown.

    ``detail`` is what the asked length wants of it — a paragraph on its own,
    or a paragraph with a bullet per note. It arrives already chosen, because
    the length is resolved once for the whole page and not once per
    section."""
    language = language_of(language)
    detail = detail or prompting.detail_for(language)
    prompt = prompting.prompts_for(language)["section"].format(
        notes=_lines(cluster.notes, language),
        shape=detail["shape"], rules=detail["rules"])
    written = _uncited(prompting.usable_answer(ask(prompt), prompt))
    return written.strip() or _lines(cluster.notes, language)


def abstract(titles, ask, language="it", detail=None):
    """The opening paragraph, written from the section titles alone.

    It never sees the bullets, and that is not an economy: the page it
    replaces had an opening paragraph identical, word for word, to the list of
    key points beneath it, because the one request that wrote both had both in
    front of it."""
    language = language_of(language)
    named = [title for title in titles if title]
    if not named:
        return ""
    detail = detail or prompting.detail_for(language)
    prompt = prompting.prompts_for(language)["abstract_from"].format(
        titles="\n".join(f"- {title}" for title in named),
        span=detail["span"])
    written = _uncited(prompting.usable_answer(ask(prompt), prompt))
    return " ".join(written.split())


def derive_title(titles, material=None, language="it"):
    """A title for the document, out of the section titles a model wrote.

    Never out of the transcript, and this is the bug it is written against: a
    summary of a meeting came back called "Ne va a Napoli Tutta una cosa",
    which is a fragment of somebody talking. A title made of the subjects is
    either useful or plainly generic, and neither of those is a sentence
    nobody meant to write down.

    Only the sections a model named count. Where there was no model the
    sections are named after the words their notes share, and three filler
    words that happened to repeat make a worse title than the recording's own
    name — which is what it falls back to."""
    language = language_of(language)
    named = [title for title in titles if title
             and title != OTHER.get(language, OTHER["en"])]
    if not named:
        spoken = getattr(material, "title", "") or ""
        return spoken or UNTITLED.get(language, UNTITLED["en"])
    if len(named) == 1:
        return named[0]
    return f"{named[0]}, {named[1].lower()}" + (" e altro" if len(named) > 2
                                                and language == "it" else
                                                " and more" if len(named) > 2
                                                else "")


def without_repeats(written, language="it"):
    """The sections' texts with each bullet said twice kept once.

    The notes lose their repeats before any section is written, and a model
    still puts one line on the page twice: in one section, from two notes
    that said it two ways, or in two sections that each got a telling of it.
    Measured the way the notes are, on the page's own bullets; the first
    stays, since the page is in the order the recording had. The decisions
    and actions at the foot repeat the body on purpose, and are not here."""
    lines = [(at, row, _BULLET.sub("", line))
             for at, (_cluster, _title, text) in enumerate(written)
             for row, line in enumerate(text.split("\n")) if _BULLET.match(line)]
    if len(lines) < 2:
        return list(written), 0
    alike = grouping.similarity([Point(None, None, bare) for *_, bare in lines],
                                language)
    dropped = set()
    for first in range(len(lines)):
        if (lines[first][0], lines[first][1]) in dropped:
            continue
        for second in range(first + 1, len(lines)):
            if alike[first, second] >= grouping.SAME_NOTE:
                dropped.add((lines[second][0], lines[second][1]))
    kept = [(cluster, title, "\n".join(line for row, line in enumerate(text.split("\n"))
                                        if (at, row) not in dropped))
            for at, (cluster, title, text) in enumerate(written)]
    return kept, len(dropped)


def _plain(text):
    """A line as compared: no marker, no quotation marks, one space, lower."""
    text = _BULLET.sub("", str(text or ""))
    return " ".join(text.strip(" \t\"'\u00ab\u00bb\u201c\u201d*.;:").split()).lower()


def _on_the_page(quoted, text):
    """The line of ``text`` a reviewer quoted, as the page has it, or None."""
    wanted = _plain(quoted)
    if len(wanted) < 8:
        return None
    best, score = None, 0.0
    for line in text.split("\n"):
        plain = _plain(line)
        if not plain:
            continue
        if wanted in plain:
            # A sentence out of a paragraph: the sentence is the finding.
            return _BULLET.sub("", quoted).strip(" \t\"'\u00ab\u00bb\u201c\u201d*")
        # The line with the reviewer's reason after it.
        ratio = 1.0 if plain in wanted and len(plain) >= 0.6 * len(wanted) \
            else difflib.SequenceMatcher(None, wanted, plain).ratio()
        if ratio > score:
            best, score = _BULLET.sub("", line).strip(), ratio
    return best if score >= QUOTED else None


def _has_a_twin(line, text, language="it"):
    """Whether another line of ``text`` says much the same as ``line``."""
    others = [_BULLET.sub("", row) for row in text.split("\n")
              if row.strip() and _plain(row) != _plain(line)]
    if not others:
        return False
    alike = grouping.similarity([Point(None, None, row) for row in [line] + others],
                                language)
    return float(alike[0, 1:].max()) >= ALIKE


def _believable(found, text):
    """What is left of one section's findings once the reviewer is doubted.

    Measured, not supposed: on Spark reading back its own page, four sections
    of eleven had more than half their lines flagged - all ten of one, among
    them "Oggi si intende finire tutto il layout della parte ACM." - and a
    line was often flagged for all three reasons at once. A reviewer that
    cannot say which thing is wrong with a line has not found one, and one
    that flags most of a section is reading nothing; of 39 findings those two
    rules left 2, both of them right. One finding is never "most": a section
    of one line may well have one thing wrong with it."""
    kinds = {}
    for _title, line, kind in found:
        kinds.setdefault(line, set()).add(kind)
    kept = [finding for finding in found if len(kinds[finding[1]]) == 1]
    lines = sum(1 for row in text.split("\n") if row.strip())
    flagged = len({line for _t, line, _k in kept})
    return [] if flagged > 1 and flagged * 2 > lines else kept


def review(written, ask, language="it"):
    """What a model reading each section back finds wrong with it.

    Every section is read again beside the notes it was written from, and
    the model is asked for three things only a reader sees: a line the notes
    do not say, a line that repeats another, a line that does not read as a
    sentence. Nothing is changed: the page stays as written and says, at the
    foot, what to check. What the reviewer says is doubted before it is
    printed - a finding has to quote a line that is on the page, a repeat has
    to have a line alike enough to repeat, and see :func:`_believable`.

    ``([(title, line, kind)], [answer per section])``: kind one of
    :data:`KINDS`' values, and the answers as they came back, for whoever
    is measuring the reviewer."""
    language = language_of(language)
    template = prompting.prompts_for(language)["review"]
    found, answers = [], []
    for cluster, title, text in written:
        prompt = template.format(notes=_lines(cluster.notes, language), text=text)
        said = ask(prompt)
        # Kept as it came, not as it is read: "NESSUNO" is in the question,
        # so the echo filter takes it out, and "found nothing" would look
        # like "answered nothing" to whoever is measuring the reviewer.
        answers.append(said)
        answer = prompting.usable_answer(said, prompt)
        mine = []
        for line in answer.split("\n"):
            match = _FINDING.match(line)
            if not match:
                continue
            quoted = _on_the_page(match.group(2), text)
            kind = KINDS[match.group(1).lower()]
            if not quoted or (kind == "repeated"
                              and not _has_a_twin(quoted, text, language)):
                continue
            if (title, quoted, kind) not in mine:
                mine.append((title, quoted, kind))
        found.extend(_believable(mine, text))
    return tuple(found), tuple(answers)


def write(body, tail, ask, material=None, language="it", progress=None,
          label_tokens=None, abstract_ask=None, length=None, catalogue=None,
          review_ask=None):
    """Every question this stage asks, in order, and the document they make.

    ``ask(prompt)`` writes a section; ``abstract_ask`` writes the opening
    paragraph, which wants more room than a section and is asked for less
    often. ``progress(done, total)`` is called as the sections are written,
    because on a small model each one is seconds and there may be a dozen.

    ``length`` is the one thing here a reader chose, and it is resolved once:
    every section of one page is asked for at the same length, and the title
    of a section is a title at every length.

    ``review_ask``, when given, reads every section back once it is written:
    see :func:`review`."""
    language = language_of(language)
    detail = prompting.detail_for(language, length)
    label_ask = ask if label_tokens is None else ask
    total = max(1, len(body) * (3 if review_ask else 2) + 1)
    done = 0
    written = []
    for cluster in body:
        cluster.title = label(cluster, label_ask, language, catalogue)
        done += 1
        if progress:
            progress(done, total)
        written.append((cluster, cluster.title,
                        section(cluster, ask, language, detail)))
        done += 1
        if progress:
            progress(done, total)
    titles = [title for _cluster, title, _body in written]
    # Only what a model named: see derive_title.
    by_model = [title for cluster, title, _body in written
                if cluster.named_by == "model"]
    opening = abstract(titles, abstract_ask or ask, language, detail)
    written, repeats = without_repeats(written, language)
    found, answers, spent = (), (), None
    if review_ask:
        def reviewed(prompt):
            nonlocal done
            answer = review_ask(prompt)
            done += 1
            if progress:
                progress(min(done, total), total)
            return answer
        started = time.monotonic()
        found, answers = review(written, reviewed, language)
        spent = round(time.monotonic() - started, 1)
    if progress:
        progress(total, total)

    lists = {}
    for cluster in tail:
        lists[cluster.kind] = list(cluster.notes)
    return Document(
        title=derive_title(by_model, material, language),
        abstract=opening,
        sections=tuple((title, text) for _cluster, title, text in written),
        decisions=tuple(lists.get("decision") or ()),
        actions=tuple(lists.get("action") or ()),
        notes=tuple(note for cluster in body for note in cluster.notes),
        repeats=repeats,
        review=found,
        review_answers=answers,
        review_s=spent,
    )
