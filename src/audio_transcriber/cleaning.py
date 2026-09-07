"""Tidying the transcript: normalisation, removal of the phrases Whisper
hallucinates over silence, and grouping into paragraphs."""
import re

#: Phrases Whisper typically invents over silence or non-speech, per language.
HALLUCINATION_PHRASES = {
    "it": {
        "grazie", "grazie a tutti", "grazie mille", "grazie a te", "grazie a voi",
        "grazie per l'attenzione", "grazie per la visione", "grazie di cuore",
        "sottotitoli e revisione a cura di qtss",
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


def clean_text(text):
    """Collapse whitespace and remove spaces before punctuation."""
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+([,.;:!?…])", r"\1", text)


def normalise(text):
    """Lowercase, punctuation-free form used for comparisons."""
    return re.sub(r"[^\w\s]", "", (text or "").lower()).strip()


def clean_segments(segments, drop_fillers=True, phrases=None):
    """Drop hallucinated segments and collapse the duplicates that chunk
    overlap produces."""
    catalogue = ALL_HALLUCINATION_PHRASES if phrases is None else phrases
    kept = []
    for segment in segments:
        text = (segment.get("text") or "").strip()
        if not text:
            continue
        key = normalise(text)
        if drop_fillers and key in catalogue:
            continue
        if kept:
            previous = normalise(kept[-1]["text"])
            duplicate = key and (
                key == previous
                or (len(key) > CONTAINMENT_MIN_LENGTH
                    and (key in previous or previous in key)))
            if duplicate:
                # Keep whichever version says more.
                if len(text) > len(kept[-1]["text"]):
                    kept[-1] = {**segment, "text": text}
                continue
        kept.append({**segment, "text": text})
    return kept


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
