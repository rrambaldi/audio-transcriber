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


def test_the_engine_menu_lists_every_backend_and_marks_the_ones_here(monkeypatch):
    """Listed even when absent — it is part of what the program is — but the
    menu says which of them this environment can actually run."""
    from audio_transcriber import backends
    from audio_transcriber.backends import BACKENDS

    monkeypatch.setattr(backends, "is_installed",
                        lambda name: name == backends.OPENVINO)
    choices = options.backend_choices()

    assert [value for _label, value, _ready in choices] == list(BACKENDS)
    assert {value: ready for _label, value, ready in choices} == {
        "auto": True, backends.FASTER_WHISPER: False, backends.OPENVINO: True}


def test_an_engine_this_machine_does_not_have_is_not_preselected(monkeypatch):
    """gui.ini outlives an environment, and a remembered 'faster-whisper' on a
    machine without it turned every job into the same failure."""
    from audio_transcriber import backends

    monkeypatch.setattr(backends, "is_installed",
                        lambda name: name == backends.OPENVINO)
    assert options.usable_backend("faster-whisper") == "auto"
    assert options.usable_backend("openvino") == "openvino"
    assert options.usable_backend("") == "auto"


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
    assert defaults["output"] == "speakers"     # the flag, read as the answer
    assert defaults["vocabulary"] == ["a", "b"]


def test_subtitles_and_diarization_together_are_the_fourth_answer():
    """Configured before the answer existed, in the only way there was."""
    defaults = options.defaults_from({"diarize": True, "subtitles": "srt"})
    assert defaults["output"] == "subtitles_speakers"


def test_a_queue_row_says_how_big_the_recording_is_and_when_it_was_made(tmp_path):
    """A queue of a dozen files named by date is told apart by those two
    before it is told apart by anything else."""
    from audio_transcriber.jobs import Job

    source = tmp_path / "2026-09-15_1830.wav"
    source.write_bytes(b"x" * (3 * 1024 * 1024))
    job = Job(source=str(source), settings={"model": "small"})

    job.audio_duration = 492.5
    details = options.job_details(job)
    assert "3.0 MiB" in details
    assert job.source_created_at[:10] in details        # the date, not the ISO
    assert "8m 12s" in details                          # and how long it is


def test_those_facts_are_on_the_row_whatever_state_it_is_in(tmp_path):
    """A failed row still has to say which recording it was."""
    from audio_transcriber.jobs import FAILED, Job

    source = tmp_path / "2026-09-15_1830.wav"
    source.write_bytes(b"x" * 1024)
    job = Job(source=str(source), settings={"model": "small"})
    job.audio_duration = 61.0
    job.status, job.error = FAILED, "ffmpeg failed to decode the audio"

    details = options.job_details(job)
    assert "1m 01s" in details and "1.0 KiB" in details
    assert "ffmpeg failed" in details                   # and why, after them


def test_a_summary_row_carries_those_facts_too(tmp_path):
    """A summary is about a recording even though it has no file of its own,
    and in a queue of meetings that recording is how it is recognised."""
    from audio_transcriber.jobs import SUMMARY, Job

    job = Job(kind=SUMMARY, title="Comitato", settings={"summary_engine": "auto"})
    job.audio_duration = 4800.0
    job.size_bytes = 439 * 1024 * 1024
    job.source_created_at = "2026-09-15T11:16:04+02:00"

    details = options.job_details(job)
    assert "1h 20m" in details and "439.0 MiB" in details
    assert "2026-09-15 11:16" in details
    assert "summary of the transcript" in details       # and what the row is


def test_a_running_row_carries_a_clock_as_well_as_a_stage():
    """On a step that reports nothing the bar stands still for twenty
    minutes; the row must not look hung while it works."""
    from audio_transcriber.jobs import RUNNING, Job, now

    job = Job(source="a.wav", settings={"model": "small"})
    job.status = RUNNING
    job.stage = "stage.diar_embeddings"
    job.started_at = now()

    text = options.status_text(job)
    assert "who said what" in text                # the step, in words
    assert text.rstrip().endswith("s") or "m" in text    # and a clock


def test_an_unset_option_does_not_override_the_configuration():
    """The queue treats None as "not chosen here", which is how config.toml
    keeps deciding what the window did not."""
    overrides = options.overrides_from({"model": "auto", "language": "",
                                        "speakers": 0})
    assert overrides["model"] == "auto"
    assert overrides["speakers"] is None
    # Not sent at all: the chosen answer says whether anybody asked who was
    # speaking, and resolve_output turns that into the flag.
    assert "diarize" not in overrides


def test_each_answer_says_for_itself_whether_anybody_asked_who_was_speaking():
    """It used to be a tick box that meant nothing next to two of the three
    answers, and made the third two answers wearing one name."""
    from audio_transcriber.config import resolve_output

    for output, diarized in (("text", False), ("speakers", True),
                             ("subtitles", False), ("subtitles_speakers", True)):
        settled = resolve_output(options.output_settings({"output": output}))
        assert settled["diarize"] is diarized, output
        assert options.output_enables(output)["speakers"] is diarized


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


