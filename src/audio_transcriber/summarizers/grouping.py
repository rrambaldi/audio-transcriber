"""Grouping notes into the sections a document is made of, without a model.

Everything here is arithmetic on the words the notes are made of, and that is
the point. A model asked to merge summaries of summaries has to hold the whole
recording in one window at every level, which is what made a summary of a
twenty-two minute meeting come back describing the first seven: turn the
reading up and the merging starves, leave it down and the reading does.
Grouping by distance costs one matrix multiplication and does not care how
long the recording is.

Three ways of deciding what a section is, and they are not three algorithms.
What they share is everything that happens to a note before it is placed —
finding what it is about, pulling the dates and the numbers out of it,
throwing away the one that arrived twice because two chunks overlapped. What
differs is only the placing:

``discover``
    sections come out of the distances between the notes. The recording
    decides how many there are.
``fixed``
    each note goes to the section its own kind names. No distances are
    computed at all: running a decision through a clustering and then mapping
    the cluster back onto a heading called "Decisions" is a lossy way of
    arriving where the note already was.
``hybrid``
    the body is discovered and the tail is routed: decisions and actions are
    collected into lists of their own **and** left in the thematic section
    that holds them. The duplication is deliberate — the section gives the
    context and the list gives the things to do.

The lexical machinery is the extractive summariser's, reused rather than
rewritten: the stopwords, the filler words, and the comparison on the form
without accents, because Whisper writes them and a model rewriting the same
word often does not.
"""
import re
from dataclasses import dataclass, field

import numpy as np

from ..summary import _terms, _vectors, language_of
from . import notes as note_kinds

#: Sections come out of the distances between notes.
DISCOVER = "discover"

#: Sections are the kinds themselves.
FIXED = "fixed"

#: Body discovered, tail routed. The default, and what the measured failure
#: asks for: a reader wants the argument in the order it was had, and the
#: things to do in one place.
HYBRID = "hybrid"

MODES = (DISCOVER, FIXED, HYBRID)

#: The kinds that are collected at the end as well as placed in the body.
TAIL_TYPES = ("decision", "action")

#: Two notes this alike are the same note said twice — which happens on every
#: seam, because chunks overlap on purpose so that nothing falls between them.
#:
#: Measured rather than chosen. On the notes of a real meeting the same thing
#: written twice scores about 0.82, and two notes that are merely about the
#: same subject score about 0.21: the gap is wide enough that anywhere in it
#: would do, and this sits below the first rather than above it because the
#: second telling of a note usually adds a clause, which pulls the pair down.
SAME_NOTE = 0.80

#: The distances a search over :func:`_choose_apart` may settle on, tightest
#: first.
#:
#: There is no one figure, and finding that out is what this range is. How
#: alike two notes look depends on how richly they are written: the notes of a
#: real twenty-two minute meeting average 0.03 apart from each other, and a
#: set of notes written plainly about three subjects averages 0.24. A
#: threshold that gives the first a dozen sections gives the second exactly
#: one, and a threshold that serves the second leaves the first as sixty notes
#: that never met. So the distance is searched for, against what a document
#: has to look like rather than against a number.
APART_RANGE = tuple(round(0.55 + step * 0.02, 2) for step in range(23))

#: What the search is looking for: no more sections than a reader will hold,
#: and not many notes left over. Both have to give at the same time, and when
#: neither can, the loosest distance is taken and the leftovers are named.
STRAY_SHARE = 0.20

#: Beyond this, a note that found no company belongs to no section, and goes
#: at the end under a heading that says as much.
ORPHANED = 0.97

#: A section of one is a bullet with a title over it.
MIN_NOTES = 2

#: More sections than a reader will hold in their head. Past it the distance
#: is tightened and the grouping run again.
MAX_SECTIONS = 12

#: How many of its own words a note is said to be about. They name a section
#: and they go in the written record; they are deliberately *not* used to
#: weight the comparison below, and that is worth a line of its own.
#:
#: The design this came from asked for the comparison to count a note's
#: entities double. Measured, it changes nothing at all — not the grouping,
#: not even the mean similarity to four decimal places — and it could not:
#: with four entities apiece across sixty notes almost every word is some
#: note's entity, so the weighting multiplies nearly every dimension by two,
#: and a vector scaled by a constant and renormalised is the vector it was.
#: Worse, where it did bite it would bite backwards: a note's strongest terms
#: by tf-idf are the words that tell it apart from the others, so counting
#: them double pushes notes away from the ones they belong with.
ENTITIES = 4

#: A date, or something that is acting like one.
_DATES = re.compile(
    r"\b(\d{1,2}[/.-]\d{1,2}(?:[/.-]\d{2,4})?"
    r"|\d{1,2}\s+(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto"
    r"|settembre|ottobre|novembre|dicembre"
    r"|january|february|march|april|may|june|july|august|september|october"
    r"|november|december)"
    r"|(?:lunedi|martedi|mercoledi|giovedi|venerdi|sabato|domenica"
    r"|monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b",
    re.IGNORECASE)

