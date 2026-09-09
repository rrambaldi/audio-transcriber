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
import threading

import numpy as np
import pytest

pytest.importorskip("PySide6", reason="the [gui] extra is not installed")

# Qt reads this when the application object is created, so it has to be set
# before any of it is touched: no window ever appears, on any machine.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox
except ImportError as exc:      # pragma: no cover - depends on the machine
    # PySide6 is installed but will not load: a partial install, or a Linux box
    # without the system libraries Qt links against. That is worth skipping
    # rather than erroring — it is the same situation as not having Qt, and
    # "audio-transcriber gui" says so too.
    pytest.skip(f"PySide6 cannot be loaded here: {exc}", allow_module_level=True)

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


# --- recording ------------------------------------------------------------

def test_the_microphone_menu_has_room_to_be_read(window):
    """It used to be 85 pixels wide, squeezed between a label and two buttons,
    so a real device name — "Microphone Array (Intel Smart Sound...)" — showed
    as nothing at all and looked like a dead control."""
    window.resize(1180, 760)
    window.show()                    # offscreen: nothing appears anywhere
    QApplication.processEvents()
    assert window.transcribe.recorder.devices.width() >= 200


def test_the_microphone_list_is_not_a_snapshot(window):
    """Plugging in a headset after the window opened used to mean reopening
    it. Qt reports the change, and refresh_devices is the slot it calls."""
    from audio_transcriber.gui import multimedia

    recorder = window.transcribe.recorder
    if not multimedia.AVAILABLE:
        pytest.skip("QtMultimedia is not installed")
    assert recorder._watcher is not None
    recorder.refresh_devices()       # safe to call at any moment
    assert recorder.devices.count() == len(multimedia.input_devices())


def test_with_no_microphone_the_recorder_says_so_instead_of_failing_later(window):
    from audio_transcriber.gui import multimedia

    if multimedia.input_devices():
        pytest.skip("this machine has a microphone")
    recorder = window.transcribe.recorder
    assert recorder.button.isEnabled() is False
    assert "microphone" in recorder.message.text().lower()


def test_without_qtmultimedia_the_player_says_why_on_the_page(
        application, tmp_path, monkeypatch):
    """PySide6 ships in two halves and only the add-ons half has QtMultimedia,
    so this branch runs on other people's machines and never on the one it was
    written on. A tooltip on a disabled button was not enough: on several
    platforms it never appears."""
    from audio_transcriber.gui import multimedia
    from audio_transcriber.gui.library_panel import LibraryPanel
    from audio_transcriber.library import Library

    monkeypatch.setattr(multimedia, "AVAILABLE", False)
    panel = LibraryPanel(Library(str(tmp_path / "library")))
    assert panel.player is None
    assert panel.play.isEnabled() is False
    assert panel.player_note.isHidden() is False
    assert "QtMultimedia" in panel.player_note.text()
    panel.deleteLater()


# --- choosing what to record from -----------------------------------------

def make_device_recorder(tmp_path, application, store=None):
    """The Audacity-style recorder, driven by devices that do not exist."""
    from audio_fakes import audio_source, two_engines
    from audio_transcriber.gui.recorder import DeviceRecorder, make_recorder
    from audio_transcriber.recording import LOOPBACK, SYSTEM

    inputs = [audio_source(key="portaudio:0:Mic", host_api="MME", label="Mic"),
              audio_source(key="portaudio:2:Mic", host_api="Windows WASAPI",
                           label="Mic"),
              audio_source(key="portaudio:2:Line", host_api="Windows WASAPI",
                           label="Line in")]
    loopbacks = [audio_source(key="wasapi:loopback:Speakers",
                              host_api="Windows WASAPI", kind=LOOPBACK,
                              engine=SYSTEM, channels=2, label="Altoparlanti")]
    backends = two_engines(inputs, loopbacks)
    recorder = make_recorder(str(tmp_path / "uploads"), store=store,
                             backends=backends)
    assert isinstance(recorder, DeviceRecorder)
    return recorder, backends


def test_the_recorder_offers_the_audio_systems_and_their_sources(tmp_path, application):
    recorder, _ = make_device_recorder(tmp_path, application)
    systems = [recorder.host_apis.itemText(i) for i in range(recorder.host_apis.count())]
    assert systems == ["MME", "Windows WASAPI"]

    recorder.host_apis.setCurrentIndex(systems.index("Windows WASAPI"))
    sources = [recorder.sources.itemText(i) for i in range(recorder.sources.count())]
    assert sources == ["Mic", "Line in", "[loopback] Altoparlanti"]
    recorder.deleteLater()


