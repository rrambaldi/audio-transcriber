"""The desktop interface, minus the widgets.

Every decision the window makes that is worth checking lives in
``gui.options``, which imports no Qt, so these tests run on the machines this
project's suite has to run on: a server with no display and no PySide6. The
widgets themselves are exercised in ``test_gui_window.py``, which skips when Qt
is absent."""
import pytest

from audio_transcriber import gui, i18n, jobs, paths
from audio_transcriber.gui import options


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "home"))
    monkeypatch.delenv("AUDIO_TRANSCRIBER_LANG", raising=False)
    i18n.set_language("en")
    yield
    i18n._current = None


# --- the menus ------------------------------------------------------------

def test_the_model_menu_says_what_auto_resolves_to():
    """'auto' on its own tells the user nothing about their machine."""
    choices = options.model_choices(recommended="small")
    assert choices[0] == ("auto (small on this machine)", "auto")
    assert ("small", "small") in choices


def test_the_language_menu_starts_with_detect_it():
    labels = [label for label, _ in options.language_choices()]
    values = [value for _, value in options.language_choices()]
    assert values[0] == ""
    assert labels[0] == "detect it"
    assert "Italiano (it)" in labels


def test_the_engine_menu_offers_every_backend():
    from audio_transcriber.backends import BACKENDS

    assert [value for _, value in options.backend_choices()] == list(BACKENDS)


def test_the_installed_keyword_sets_are_offered_by_name():
    items = options.vocabulary_items()
    names = [item["name"] for item in items]
    assert "iso27001-it" in names
    bundled = next(item for item in items if item["name"] == "iso27001-it")
    assert bundled["terms"] > 0 and bundled["source"] == "bundled"
    assert bundled["name"] in bundled["label"]


def test_a_hand_written_set_shadows_a_bundled_one(tmp_path, monkeypatch):
    directory = tmp_path / "vocabularies"
    directory.mkdir()
    (directory / "iso27001-it.txt").write_text("# title: Mine\nalpha, beta\n",
                                               encoding="utf-8")
    monkeypatch.setenv(paths.ENV_VOCAB_DIR, str(directory))
    mine = next(item for item in options.vocabulary_items()
                if item["name"] == "iso27001-it")
    assert mine["title"] == "Mine" and mine["source"] == "user"


# --- what the widgets start from, and what they hand back -----------------

def test_the_configuration_decides_what_is_preselected():
    defaults = options.defaults_from({"model": "medium", "language": "",
                                      "diarize": True, "speakers": 3,
                                      "vocabulary": "a, b"})
    assert defaults["model"] == "medium"
    assert defaults["language"] == ""
    assert defaults["diarize"] is True
    assert defaults["vocabulary"] == ["a", "b"]


def test_an_unset_option_does_not_override_the_configuration():
    """The queue treats None as "not chosen here", which is how config.toml
    keeps deciding what the window did not."""
    overrides = options.overrides_from({"model": "auto", "language": "",
                                        "diarize": False, "speakers": 0})
    assert overrides["model"] == "auto"
    assert overrides["diarize"] is None
    assert overrides["speakers"] is None


def test_detecting_the_language_is_a_real_choice_not_an_absent_one():
    assert options.overrides_from({"language": ""})["language"] == ""


def test_an_oversized_vocabulary_is_refused_with_a_reason():
    from audio_transcriber.vocabularies import MAX_CUSTOM_VOCABULARY

    assert options.custom_vocabulary_problem("alpha, beta") is None
    problem = options.custom_vocabulary_problem("x" * (MAX_CUSTOM_VOCABULARY + 1))
    assert str(MAX_CUSTOM_VOCABULARY) in problem


def test_the_file_dialog_offers_media_and_then_everything():
    assert "*.mp3" in options.media_filter()
    assert options.media_filter().endswith("(*)")


# --- the queue table ------------------------------------------------------

def make_job(**fields):
    job = jobs.Job("/tmp/meeting.wav", settings={"model": "small"})
    for name, value in fields.items():
        setattr(job, name, value)
    return job


def test_a_queued_job_shows_no_numbers_it_does_not_have_yet():
    row = options.job_row(make_job())
    assert row["status"] == "queued"
    assert row["progress"] == 0 and row["words"] == "-" and row["duration"] == "-"
    assert row["finished"] is False


def test_a_finished_job_carries_its_entry_and_its_figures():
    row = options.job_row(make_job(status=jobs.DONE, progress=100, words=1200,
                                   audio_duration=3600, entry_id="2026-09-04_1200_x"))
    assert row["status"] == "done" and row["words"] == "1200"
    assert row["duration"] == "1h 00m"
    assert row["entry_id"] == "2026-09-04_1200_x" and row["finished"] is True


def test_a_failed_job_says_why_on_one_line():
    row = options.job_row(make_job(status=jobs.FAILED,
                                   error="ffmpeg failed\nsecond line"))
    assert row["status"] == "failed: ffmpeg failed"
    assert row["failed"] is True