#: A quantity worth keeping: a figure with something attached to it.
_NUMBERS = re.compile(
    r"\b(\d+(?:[.,]\d+)?\s*(?:%|percento|per cento|euro|€|\$|GB|MB|TB|KB"
    r"|minuti|minute|minutes|secondi|seconds|ore|hours|giorni|days"
    r"|settimane|weeks|mesi|months|utenti|users|ticket|tickets))\b",
    re.IGNORECASE)


@dataclass
class Cluster:
    """The notes of one section, and what it turned out to be about."""

    notes: list = field(default_factory=list)
    title: str | None = None
    #: ``discovered`` when the distances made it, ``routed`` when a kind did.
    origin: str = "discovered"
    #: The kind, when a kind made it: the heading is then already known.
    kind: str | None = None
    keywords: list = field(default_factory=list)

    @property
    def ts_min(self):
        """When the earliest of its notes was said, for putting sections in
        the order the recording had them."""
        said = [note.ts_start for note in self.notes if note.ts_start is not None]
        return min(said) if said else 0.0

    def __len__(self):
        return len(self.notes)


# --- what happens to every note, whichever way it is placed ----------------

def entities_of(found, language="it", how_many=ENTITIES):
    """The words each note is most about: its own, that the meeting keeps
    coming back to.

    The design this came from asked for the note's strongest terms by tf-idf.
    Tried, that gives the exact opposite of what the name promises. Tf-idf
    rewards a word for being *rare* among the others, so on forty notes about
    one meeting the word "dashboard" — which is what half of them are about —
    scores near nothing, and what comes back are the words that make each note
    unlike its neighbours. A note about the dashboard came out as being about
    "distingue" and "aperto".

    So: the note's content words, ranked by how much of the meeting uses
    them. That is the domain vocabulary, and it is what somebody reading the
    record would call the thing a note mentions."""
    if not found:
        return []
    language = language_of(language)
    documents = [_terms(note.text, language) for note in found]
    common = {}
    for document in documents:
        for word in set(document):
            common[word] = common.get(word, 0) + 1
    picked = []
    for document in documents:
        order = sorted(set(document),
                       key=lambda word: (-common[word], -len(word), word))
        picked.append(order[:how_many])
    return picked


def enrich(found, language="it"):
    """Fill in what can be worked out about each note by looking at it.

    None of this is asked of the model. Its entities are its own strongest
    words; its dates and numbers are in its text or they are not. A model
    asked for them would sometimes supply ones that were never said, and a
    date nobody mentioned is worse than no date at all."""
    for note, words in zip(found, entities_of(found, language), strict=True):
        note.entities = words
        note.dates = [found.strip() for found in _DATES.findall(note.text)]
        note.numbers = [figure.strip() for figure in _NUMBERS.findall(note.text)]
    return found


def similarity(found, language="it"):
    """How alike every pair of notes is, 0..1.

    Plain tf-idf cosine over the content words. See :data:`ENTITIES` for why
    there is no weighting of what a note is about, which the design this came
    from asked for."""
    if not found:
        return np.zeros((0, 0))
    matrix, vocabulary = _vectors(found, language_of(language))
    if not vocabulary:
        return np.eye(len(found))
    return np.clip(matrix @ matrix.T, 0.0, 1.0)


def dedupe(found, language="it", same=SAME_NOTE):
    """Drop the note that arrived twice, keeping the fuller telling of it.

    Chunks overlap on purpose, so that nothing falls between two of them; the
    price is that whatever sits on a seam is read twice. The one kept carries
    the earlier of the two minutes, because that is when it was said."""
    if len(found) < 2:
        return list(found)
    alike = similarity(found, language)
    kept, dropped = [], set()
    for first in range(len(found)):
        if first in dropped:
            continue
        best = found[first]
        for second in range(first + 1, len(found)):
            if second in dropped or alike[first, second] < same:
                continue
            dropped.add(second)
            other = found[second]
            if len(other.text) > len(best.text):
                other.ts_start = _earliest(best, other)
                best = other
            else:
                best.ts_start = _earliest(best, other)
        kept.append(best)
    return kept


def _earliest(one, other):
    said = [note.ts_start for note in (one, other) if note.ts_start is not None]
    return min(said) if said else None


# --- the three ways of placing one -----------------------------------------

def _merge(alike, apart):
    """Average-linkage agglomeration, written as plainly as it can be.

    A loop rather than a library: the number of notes in a meeting is in the
    dozens, the cost is invisible beside one call to a model, and the
    alternative is a dependency this project does not need for it."""
    groups = [[index] for index in range(alike.shape[0])]
    while len(groups) > 1:
        best, pair = -1.0, None
        for first in range(len(groups)):
            for second in range(first + 1, len(groups)):
                block = alike[np.ix_(groups[first], groups[second])]
                score = float(block.mean())
                if score > best:
                    best, pair = score, (first, second)
        if pair is None or best < 1.0 - apart:
            break
        first, second = pair
        groups[first] = groups[first] + groups[second]
        del groups[second]
    return groups