def test_choosing_another_audio_system_changes_the_sources(tmp_path, application):
    recorder, _ = make_device_recorder(tmp_path, application)
    recorder.host_apis.setCurrentIndex(0)                       # MME
    assert recorder.sources.count() == 1
    recorder.host_apis.setCurrentIndex(1)                       # WASAPI
    assert recorder.sources.count() == 3
    recorder.deleteLater()


def test_the_second_source_menu_leaves_out_the_one_being_recorded(tmp_path, application):
    recorder, _ = make_device_recorder(tmp_path, application)
    recorder.host_apis.setCurrentIndex(1)
    recorder.sources.setCurrentIndex(0)                          # Mic on WASAPI
    keys = [recorder.mix_sources.itemData(i)
            for i in range(recorder.mix_sources.count())]
    assert recorder.sources.currentData() not in keys
    assert keys[0] == "wasapi:loopback:Speakers"                 # loopbacks first
    recorder.deleteLater()


def test_recording_two_sources_writes_one_file_and_hands_it_over(tmp_path, application):
    """The whole point: a microphone and the speakers of a call in one file."""
    recorder, backends = make_device_recorder(tmp_path, application)
    handed = []
    recorder.recorded.connect(handed.append)

    recorder.host_apis.setCurrentIndex(1)
    recorder.sources.setCurrentIndex(0)
    recorder.mix_enabled.setChecked(True)
    recorder.start()
    assert recorder.recording is True
    assert wait_for(lambda: recorder._session.frames > 0)
    recorder.stop()

    assert len(handed) == 1 and os.path.exists(handed[0])
    assert handed[0].endswith(".wav")
    opened = [source.key for source, _channels, _rate in backends[0].opened]
    assert opened == ["portaudio:2:Mic"]
    assert [source.key for source, _c, _r in backends[1].opened] == [
        "wasapi:loopback:Speakers"]
    recorder.deleteLater()


def test_reloading_looks_for_devices_again(tmp_path, application):
    """PortAudio reads the devices once, at startup: a headset plugged in
    afterwards is invisible until something asks it to look again."""
    from audio_fakes import audio_source

    recorder, backends = make_device_recorder(tmp_path, application)
    before = recorder.host_apis.count()
    backends[0]._sources.append(
        audio_source(key="portaudio:5:USB", host_api="Windows WDM-KS",
                     label="Headset"))
    recorder.rescan()
    assert recorder.host_apis.count() == before + 1
    recorder.deleteLater()


def test_the_level_meters_move_while_recording_and_rest_afterwards(tmp_path, application):
    """The bar is the answer to "is anything arriving": it has to move when
    something does, and it must not be left showing a level once stopped."""
    recorder, _ = make_device_recorder(tmp_path, application)
    recorder.host_apis.setCurrentIndex(1)
    recorder.sources.setCurrentIndex(0)
    recorder.mix_enabled.setChecked(True)
    recorder.start()
    assert wait_for(lambda: recorder._session.frames > 0)
    recorder._tick()
    assert recorder.level.value() > 0
    assert recorder.mix_level.value() == 0     # the fake loopback delivers nothing
    recorder.stop()
    assert recorder.level.value() == 0
    recorder.deleteLater()


def test_a_silent_recording_is_flagged_even_though_it_was_filed(tmp_path, application):
    """A muted microphone writes a file full of zeros: real, queued, and worth
    nothing. The warning goes out alongside the file, not instead of it."""
    from audio_fakes import FakeStream, audio_source, two_engines
    from audio_transcriber.gui.recorder import DeviceRecorder

    mic = audio_source(samplerate=1000)
    backends = two_engines([mic], stream=FakeStream(fill=0.0))
    recorder = DeviceRecorder(str(tmp_path / "uploads"), backends=backends)
    handed, said = [], []
    recorder.recorded.connect(handed.append)
    recorder.failed.connect(said.append)

    recorder.start()
    assert wait_for(lambda: recorder._session.frames > 0)
    recorder.stop()
    assert len(handed) == 1 and os.path.exists(handed[0])
    assert said and "silence" in said[0].lower()
    recorder.deleteLater()


