"""The desktop window itself, driven without a display.

Qt is an optional extra, so this module skips entirely when PySide6 is not
installed — the rest of the suite still covers every decision the window makes,
because those live in ``gui.options``. What is checked here is the wiring: that
the tabs exist, that a file dropped in really reaches the queue, that the table
follows a job, and that the library pane reads an entry back and writes its
notes.

Everything runs on Qt's "offscreen" platform plugin and with a queue whose
worker only pretends to transcribe, so no model, no display and no microphone
are needed."""
import os

import pytest

pytest.importorskip("PySide6", reason="the [gui] extra is not installed")

# Qt reads this when the application object is created, so it has to be set
# before any of it is touched: no window ever appears, on any machine.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from audio_transcriber import i18n, paths  # noqa: E402
from audio_transcriber.gui.window import MainWindow  # noqa: E402
from audio_transcriber.jobs import JobQueue  # noqa: E402
from audio_transcriber.library import STORE_COPY  # noqa: E402

SETTINGS = {"model": "auto", "language": "it", "backend": "auto", "device": "auto",
            "para_gap": 1.2, "para_max_chars": 600, "prompt": "", "prompt_file": None,
            "vocabulary": None, "vocab_dir": None, "library_dir": None,
            "diarize": False, "speakers": None, "diar_model": None}


@pytest.fixture(scope="session")
def application():
    """One QApplication for the whole session: Qt allows exactly one."""
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch, tmp_path):
    """Everything the window writes — gui.ini included — under a temp folder."""
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "home"))
    monkeypatch.delenv("AUDIO_TRANSCRIBER_LANG", raising=False)
    i18n.set_language("en")
    yield
    i18n._current = None


@pytest.fixture
def queue():
    """A queue that files a plausible entry without transcribing anything."""
    def runner(job):
        if "boom" in job.filename:
            raise RuntimeError("the model exploded")
        entry = queue_holder["queue"].library.create(source=job.source,
                                                     title=job.title,
                                                     store=STORE_COPY)
        entry.write_transcript("Hello everyone.\n", [
            {"start": 0.0, "end": 2.0, "text": "Hello everyone."},
            {"start": 61.5, "end": 65.0, "text": "Later on."}])
        entry.update(audio={"duration_seconds": 120.0}, stats={"words": 2},
                     transcription={"model": "small", "backend": "faster-whisper"})
        job.entry_id = entry.id
        job.words = 2
        job.audio_duration = 120.0

    queue_holder = {"queue": JobQueue(SETTINGS, runner=runner)}
    return queue_holder["queue"]


@pytest.fixture
def window(application, queue):
    window = MainWindow(SETTINGS, queue=queue)
    yield window
    window.transcribe.shutdown()
    window.library.shutdown()
    window.deleteLater()


def wait_for(condition, timeout=5.0):
    """Spin Qt's event loop until ``condition`` holds, the way a user waits."""
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        QApplication.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


def sample(tmp_path, name="meeting.wav"):
    path = tmp_path / name
    path.write_bytes(b"not really audio")
    return str(path)


# --- what the window is made of -------------------------------------------

def test_the_window_has_the_three_tabs(window):
    labels = [window.tabs.tabText(index) for index in range(window.tabs.count())]
    assert labels == ["Transcribe", "Library", "This machine"]


def test_the_options_offer_the_installed_keyword_sets(window):
    names = [window.transcribe.vocabularies.item(row).data(Qt.ItemDataRole.UserRole)
             for row in range(window.transcribe.vocabularies.count())]
    assert "iso27001-it" in names


def test_diarization_is_greyed_out_when_the_machine_cannot_do_it(window):
    """Offering it would only produce a job that fails after the wait."""
    from audio_transcriber.diarization import availability

    ready = availability()[0] == "ready"
    assert window.transcribe.diarize.isEnabled() is ready


def test_this_machine_tab_reports_hardware_and_paths(window):
    assert window.system.hardware_form.rowCount() >= 2


# --- transcribing ---------------------------------------------------------

