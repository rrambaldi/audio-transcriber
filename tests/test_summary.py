"""Summaries: sentences, ranking, selection, the page, and the command.

Everything here runs with no model, no network and no accelerator, which is
the whole point of the extractive engine: the machinery around the engines can
be tested on the same machine that could never run one.
"""
import os

import pytest

from audio_transcriber import cli, paths, summary
from audio_transcriber.library import Library
from audio_transcriber.summarizers import (
    CHOICES,
    EXTRACTIVE,
    available,
    load,
    resolve_summarizer,
)


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "home"))
    monkeypatch.delenv("AUDIO_TRANSCRIBER_LANG", raising=False)


#: A small meeting that has a subject: the budget of the ISO project comes up
#: again and again, and the weather does not. A summary that cannot tell those
#: apart is not doing anything.
SEGMENTS = [
    {"start": 0.0, "end": 8.0, "speaker": "SPEAKER_00",
     "text": "Buongiorno a tutti. Oggi parliamo del budget del progetto ISO."},
    {"start": 8.0, "end": 16.0, "speaker": "SPEAKER_01",
     "text": "Il budget del progetto ISO e' il punto piu' importante di oggi."},
    {"start": 16.0, "end": 24.0, "speaker": "SPEAKER_00",
     "text": "Ha piovuto tutta la notte."},
    {"start": 24.0, "end": 40.0, "speaker": "SPEAKER_01",
     "text": "Sul budget del progetto ISO dobbiamo decidere entro venerdi'."},
    {"start": 40.0, "end": 55.0, "speaker": "SPEAKER_00",
     "text": "La decisione sul budget spetta al comitato del progetto ISO."},
    {"start": 55.0, "end": 70.0, "speaker": "SPEAKER_01",
     "text": "Vi mando il documento con il budget aggiornato."},
]


def transcript_text():
    return " ".join(segment["text"] for segment in SEGMENTS)


# --- sentences ------------------------------------------------------------

def test_a_segment_is_split_into_its_sentences():
    sentences = summary.sentences_of(SEGMENTS[:1])
    assert [s.text for s in sentences] == [
        "Buongiorno a tutti.", "Oggi parliamo del budget del progetto ISO."]


def test_every_sentence_keeps_where_and_by_whom_it_was_said():
    first, second = summary.sentences_of(SEGMENTS[:1])
    assert first.start == second.start == 0.0
    assert first.speaker == second.speaker == "SPEAKER_00"


def test_an_abbreviation_does_not_end_a_sentence():
    assert summary.split_sentences("Ne parlo con l'ing. Rossi domani.") == [
        "Ne parlo con l'ing. Rossi domani."]


def test_a_transcript_with_no_segments_still_yields_sentences():
    sentences = summary.sentences_from_text(transcript_text())
    assert len(sentences) == 7
    assert all(sentence.start is None for sentence in sentences)


def test_empty_input_yields_no_sentences():
    assert summary.split_sentences("") == []
    assert summary.sentences_of([]) == []
    assert summary.sentences_of([{"text": "   "}]) == []


# --- ranking and selection ------------------------------------------------

def test_the_recurring_subject_outranks_the_aside():
    sentences = summary.sentences_of(SEGMENTS)
    scores = summary.rank(sentences, "it")
    weather = next(index for index, sentence in enumerate(sentences)
                   if "piovuto" in sentence.text)
    assert scores[weather] == min(scores)


def test_ranking_survives_degenerate_input():
    assert len(summary.rank([], "it")) == 0
    assert len(summary.rank(summary.sentences_from_text("Una frase."), "it")) == 1
    # Sentences sharing no content word at all: nothing to walk between, but
    # the walk must still terminate and score them.
    isolated = summary.sentences_from_text("Alfa beta. Gamma delta.")
    assert len(summary.rank(isolated, "it")) == 2


def test_selection_comes_back_in_the_order_it_was_spoken():
    sentences = summary.sentences_of(SEGMENTS)
    scores = summary.rank(sentences, "it")
    chosen = summary.select(sentences, scores, 4, "it")
    assert chosen == sorted(chosen)


def test_two_sentences_that_say_the_same_thing_are_not_both_kept():
    doubled = summary.sentences_from_text(
        "Il budget del progetto ISO va deciso entro venerdi. "
        "Il budget del progetto ISO va deciso entro venerdi. "
        "Il catering della mensa cambia fornitore a marzo.")
    scores = summary.rank(doubled, "it")
    chosen = summary.select(doubled, scores, 2, "it")
    assert len(chosen) == 2
    assert {doubled[index].text for index in chosen} == {
        "Il budget del progetto ISO va deciso entro venerdi.",
        "Il catering della mensa cambia fornitore a marzo."}


