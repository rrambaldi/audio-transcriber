"""The four questions about a transcription, wherever they are asked.

They used to live down the left of the Transcribe tab, where they were
answered for a recording that did not exist yet and answered once for all of
them. They are now one widget, put to one recording at a time in the dialog
its Transcribe button opens — so this is where the answers, what they imply
about each other, and what they turn into for the queue are checked.
"""
import os

import pytest

pytest.importorskip("PySide6", reason="the [gui] extra is not installed")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
except ImportError as exc:      # pragma: no cover - depends on the machine
    pytest.skip(f"PySide6 cannot be loaded here: {exc}", allow_module_level=True)

from audio_transcriber import i18n, paths  # noqa: E402
from audio_transcriber.config import resolve_output  # noqa: E402
from audio_transcriber.gui import options  # noqa: E402
from audio_transcriber.gui.job_dialog import JobDialog  # noqa: E402
from audio_transcriber.gui.options_form import OptionsForm  # noqa: E402
from audio_transcriber.vocabularies import MAX_CUSTOM_VOCABULARY  # noqa: E402

SETTINGS = {"model": "auto", "language": "it", "backend": "auto",
            "device": "auto", "vocabulary": None, "vocab_dir": None,
            "diarize": False, "speakers": None, "diar_model": None}


@pytest.fixture(scope="session")
def application():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "home"))
    monkeypatch.delenv("AUDIO_TRANSCRIBER_LANG", raising=False)
    i18n.set_language("en")
    yield
    i18n._current = None


@pytest.fixture
def form(application):
    return OptionsForm(SETTINGS)


def settings_of(form):
    """What the queue would make of these answers."""
    chosen = form.choices()
    overrides = options.overrides_from(chosen)
    overrides.update(options.subtitle_settings(chosen))
    overrides.update(options.output_settings(chosen))
    merged = {k: v for k, v in overrides.items() if v is not None}
    return resolve_output(merged)


# --- what is asked ---------------------------------------------------------

def test_it_asks_the_four_questions_and_no_more(form):
    assert [section.button.text().split(" — ")[0] for section in form.sections] == [
        "What do you want out of it?", "How to transcribe it",
        "Subtitles", "Keyword sets"]
    assert set(form.output_buttons) == {"text", "speakers", "subtitles"}


def test_the_installed_keyword_sets_are_offered(form):
    names = [form.vocabularies.item(row).data(Qt.ItemDataRole.UserRole)
             for row in range(form.vocabularies.count())]
    assert "iso27001-it" in names


def test_a_vocabulary_that_is_too_long_says_so(form):
    form.custom.setPlainText("x" * (MAX_CUSTOM_VOCABULARY + 1))
    assert str(MAX_CUSTOM_VOCABULARY) in form.prompt_size.text()


# --- what the answers do to each other -------------------------------------

def test_plain_text_ignores_the_subtitle_numbers(form):
    """Which is the point of choosing: the knobs of the other two answers
    stop applying instead of quietly doing something."""
    form.output_buttons["subtitles"].setChecked(True)
    form.save_srt.setChecked(True)
    form.output_buttons["text"].setChecked(True)

    settings = settings_of(form)
    assert settings["output"] == "text"
    assert settings["subtitles"] is None
    assert settings["diarize"] is False


def test_who_said_what_turns_diarization_on(form):
    form.output_buttons["speakers"].setChecked(True)

    settings = settings_of(form)
    assert settings["output"] == "speakers"
    assert settings["diarize"] is True
    assert settings["subtitles"] is None


def test_the_controls_of_the_other_answers_are_greyed_out(form):
    form.output_buttons["text"].setChecked(True)
    assert form.subtitle_preset.isEnabled() is False
    assert form.save_srt.isEnabled() is False
    assert form.speakers.isEnabled() is False

    form.output_buttons["subtitles"].setChecked(True)
    assert form.subtitle_preset.isEnabled() is True
    assert form.save_srt.isEnabled() is True


def test_the_subtitle_section_waits_for_the_answer_that_needs_it(form):
    """It stays in the list and goes quiet, saying which answer brings it to
    life, and opens itself when that answer is chosen."""
    form.output_buttons["text"].setChecked(True)
    assert form.step_subtitles.is_available() is False
    assert form.step_subtitles.is_open() is False
    assert "Subtitles" in form.step_subtitles.button.text()

    form.output_buttons["subtitles"].setChecked(True)
    assert form.step_subtitles.is_available() is True
    assert form.step_subtitles.is_open() is True


