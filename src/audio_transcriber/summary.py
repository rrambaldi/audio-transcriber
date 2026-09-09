"""Summaries: what to keep out of an hour of talking, and how it reads.

A transcript of a one-hour meeting is around fifteen thousand tokens of
speech — repetitions, false starts, three people agreeing in four different
ways. A summary of it is two things, and only the second one needs a model:

*selection*
    which sentences carry the meeting. That is arithmetic on the words
    themselves — TextRank over a sentence-similarity graph — and it runs in
    milliseconds on numpy, which the core already depends on.
*writing*
    turning what was selected into prose: an abstract, decisions, actions.
    That is language work, and it needs a language model.

Splitting them this way is what makes the feature portable across the two
machines this program runs on. Where there is an accelerator the model reads
the whole transcript and selection is a nicety; on a two-core server with no
GPU the same selection cuts fifteen thousand tokens down to three thousand
first, and a small model that would have drowned in the raw stream produces
something usable. Same module, same output format, different amount of help.

The engines live in :mod:`audio_transcriber.summarizers`, chosen by name the
way transcription backends are. This module holds everything that is *not* an
engine: sentences, ranking, selection, the reduction stage and the page that
comes out. All of it is pure — text in, text out, no I/O and no model — which
is why the test suite can cover it on a machine with neither.
"""
import re
import time
from collections import namedtuple
from datetime import datetime

import numpy as np

from .formatting import format_clock
from .i18n import t

#: How long the summary should be, by name rather than by number — the same
#: bargain the subtitle presets make. Each is ``(ratio, fewest, most)``: a
#: share of the sentences in the transcript, with a floor so a five-minute
#: note still says something and a ceiling so an all-day recording does not
#: produce a second transcript.
LENGTHS = {
    "short":  (0.05, 3, 8),
    "medium": (0.10, 5, 15),
    "long":   (0.18, 8, 30),
}

#: Used when nothing says otherwise.
DEFAULT_LENGTH = "medium"

#: Two sentences this similar say the same thing: the second one is dropped
#: however well it scores. Meetings are repetitive, and a summary that repeats
#: an agreement three times has spent its budget on one point.
REDUNDANCY = 0.62

#: Sentence enders, and the abbreviations that are not them.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")
_ABBREVIATIONS = {"dott", "dr", "sig", "ing", "avv", "prof", "sig.ra", "ecc",
                  "mr", "mrs", "ms", "vs", "etc", "e.g", "i.e"}

#: A word, for the purpose of ranking: letters and digits, apostrophes kept
#: inside so "dell'azienda" arrives here in one piece.
_WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?|\d+", re.UNICODE)

#: Italian articles and prepositions that lose their vowel before another
#: one. They arrive glued to the word that follows — "l'ente", "dell'audit",
#: "d'accordo" — and without this the ranking treats "l'ente" and "ente" as
#: two unrelated terms, which is how "l'audit" ends up in a list of recurring
#: terms next to "audit".
_ELIDED = {"l", "un", "d", "dell", "nell", "all", "dall", "sull", "coll",
           "quell", "bell", "sant", "anch", "senz", "tutt", "c", "s", "t",
           "m", "v", "gl", "n"}

