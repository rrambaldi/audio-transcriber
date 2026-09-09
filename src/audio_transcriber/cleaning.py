"""Tidying the transcript: normalisation, removal of the phrases Whisper
hallucinates over silence, and grouping into paragraphs.

Two of the things removed here are not the speaker's doing but the engine's. A
backend that transcribes a long recording in overlapping windows has to stitch
them back together, and when the stitch fails the overlap is emitted twice —
the tail of one segment reappearing at the head of the next, or, when the
engine glued its windows into one segment, the same run of words twice in a
row. Neither is something anybody said, so both are cut: the transcript is
meant to be what was spoken, and a doubled passage also doubles the characters
a subtitle has to show in the same seconds, which is what pushes cues past a
preset's reading speed.
"""
import re
from difflib import SequenceMatcher

#: Phrases Whisper typically invents over silence or non-speech, per language.
HALLUCINATION_PHRASES = {
    "it": {
        "grazie", "grazie a tutti", "grazie mille", "grazie a te", "grazie a voi",
        "grazie per l'attenzione", "grazie per la visione", "grazie di cuore",
        "sottotitoli e revisione a cura di qtss",
        "sottotitoli e revisione a cura di qtss grazie a tutti",
        "autore dei sottotitoli e delle caratteristiche di qtss",
        "sottotitoli creati dalla comunita amara.org",
        "ciao", "buongiorno a tutti", "buona giornata",
    },
    "en": {
        "thank you", "thanks for watching", "thank you for watching",
        "thanks for watching!", "please subscribe", "subscribe to my channel",
        "you", "bye", "goodbye", "see you next time",
    },
}

#: Union of every catalogue: the transcript language is not always known.
ALL_HALLUCINATION_PHRASES = frozenset().union(*HALLUCINATION_PHRASES.values())

#: Two identical segments are collapsed on sight; longer ones are also
#: collapsed when one contains the other, which is how chunk overlap shows up.
CONTAINMENT_MIN_LENGTH = 40

#: The shortest run worth collapsing when it repeats itself immediately, inside
#: one segment. Deliberately cautious: "no no no" and "cioè la creazione
#: dell'asset cioè la creazione dell'asset" are how people talk, and a run this
#: long repeated verbatim, back to back, is not.
REPEAT_MIN_WORDS = 6

#: The shortest run worth trimming off the head of a segment because the
#: segments before it already said it. Higher than :data:`REPEAT_MIN_WORDS`
#: because this one also throws away whatever sits in front of the match (see
#: :func:`overlap_size`), and because a meeting really does echo short phrases
#: — "ogni asset ha i suoi impatti" gets said three times in one conversation
#: by three people, and that is the record, not an artefact.
OVERLAP_MIN_WORDS = 8

#: The longest doubling looked for. A chunked engine overlaps its windows by a
#: few seconds, which at speaking speed is some tens of words; looking further
#: than this costs time and finds nothing.
REPEAT_MAX_WORDS = 80

#: How much of what is cut the alignment has to actually account for. Below
#: this, the "doubling" is just the small words two unrelated passages of the
#: same language have in common, and cutting on it would delete real speech.
OVERLAP_MIN_RATIO = 0.75

#: The shortest aligned run that counts as evidence. One word in common is
#: noise — every Italian sentence has a "che" in it somewhere.
MATCH_MIN_WORDS = 2

#: How much may sit in front of a doubling and still be thrown away with it.
#: The two copies of an overlap are never word-identical — the engine heard
#: the second one mid-window, and it comes out as "in solo questo campo e
#: tabellini" against "solo questo. quindi campo e tabellini" — so the match
#: starts a few words in, and those few words are the botched half of a
#: sentence that is about to be said properly.
OVERLAP_PREFIX_MAX_WORDS = 12

#: How far back a segment's head is compared. Two segments, because an engine
#: that doubled one window often doubles the next as well, and the second
#: doubling then repeats something two segments back rather than one.
OVERLAP_LOOKBACK_SEGMENTS = 2

#: The longest invented phrase looked for at a segment's edge; the catalogue's
#: longest entry is seven words.
HALLUCINATION_MAX_WORDS = 8