def _adopt(groups, alike, orphaned):
    """Give a note that found no company to whichever section is nearest.

    Past :data:`ORPHANED` nobody adopts it: it goes at the end, under a
    heading that says it belongs nowhere, which is honest and is also how a
    person taking minutes writes down the thing that came up once."""
    settled = [group for group in groups if len(group) >= MIN_NOTES]
    alone = [group[0] for group in groups if len(group) < MIN_NOTES]
    if not settled:
        # Nothing found company. A dozen sections of one note each is not a
        # document, and pretending otherwise would be the same dishonesty as
        # a page that looks finished: they all go under the heading that says
        # they belong nowhere.
        return [], alone
    left = []
    for index in alone:
        scores = [float(alike[index, settled[at]].mean())
                  for at in range(len(settled))]
        best = int(np.argmax(scores))
        if scores[best] >= 1.0 - orphaned:
            settled[best] = settled[best] + [index]
        else:
            left.append(index)
    return settled, left


def _choose_apart(alike, most=MAX_SECTIONS, stray=STRAY_SHARE):
    """The tightest distance at which this set of notes makes a document.

    Tightest rather than loosest, because loosening always "works": at the far
    end every note is in one section, which is a document with one heading and
    nothing said by having it. So the search walks from tight to loose and
    stops at the first distance that produces no more than ``most`` sections
    and leaves no more than ``stray`` of the notes on their own.

    When nothing satisfies both — a recording of sixty unrelated remarks — the
    loosest is taken and whatever is still alone is named as such further
    down. Silently returning a hundred sections of one note would be the same
    dishonesty as a page that looks finished."""
    total = alike.shape[0]
    if total < 2:
        return APART_RANGE[0], [[index] for index in range(total)]
    last = None
    for apart in APART_RANGE:
        groups = _merge(alike, apart)
        sections = [group for group in groups if len(group) >= MIN_NOTES]
        alone = total - sum(len(group) for group in sections)
        last = (apart, groups)
        if sections and len(sections) <= most and alone <= stray * total:
            return apart, groups
    return last


def discover(found, language="it", apart=None, orphaned=ORPHANED,
             most=MAX_SECTIONS):
    """Sections out of the distances, and the leftovers named as such."""
    if not found:
        return [], []
    alike = similarity(found, language)
    if apart is None:
        _apart, groups = _choose_apart(alike, most)
    else:
        groups = _merge(alike, apart)
    settled, left = _adopt(groups, alike, orphaned)
    sections = [Cluster(notes=[found[at] for at in sorted(group)])
                for group in settled]
    for section in sections:
        section.keywords = _about(section.notes, language)
    sections.sort(key=lambda section: section.ts_min)
    return sections, [found[at] for at in sorted(left)]


def route(found, kinds=None):
    """One section per kind, in the order the catalogue has them.

    No distances: a note of kind ``decision`` belongs under "Decisions", and
    working that out by measuring how far it is from the other decisions is a
    lossy way of arriving where it already was."""
    wanted = tuple(kinds or note_kinds.TYPES)
    sections = []
    for kind in wanted:
        mine = [note for note in found if note.type == kind]
        if mine:
            sections.append(Cluster(notes=mine, origin="routed", kind=kind,
                                    keywords=_about(mine)))
    return sections


def _about(found, language="it", how_many=3):
    """The three words a section is most about, for naming it without a model.

    Counted inside the section rather than against the meeting: what a section
    is about is the word its notes have in common, which is exactly the word a
    measure of rarity throws away."""
    counted = {}
    for note in found:
        for word in set(_terms(note.text, language_of(language))):
            counted[word] = counted.get(word, 0) + 1
    return [word for word, _ in
            sorted(counted.items(),
                   key=lambda pair: (-pair[1], -len(pair[0]), pair[0]))][:how_many]


def assign(found, mode=HYBRID, language="it", apart=None, orphaned=ORPHANED,
           most=MAX_SECTIONS, kinds=None):
    """Notes in, sections out. ``(body, tail)``.

    ``tail`` is empty in every mode but :data:`HYBRID`, where it carries the
    decisions and the actions as lists of their own — and they stay in the
    body section that holds them as well. That duplication is the one thing a
    reader of minutes actually asks for twice: what was being discussed, and
    what has to be done about it."""
    mode = str(mode or HYBRID).strip().lower()
    if mode not in MODES:
        raise ValueError(f"unknown way of making sections: {mode}")
    found = list(found)
    if not found:
        return [], []

    if mode == FIXED:
        return route(found, kinds), []

    body_notes = found
    tail = []
    if mode == HYBRID:
        tail = route([note for note in found if note.type in TAIL_TYPES],
                     TAIL_TYPES)
        # Left in the body as well, on purpose: the section is where a
        # decision is explained, and the list is where it is acted on.
        body_notes = found

    sections, left = discover(body_notes, language, apart, orphaned, most)
    if left:
        sections.append(Cluster(notes=left, origin="discovered",
                                kind="other", keywords=_about(left, language)))
    return sections, tail
