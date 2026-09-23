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
import re
from collections import namedtuple

from ..formatting import format_clock
from ..summary import DEFAULT_LENGTH, Document, language_of
from . import notes as note_kinds
from . import prompting

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
    "short":  Page(sections=6, answer=0.7),
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


def _lines(found, language="it", minutes=False):
    """The notes of one section, as the model is given them."""
    written = []
    for note in found:
        clock = ("" if note.ts_start is None or not minutes
                 else f"[{format_clock(note.ts_start)}] ")
        written.append(f"- {clock}{note.text}")
    return "\n".join(written)


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
    return line


def label(cluster, ask, language="it"):
    """A title for one section, from its own notes and nothing else.

    ``ask(prompt)`` is how a question reaches whichever model is loaded; this
    module does not know or care which. When there is no usable answer the
    section is named from the words its notes have in common, which is what
    the engine with no model does for every section and is better than
    "Section 3"."""
    language = language_of(language)
    if cluster.kind and cluster.kind != "other":
        cluster.named_by = "catalogue"
        return note_kinds.heading_of(cluster.kind, language)
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
    written = prompting.usable_answer(ask(prompt), prompt)
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
    written = prompting.usable_answer(ask(prompt), prompt)
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


def write(body, tail, ask, material=None, language="it", progress=None,
          label_tokens=None, abstract_ask=None, length=None):
    """Every question this stage asks, in order, and the document they make.

    ``ask(prompt)`` writes a section; ``abstract_ask`` writes the opening
    paragraph, which wants more room than a section and is asked for less
    often. ``progress(done, total)`` is called as the sections are written,
    because on a small model each one is seconds and there may be a dozen.

    ``length`` is the one thing here a reader chose, and it is resolved once:
    every section of one page is asked for at the same length, and the title
    of a section is a title at every length."""
    language = language_of(language)
    detail = prompting.detail_for(language, length)
    label_ask = ask if label_tokens is None else ask
    total = max(1, len(body) * 2 + 1)
    done = 0
    written = []
    for cluster in body:
        cluster.title = label(cluster, label_ask, language)
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
    )