#: Words that carry no topic. Ranking without them makes every sentence look
#: like every other one, because in speech the connective tissue is most of
#: the text. Two languages only: the ones the interface itself speaks.
STOPWORDS = {
    "it": {
        "a", "abbiamo", "adesso", "ad", "agli", "ai", "al", "alcuni", "all",
        "alla", "alle", "allo", "allora", "altre", "altri", "altro", "anche",
        "ancora", "avere", "aveva", "avevo", "avete", "avuto", "basta", "bene",
        "c", "che", "chi", "ci", "cio", "cioe", "come", "con", "cosa", "cosi",
        "cui", "da", "dai", "dal", "dalla", "dallo", "degli", "dei", "del",
        "della", "delle", "dello", "dentro", "detto", "deve", "devo", "di",
        "dopo", "dove", "due", "durante", "e", "ecco", "ed", "entro", "era",
        "erano", "essere",
        "fa", "fare", "fatto", "fino", "forse", "fra", "gia", "gli", "grazie",
        "ha", "hai", "hanno", "ho", "i", "il", "in", "invece", "io", "l", "la",
        "le", "lei", "li", "lo", "loro", "lui", "ma", "magari", "mai", "me",
        "mentre", "mi", "mia", "mie", "miei", "mio", "molto", "ne", "negli",
        "nei", "nel", "nella", "nelle", "nello", "no", "noi", "non", "nostro",
        "o", "ogni", "oppure", "ora", "per", "percio", "perche", "pero", "piu",
        "po", "poi", "porta", "prima", "puo", "qua", "quale", "quando",
        "quanto", "quasi", "quella", "quelle", "quelli", "quello", "questa",
        "queste", "questi", "questo", "qui", "quindi", "s", "sara", "se",
        "sei", "sempre", "senza", "si", "sia", "siamo", "solo", "sono",
        "oltre", "sopra", "sotto", "sta", "stato", "su", "sua", "sue", "sui",
        "sul",
        "sulla", "suo", "t", "tanto", "te", "tra", "tu", "tuo", "tutti",
        "tutto", "un", "una", "uno", "va", "vedi", "vi", "voi", "vuole",
    },
    "en": {
        "a", "about", "actually", "after", "all", "also", "an", "and", "any",
        "are", "as", "at", "back", "be", "because", "been", "before", "being",
        "but", "by", "can", "come", "could", "did", "do", "does", "doing",
        "done", "down", "each", "even", "every", "for", "from", "get", "go",
        "going", "good", "got", "had", "has", "have", "he", "her", "here",
        "him", "his", "how", "i", "if", "in", "into", "is", "it", "its",
        "just", "keep", "know", "like", "look", "make", "many", "may", "me",
        "mean", "might", "more", "most", "much", "must", "my", "need", "no",
        "not", "now", "of", "off", "ok", "on", "one", "only", "or", "other",
        "our", "out", "over", "really", "right", "said", "say", "see", "she",
        "should", "so", "some", "something", "still", "such", "sure", "take",
        "than", "that", "the", "their", "them", "then", "there", "these",
        "they", "thing", "think", "this", "those", "through", "to", "too",
        "up", "use", "very", "want", "was", "way", "we", "well", "were",
        "what", "when", "where", "which", "while", "who", "why", "will",
        "with", "would", "yeah", "yes", "you", "your",
    },
}

#: The words the page is built from. These do *not* come from :mod:`i18n`:
#: that catalogue is the language of the interface, and a summary is a
#: document in the language that was spoken. Somebody with an English desktop
#: summarising an Italian meeting wants an Italian page.
HEADINGS = {
    "en": {
        "title": "Summary",
        "abstract": "In brief",
        "points": "Key points",
        "decisions": "Decisions",
        "actions": "Actions",
        "keywords": "Recurring terms",
        "made_by": "{engine}, {when} — from a {minutes}-minute recording",
        "made_by_untimed": "{engine}, {when}",
        "extractive_note":
            "These are sentences taken from the transcript, chosen by weight "
            "and left as they were said — not a text written about it.",
    },
    "it": {
        "title": "Riassunto",
        "abstract": "In breve",
        "points": "Punti chiave",
        "decisions": "Decisioni",
        "actions": "Azioni",
        "keywords": "Termini ricorrenti",
        "made_by": "{engine}, {when} — da una registrazione di {minutes} minuti",
        "made_by_untimed": "{engine}, {when}",
        "extractive_note":
            "Queste sono frasi prese dalla trascrizione, scelte per peso e "
            "lasciate come sono state dette: non un testo scritto su di essa.",
    },
}

#: One sentence of the transcript, with where it was said. ``start`` is the
#: start of the *segment* the sentence came from, not of the sentence itself:
#: Whisper times segments, not clauses, and a label that lands a few seconds
#: early is right for jumping to, which is the only thing it is used for.
Sentence = namedtuple("Sentence", "text start end speaker")
Sentence.__new__.__defaults__ = (None, None, None)

#: What is being summarised, assembled by the caller from a library entry or
#: from a bare file, so no engine ever has to know about either.
Material = namedtuple("Material", "title sentences language duration")
Material.__new__.__defaults__ = ("", (), "it", None)

#: What an engine returns. Every field is optional but ``abstract``: the
#: extractive engine fills three of them, a model fills five, and the page
#: leaves out what it was not given rather than printing empty headings.
Sections = namedtuple("Sections", "abstract points keywords decisions actions")
Sections.__new__.__defaults__ = ("", (), (), (), ())

#: A point on the page: when it was said, who said it, what was said.
Point = namedtuple("Point", "start speaker text")
Point.__new__.__defaults__ = (None, None, "")

#: One finished summary, ready to be written to ``summary.md``.
Summary = namedtuple("Summary", "text sections engine language elapsed kept of")


class SummaryError(Exception):
    """Any reason a summary could not be produced."""


def estimate_tokens(text):
    """Roughly how many tokens a piece of text is worth.

    Four characters to the token, which is close enough for the only two
    questions asked of it — does this fit in the context, and how much has the
    reduction saved — and wrong enough that nothing should be promised on it.
    """
    return max(0, len(text or "")) // 4


def language_of(code):
    """The stopword and heading language to use for a spoken-language code."""
    code = str(code or "").strip().lower().split("_")[0].split("-")[0]
    return code if code in STOPWORDS else "en"