#: Sentence ends, for grouping words back into segments.
SENTENCE_END = re.compile(r"[.!?…]+[\"'”»)\]]*$")


def clean_text(text):
    """Collapse whitespace and remove spaces before punctuation."""
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+([,.;:!?…])", r"\1", text)


def normalise(text):
    """Lowercase, punctuation-free form used for comparisons."""
    return re.sub(r"[^\w\s]", "", (text or "").lower()).strip()


def _keys(words):
    """The comparison form of each word: what two copies of a run share.

    Compared word by word rather than as one string because the two copies of
    a doubled passage are rarely punctuated the same way — the engine heard
    the second one mid-window."""
    return [re.sub(r"[^\w]", "", word.lower()) for word in words]


def _same(left, right):
    """Whether two runs of comparison keys say the same thing.

    Empty keys — a word that was nothing but punctuation — are ignored on both
    sides, so "campo, e tabellini" matches "campo e tabellini"."""
    return [key for key in left if key] == [key for key in right if key]


# --------------------------------------------------------------------------
# the engine's doubling
# --------------------------------------------------------------------------

def overlap_size(previous, current, min_words=OVERLAP_MIN_WORDS,
                 max_words=REPEAT_MAX_WORDS, min_ratio=OVERLAP_MIN_RATIO,
                 prefix_max=OVERLAP_PREFIX_MAX_WORDS):
    """How many words to cut off the head of ``current`` because ``previous``
    already said them.

    Not "how long a prefix they share word for word": the two copies of a
    stitched-up overlap are never identical. The engine heard the second one
    mid-window, so it comes out with a word missing here and one invented
    there — "l'ho fatto non l'ho fatto" against "l'ho fatto o non l'ho fatto",
    "solo questo. quindi campo e tabellini" against "in solo questo campo e
    tabellini". Matching exactly finds none of it.

    So the two are aligned instead, and what is looked for is where the last
    thing ``previous`` also said *ends*: everything up to there goes. The
    alignment has to account for most of what is cut — :data:`OVERLAP_MIN_RATIO`
    of it — or nothing is cut at all, because two unrelated passages of the
    same language always share a scattering of small words and that must not
    be mistaken for a doubling."""
    tail, head = _keys(previous)[-max_words:], _keys(current)[:max_words]
    if len(tail) < min_words or len(head) < min_words:
        return 0
    blocks = [block for block
              in SequenceMatcher(None, tail, head, autojunk=False).get_matching_blocks()
              if block.size >= MATCH_MIN_WORDS]
    if not blocks or min(block.b for block in blocks) > prefix_max:
        return 0
    trim = max(block.b + block.size for block in blocks)
    matched = sum(block.size for block in blocks)
    if trim < min_words or matched < min_ratio * trim:
        return 0
    return trim


def collapse_repeats(words, min_words=REPEAT_MIN_WORDS, max_words=REPEAT_MAX_WORDS):
    """Drop every run of words that immediately repeats the run before it.

    This is the same doubling as :func:`overlap_size`, inside one segment: it
    is what an engine leaves behind when it glued two overlapping windows into
    a single segment instead of two."""
    keys = _keys(words)
    kept, kept_keys, index = [], [], 0
    while index < len(words):
        size = min(max_words, len(kept), len(words) - index)
        while size >= min_words:
            if _same(kept_keys[len(kept) - size:], keys[index:index + size]):
                break
            size -= 1
        if size >= min_words:
            index += size           # the second copy: skip it
            continue
        kept.append(words[index])
        kept_keys.append(keys[index])
        index += 1
    return kept