def test_how_many_respects_the_floor_and_the_ceiling():
    assert summary.how_many(2, "medium") == 2          # shorter than the floor
    assert summary.how_many(40, "short") == 3          # the floor
    assert summary.how_many(1000, "short") == 8        # the ceiling
    assert summary.how_many(1000, "long") == 30
    assert summary.how_many(100, "medium") == 10       # the ratio
    assert summary.how_many(100, None) == summary.how_many(100, "medium")
    assert summary.how_many(100, "nonsense") == summary.how_many(100, "medium")


def test_an_elided_article_is_not_part_of_the_word():
    """"l'audit" and "audit" are the same term, and must rank as one."""
    sentences = summary.sentences_from_text(
        "L'audit di marzo e' confermato. Dell'audit parliamo dopo. "
        "L'audit costa quarantamila euro.")
    found = summary.keywords(sentences, "it", 5)
    assert "audit" in found
    assert not [word for word in found if "'" in word]


def test_keywords_are_what_the_transcript_keeps_returning_to():
    found = summary.keywords(summary.sentences_of(SEGMENTS), "it", 5)
    assert "budget" in found and "progetto" in found
    assert "piovuto" not in found


# --- the reduction stage --------------------------------------------------

def test_a_short_transcript_is_not_reduced_at_all():
    sentences = summary.sentences_of(SEGMENTS)
    assert summary.reduce(sentences, 10_000, "it") == sentences


def test_reduction_cuts_to_the_budget_and_keeps_the_order():
    sentences = summary.sentences_of(SEGMENTS)
    kept = summary.reduce(sentences, 30, "it")
    assert 0 < len(kept) < len(sentences)
    assert sum(summary.estimate_tokens(s.text) for s in kept) <= 30
    assert [s.text for s in kept] == [s.text for s in sentences
                                      if s.text in {k.text for k in kept}]


def test_reduction_of_nothing_is_nothing():
    assert summary.reduce([], 100, "it") == []


# --- the page -------------------------------------------------------------

def test_the_page_is_written_in_the_language_that_was_spoken():
    material = summary.Material(title="Riunione", sentences=(), language="it")
    page = summary.render(material, summary.Sections(abstract="Testo."),
                          "extractive (TextRank)")
    assert page.startswith("# Riassunto: Riunione")
    assert "## In breve" in page

    english = summary.Material(title="Standup", sentences=(), language="en")
    page = summary.render(english, summary.Sections(abstract="Text."), "engine")
    assert page.startswith("# Summary: Standup")
    assert "## In brief" in page


def test_an_unknown_spoken_language_falls_back_to_english_headings():
    material = summary.Material(title="X", sentences=(), language="sv")
    assert "## In brief" in summary.render(
        material, summary.Sections(abstract="Text."), "engine")


def test_headings_with_nothing_under_them_are_left_out():
    material = summary.Material(title="X", sentences=(), language="it")
    page = summary.render(material, summary.Sections(abstract="Testo."), "engine")
    assert "## Punti chiave" not in page
    assert "## Decisioni" not in page


def test_a_point_carries_its_minute_and_its_speaker():
    material = summary.Material(title="X", sentences=(), language="it")
    page = summary.render(material, summary.Sections(
        abstract="Testo.",
        points=[summary.Point(75.0, "SPEAKER_01", "Decidiamo venerdi.")]), "engine")
    assert "- `[1:15]` **SPEAKER_01** Decidiamo venerdi." in page


def test_the_page_says_which_engine_made_it_and_how_long_the_recording_was():
    material = summary.Material(title="X", sentences=(), language="it",
                                duration=3600)
    page = summary.render(material, summary.Sections(abstract="Testo."),
                          "extractive (TextRank)")
    assert "extractive (TextRank)" in page
    assert "60 minuti" in page


# --- choosing an engine ---------------------------------------------------

def test_auto_picks_the_only_engine_there_is_for_now():
    assert resolve_summarizer("auto") == EXTRACTIVE
    assert resolve_summarizer(None) == EXTRACTIVE
    assert available() == [EXTRACTIVE]
    assert "auto" in CHOICES and EXTRACTIVE in CHOICES


def test_an_engine_can_be_asked_for_by_a_tolerated_spelling():
    assert resolve_summarizer("TextRank") == EXTRACTIVE