def split_sentences(text):
    """Split a blob of speech into sentences, keeping abbreviations whole."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return []
    parts, buffer = [], ""
    for candidate in _SENTENCE_SPLIT.split(text):
        buffer = f"{buffer} {candidate}".strip() if buffer else candidate
        tail = buffer.rsplit(" ", 1)[-1].rstrip(".!?…").lower()
        # "l'ing." is the abbreviation "ing." wearing an elided article.
        if tail.rsplit("'", 1)[-1] in _ABBREVIATIONS:
            continue
        parts.append(buffer)
        buffer = ""
    if buffer:
        parts.append(buffer)
    return [part for part in parts if part]


def sentences_of(segments):
    """Sentences with their timestamps, from the transcript's segments."""
    found = []
    for segment in segments or []:
        text = (segment.get("text") or "").strip()
        if not text:
            continue
        speaker = segment.get("speaker")
        start, end = segment.get("start"), segment.get("end")
        for piece in split_sentences(text):
            found.append(Sentence(piece, start, end, speaker))
    return found


def sentences_from_text(text):
    """Sentences from a transcript with no segments: no timestamps, then."""
    return [Sentence(piece) for piece in split_sentences(text)]


def _terms(sentence_text, language):
    """The content words of one sentence, lowercased."""
    stop = STOPWORDS.get(language, STOPWORDS["en"])
    words = []
    for match in _WORD.findall(str(sentence_text or "").lower()):
        word = match.strip("'")
        head, sep, tail = word.partition("'")
        if sep and tail and head in _ELIDED:
            word = tail
        if len(word) < 3 or word in stop:
            continue
        words.append(word)
    return words


def _vectors(sentences, language):
    """A tf-idf matrix of the sentences, rows normalised to unit length.

    Unit rows mean the cosine similarity of two sentences is just their dot
    product, which is what makes both the ranking and the redundancy check one
    matrix multiplication instead of a loop."""
    documents = [_terms(sentence.text, language) for sentence in sentences]
    vocabulary = {}
    for document in documents:
        for word in document:
            vocabulary.setdefault(word, len(vocabulary))
    if not vocabulary:
        return np.zeros((len(sentences), 0)), vocabulary

    counts = np.zeros((len(sentences), len(vocabulary)), dtype=np.float64)
    for row, document in enumerate(documents):
        for word in document:
            counts[row, vocabulary[word]] += 1.0

    appearances = np.count_nonzero(counts, axis=0)
    idf = np.log((1.0 + len(sentences)) / (1.0 + appearances)) + 1.0
    matrix = counts * idf
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms, vocabulary


def rank(sentences, language="it", damping=0.85, iterations=40):
    """TextRank: how much of the transcript each sentence speaks for.

    Sentences are nodes, their cosine similarity is the edge weight, and the
    score is the stationary distribution of a random walk over that graph —
    PageRank, on sentences. What it finds is the sentence that says what the
    other sentences keep saying, which in a meeting is exactly the point being
    made."""
    count = len(sentences)
    if count == 0:
        return np.zeros(0)
    if count == 1:
        return np.ones(1)

    matrix, _ = _vectors(sentences, language)
    similarity = matrix @ matrix.T
    np.fill_diagonal(similarity, 0.0)
    np.clip(similarity, 0.0, None, out=similarity)

    weights = similarity.sum(axis=1, keepdims=True)
    # A sentence sharing no word with any other is not connected to anything;
    # give it the uniform row so the walk can leave it instead of stalling.
    isolated = (weights == 0).ravel()
    transition = np.divide(similarity, np.where(weights == 0, 1.0, weights))
    transition[isolated] = 1.0 / count

    scores = np.full(count, 1.0 / count)
    for _ in range(iterations):
        updated = (1.0 - damping) / count + damping * (transition.T @ scores)
        if np.allclose(updated, scores, atol=1e-9):
            scores = updated
            break
        scores = updated
    return scores


def how_many(sentence_count, length=None):
    """How many sentences a summary of this length keeps."""
    ratio, fewest, most = LENGTHS.get(
        str(length or DEFAULT_LENGTH).strip().lower(), LENGTHS[DEFAULT_LENGTH])
    if sentence_count <= fewest:
        return sentence_count
    return int(max(fewest, min(most, round(sentence_count * ratio))))


def select(sentences, scores, count, language="it", redundancy=REDUNDANCY):
    """The ``count`` best sentences, without two that say the same thing.

    Returned in the order they were spoken, not by score: a summary is read as
    a narrative, and the meeting happened in that order."""
    if count <= 0 or not sentences:
        return []
    matrix, _ = _vectors(sentences, language)
    chosen = []
    for index in np.argsort(scores)[::-1]:
        index = int(index)
        if len(chosen) >= count:
            break
        if matrix.shape[1] and chosen:
            similar = matrix[chosen] @ matrix[index]
            if similar.size and float(similar.max()) >= redundancy:
                continue
        chosen.append(index)
    return sorted(chosen)