def hallucinated_run(words, catalogue, at_end=False,
                     max_words=HALLUCINATION_MAX_WORDS):
    """How many words at one end of ``words`` are an invented phrase.

    A whole segment that is nothing but "Grazie a tutti" is dropped by
    :func:`clean_segments`. This is the other shape the same invention takes:
    glued to the front or the back of a segment that does have speech in it,
    which is what happens when the engine's window straddles a silence.

    Looped, because the engine stacks them — "Sottotitoli e revisione a cura
    di QTSS. Grazie a tutti." — and longest phrase first, so "grazie a tutti"
    is preferred over the bare "grazie" it starts with."""
    if not catalogue:
        return 0
    keys = _keys(words)
    total = 0
    while total < len(keys):
        available = len(keys) - total
        for size in range(min(max_words, available), 0, -1):
            run = (keys[available - size:available] if at_end
                   else keys[total:total + size])
            phrase = " ".join(key for key in run if key)
            if phrase and phrase in catalogue:
                total += size
                break
        else:
            break
    return total


def strip_hallucinations(words, catalogue):
    """``(words, cut from the head)`` with the invented edges removed.

    The head count is returned because it is also how far into the recording
    the segment now starts: a segment whose first seconds were an invented
    phrase no longer begins where it claimed to."""
    head = hallucinated_run(words, catalogue)
    words = words[head:]
    tail = hallucinated_run(words, catalogue, at_end=True)
    return (words[:len(words) - tail] if tail else words), head


# --------------------------------------------------------------------------
# segments
# --------------------------------------------------------------------------

def _words_of(segment):
    """``(words, timed)``: the segment's words, and its timed list if it has one.

    A backend asked for word timings reports them, and the two views must not
    drift apart — trimming the text without trimming the timings would leave
    subtitles cut on words that are no longer there."""
    timed = segment.get("words") or []
    if timed:
        return [str(word.get("word") or "").strip() for word in timed], timed
    return ((segment.get("text") or "").split()), None


def _rebuilt(segment, words, timed, original, head):
    """A copy of ``segment`` holding only ``words``, timings included.

    With word timings, the words that survived are matched back onto the timed
    list in order, skipping the entries that were cut: trimming only ever
    removes words and never reorders them, so the first entry that matches is
    the right one — and where a repeat was collapsed it is the first copy that
    was kept, whose timings come first.

    Without them there is nothing to match, so a segment that lost ``head``
    words off its front has its start moved along by their share of the
    characters. Leaving the old start would put every subtitle in the segment
    early by exactly the length of the doubling that was cut, which is the one
    error worth avoiding: the text was wrong before and is right now, and a
    right text on a wrong clock is no better on screen."""
    fresh = {**segment, "text": clean_text(" ".join(words))}
    if timed is None:
        start, end = segment.get("start"), segment.get("end")
        chars = sum(len(word) for word in original)
        if head and chars and start is not None and end is not None:
            cut = sum(len(word) for word in original[:head])
            fresh["start"] = start + (float(end) - float(start)) * cut / chars
        return fresh
    keys = _keys(words)
    chosen, at = [], 0
    for key, word in zip(keys, words, strict=False):
        while at < len(timed):
            candidate = timed[at]
            at += 1
            if re.sub(r"[^\w]", "", str(candidate.get("word") or "").lower()) == key:
                chosen.append(candidate)
                break
        else:
            chosen.append({"word": word, "start": fresh.get("start"),
                           "end": fresh.get("end")})
    if chosen:
        fresh["words"] = chosen
        first, last = chosen[0].get("start"), chosen[-1].get("end")
        if first is not None:
            fresh["start"] = first
        if last is not None:
            fresh["end"] = last
    else:
        fresh.pop("words", None)
    return fresh