def test_choosing_subtitles_ticks_the_file_it_will_write(form):
    """The answer is the files, and one is written either way: an empty box
    over an .srt on disk is the form lying about what it does."""
    form.save_srt.setChecked(False)
    form.save_vtt.setChecked(False)
    form.output_buttons["subtitles"].setChecked(True)

    assert form.save_srt.isChecked() is True


def test_the_note_says_what_the_chosen_answer_produces(form):
    form.output_buttons["text"].setChecked(True)
    plain = form.output_note.text()
    form.output_buttons["subtitles"].setChecked(True)

    assert plain and plain != form.output_note.text()
    assert ".srt" in form.output_note.text()
    assert form.output_note.minimumHeight() > 0


def test_who_said_what_is_refused_when_the_machine_cannot_diarize(form):
    """An output this machine cannot produce is not offered: a job that fails
    after the wait is a worse way to find that out."""
    from audio_transcriber.diarization import availability

    ready = availability(None)[0] == "ready"
    assert form.output_buttons["speakers"].isEnabled() is ready
    assert form.diarize.isEnabled() is (ready and form.chosen_output() == "subtitles")
    if not ready:
        assert form.chosen_output() != "speakers"
        assert form.output_unavailable.text()


# --- the numbers reaching the queue ----------------------------------------

def test_the_subtitle_numbers_survive_the_trip(form):
    """The form's job is to collect them; the cutting is the core's."""
    form.output_buttons["subtitles"].setChecked(True)
    form.subtitle_preset.setCurrentIndex(
        form.subtitle_preset.findData("ebu_broadcast"))
    form.subtitle_chars.setValue(32)
    form.subtitle_words.setValue(9)
    form.save_srt.setChecked(True)

    settings = settings_of(form)
    assert settings["subtitles"] == "srt"
    assert settings["subtitle_preset"] == "ebu_broadcast"
    assert settings["subtitle_chars"] == 32
    assert settings["subtitle_words"] == 9


def test_zero_means_whatever_the_preset_says(form):
    """A spin box at zero is "not chosen", not "no characters allowed"."""
    form.output_buttons["subtitles"].setChecked(True)
    form.subtitle_chars.setValue(0)
    form.subtitle_words.setValue(0)

    settings = settings_of(form)
    assert settings.get("subtitle_chars") is None
    assert settings.get("subtitle_words") is None
    # Subtitles were the chosen output, so a format is assumed rather than
    # producing cues nobody keeps.
    assert settings["subtitles"] == "srt"


# --- every closed section still reports ------------------------------------

def test_a_closed_section_says_what_it_holds(form):
    form.output_buttons["subtitles"].setChecked(True)
    said = {section.key: section.button.text() for section in form.sections}

    assert said["output"].endswith("Subtitles")
    assert "auto" in said["options"] and "Italiano" in said["options"]
    assert "netflix" in said["subtitles"] and ".srt" in said["subtitles"]
    assert said["vocabulary"].endswith("none")

    form.vocabularies.item(0).setCheckState(Qt.CheckState.Checked)
    assert form.vocab_panel.button.text().endswith("1 chosen")


# --- the dialog around it --------------------------------------------------

def test_the_dialog_starts_from_the_last_answers(application, tmp_path):
    """Six meetings in the queue should be six confirmations, not six forms."""
    from PySide6.QtCore import QSettings

    store = QSettings(str(tmp_path / "gui.ini"), QSettings.Format.IniFormat)
    first = JobDialog("Comitato", SETTINGS, store=store)
    first.form.output_buttons["subtitles"].setChecked(True)
    first.form.subtitle_chars.setValue(32)
    first.accept()

    second = JobDialog("Consiglio", SETTINGS, store=store)
    assert second.form.chosen_output() == "subtitles"
    assert second.form.subtitle_chars.value() == 32


def test_the_dialog_names_the_recording_it_is_about(application):
    dialog = JobDialog("Comitato di direzione", SETTINGS)
    assert "Comitato di direzione" in dialog.windowTitle()
    assert dialog.start.text() == "Transcribe"


# --- a text you already have ----------------------------------------------

def test_the_form_takes_a_text_you_already_have(form):
    """It helps the engine spell and then corrects what it misheard; it sits
    with the subtitle numbers, which is where the use case comes up."""
    form.reference.setPlainText("  Buongiorno a tutti. Cominciamo.  ")

    assert form.choices()["reference"] == "Buongiorno a tutti. Cominciamo."
    # And it reaches the queue the way every other choice does.
    assert settings_of(form)["reference"] == "Buongiorno a tutti. Cominciamo."


def test_an_empty_text_is_not_an_override(form):
    """Empty means "just transcribe", which is the program's default: it must
    not travel as an empty string and turn into a proof-reading against
    nothing."""
    assert form.choices()["reference"] == ""
    assert "reference" not in settings_of(form)