def keywords(sentences, language="it", count=10):
    """The terms the transcript keeps coming back to."""
    matrix, vocabulary = _vectors(sentences, language)
    if not vocabulary:
        return []
    weight = matrix.sum(axis=0)
    order = np.argsort(weight)[::-1][:count]
    names = list(vocabulary)
    return [names[int(index)] for index in order if weight[int(index)] > 0]


def reduce(sentences, target_tokens, language="it"):
    """Cut a transcript down to roughly ``target_tokens``, keeping the best.

    This is the stage that lets a small model summarise an hour of speech on a
    machine that could never read all of it: the selection is arithmetic, so
    it costs nothing, and what reaches the model is the same material in the
    same order — just less of it. An engine with room to spare skips this and
    reads everything."""
    if not sentences or target_tokens <= 0:
        return list(sentences)
    total = sum(estimate_tokens(sentence.text) for sentence in sentences)
    if total <= target_tokens:
        return list(sentences)

    scores = rank(sentences, language)
    budget, kept = target_tokens, []
    for index in np.argsort(scores)[::-1]:
        index = int(index)
        cost = estimate_tokens(sentences[index].text)
        if cost > budget:
            continue
        kept.append(index)
        budget -= cost
        if budget <= 0:
            break
    return [sentences[index] for index in sorted(kept)]


def _bullet(point):
    """One key point as a line of markdown, with its anchor and its speaker."""
    prefix = ""
    if point.start is not None:
        prefix = f"`[{format_clock(point.start)}]` "
    if point.speaker:
        prefix += f"**{point.speaker}** "
    return f"- {prefix}{point.text}".rstrip()


def render(material, sections, engine, when=None, note=None):
    """The finished ``summary.md``.

    Markdown, for the same reason the transcript is a ``.txt``: the entry has
    to stay readable by a person with no program at all, and this is a page
    someone will paste into an email."""
    words = HEADINGS.get(language_of(material.language), HEADINGS["en"])
    when = when or datetime.now()
    lines = [f"# {words['title']}: {material.title}".rstrip(": "), ""]

    stamp = when.astimezone().strftime("%Y-%m-%d %H:%M")
    if material.duration:
        lines.append("_" + words["made_by"].format(
            engine=engine, when=stamp,
            minutes=int(round(material.duration / 60))) + "_")
    else:
        lines.append("_" + words["made_by_untimed"].format(
            engine=engine, when=stamp) + "_")
    if note:
        lines.append("")
        lines.append(f"_{note}_")
    lines.append("")

    if sections.abstract:
        lines += [f"## {words['abstract']}", "", sections.abstract, ""]
    for field, heading in (("points", "points"), ("decisions", "decisions"),
                           ("actions", "actions")):
        entries = getattr(sections, field)
        if entries:
            lines.append(f"## {words[heading]}")
            lines.append("")
            lines += [_bullet(entry) for entry in entries]
            lines.append("")
    if sections.keywords:
        lines += [f"## {words['keywords']}", "",
                  ", ".join(sections.keywords), ""]
    return "\n".join(lines).rstrip() + "\n"


def material_from_entry(entry):
    """Everything an engine needs, read out of a library entry."""
    metadata = entry.metadata
    segments = entry.read_segments()
    sentences = sentences_of(segments)
    if not sentences:
        sentences = sentences_from_text(entry.read_transcript())
    transcription = metadata.get("transcription") or {}
    audio = metadata.get("audio") or {}
    return Material(
        title=metadata.get("title") or entry.id,
        sentences=sentences,
        language=transcription.get("language") or "",
        duration=audio.get("duration_seconds"),
    )


def material_from_text(text, title="", language="", duration=None):
    """The same, for a transcript that is only a file on disk."""
    return Material(title=title, sentences=sentences_from_text(text),
                    language=language, duration=duration)


def summarize(material, settings=None):
    """Summarise ``material`` with whichever engine the settings ask for.

    The engine does the writing; everything around it — choosing one, timing
    the run, laying out the page — happens here, so every engine produces the
    same document."""
    from .summarizers import load, resolve_summarizer

    settings = settings or {}
    if not material.sentences:
        raise SummaryError(t("summary.empty"))

    name = resolve_summarizer(settings.get("summarizer"))
    engine = load(name)
    started = time.time()
    sections, note = engine.summarize(material, settings)
    text = render(material, sections, engine.label(settings), note=note)
    kept = len(sections.points) + len(sections.decisions) + len(sections.actions)
    return Summary(text=text, sections=sections, engine=name,
                   language=language_of(material.language),
                   elapsed=time.time() - started,
                   kept=kept, of=len(material.sentences))
