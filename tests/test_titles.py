"""Naming a recording after what was said in it.

A library of ``2026-09-15_1830`` is a library nobody can look through, and the
date is already in the row. Nothing here loads a model: the transcript is
ranked the way the extractive summary ranks it, and the strongest sentence is
trimmed into a label.
"""
import pytest

from audio_transcriber import titles

MEETING_IT = ("Allora, volevo parlarvi del budget del terzo trimestre e delle "
              "assunzioni previste. Il punto principale e che il budget del terzo "
              "trimestre non copre le assunzioni. Poi vediamo la questione delle ferie.")
MEETING_EN = ("So, we need to talk about the third quarter budget and the hiring "
              "plan we agreed last week. The budget does not cover the hires.")


def test_a_title_comes_out_of_what_was_said():
    title = titles.suggest(text=MEETING_IT, language="it")
    assert "budget" in title.lower()
    assert len(title.split()) <= titles.MAX_WORDS
    assert title[0].isupper()


def test_the_opening_filler_is_not_the_title():
    """Every spoken sentence starts with one, and a title that starts with
    "allora" is a title that starts with noise."""
    assert not titles.suggest(text=MEETING_IT, language="it").lower().startswith("allora")
    assert not titles.suggest(text=MEETING_EN, language="en").lower().startswith("so,")


def test_a_long_sentence_is_cut_where_it_breaks_cleanly():
    """The half of a spoken sentence that says something is rarely the half
    it starts with, and a title must not end mid-phrase."""
    title = titles.shorten("Il punto principale e che il budget del terzo trimestre "
                           "non copre le assunzioni previste", "it")
    assert title.endswith("assunzioni") or title.endswith("assunzioni previste")
    assert "punto principale" not in title


def test_a_title_never_ends_on_a_preposition_or_an_article():
    for sentence, language in ((
            "Parliamo del budget e delle assunzioni previste per il", "it"),
            ("We talked about the budget and the hiring plan for the", "en")):
        title = titles.shorten(sentence, language)
        assert title.lower().split()[-1] not in ("per", "il", "for", "the")


def test_a_summary_beats_the_transcript_when_there_is_one():
    """A sentence written about the whole recording says more than the best
    sentence taken out of it."""
    written = ("# Riassunto\n\n_extractive_\n\n## In breve\n\n"
               "La riunione decide il budget del terzo trimestre.")
    assert "riunione" in titles.suggest(text=MEETING_IT, summary_text=written,
                                        language="it").lower()


def test_headings_and_caveats_are_not_the_summary(language="it"):
    """The first line of a summary is "# Riassunto", and the second is the
    italic line saying which engine wrote it."""
    written = "# Riassunto\n\n_extractive (TextRank), 2026-09-15_\n\n## In breve\n\nIl budget non copre le assunzioni."
    title = titles.suggest(summary_text=written, language=language)
    assert "riassunto" not in title.lower() and "textrank" not in title.lower()
    assert "budget" in title.lower()


def test_a_recording_with_nothing_in_it_gets_no_title():
    """Better the file name than a title made up out of one word of noise."""
    assert titles.suggest(text="", language="it") == ""
    assert titles.suggest(text=None, segments=[], language="it") == ""


def test_segments_are_used_when_there_are_some():
    segments = [{"start": 0.0, "end": 4.0,
                 "text": "Parliamo della certificazione ISO 27001 e dell audit."},
                {"start": 4.0, "end": 8.0,
                 "text": "La certificazione scade a novembre."}]
    title = titles.suggest(segments=segments, language="it")
    assert "certificazione" in title.lower()


@pytest.mark.parametrize("language", ["it", "en", "xx"])
def test_any_language_gets_a_title_or_an_honest_nothing(language):
    """An unknown language falls back to the English word lists rather than
    to a crash, like everything else that is keyed by language here."""
    title = titles.suggest(text=MEETING_EN, language=language)
    assert isinstance(title, str)