def test_an_unknown_engine_is_refused_by_name():
    with pytest.raises(summary.SummaryError) as raised:
        resolve_summarizer("gpt-9")
    assert "gpt-9" in str(raised.value)
    with pytest.raises(summary.SummaryError):
        load("gpt-9")


# --- end to end -----------------------------------------------------------

def test_summarising_a_transcript_produces_a_readable_page():
    material = summary.Material(title="Riunione ISO",
                                sentences=summary.sentences_of(SEGMENTS),
                                language="it", duration=70)
    result = summary.summarize(material, {"summary_length": "short"})

    assert result.engine == EXTRACTIVE
    assert result.of == len(material.sentences)
    assert 0 < result.kept < result.of
    assert "budget" in result.text.lower()
    assert "# Riassunto: Riunione ISO" in result.text
    # The caveat is not optional: these are somebody's own words, selected.
    assert "frasi prese dalla trascrizione" in result.text


def test_the_abstract_and_the_points_never_repeat_each_other():
    material = summary.Material(title="X", sentences=summary.sentences_of(SEGMENTS),
                                language="it")
    result = summary.summarize(material, {"summary_length": "long"})
    for point in result.sections.points:
        assert point.text not in result.sections.abstract


def test_summarising_nothing_is_an_error_with_a_sentence_in_it():
    empty = summary.Material(title="X", sentences=(), language="it")
    with pytest.raises(summary.SummaryError) as raised:
        summary.summarize(empty)
    assert str(raised.value)


# --- the library round trip -----------------------------------------------

@pytest.fixture
def entry(tmp_path):
    library = Library(str(tmp_path / "library"))
    made = library.create(title="Riunione ISO")
    made.write_transcript(transcript_text(), segments=SEGMENTS)
    made.update(transcription={"language": "it"}, audio={"duration_seconds": 70})
    return made


def test_material_is_read_out_of_an_entry_with_its_timestamps(entry):
    material = summary.material_from_entry(entry)
    assert material.title == "Riunione ISO"
    assert material.language == "it"
    assert material.duration == 70
    assert material.sentences[0].start == 0.0


def test_an_entry_without_segments_falls_back_to_the_plain_transcript(entry):
    os.remove(entry.segments_path)
    material = summary.material_from_entry(entry)
    assert material.sentences and material.sentences[0].start is None


def test_a_summary_is_stored_beside_the_transcript(entry):
    assert not entry.has_summary()
    entry.write_summary("# Riassunto\n\nTesto.")
    assert entry.has_summary()
    assert entry.read_summary().endswith("\n")
    assert os.path.basename(entry.summary_path) == "summary.md"


# --- the command ----------------------------------------------------------

def test_the_command_writes_into_the_entry_and_records_what_it_did(entry, capsys):
    root = os.path.dirname(entry.path)
    assert cli.main(["summarize", entry.id, "--library-dir", root]) is None

    assert entry.has_summary()
    stored = entry.read_metadata()["summary"]
    assert stored["engine"] == "extractive"
    assert stored["sentences_total"] == len(summary.sentences_of(SEGMENTS))
    assert entry.summary_path in capsys.readouterr().out


def test_the_command_can_summarise_a_bare_text_file(tmp_path, capsys):
    source = tmp_path / "verbale.txt"
    source.write_text(transcript_text(), encoding="utf-8")
    cli.main(["summarize", str(source), "--length", "short"])

    written = tmp_path / "verbale.summary.md"
    assert written.exists()
    assert "# Riassunto" in written.read_text(encoding="utf-8")
    assert str(written) in capsys.readouterr().out


def test_printing_a_summary_writes_no_file(tmp_path, capsys):
    source = tmp_path / "verbale.txt"
    source.write_text(transcript_text(), encoding="utf-8")
    cli.main(["summarize", str(source), "--print"])

    assert not (tmp_path / "verbale.summary.md").exists()
    assert "# Riassunto" in capsys.readouterr().out


def test_an_out_path_wins_over_the_entry(entry, tmp_path, capsys):
    target = tmp_path / "altrove" / "riassunto.md"
    cli.main(["summarize", entry.id, "--library-dir", os.path.dirname(entry.path),
              "--out", str(target)])
    assert target.exists()
    assert not entry.has_summary()


def test_an_unknown_entry_stops_the_command(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(["summarize", "nessuna-voce",
                  "--library-dir", str(tmp_path / "library")])