def test_the_summary_distinguishes_working_from_finished():
    assert "Nothing" in options.queue_summary([])
    busy = options.queue_summary([make_job(status=jobs.RUNNING), make_job()])
    assert "1 running, 1 waiting" in busy
    idle = options.queue_summary([make_job(status=jobs.DONE),
                                  make_job(status=jobs.FAILED)])
    assert "1 transcribed, 1 failed" in idle


# --- the library table and the reading pane -------------------------------

@pytest.fixture
def library(tmp_path):
    from audio_transcriber.library import Library

    return Library(str(tmp_path / "library"))


def make_entry(library, title="Board meeting", **transcription):
    entry = library.create(title=title)
    entry.write_transcript("Hello everyone.\n\nSecond paragraph.\n", [])
    entry.update(audio={"duration_seconds": 3600.0},
                 stats={"words": 4},
                 transcription={"model": "small", **transcription})
    return entry


def test_an_entry_becomes_one_readable_row(library):
    row = options.entry_row(make_entry(library))
    assert row["title"] == "Board meeting"
    assert row["duration"] == "1h 00m" and row["words"] == "4"
    assert row["model"] == "small"
    assert row["notes"] == ""          # the entry's notes.md holds only a title


def test_written_notes_are_marked_as_such(library):
    entry = make_entry(library)
    entry.write_notes("# Board meeting\n\nDecisions: ship it.\n")
    assert options.entry_row(entry)["notes"] == "yes"


def test_a_broken_entry_is_skipped_instead_of_breaking_the_list(library):
    """The library is meant to outlive this program: one unreadable folder
    must not take the whole list with it."""
    import os

    from audio_transcriber.library import Entry

    good = make_entry(library, title="Fine")
    broken = make_entry(library, title="Broken")
    with open(broken.metadata_path, "w", encoding="utf-8") as handle:
        handle.write("{ not json")
    rows = options.entry_rows([Entry(broken.path), Entry(good.path)])
    assert [row["title"] for row in rows] == ["Fine"]
    assert os.path.isdir(broken.path)   # skipped, not touched


def test_the_details_report_how_the_transcription_was_made(library):
    entry = make_entry(library, backend="faster-whisper", device="CPU",
                       language="it", elapsed_seconds=5400,
                       vocabulary=["iso27001-it"])
    details = dict(options.entry_details(entry))
    assert details["Model"] == "small / faster-whisper / CPU"
    assert details["Transcribed in"] == "1h 30m"
    assert details["Keyword sets"] == "iso27001-it"
    assert details["Folder"] == entry.path


def test_a_diarized_entry_reports_its_speakers(library):
    entry = make_entry(library, diarized=True, speakers=3)
    assert dict(options.entry_details(entry))["Speakers"] == "3"


def test_segments_become_blocks_with_a_clickable_timestamp():
    blocks = options.transcript_blocks(
        [{"start": 0.0, "text": "Hello."},
         {"start": 61.5, "text": "Later.", "speaker": "SPEAKER_01"},
         {"start": 90.0, "text": "   "}])
    assert blocks[0] == (0.0, "0:00", "Hello.")
    assert blocks[1] == (61.5, "1:01", "SPEAKER_01: Later.")
    assert len(blocks) == 2            # the empty segment is dropped


def test_without_segments_the_paragraphs_are_shown_untimed():
    blocks = options.transcript_blocks([], "First one.\n\nSecond one.\n")
    assert [block[0] for block in blocks] == [None, None]
    assert blocks[1][2] == "Second one."


def test_the_search_summary_says_what_was_searched():
    assert options.search_summary("", 3) == "3 recordings."
    assert "'risk'" in options.search_summary(" risk ", 2)


# --- names, drops and recordings ------------------------------------------

def test_a_recording_is_named_after_the_moment_it_was_made():
    from datetime import datetime

    when = datetime(2026, 9, 4, 15, 30, 5)
    assert options.recording_stem(when) == "2026-09-04_153005-recording"
    assert options.recording_title(when) == "Recording 2026-09-04 15:30"


def test_a_dropped_folder_or_a_repeat_never_reaches_the_queue(tmp_path):
    first = tmp_path / "a.wav"
    first.write_bytes(b"x")
    folder = tmp_path / "sub"
    folder.mkdir()
    kept = options.playable_files([str(first), str(first), str(folder),
                                   str(tmp_path / "missing.wav"), ""])
    assert kept == [str(first)]


def test_a_title_is_the_file_name_without_its_extension():
    assert options.title_from_path("/tmp/Weekly meeting.mp4") == "Weekly meeting"


# --- starting the interface at all ----------------------------------------

def test_without_qt_the_gui_explains_how_to_install_it(monkeypatch, capsys):
    from audio_transcriber import hardware

    monkeypatch.setattr(hardware, "module_available", lambda name: False)
    with pytest.raises(SystemExit) as raised:
        gui.run({})
    assert "PySide6" in str(raised.value)


def test_the_cli_has_a_gui_command(monkeypatch):
    """``audio-transcriber gui`` reaches the window with the resolved settings."""
    from audio_transcriber import cli

    seen = {}
    monkeypatch.setattr(gui, "run", lambda settings: seen.setdefault("settings", settings))
    cli.main(["gui"])
    assert seen["settings"]["model"] == "auto"