def test_the_audio_test_opens_the_device_without_recording(tmp_path, application):
    """"Test audio" answers "is anything arriving" before an hour of meeting
    depends on the answer, and must leave nothing behind."""
    recorder, backends = make_device_recorder(tmp_path, application)
    recorder.start_test()
    assert recorder.testing is True
    assert recorder.recording is False
    assert recorder.host_apis.isEnabled() is False      # the menus are frozen
    assert wait_for(lambda: recorder._monitor.levels[0] > 0)
    recorder._tick()
    assert recorder.level.value() > 0
    assert recorder.verdict.text()

    recorder.stop_test()
    assert recorder.testing is False
    assert recorder.host_apis.isEnabled() is True
    assert recorder.level.value() == 0
    assert not list((tmp_path / "uploads").glob("*")) if (tmp_path / "uploads").exists() else True
    recorder.deleteLater()


def test_the_audio_test_says_when_it_hears_speech(tmp_path, application):
    """The synthetic signal is bursts of band-limited noise with pauses, which
    is what the heuristic is built to recognise; the sentence has to reach the
    label."""
    from audio_fakes import FakeStream, audio_source, two_engines
    from audio_transcriber.gui.recorder import DeviceRecorder

    rate, block = 48000, 4800
    rng = np.random.default_rng(21)
    blocks = []
    for index in range(120):
        room = (rng.standard_normal(block) * 0.001).astype(np.float32)
        if (index % 9) < 5:
            spectrum = np.fft.rfft(rng.standard_normal(block))
            frequencies = np.fft.rfftfreq(block, 1 / rate)
            spectrum[(frequencies < 300) | (frequencies > 3400)] = 0
            shaped = np.fft.irfft(spectrum, block)
            room = room + (shaped / (np.abs(shaped).max() or 1) * 0.15).astype(np.float32)
        blocks.append(room.reshape(-1, 1))

    mic = audio_source(samplerate=rate)
    backends = two_engines([mic], stream=FakeStream(blocks=blocks, pace=0.001))
    recorder = DeviceRecorder(str(tmp_path / "uploads"), backends=backends)
    recorder.start_test()
    assert wait_for(lambda: recorder._monitor.measure()[0] == "speech")
    recorder._tick()
    assert "speech" in recorder.verdict.text().lower()
    recorder.stop_test()
    recorder.deleteLater()


def test_the_verdict_has_room_for_two_lines_before_there_is_one(tmp_path, application):
    """A word-wrapped label starts one line tall and the box is sized from
    that, so the first verdict had its second line cut off. Reserved height is
    the fix, and this is the assertion that would have caught it."""
    recorder, _ = make_device_recorder(tmp_path, application)
    two_lines = 2 * recorder.verdict.fontMetrics().height()
    assert recorder.verdict.minimumHeight() >= two_lines
    assert recorder.message.minimumHeight() >= two_lines
    recorder.deleteLater()


def test_starting_a_recording_takes_the_device_back_from_the_test(tmp_path, application):
    recorder, _ = make_device_recorder(tmp_path, application)
    recorder.start_test()
    assert recorder.testing is True
    recorder.start()
    assert recorder.testing is False
    assert recorder.recording is True
    recorder.stop()
    recorder.deleteLater()


def test_a_forgotten_test_stops_itself(tmp_path, application, monkeypatch):
    """It holds the microphone open; nobody should be able to leave it that
    way all afternoon."""
    from audio_transcriber.gui import recorder as recorder_module

    recorder, _ = make_device_recorder(tmp_path, application)
    recorder.start_test()
    monkeypatch.setattr(recorder_module.time, "monotonic",
                        lambda: recorder._test_started
                        + recorder_module.MAX_TEST_SECONDS + 1)
    recorder._tick()
    assert recorder.testing is False
    assert "30" in recorder.message.text()
    recorder.deleteLater()


def test_a_source_that_will_not_open_is_reported_not_swallowed(tmp_path, application):
    from audio_fakes import audio_source, two_engines
    from audio_transcriber.gui.recorder import DeviceRecorder

    class Refusing:
        name = "portaudio"

        def available(self):
            return True

        def sources(self):
            return [audio_source()]

        def open(self, *args):
            raise OSError("Invalid number of channels")

    backends = (Refusing(), two_engines()[1])
    recorder = DeviceRecorder(str(tmp_path / "uploads"), backends=backends)
    said = []
    recorder.failed.connect(said.append)
    recorder.start()
    assert recorder.recording is False
    assert said and "Invalid number of channels" in said[0]
    assert "Invalid number of channels" in recorder.message.text()
    recorder.deleteLater()