def test_a_file_added_is_queued_and_the_table_follows_it(window, tmp_path, queue):
    window.transcribe.add_files([sample(tmp_path)])
    assert window.transcribe.files.count() == 1
    window.transcribe.submit()

    assert window.transcribe.files.count() == 0      # the list empties
    assert len(queue.jobs()) == 1
    assert wait_for(lambda: queue.jobs()[0].status == "done")
    window.transcribe.refresh()
    assert window.transcribe.table.item(0, 0).text() == "meeting"
    assert window.transcribe.table.item(0, 1).text() == "done"
    assert window.transcribe.table.cellWidget(0, 2).value() == 100


def test_a_local_file_is_copied_into_the_library_not_moved(window, tmp_path, queue):
    """Moving someone's own recording out of their folder is not the window's
    decision to make."""
    source = sample(tmp_path)
    window.transcribe.add_files([source])
    window.transcribe.submit()
    assert wait_for(lambda: queue.jobs()[0].status == "done")
    assert os.path.exists(source)


def test_submitting_nothing_says_so_instead_of_doing_nothing(window):
    said = []
    window.transcribe.message.connect(said.append)
    window.transcribe.submit()
    assert said == ["Add a file, or record one, first."]


def test_an_oversized_vocabulary_stops_the_submission(window, tmp_path):
    from audio_transcriber.vocabularies import MAX_CUSTOM_VOCABULARY

    said = []
    window.transcribe.message.connect(said.append)
    window.transcribe.custom.setPlainText("x" * (MAX_CUSTOM_VOCABULARY + 1))
    window.transcribe.add_files([sample(tmp_path)])
    window.transcribe.submit()
    assert window.queue.jobs() == []
    assert said and str(MAX_CUSTOM_VOCABULARY) in said[-1]


def test_a_failed_job_is_shown_with_its_reason(window, tmp_path, queue):
    window.transcribe.add_files([sample(tmp_path, "boom.wav")])
    window.transcribe.submit()
    assert wait_for(lambda: queue.jobs()[0].status == "failed")
    window.transcribe.refresh()
    assert window.transcribe.table.item(0, 1).text().startswith("failed: the model exploded")


def test_forgetting_one_job_keeps_the_right_row_selected(window, tmp_path, queue):
    """The table is rebuilt when a job disappears, and the row indices shift
    with it: the selection has to follow the job, not its old position."""
    window.transcribe.add_files([sample(tmp_path, "first.wav"),
                                 sample(tmp_path, "second.wav")])
    window.transcribe.submit()
    assert wait_for(lambda: len(queue.jobs()) == 2
                    and all(job.status == "done" for job in queue.jobs()))
    window.transcribe.refresh()

    oldest = queue.jobs()[-1].id            # the table lists the newest first
    window.transcribe.table.selectRow(1)
    assert window.transcribe.selected_job_id() == oldest
    window.transcribe.forget_selected()
    assert len(queue.jobs()) == 1
    assert window.transcribe.table.rowCount() == 1


def test_the_chosen_options_are_remembered_for_next_time(window, tmp_path, queue):
    window.transcribe.model.setCurrentIndex(window.transcribe.model.findData("base"))
    window.transcribe.custom.setPlainText("alpha, beta")
    window.transcribe.add_files([sample(tmp_path)])
    window.transcribe.submit()
    assert queue.jobs()[0].settings["model"] == "base"
    assert queue.jobs()[0].prompt == "alpha, beta"

    later = MainWindow(SETTINGS, queue=queue)
    try:
        assert later.transcribe.model.currentData() == "base"
        assert later.transcribe.custom.toPlainText() == "alpha, beta"
    finally:
        later.transcribe.shutdown()
        later.deleteLater()


# --- from a finished job to the library -----------------------------------

def test_a_finished_job_opens_in_the_library(window, tmp_path, queue):
    window.transcribe.add_files([sample(tmp_path)])
    window.transcribe.submit()
    assert wait_for(lambda: queue.jobs()[0].status == "done")
    window.transcribe.refresh()          # emits job_finished; the list reloads

    entry_id = queue.jobs()[0].entry_id
    window.show_entry(entry_id)
    assert window.tabs.currentWidget() is window.library
    assert window.library.entry.id == entry_id
    assert "Hello everyone." in window.library.transcript.toPlainText()


