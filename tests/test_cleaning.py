"""Text-cleaning tests. No models, no accelerators, no network."""
from audio_transcriber.cleaning import (
    HALLUCINATION_PHRASES,
    clean_segments,
    clean_text,
    normalise,
    paragraphs_from_blob,
    to_paragraphs,
)


def test_clean_text_collapses_spaces_and_punctuation():
    assert clean_text("ciao   mondo , come  va ?") == "ciao mondo, come va?"


def test_normalise_strips_punctuation_and_case():
    assert normalise("Grazie, a tutti!") == "grazie a tutti"


def test_drops_italian_hallucinations():
    segments = [
        {"text": "Grazie a tutti", "start": 0.0, "end": 1.0},
        {"text": "Parliamo del progetto", "start": 1.0, "end": 3.0},
    ]
    kept = clean_segments(segments)
    assert [s["text"] for s in kept] == ["Parliamo del progetto"]


def test_drops_english_hallucinations():
    segments = [
        {"text": "Thanks for watching", "start": 0.0, "end": 1.0},
        {"text": "Let us look at the numbers", "start": 1.0, "end": 3.0},
    ]
    kept = clean_segments(segments)
    assert [s["text"] for s in kept] == ["Let us look at the numbers"]


def test_keep_fillers_keeps_everything():
    segments = [{"text": "Grazie a tutti", "start": 0.0, "end": 1.0}]
    assert len(clean_segments(segments, drop_fillers=False)) == 1


def test_collapses_identical_consecutive_segments():
    segments = [
        {"text": "stessa frase", "start": 0.0, "end": 1.0},
        {"text": "stessa frase", "start": 1.0, "end": 2.0},
    ]
    assert len(clean_segments(segments)) == 1


def test_collapses_contained_long_segments_keeping_the_longer_one():
    long_text = "una frase abbastanza lunga da superare la soglia di contenimento"
    segments = [
        {"text": long_text, "start": 0.0, "end": 2.0},
        {"text": long_text + " e con una coda in piu", "start": 1.5, "end": 3.0},
    ]
    kept = clean_segments(segments)
    assert len(kept) == 1
    assert kept[0]["text"].endswith("coda in piu")


def test_short_similar_segments_are_not_collapsed():
    segments = [
        {"text": "va bene", "start": 0.0, "end": 1.0},
        {"text": "va bene cosi", "start": 1.0, "end": 2.0},
    ]
    assert len(clean_segments(segments)) == 2


def test_paragraph_breaks_on_a_long_pause():
    segments = [
        {"text": "Prima frase.", "start": 0.0, "end": 1.0},
        {"text": "Seconda frase.", "start": 5.0, "end": 6.0},
    ]
    assert to_paragraphs(segments, gap_break=1.2, max_chars=600) == [
        "Prima frase.", "Seconda frase."]


def test_paragraph_keeps_segments_separated_by_a_short_pause_together():
    segments = [
        {"text": "Prima frase.", "start": 0.0, "end": 1.0},
        {"text": "Seconda frase.", "start": 1.1, "end": 2.0},
    ]
    assert to_paragraphs(segments, gap_break=1.2, max_chars=600) == [
        "Prima frase. Seconda frase."]


def test_paragraph_breaks_on_max_chars():
    segments = [{"text": "x" * 30, "start": i, "end": i + 0.5} for i in range(4)]
    assert len(to_paragraphs(segments, gap_break=10, max_chars=50)) == 2


def test_paragraph_breaks_when_timestamps_are_missing():
    segments = [
        {"text": "Prima.", "start": None, "end": None},
        {"text": "Seconda.", "start": None, "end": None},
    ]
    assert to_paragraphs(segments, gap_break=1.2, max_chars=600) == ["Prima.", "Seconda."]


def test_paragraphs_from_blob_groups_sentences():
    blob = "Una. Due. Tre. Quattro. Cinque. Sei."
    assert len(paragraphs_from_blob(blob, sentences_per_para=5)) == 2


def test_hallucination_catalogues_are_lowercase_and_unpunctuated():
    for phrases in HALLUCINATION_PHRASES.values():
        for phrase in phrases:
            assert phrase == phrase.lower()