def test_without_the_audio_libraries_the_window_still_records_through_qt(tmp_path):
    """The fallback the [record] extra is optional because of."""
    from audio_fakes import two_engines
    from audio_transcriber.gui.qt_recorder import QtRecorder
    from audio_transcriber.gui.recorder import make_recorder

    recorder = make_recorder(str(tmp_path / "uploads"),
                             backends=two_engines(available=False))
    assert isinstance(recorder, QtRecorder)
    assert "record" in recorder.message.text() or not recorder.button.isEnabled()
    recorder.deleteLater()


# --- transcribing ---------------------------------------------------------

def test_a_file_added_waits_in_the_queue_until_transcribe_is_pressed(
        window, tmp_path, queue):
    """Two complaints, one flow. A file used to sit in a list of its own with
    no way to begin; then adding it started it immediately, which left no room
    to change the model afterwards. It goes into the queue, and the queue runs
    when told."""
    window.transcribe.add_files([sample(tmp_path)])
    assert len(queue.jobs()) == 1
    assert queue.jobs()[0].status == "held"
    window.transcribe.refresh()
    assert window.transcribe.table.item(0, 1).text() == "not started"
    assert window.transcribe.start.isEnabled() is True
    assert "Transcribe" in window.transcribe.summary.text()

    window.transcribe.start_queue()
    assert wait_for(lambda: queue.jobs()[0].status == "done")
    window.transcribe.refresh()
    assert window.transcribe.table.item(0, 0).text() == "meeting"
    assert window.transcribe.table.item(0, 1).text() == "done"
    assert window.transcribe.table.cellWidget(0, 2).value() == 100
    assert window.transcribe.start.isEnabled() is False    # nothing left to start


