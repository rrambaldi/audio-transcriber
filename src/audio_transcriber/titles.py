"""A title for a recording, taken from what was said in it.

A recording arrives called `2026-09-15_1830.wav`, or `Registrazione (3)`, and
a library of those is a library nobody can look through: the date is already
in the row, and the name adds nothing. What does distinguish one meeting from
another is what it was about, and that is in the transcript.

Nothing here loads a model. The transcript is ranked the way the extractive
summary ranks it — TextRank over the sentences — and the strongest sentence
is trimmed into a label: the same machinery, asked a smaller question. Where a
model *has* already written a summary, its first sentence is used instead,
because a sentence written about the whole recording beats the best sentence
taken out of it.
"""
import re

from . import summary

#: How long a title may be before it stops being one and becomes a sentence.
MAX_WORDS = 9
MAX_CHARS = 72

#: Openings that say nothing about the recording. They are the first words of
#: spoken sentences everywhere, and a title that starts with one is a title
#: that starts with noise.
_OPENERS = {
    "it": ("allora", "ecco", "quindi", "dunque", "insomma", "comunque", "beh",
           "bene", "ok", "okay", "cioe", "diciamo", "praticamente", "senti",
           "sentite", "guarda", "guardate", "niente", "ciao", "buongiorno",
           "buonasera", "salve", "perfetto", "esatto", "va bene"),
    "en": ("so", "well", "right", "okay", "ok", "now", "anyway", "basically",
           "actually", "yeah", "hello", "hi", "good morning", "good evening",
           "alright", "look", "listen"),
}

#: Words a title must not end on: it would read as a sentence cut in half.
_DANGLING = {
    "it": ("di", "a", "da", "in", "con", "su", "per", "tra", "fra", "e", "o",
           "ma", "che", "il", "lo", "la", "i", "gli", "le", "un", "uno", "una",
           "del", "della", "dei", "delle", "al", "alla", "nel", "nella", "come",
           "se", "quando", "dove", "perche", "non", "ci", "si"),
    "en": ("of", "to", "from", "in", "with", "on", "for", "and", "or", "but",
           "that", "the", "a", "an", "as", "at", "by", "is", "are", "was",
           "were", "not", "if", "when", "where", "because", "this", "these"),
}

#: What a spoken sentence ends with and a title does not.
_TRAILING = " ,;:.!?…-–—\"'«»"


def _words_of(language):
    return (_OPENERS.get(language, _OPENERS["en"]),
            _DANGLING.get(language, _DANGLING["en"]))


#: Where a spoken sentence can be cut without breaking a phrase. Speech is
#: one clause after another, and the clause carrying the subject is usually
#: not the first: "the point is that the budget does not cover the hires".
_CLAUSE = re.compile(r",|;|:|\bche\b|\bthat\b|\bma\b|\bbut\b|\be\b|\band\b",
                     re.IGNORECASE)


def shorten(sentence, language="it"):
    """One spoken sentence, trimmed into something that reads as a title.

    The opening filler goes first. What is left is used whole when it is
    short enough; when it is not, the longest *clause* that fits is taken
    rather than the first N words, because the half of a sentence that says
    something is rarely the half it starts with. A clause that would end on a
    preposition or an article is trimmed back: a title that breaks mid-phrase
    reads as a mistake, not as a short label.

    Returns "" when nothing survives that is worth calling a title — three
    words is the floor — and the caller falls back to the terms instead."""
    openers, dangling = _words_of(summary.language_of(language))
    text = re.sub(r"\s+", " ", str(sentence or "")).strip(_TRAILING).strip()
    if not text:
        return ""
    lowered = summary.fold(text.lower())
    for opener in sorted(openers, key=len, reverse=True):
        if lowered.startswith(opener + " ") or lowered == opener:
            text = text[len(opener):].lstrip(_TRAILING).strip()
            break

    best = _fit(text, dangling)
    if best is None:
        # The longest clause that fits, and the widest one wins: the point of
        # a sentence is usually in its longer half.
        clauses = [_fit(part, dangling) for part in _CLAUSE.split(text)]
        found = [clause for clause in clauses if clause and len(clause.split()) >= 3]
        best = max(found, key=lambda clause: len(clause.split()), default=None)
    if best is None:
        # Nothing breaks cleanly: the first words, then, which is what a
        # written sentence — a summary's opening line — usually wants anyway.
        best = _fit(" ".join(text.split()[:MAX_WORDS]), dangling)
    if not best:
        return ""
    if len(best) > MAX_CHARS:
        best = best[:MAX_CHARS].rsplit(" ", 1)[0].strip(_TRAILING)
    return best[:1].upper() + best[1:] if best else ""


def _fit(text, dangling):
    """``text`` as a title if it is short enough already, else None."""
    words = str(text or "").strip(_TRAILING).strip().split()
    while words and summary.fold(words[-1].lower().strip(_TRAILING)) in dangling:
        words.pop()
    # And not starting on one either: a clause taken out of the middle of a
    # sentence often begins with the word that joined it to the one before.
    while words and summary.fold(words[0].lower().strip(_TRAILING)) in dangling:
        words.pop(0)
    if not words or len(words) > MAX_WORDS:
        return None
    return " ".join(words).strip(_TRAILING).strip()


def from_summary(text, language="it"):
    """A title out of a summary that has already been written, or ""."""
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "_", "-", "*", ">")):
            continue          # headings, the caveat in italics, bullet lists
        sentences = summary.split_sentences(line)
        if sentences:
            return shorten(sentences[0], language)
    return ""


def suggest(text=None, segments=None, language="it", summary_text=None):
    """A title for this recording, or "" when there is nothing to take one from.

    ``summary_text`` wins when there is one: a sentence written about the
    whole recording says more than the best sentence taken out of it. Failing
    that the transcript is ranked and its strongest sentence is trimmed, and
    failing *that* — a transcript of one word, a recording of somebody saying
    "pronto?" — the terms it keeps coming back to are the label, because a
    short honest list beats a file name that says nothing."""
    language = summary.language_of(language)
    from_written = from_summary(summary_text, language)
    if from_written:
        return from_written

    sentences = (summary.sentences_of(segments) if segments
                 else summary.sentences_from_text(text))
    if not sentences:
        return ""
    if len(sentences) > 1:
        scores = summary.rank(sentences, language)
        # select() returns positions, in the order they were spoken.
        best = summary.select(sentences, scores, 1, language)
        candidate = sentences[best[0]].text if best else sentences[0].text
    else:
        candidate = sentences[0].text
    title = shorten(candidate, language)
    if title:
        return title
    terms = summary.keywords(sentences, language, count=4)
    return shorten(", ".join(terms), language) if terms else ""