def test_a_running_job_says_which_stage_it_is_in():
    """On an engine that reports no progress of its own the bar stands still
    for the whole transcription: the stage is the difference between waiting
    and wondering."""
    row = options.job_row(make_job(status=jobs.RUNNING, progress=5,
                                   stage="stage.loading_model"))
    assert row["status"] == "running: loading the model"


def test_a_running_job_with_no_stage_yet_just_says_running():
    assert options.job_row(make_job(status=jobs.RUNNING))["status"] == "running"


def test_a_finished_job_does_not_still_show_a_stage():
    """The last stage reached is not what a finished job is doing."""
    row = options.job_row(make_job(status=jobs.DONE, stage="stage.laying_out"))
    assert row["status"] == "done"


def test_a_summary_row_says_it_is_a_summary_and_not_the_recording():
    """A summary is made with the title of the entry it reads and has no
    recording of its own, so five retries of one summary read as five files
    with an unknown name and no length, size or date under them."""
    job = jobs.Job(kind=jobs.SUMMARY, entry_id="2026-09-15_1742_x",
                   title="Untitled", settings={"summary_engine": "auto"})
    row = options.job_row(job)

    assert row["title"] == "Summary: Untitled"
    assert "summary of the transcript" in row["details"]
    # And it does not pretend to be a file: there is nothing to measure.
    assert "MiB" not in row["details"]


def test_a_recording_row_is_still_just_its_name():
    assert options.job_row(make_job(title="verbale"))["title"] == "verbale"


def test_a_failed_job_says_why_on_one_line():
    row = options.job_row(make_job(status=jobs.FAILED,
                                   error="ffmpeg failed\nsecond line"))
    # The state stays a state; the reason goes on the recording's own line,
    # where it has the width of the column instead of a corner of the status
    # cell.
    assert row["status"] == "failed"
    # One line of it, after the facts about the recording, which the row still
    # has to carry: a failed job is still the file it was.
    assert row["details"].endswith("ffmpeg failed")
    assert "second line" not in row["details"]
    assert row["failed"] is True


def test_the_summary_distinguishes_working_from_finished():
    assert "Nothing" in options.queue_summary([])
    busy = options.queue_summary([make_job(status=jobs.RUNNING), make_job()])
    assert "1 running" in busy and "1 waiting" in busy
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


# --- what the recording menus say -----------------------------------------

def test_a_loopback_is_marked_as_one_in_the_menu():
    """"Speakers" among the recording sources is otherwise a contradiction."""
    from audio_fakes import audio_source
    from audio_transcriber.recording import LOOPBACK

    speakers = audio_source(key="wasapi:loopback:Speakers", kind=LOOPBACK,
                            label="Altoparlanti")
    assert options.source_label(speakers) == "[loopback] Altoparlanti"
    assert options.source_label(audio_source(label="Mic")) == "Mic"


def test_the_second_source_is_labelled_with_its_audio_system():
    """The "together with" menu mixes audio systems, and the same device shows
    up under each of them: without the suffix it would list twins."""
    from audio_fakes import audio_source

    mic = audio_source(host_api="MME", label="Mic")
    assert options.source_label(mic, with_host_api=True) == "Mic - MME"


def test_the_second_source_menu_offers_the_loopbacks_first():
    """They are the reason it exists: a call has the others in the speakers."""
    from audio_fakes import audio_source
    from audio_transcriber.recording import LOOPBACK

    mic = audio_source(key="portaudio:0:Mic")
    other = audio_source(key="portaudio:1:Line")
    speakers = audio_source(key="wasapi:loopback:Speakers", kind=LOOPBACK)
    candidates = options.mix_candidates([mic, other, speakers], mic.key)
    assert [source.key for source in candidates] == [speakers.key, other.key]


def test_a_source_is_never_offered_to_be_mixed_with_itself():
    """It would only make the same microphone twice as loud."""
    from audio_fakes import audio_source

    mic = audio_source()
    assert options.mix_candidates([mic], mic.key) == []


def test_the_level_meter_is_read_in_decibels_not_in_amplitude():
    """A linear bar would leave ordinary speech - a tenth of full scale -
    against the left edge, making a working microphone look broken."""
    assert options.level_percent(1.0) == 100
    assert options.level_percent(0.1) == 67          # -20 dBFS, normal speech
    assert options.level_percent(0.01) == 33         # -40 dBFS, a whisper
    assert options.level_percent(0.0) == 0
    assert options.level_percent(None) == 0
    assert options.level_percent(0.0001) == 0        # under the -60 dB floor
    assert options.level_percent(2.0) == 100         # never past the end