def test_the_transcript_offers_a_timestamp_to_click(window, tmp_path, queue):
    window.transcribe.add_files([sample(tmp_path)])
    window.transcribe.submit()
    assert wait_for(lambda: queue.jobs()[0].status == "done")
    window.library.reload()
    window.library.show_entry(queue.jobs()[0].entry_id)
    html = window.library.transcript.toHtml()
    assert 'href="#t=61.50"' in html and "[1:01]" in html


def test_notes_are_written_into_the_entry(window, tmp_path, queue):
    window.transcribe.add_files([sample(tmp_path)])
    window.transcribe.submit()
    assert wait_for(lambda: queue.jobs()[0].status == "done")
    window.library.reload()

    window.library.notes.setPlainText("Decisions: ship it.\n")
    assert window.library.save_notes.isEnabled()
    assert window.library.write_notes() is True
    with open(window.library.entry.notes_path, encoding="utf-8") as handle:
        assert handle.read() == "Decisions: ship it.\n"
    assert window.library.table.item(0, 5).text() == "yes"


def test_cancelling_the_notes_prompt_keeps_the_entry_being_written_on(
        window, tmp_path, queue, monkeypatch):
    """Clicking another recording with half a note typed asks what to do, and
    "cancel" has to put the selection back where the note is."""
    window.transcribe.add_files([sample(tmp_path, "first.wav"),
                                 sample(tmp_path, "second.wav")])
    window.transcribe.submit()
    assert wait_for(lambda: len(queue.jobs()) == 2
                    and all(job.status == "done" for job in queue.jobs()))
    window.library.reload()
    assert window.library.table.rowCount() == 2
    writing_on = window.library.entry.id
    window.library.notes.setPlainText("half a thought")

    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Cancel))
    window.library.table.selectRow(1)
    assert window.library.entry.id == writing_on
    assert window.library.selected_id() == writing_on
    assert window.library.notes.toPlainText() == "half a thought"


def test_searching_looks_inside_the_transcripts(window, tmp_path, queue):
    window.transcribe.add_files([sample(tmp_path)])
    window.transcribe.submit()
    assert wait_for(lambda: queue.jobs()[0].status == "done")
    window.library.reload()

    window.library.search.setText("everyone")
    window.library.reload()
    assert window.library.table.rowCount() == 1
    window.library.search.setText("nothing like this")
    window.library.reload()
    assert window.library.table.rowCount() == 0
    assert window.library.entry is None


def test_an_entry_can_be_deleted_from_the_window(window, tmp_path, queue, monkeypatch):
    window.transcribe.add_files([sample(tmp_path)])
    window.transcribe.submit()
    assert wait_for(lambda: queue.jobs()[0].status == "done")
    window.library.reload()
    path = window.library.entry.path

    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    window.library.delete_entry()
    assert not os.path.exists(path)
    assert window.library.table.rowCount() == 0


# --- closing --------------------------------------------------------------

def test_closing_with_a_job_still_running_asks_first(window, monkeypatch):
    """The queue lives in this process: closing the window ends any
    transcription with it, so it is worth one question.

    ``pending_count`` is faked because a real pending job would be a race:
    what is being checked here is the window's manners, and the counting
    itself is covered in ``test_jobs.py``."""
    answers = []
    monkeypatch.setattr(window.queue, "pending_count", lambda: 2)
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: answers.pop()))

    answers.append(QMessageBox.StandardButton.No)
    assert window.close() is False        # refused: the transcription goes on
    answers.append(QMessageBox.StandardButton.Yes)
    assert window.close() is True


def test_closing_offers_to_save_edited_notes(window, tmp_path, queue, monkeypatch):
    """Notes are typed by hand and never regenerated, so neither discarding
    them silently nor writing them silently is acceptable."""
    window.transcribe.add_files([sample(tmp_path)])
    window.transcribe.submit()
    assert wait_for(lambda: queue.jobs()[0].status == "done")
    window.library.reload()
    window.library.notes.setPlainText("Decisions: ship it.\n")

    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Save))
    assert window.close() is True
    with open(window.library.entry.notes_path, encoding="utf-8") as handle:
        assert "ship it" in handle.read()