def test_a_drop_on_the_tab_queues_the_files(window, tmp_path, queue):
    """The drop target is the whole tab: there is no list to aim at any more."""
    from PySide6.QtCore import QMimeData, QPoint, QUrl
    from PySide6.QtGui import QDropEvent

    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(sample(tmp_path))])
    event = QDropEvent(QPoint(10, 10), Qt.DropAction.CopyAction, data,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.transcribe.dropEvent(event)
    assert len(queue.jobs()) == 1


def test_the_queue_is_a_box_with_a_name_on_it(window):
    """It had neither a title nor a way to take anything out of it, which is
    half of why nobody could tell how the tab worked."""
    from PySide6.QtWidgets import QGroupBox

    titles = [box.title() for box in window.transcribe.findChildren(QGroupBox)]
    assert "Transcription queue" in titles


def test_a_job_that_has_not_started_can_be_taken_back_out(window, tmp_path, queue):
    """It leaves no row behind: nothing happened to it. And the buttons offer
    what applies to the selected job and nothing else."""
    blocked = threading.Event()
    queue._runner = lambda job: blocked.wait(5)
    window.transcribe.add_files([sample(tmp_path, "first.wav")])
    window.transcribe.start_queue()
    assert wait_for(lambda: queue.jobs()[0].status == "running")
    window.transcribe.add_files([sample(tmp_path, "second.wav")])
    window.transcribe.refresh()

    window.transcribe.table.selectRow(0)          # newest first: the held one
    assert window.transcribe.cancel_job.isEnabled() is True
    assert window.transcribe.stop_job.isEnabled() is False
    window.transcribe.cancel_selected()
    assert len(queue.jobs()) == 1                 # the row is gone entirely

    window.transcribe.refresh()
    window.transcribe.table.selectRow(0)          # the one that is running
    assert window.transcribe.cancel_job.isEnabled() is False
    assert window.transcribe.stop_job.isEnabled() is True
    blocked.set()


def test_stopping_a_running_transcription_asks_first(window, tmp_path, queue, monkeypatch):
    """It may be forty minutes in, and what it has done is discarded."""
    blocked = threading.Event()
    queue._runner = lambda job: blocked.wait(5)
    window.transcribe.add_files([sample(tmp_path)])
    window.transcribe.start_queue()
    assert wait_for(lambda: queue.jobs()[0].status == "running")
    window.transcribe.refresh()
    window.transcribe.table.selectRow(0)

    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    window.transcribe.stop_selected()
    assert queue.jobs()[0].cancel_requested is False      # refused, so untouched

    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    window.transcribe.stop_selected()
    assert queue.jobs()[0].cancel_requested is True
    blocked.set()


def test_the_finished_jobs_can_be_cleared_in_one_go(window, tmp_path, queue):
    window.transcribe.add_files([sample(tmp_path, "a.wav")])
    window.transcribe.start_queue()
    window.transcribe.add_files([sample(tmp_path, "b.wav")])
    window.transcribe.start_queue()
    assert wait_for(lambda: all(job.status == "done" for job in queue.jobs())
                    and len(queue.jobs()) == 2)
    window.transcribe.refresh()
    assert window.transcribe.clear_finished.isEnabled() is True
    window.transcribe.forget_finished()
    assert queue.jobs() == []
    assert window.transcribe.table.rowCount() == 0


def test_a_local_file_is_copied_into_the_library_not_moved(window, tmp_path, queue):
    """Moving someone's own recording out of their folder is not the window's
    decision to make."""
    source = sample(tmp_path)
    window.transcribe.add_files([source])
    window.transcribe.start_queue()
    assert wait_for(lambda: queue.jobs()[0].status == "done")
    assert os.path.exists(source)


def test_a_drop_of_something_that_is_not_a_file_queues_nothing(window, tmp_path):
    """A folder, or a URL to something that is not on disk."""
    folder = tmp_path / "sub"
    folder.mkdir()
    assert window.transcribe.add_files([str(folder), ""]) is False
    assert window.queue.jobs() == []


def test_an_oversized_vocabulary_keeps_the_file_out_of_the_queue(window, tmp_path):
    from audio_transcriber.vocabularies import MAX_CUSTOM_VOCABULARY

    said = []
    window.transcribe.message.connect(said.append)
    window.transcribe.custom.setPlainText("x" * (MAX_CUSTOM_VOCABULARY + 1))
    assert window.transcribe.add_files([sample(tmp_path)]) is False
    assert window.queue.jobs() == []
    assert said and str(MAX_CUSTOM_VOCABULARY) in said[-1]


def test_the_table_shows_the_stage_of_the_job_that_is_running(window, tmp_path, queue):
    """What the queue reports while a long transcription is under way."""
    blocked = threading.Event()

    def runner(job):
        queue._advance(job, 5, "stage.loading_model")
        blocked.wait(5)

    queue._runner = runner
    window.transcribe.add_files([sample(tmp_path)])
    window.transcribe.start_queue()
    assert wait_for(lambda: queue.jobs()[0].stage == "stage.loading_model")
    window.transcribe.refresh()
    assert window.transcribe.table.item(0, 1).text() == "running: loading the model"
    blocked.set()


def test_the_status_column_grows_to_fit_the_stage(window):
    """It was sized while it said "queued" and then truncated "running:
    converting the model" to "running: ...", which is the one thing the stage
    was added to avoid."""
    from PySide6.QtWidgets import QHeaderView

    header = window.transcribe.table.horizontalHeader()
    assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.ResizeToContents
    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Stretch


def test_a_failed_job_is_shown_with_its_reason(window, tmp_path, queue):
    window.transcribe.add_files([sample(tmp_path, "boom.wav")])
    window.transcribe.start_queue()
    assert wait_for(lambda: queue.jobs()[0].status == "failed")
    window.transcribe.refresh()
    assert window.transcribe.table.item(0, 1).text().startswith("failed: the model exploded")


def test_forgetting_one_job_keeps_the_right_row_selected(window, tmp_path, queue):
    """The table is rebuilt when a job disappears, and the row indices shift
    with it: the selection has to follow the job, not its old position."""
    window.transcribe.add_files([sample(tmp_path, "first.wav"),
                                 sample(tmp_path, "second.wav")])
    window.transcribe.start_queue()
    assert wait_for(lambda: len(queue.jobs()) == 2
                    and all(job.status == "done" for job in queue.jobs()))
    window.transcribe.refresh()

    oldest = queue.jobs()[-1].id            # the table lists the newest first
    window.transcribe.table.selectRow(1)
    assert window.transcribe.selected_job_id() == oldest
    window.transcribe.forget_selected()
    assert len(queue.jobs()) == 1
    assert window.transcribe.table.rowCount() == 1


def test_the_subtitle_numbers_reach_the_job(window, tmp_path, queue):
    """The window's job is to collect them; the cutting is the core's."""
    panel = window.transcribe
    panel.subtitle_preset.setCurrentIndex(panel.subtitle_preset.findData("ebu_broadcast"))
    panel.subtitle_chars.setValue(32)
    panel.subtitle_words.setValue(9)
    panel.save_srt.setChecked(True)
    panel.add_files([sample(tmp_path)])

    settings = queue.jobs()[0].settings
    assert settings["subtitles"] == "srt"
    assert settings["subtitle_preset"] == "ebu_broadcast"
    assert settings["subtitle_chars"] == 32
    assert settings["subtitle_words"] == 9


def test_zero_means_whatever_the_preset_says(window, tmp_path, queue):
    """A spin box at zero is "not chosen", not "no characters allowed"."""
    panel = window.transcribe
    panel.subtitle_chars.setValue(0)
    panel.subtitle_words.setValue(0)
    panel.save_srt.setChecked(False)
    panel.save_vtt.setChecked(False)
    panel.add_files([sample(tmp_path)])

    # The queue drops overrides that are None - that is how "not chosen here"
    # leaves the configured value standing - so the keys are simply absent.
    settings = queue.jobs()[0].settings
    assert settings.get("subtitle_chars") is None
    assert settings.get("subtitle_words") is None
    assert settings.get("subtitles") is None      # nothing saved unless asked


def test_an_entry_can_be_cut_into_subtitles_from_the_library(window, tmp_path,
                                                             queue, monkeypatch):
    """From the segments, so an entry transcribed months ago can be cut again
    with today's numbers."""
    from PySide6.QtWidgets import QFileDialog

    entry = queue.library.create(title="Comitato")
    entry.write_transcript("Il primo punto all'ordine del giorno riguarda il budget.\n", [
        {"text": "Il primo punto all'ordine del giorno riguarda il budget.",
         "start": 0.0, "end": 4.0}])
    entry.update(transcription={"model": "small"})
    window.library.reload()

    target = tmp_path / "comitato.srt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(target), "")))
    said = []
    window.library.message.connect(said.append)
    window.library.export_subtitles()
    assert target.exists()
    assert " --> " in target.read_text(encoding="utf-8")
    assert said and "cues" in said[-1]


def test_an_entry_without_timestamps_cannot_be_cut(window, tmp_path, queue):
    entry = queue.library.create(title="Senza tempi")
    entry.write_transcript("Testo.\n", [])
    entry.update(transcription={"model": "small"})
    window.library.reload()
    said = []
    window.library.message.connect(said.append)
    window.library.export_subtitles()
    assert said and "timestamps" in said[-1]


def test_the_chosen_options_are_remembered_for_next_time(window, tmp_path, queue):
    window.transcribe.model.setCurrentIndex(window.transcribe.model.findData("base"))
    window.transcribe.custom.setPlainText("alpha, beta")
    window.transcribe.add_files([sample(tmp_path)])
    window.transcribe.start_queue()
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
    window.transcribe.start_queue()
    assert wait_for(lambda: queue.jobs()[0].status == "done")
    window.transcribe.refresh()          # emits job_finished; the list reloads

    entry_id = queue.jobs()[0].entry_id
    window.show_entry(entry_id)
    assert window.tabs.currentWidget() is window.library
    assert window.library.entry.id == entry_id
    assert "Hello everyone." in window.library.transcript.toPlainText()


def test_the_transcript_offers_a_timestamp_to_click(window, tmp_path, queue):
    window.transcribe.add_files([sample(tmp_path)])
    window.transcribe.start_queue()
    assert wait_for(lambda: queue.jobs()[0].status == "done")
    window.library.reload()
    window.library.show_entry(queue.jobs()[0].entry_id)
    html = window.library.transcript.toHtml()
    assert 'href="#t=61.50"' in html and "[1:01]" in html


def test_notes_are_written_into_the_entry(window, tmp_path, queue):
    window.transcribe.add_files([sample(tmp_path)])
    window.transcribe.start_queue()
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
    window.transcribe.start_queue()
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
    window.transcribe.start_queue()
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
    window.transcribe.start_queue()
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
    window.transcribe.start_queue()
    assert wait_for(lambda: queue.jobs()[0].status == "done")
    window.library.reload()
    window.library.notes.setPlainText("Decisions: ship it.\n")

    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Save))
    assert window.close() is True
    with open(window.library.entry.notes_path, encoding="utf-8") as handle:
        assert "ship it" in handle.read()