def test_an_audio_system_says_how_many_sources_it_has():
    from audio_fakes import audio_source
    from audio_transcriber.recording import LOOPBACK

    summary = options.host_api_summary([audio_source(),
                                        audio_source(key="wasapi:loopback:S",
                                                     kind=LOOPBACK)])
    assert "2" in summary and "1" in summary


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
    monkeypatch.setattr(gui, "run", lambda settings, lang=None: seen.update(
        settings=settings, lang=lang))
    cli.main(["gui"])
    assert seen["settings"]["model"] == "auto"
    assert seen["lang"] is None
    # A --lang typed here is handed on, to win over the window's own menu.
    cli.main(["gui", "--lang", "de"])
    assert seen["lang"] == "de"
    from audio_transcriber import i18n
    i18n.set_language("en")


# --- summaries ------------------------------------------------------------

def test_the_summary_menus_say_what_each_choice_does():
    """"openvino" tells nobody whether it is worth waiting for."""
    engines = options.summary_engine_choices()
    assert engines, "the extractive engine is always available"
    names = [name for name, _label in engines]
    assert "extractive" in names
    for _name, label in engines:
        assert label and not label.startswith("gui.")

    lengths = options.summary_length_choices()
    assert [name for name, _ in lengths] == ["short", "medium", "long"]
    assert options.summary_default_length() == "medium"


def test_the_model_menu_groups_every_model_by_where_it_runs():
    """Automatic first, saying what it would pick now; then each engine's
    models under GPU or CPU, each saying whether it fits in what is free; the
    engine with no model last."""
    where = {"openvino": "GPU", "llamacpp": "CPU", "extractive": None}
    menu = options.summary_model_menu({}, ["openvino", "llamacpp", "extractive"],
                                      9.0, 31.5, lambda engine, _s: where[engine])
    headings = [heading for heading, _ in menu]
    assert headings[0] is None and len(menu[0][1]) == 1
    auto_value, auto_label = menu[0][1][0]
    assert auto_value == "\tauto" and "MiniCPM5-2B" in auto_label  # OpenVINO first
    assert headings[1:] == ["GPU \u00b7 OpenVINO", "CPU \u00b7 llama.cpp",
                            i18n.t("gui.summary_model_group_none")]

    gpu = dict(menu[1][1])
    assert "openvino\topenbmb/MiniCPM5-2B" in gpu
    assert not any("Spark" in label for label in gpu.values())
    cpu = dict(menu[2][1])
    spark = cpu["llamacpp\tXHToken/Spark-X2.5-4B"]
    assert spark.startswith("Spark-X2.5-4B") and "5.0 GiB" in spark
    assert spark == i18n.t("gui.summary_model_fits", model="Spark-X2.5-4B",
                           need="5.0")
    assert menu[3][1] == [("extractive\t", i18n.t("gui.summary_model_extractive"))]

    busy = options.summary_model_menu({}, ["llamacpp"], 3.0, 31.5,
                                      lambda engine, _s: "GPU")
    spark = dict(busy[1][1])["llamacpp\tXHToken/Spark-X2.5-4B"]
    assert spark == i18n.t("gui.summary_model_too_big", model="Spark-X2.5-4B",
                           need="5.0", usable="1.0")


def test_the_sections_menu_opens_on_the_page_the_recording_decides():
    """First entry the one that asks for nothing, last the box underneath,
    and the bundled templates of the spoken language in between."""
    choices = options.summary_template_choices(language="it")
    names = [name for name, _label in choices]
    assert names[0] == ""
    assert names[-1] == options.SUMMARY_OWN_TEMPLATE
    assert "minutes-it" in names
    assert "minutes-en" not in names
    for _name, label in choices:
        assert label and not label.startswith("gui.")


def test_a_templates_directory_that_cannot_be_read_is_no_templates(tmp_path):
    """The window has to open on a machine where nothing has been set up."""
    choices = options.summary_template_choices(
        {"summary_templates_dir": str(tmp_path / "nowhere")}, "it")
    assert [name for name, _ in choices][0] == ""
    assert len(choices) >= 2


def test_an_entry_with_no_summary_says_so_rather_than_showing_nothing(tmp_path):
    from audio_transcriber.library import Library

    entry = Library(str(tmp_path / "library")).create(title="Riunione")
    text, note = options.summary_state(entry)
    assert text == ""
    assert "No summary yet" in note


def test_a_summary_says_which_engine_wrote_it_and_when(tmp_path):
    """Otherwise it gets quoted in a meeting without anybody knowing whether a
    model or a sentence-picker produced it."""
    from audio_transcriber.library import Library

    entry = Library(str(tmp_path / "library")).create(title="Riunione")
    entry.write_summary("# Riassunto\n\nTesto.\n")
    entry.update(summary={"engine": "extractive",
                          "created_at": "2026-09-09T18:40:00+02:00"})

    text, note = options.summary_state(entry)
    assert "Testo." in text
    assert "extractive" in note
    assert "2026-09-09 18:40" in note