def clean_segments(segments, drop_fillers=True, phrases=None):
    """Drop hallucinated segments and cut the doubling the engine left behind.

    Three different things, in the order they have to happen: a segment that is
    nothing but an invented phrase goes; an invented phrase glued to the edge
    of a real segment is cut off it; and a run of words that repeats the run
    before it — whether the repeat is inside one segment or across two — is
    cut, because nobody said it twice.

    ``drop_fillers`` governs the invented phrases only. The doubling is not
    editorial and is always cut: a verbatim transcript is a faithful record of
    the speech, not of the engine's stitching."""
    catalogue = ALL_HALLUCINATION_PHRASES if phrases is None else phrases
    if not drop_fillers:
        catalogue = frozenset()
    kept = []
    for segment in segments:
        text = (segment.get("text") or "").strip()
        if not text:
            continue
        key = normalise(text)
        if key in catalogue:
            continue
        words, timed = _words_of(segment)
        trimmed, head = strip_hallucinations(list(words), catalogue)
        recent = []
        for earlier in kept[-OVERLAP_LOOKBACK_SEGMENTS:]:
            recent.extend(_words_of(earlier)[0])
        doubled = overlap_size(recent[-REPEAT_MAX_WORDS:], trimmed) if recent else 0
        head += doubled
        trimmed = collapse_repeats(trimmed[doubled:])
        if not trimmed:
            continue
        if trimmed != words:
            segment = _rebuilt(segment, trimmed, timed, words, head)
            text = segment["text"]
            key = normalise(text)
        else:
            segment = {**segment, "text": text}
        if kept:
            previous = normalise(kept[-1]["text"])
            duplicate = key and (
                key == previous
                or (len(key) > CONTAINMENT_MIN_LENGTH
                    and (key in previous or previous in key)))
            if duplicate:
                # Keep whichever version says more.
                if len(text) > len(kept[-1]["text"]):
                    kept[-1] = segment
                continue
        kept.append(segment)
    return kept


def segments_from_words(timed, pause=0.6, max_seconds=20.0, max_chars=400):
    """Group timed words into segments, the way a speaker groups them.

    An engine asked for word timings and nothing else — the OpenVINO
    backend — hands back one word per entry and no segments at all. Cutting
    them at a sentence end, at a real pause, or when a segment has simply gone
    on long enough gives the transcript its paragraphs back, and every segment
    keeps the timings underneath it so subtitles are still cut on measured
    times rather than interpolated ones."""
    built, current = [], []

    def flush():
        if not current:
            return
        starts = [word["start"] for word in current if word.get("start") is not None]
        ends = [word["end"] for word in current if word.get("end") is not None]
        built.append({
            "text": clean_text(" ".join(word["word"] for word in current)),
            "start": starts[0] if starts else 0.0,
            "end": ends[-1] if ends else (starts[-1] if starts else 0.0),
            "words": list(current),
        })
        current.clear()

    for word in timed:
        body = str(word.get("word") or "").strip()
        if not body:
            continue
        entry = {"word": body, "start": word.get("start"), "end": word.get("end")}
        if current:
            previous_end = current[-1].get("end")
            start = entry.get("start")
            gap = (start - previous_end) if (start is not None
                                             and previous_end is not None) else 0.0
            opened = current[0].get("start")
            span = ((entry.get("end") or start or 0.0) - opened
                    if opened is not None else 0.0)
            width = sum(len(item["word"]) + 1 for item in current)
            if gap > pause or span > max_seconds or width >= max_chars:
                flush()
        current.append(entry)
        if SENTENCE_END.search(body):
            flush()
    flush()
    return built


def to_paragraphs(segments, gap_break, max_chars):
    """Group segments into paragraphs, breaking on a long pause in speech or
    when a paragraph grows too long."""
    paragraphs, current = [], ""
    for index, segment in enumerate(segments):
        text = (segment.get("text") or "").strip()
        if not text:
            continue
        current = (current + " " + text).strip() if current else text
        following = segments[index + 1] if index + 1 < len(segments) else None
        end = segment.get("end")
        next_start = following.get("start") if following else None
        # No timestamps means no way to measure the pause: break here.
        gap = (next_start - end) if (end is not None and next_start is not None) else None
        if gap is None or gap > gap_break or len(current) >= max_chars:
            paragraphs.append(clean_text(current))
            current = ""
    if current:
        paragraphs.append(clean_text(current))
    return [p for p in paragraphs if p]


def paragraphs_from_blob(text, sentences_per_para=5):
    """Fallback when there are no timestamps: split into sentences and group."""
    sentences = re.split(r"(?<=[.!?…])\s+", clean_text(text))
    paragraphs = []
    for index in range(0, len(sentences), sentences_per_para):
        chunk = " ".join(sentences[index:index + sentences_per_para]).strip()
        if chunk:
            paragraphs.append(chunk)
    return paragraphs
