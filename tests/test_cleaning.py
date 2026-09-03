# -*- coding: utf-8 -*-
"""Test delle funzioni di pulizia (non richiedono modelli ne' GPU)."""
from audio_transcriber.cleaning import (
    clean_segments, clean_text, paragraphs_from_blob, to_paragraphs,
)


def test_clean_text_spaces():
    assert clean_text("ciao   mondo , come  va ?") == "ciao mondo, come va?"


def test_clean_segments_drops_hallucinations():
    segs = [
        {"text": "Grazie a tutti", "start": 0.0, "end": 1.0},
        {"text": "Parliamo del progetto", "start": 1.0, "end": 3.0},
    ]
    out = clean_segments(segs)
    assert len(out) == 1
    assert out[0]["text"] == "Parliamo del progetto"


def test_clean_segments_collapses_duplicates():
    segs = [
        {"text": "stessa frase", "start": 0.0, "end": 1.0},
        {"text": "stessa frase", "start": 1.0, "end": 2.0},
    ]
    assert len(clean_segments(segs)) == 1


def test_to_paragraphs_breaks_on_gap():
    segs = [
        {"text": "Prima frase.", "start": 0.0, "end": 1.0},
        {"text": "Seconda frase.", "start": 5.0, "end": 6.0},  # gap > 1.2s
    ]
    assert to_paragraphs(segs, gap_break=1.2, max_chars=600) == [
        "Prima frase.", "Seconda frase."]


def test_paragraphs_from_blob():
    blob = "Una. Due. Tre. Quattro. Cinque. Sei."
    paras = paragraphs_from_blob(blob, sentences_per_para=5)
    assert len(paras) == 2
