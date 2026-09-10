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
    from PySide6.QtGui import QColor, QFont, QKeySequence, QPalette, QShortcut
    from PySide6.QtWidgets import QApplication, QLabel, QMessageBox
except ImportError as exc:      # pragma: no cover - depends on the machine
    # PySide6 is installed but will not load: a partial install, or a Linux box
    # without the system libraries Qt links against. That is worth skipping
    # rather than erroring — it is the same situation as not having Qt, and
    # "audio-transcriber gui" says so too.
    pytest.skip(f"PySide6 cannot be loaded here: {exc}", allow_module_level=True)

from audio_transcriber import __version__, branding, i18n, paths  # noqa: E402
from audio_transcriber.gui import masthead as masthead_module  # noqa: E402
from audio_transcriber.gui import style, theme, widgets  # noqa: E402
from audio_transcriber.gui import window as window_module  # noqa: E402
from audio_transcriber.gui.about_dialog import AboutDialog  # noqa: E402
from audio_transcriber.gui.masthead import MARK_PX, Masthead  # noqa: E402
from audio_transcriber.gui.window import (  # noqa: E402
    MainWindow,
    app_icon,
    claim_taskbar_identity,
)
from audio_transcriber.jobs import JobQueue  # noqa: E402
from audio_transcriber.library import STORE_COPY  # noqa: E402

SETTINGS = {"model": "auto", "language": "it", "backend": "auto", "device": "auto",
            "para_gap": 1.2, "para_max_chars": 600, "prompt": "", "prompt_file": None,
            "vocabulary": None, "vocab_dir": None, "library_dir": None,
            "diarize": False, "speakers": None, "diar_model": None}


@pytest.fixture(scope="session")
def application():
    """One QApplication for the whole session: Qt allows exactly one.

    Painted the way ``window.launch`` paints it - Fusion, the brand's palette
    and its two faces - because a window whose theme was never installed is
    not the window anybody runs."""
    application = QApplication.instance() or QApplication([])
    application.setStyle("Fusion")
    style.apply(application)
    return application


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


def actions(window, row):
    """The three buttons on one row of the queue."""
    return window.transcribe._actions[row["id"]]


def sample(tmp_path, name="meeting.wav"):
    path = tmp_path / name
    path.write_bytes(b"not really audio")
    return str(path)


# --- what the window is made of -------------------------------------------

def test_the_window_has_the_three_tabs(window):
    labels = [window.tabs.tabText(index) for index in range(window.tabs.count())]
    assert labels == ["Transcribe", "Library", "This machine"]


def test_this_machine_tab_reports_hardware_and_paths(window):
    assert window.system.hardware_form.rowCount() >= 2


def test_the_window_wears_the_icon(window):
    """Every rendered size is handed over, so the desktop picks one instead
    of scaling the only one it was given."""
    icon = window.windowIcon()
    assert not icon.isNull()
    widths = sorted(size.width() for size in icon.availableSizes())
    assert widths == sorted(branding.ICON_SIZES)


def test_the_masthead_carries_the_mark_the_name_and_the_promise(window):
    """The window says whose it is and what it does without its title bar.

    A maximised window on Windows shows the icon 16 px wide, and a tiling
    desktop draws no title bar at all: everything the title bar was carrying
    had to be somewhere inside the window as well."""
    masthead = window.masthead
    assert masthead.name.text() == i18n.t("gui.wordmark")
    # Lower case, like the page's own h1 and the README: it is a command's
    # name, not a product's.
    assert masthead.name.text() == masthead.name.text().lower()
    assert masthead.tagline.text() == i18n.t("gui.tagline")
    # The version is not here any more: it belongs with the licence and the
    # rest of what this program is, one click away.
    assert __version__ not in masthead.about.text()
    assert masthead.mark.isVisibleTo(window)
    pixmap = masthead.mark.pixmap()
    assert not pixmap.isNull()
    # Asked for in device pixels and told what the ratio was, so a retina
    # screen gets the 128 px render rather than the 48 px one stretched.
    ratio = masthead.devicePixelRatioF() or 1.0
    assert pixmap.width() == round(MARK_PX * ratio)


def test_the_masthead_is_the_way_into_the_about_box(window):
    """The window has no menu bar to hide an About box behind, so the way in
    is a link in the masthead, where the version used to be."""
    link = window.masthead.about

    assert '<a href="#about">' in link.text()
    assert i18n.t("about.open") in link.text()
    assert link.toolTip()

    # The window is listening, and what comes up is the About box itself.
    link.linkActivated.emit("#about")
    opened = window.findChildren(AboutDialog)
    assert len(opened) == 1
    assert "Permission is hereby granted" in opened[0].licence.toPlainText()
    opened[0].reject()


def test_the_about_box_is_where_the_version_number_lives(window):
    """It left the masthead, so this is the one place in the window that
    writes it down apart from the title bar."""
    dialog = AboutDialog(icon=window.windowIcon(), parent=window)
    try:
        written = [label.text() for label in dialog.findChildren(QLabel)]
        assert any(__version__ in text for text in written)
        assert i18n.t("gui.wordmark") in written
    finally:
        dialog.deleteLater()


def test_f1_asks_for_the_about_box_too(window):
    """The key somebody presses looking for help, on a window with no help."""
    keys = [shortcut.key() for shortcut in window.findChildren(QShortcut)]

    assert QKeySequence(QKeySequence.StandardKey.HelpContents) in keys


def test_the_about_box_shows_the_whole_licence(window):
    """Not its name: the licence is the MIT license with a wish in front of
    it, and the wish is the half worth a screen."""
    dialog = AboutDialog(icon=window.windowIcon(), parent=window)
    try:
        text = dialog.licence.toPlainText()

        assert "Permission is hereby granted" in text
        assert "senseless acts of beauty" in text
        assert dialog.licence.isReadOnly()
        # Selectable, because copying it is the one thing somebody may want.
        assert dialog.licence.textInteractionFlags() & \
            Qt.TextInteractionFlag.TextSelectableByMouse
        # And what is bundled that is not ours.
        assert "SIL Open Font License 1.1" in dialog.bundled.text()
        assert dialog.open_file.isEnabled() is True
    finally:
        dialog.deleteLater()


def test_the_about_box_survives_a_build_with_no_licence_file(window, monkeypatch):
    """A licence that cannot be shown is worth admitting, not worth a
    traceback on a dialog somebody opened out of curiosity."""
    from audio_transcriber import about

    monkeypatch.setattr(about, "_installed_path", lambda: None)
    monkeypatch.setattr(about, "_CHECKOUT", "/nowhere/LICENSE")
    about.licence_text.cache_clear()
    try:
        dialog = AboutDialog(icon=window.windowIcon(), parent=window)
        assert i18n.t("about.licence_missing") in dialog.licence.toPlainText()
        # Nothing to open, and the button says so by being off.
        assert dialog.open_file.isEnabled() is False
        dialog.deleteLater()
    finally:
        about.licence_text.cache_clear()


def test_the_masthead_is_above_the_tabs_not_inside_one(window):
    """It is true of the whole window, so it must not scroll away with a tab."""
    central = window.centralWidget()
    assert window.masthead.parent() is central
    assert window.tabs.parent() is central


def test_the_masthead_is_painted_in_the_brand_not_in_the_desktop_s_colours(window):
    """This is the reversal, pinned down: the window used to be painted by the
    desktop on purpose, and is now painted in the program's own palette and
    faces so that it and the web page read as one program. What did *not*
    change is the floor under it — the tagline is the brand's muted ink, and
    that ink still has to clear WCAG AA on the ground it sits on."""
    masthead = window.masthead
    ground = masthead.palette().color(QPalette.ColorRole.Window)
    which = "dark" if ground.lightnessF() < 0.5 else "light"
    assert ground == theme.colour("paper", which)

    muted = QColor(masthead.tagline.styleSheet().split("color:")[1].strip(" ;"))
    assert muted == theme.colour("muted", which)
    assert style.contrast(muted, ground) >= style.MIN_CONTRAST

    # The page's three lines, in the page's two faces: the eyebrow in the
    # letter-spaced sans, the name and the promise in the serif.
    assert masthead.eyebrow.font().capitalization() == QFont.Capitalization.AllUppercase
    assert masthead.name.font().family() == theme.family(branding.SERIF)
    assert masthead.tagline.font().italic() is True
    # And the name is the page's h1: the display cut, at display size.
    if hasattr(QFont, "setVariableAxis"):
        assert masthead.name.font().variableAxisValue(QFont.Tag("opsz")) \
            == theme.DISPLAY_OPSZ
    assert masthead.name.font().pointSizeF() > masthead.tagline.font().pointSizeF()


def test_the_rule_under_the_masthead_keeps_the_gutter(window):
    """It is the bottom edge of the masthead, and the masthead sits in the
    window's gutter: a rule running out to the frame was the one line in the
    window that did not."""
    window.resize(1000, 480)
    window.show()
    QApplication.processEvents()
    rule = window.masthead.rule

    left = rule.mapTo(window.masthead, rule.rect().topLeft()).x()
    right = window.masthead.width() - (left + rule.width())
    assert left == theme.GUTTER
    assert right == theme.GUTTER
    assert rule.height() == 1


def test_on_a_dark_theme_the_mark_loses_its_plate(window):
    """The plate is a dark navy: on a dark desktop it stops being a shape and
    becomes a rounded smudge of nearly the window colour. The brand has a
    plateless drawing for that background, and this is where it is used."""
    light, dark = QPalette(), QPalette()
    light.setColor(QPalette.ColorRole.Window, QColor("#f6f6f6"))
    dark.setColor(QPalette.ColorRole.Window, QColor("#1c1c1c"))
    icon = window.windowIcon()

    window.masthead.setPalette(light)
    assert masthead_module.drawing_for(icon, window.masthead) is icon

    window.masthead.setPalette(dark)
    plateless = masthead_module.drawing_for(icon, window.masthead)
    assert plateless is not icon
    # It is an SVG, and Qt's SVG plugin is not on every machine: if it cannot
    # be drawn, mark_pixmap has to fall back to the renders rather than
    # leaving an empty label.
    assert not masthead_module.mark_pixmap(icon, window.masthead).isNull()


def test_the_mark_is_redrawn_when_the_desktop_changes_theme(window):
    """GNOME and Windows both switch light to dark without restarting
    anything. Qt hands that over as a palette change."""
    before = window.masthead.mark.pixmap().toImage()
    dark = QPalette()
    dark.setColor(QPalette.ColorRole.Window, QColor("#1c1c1c"))
    dark.setColor(QPalette.ColorRole.WindowText, QColor("#f0f0f0"))
    window.masthead.setPalette(dark)          # delivers a PaletteChange
    after = window.masthead.mark.pixmap().toImage()
    assert not after.isNull()
    if masthead_module.drawing_for(window.windowIcon(), window.masthead) \
            is not window.windowIcon():
        assert after != before


def test_a_build_with_no_icon_files_still_gets_a_masthead(application, monkeypatch):
    """The icon set is data: a wheel that lost it must not stop the window.

    ``branding.icon_files()`` comes back short rather than failing, so the
    band has to survive having no picture to put in it."""
    monkeypatch.setattr(branding, "icon_files", lambda: [])
    masthead = Masthead(app_icon())
    assert not masthead.mark.isVisibleTo(masthead)
    assert masthead.name.text() == i18n.t("gui.wordmark")


def test_the_taskbar_identity_is_claimed_only_on_windows(monkeypatch):
    """Explorer takes a task bar button's icon from the Application User Model
    ID, whose default is python.exe's. Everywhere else there is nothing to
    claim, and the call must not be attempted."""
    monkeypatch.setattr(window_module.sys, "platform", "linux")
    assert claim_taskbar_identity() is False
    monkeypatch.setattr(window_module.sys, "platform", "win32")
    # Off Windows there is no ctypes.windll to call, and this is best effort:
    # it answers rather than raising in the middle of starting up. On Windows
    # itself the call is real and succeeds.
    assert claim_taskbar_identity() in (True, False)


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
    # No bar on a row that has finished: a measurement of something that is
    # not happening. What it did is on the second line of the recording.
    assert window.transcribe.table.cellWidget(0, 2) is None
    details = window.transcribe.table.item(0, 0).data(widgets.DETAILS_ROLE)
    assert "2 words" in details
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
    """It leaves no row behind: nothing happened to it. And every row carries
    the buttons that apply to it, so there is no selection to get wrong."""
    blocked = threading.Event()
    queue._runner = lambda job: blocked.wait(5)
    window.transcribe.add_files([sample(tmp_path, "first.wav")])
    window.transcribe.start_queue()
    assert wait_for(lambda: queue.jobs()[0].status == "running")
    window.transcribe.add_files([sample(tmp_path, "second.wav")])
    window.transcribe.refresh()

    held, running = window.transcribe._rows          # newest first
    assert actions(window, held).run.text() == "Transcribe"
    assert actions(window, held).drop.isEnabled() is True
    # The one that is running offers to stop, and cannot be dropped.
    assert actions(window, running).run.text() == "Stop"
    assert actions(window, running).drop.isEnabled() is False

    window.transcribe.remove_row(held["id"])
    assert len(queue.jobs()) == 1                    # the row is gone entirely
    blocked.set()


def test_the_first_button_on_a_row_follows_its_state(window, tmp_path, queue):
    """"Start it" and "stop it" are the same place in the row and never both
    apply, so the button changes rather than the row growing a fourth."""
    window.transcribe.add_files([sample(tmp_path)])
    window.transcribe.refresh()
    assert actions(window, window.transcribe._rows[0]).run.text() == "Transcribe"

    window.transcribe.start_queue()
    assert wait_for(lambda: queue.jobs()[0].status == "done")
    window.transcribe.refresh()
    assert actions(window, window.transcribe._rows[0]).run.text() == "Open"


def test_a_failed_recording_can_be_asked_again(window, tmp_path, queue):
    """Nothing was filed and the file is still where it was, so there is
    nothing to undo: the row goes back to waiting."""
    def explode(job):
        raise RuntimeError("the model exploded")

    queue._runner = explode
    window.transcribe.add_files([sample(tmp_path)])
    window.transcribe.start_queue()
    assert wait_for(lambda: queue.jobs()[0].status == "failed")
    window.transcribe.refresh()
    assert actions(window, window.transcribe._rows[0]).run.text() == "Try again"

    assert queue.retry(queue.jobs()[0].id) is True
    assert queue.jobs()[0].status == "held"


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
    assert window.transcribe.table.item(0, 1).text() == "failed"
    assert window.transcribe.table.item(0, 0).data(
        widgets.DETAILS_ROLE).startswith("the model exploded")


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


# --- what the run is for --------------------------------------------------

def test_the_start_button_says_how_much_it_starts(window, tmp_path, queue):
    """A button that says only "Transcribe" leaves the count to be worked out
    from the list."""
    panel = window.transcribe
    assert panel.start.text() == "Transcribe"

    panel.add_files([sample(tmp_path), sample(tmp_path, name="second.wav")])
    assert panel.start.text() == "Transcribe 2 recordings"
    # and it is the one filled button on the tab, and the default one
    assert panel.start.objectName() == "primary"
    assert panel.start.isDefault() is True


def test_the_queue_line_lists_the_states_instead_of_choosing_one(window, tmp_path, queue):
    """One running at 34% and one waiting used to read "1 waiting, press
    Transcribe", which the table on the same screen contradicted."""
    running = queue.submit(sample(tmp_path), title="prima", start=False)
    waiting = queue.submit(sample(tmp_path, name="b.wav"), title="seconda",
                           start=False)
    running.status, running.progress = "running", 34
    waiting.status = "held"
    window.transcribe.refresh()

    line = window.transcribe.summary.text()
    assert "1 running" in line and "34" in line
    assert "1 not started" in line


def test_the_status_bar_says_what_is_in_the_library(window):
    """It used to hold the library path, permanently, in the one place a
    message can appear."""
    assert "recordings in the library" in window.status_line.text()


# --- starting one recording ------------------------------------------------

class FakeDialog:
    """Stands in for the per-recording dialog: records how it was opened.

    Every test gets it, through an autouse fixture, so that a test which
    starts a transcription can never open a real modal dialog and hang the
    suite waiting for a click that will not come."""

    answer = True
    seen = {}
    choices_to_give = {}

    def __init__(self, title, settings=None, defaults=None, vocabularies=None,
                 custom_text=None, store=None, parent=None):
        FakeDialog.seen = {"title": title, "settings": settings, "store": store}
        self._choices = {"model": "auto", "language": "it", "backend": "auto",
                         "output": "text", "diarize": False, "speakers": 0,
                         "subtitle_preset": "netflix", "subtitle_chars": 0,
                         "subtitle_words": 0, "srt": False, "vtt": False}
        self._choices.update(defaults or {})
        self._choices.update(FakeDialog.choices_to_give)

    def exec(self):
        from PySide6.QtWidgets import QDialog
        return (QDialog.DialogCode.Accepted if FakeDialog.answer
                else QDialog.DialogCode.Rejected)

    def choices(self):
        return self._choices

    def vocabularies(self):
        return []

    def custom_text(self):
        return ""


@pytest.fixture(autouse=True)
def fake_dialog(monkeypatch):
    from audio_transcriber.gui import transcribe_panel

    FakeDialog.answer = True
    FakeDialog.choices_to_give = {}
    monkeypatch.setattr(transcribe_panel, "JobDialog", FakeDialog)
    return FakeDialog


def test_starting_one_recording_asks_what_it_is_for(window, tmp_path, queue,
                                                    fake_dialog):
    """Six meetings dropped in at once, and one of them is the interview that
    needs subtitles: the answer belongs to the recording, not to the tab."""
    window.transcribe.add_files([sample(tmp_path)])
    window.transcribe.refresh()
    fake_dialog.choices_to_give = {"output": "subtitles"}

    assert window.transcribe.transcribe_row(queue.jobs()[0].id) is True
    assert fake_dialog.seen["title"] == 'Transcribe "meeting"'
    # ...and it is handed the store, which is where the last answers are
    assert fake_dialog.seen["store"] is window.transcribe.store
    assert queue.jobs()[0].settings["output"] == "subtitles"
    assert queue.jobs()[0].settings["subtitles"] == "srt"
    assert queue.jobs()[0].status != "held"


def test_saying_no_to_the_dialog_leaves_the_recording_waiting(window, tmp_path,
                                                              queue, fake_dialog):
    window.transcribe.add_files([sample(tmp_path)])
    window.transcribe.refresh()
    fake_dialog.answer = False

    assert window.transcribe.transcribe_row(queue.jobs()[0].id) is False
    assert queue.jobs()[0].status == "held"


def test_the_answers_reach_only_the_recording_that_was_asked(window, tmp_path,
                                                             queue, fake_dialog):
    """The other rows are untouched: they have not been asked yet."""
    window.transcribe.add_files([sample(tmp_path, "one.wav"),
                                 sample(tmp_path, "two.wav")])
    window.transcribe.refresh()
    asked, other = queue.jobs()[0], queue.jobs()[1]
    fake_dialog.choices_to_give = {"model": "medium"}

    window.transcribe.transcribe_row(asked.id)
    assert asked.settings["model"] == "medium"
    assert other.settings["model"] != "medium"


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


def test_the_row_buttons_survive_a_second_file(window, tmp_path, queue):
    """Qt owns a cell widget and deletes the one it is replacing: reusing the
    same objects across a rebuild had the first row's buttons destroyed the
    moment a second recording was added."""
    window.transcribe.add_files([sample(tmp_path, "first.wav")])
    window.transcribe.refresh()
    window.transcribe.add_files([sample(tmp_path, "second.wav")])
    window.transcribe.refresh()

    assert window.transcribe.table.rowCount() == 2
    for index in range(2):
        buttons = window.transcribe.table.cellWidget(index, 3)
        assert buttons is not None, f"riga {index} senza pulsanti"
        assert buttons.run.text() == "Transcribe"
        assert buttons.isVisibleTo(window.transcribe.table)


def test_the_actions_column_is_wide_enough_for_its_buttons(window, tmp_path):
    """A column sized from its (empty) cells clipped the buttons to nothing on
    a machine whose font is wider than this one's."""
    window.transcribe.add_files([sample(tmp_path)])
    window.transcribe.refresh()
    buttons = window.transcribe.table.cellWidget(0, 3)

    assert window.transcribe.table.columnWidth(3) >= buttons.sizeHint().width()


def test_no_button_relies_on_an_icon_it_does_not_have(window):
    """The rule that would have caught three invisible buttons on Windows.

    A QToolButton defaults to "icon only". With no icon the Fusion style
    draws the text anyway and the Windows one draws nothing, so every tool
    button in this window either carries an icon or says out loud that it is
    showing text. Painting one and looking at it cannot catch this: on the
    machine the tests run on, the broken version looked fine."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QToolButton

    guilty = []
    for button in window.findChildren(QToolButton):
        icon_only = button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
        arrow = button.arrowType() != Qt.ArrowType.NoArrow
        if icon_only and button.icon().isNull() and not arrow and button.text():
            guilty.append(button.text())
    assert guilty == []

# --- summarising from the window ------------------------------------------

def filed_entry(queue, title="Riunione ISO"):
    """An entry with enough said in it to be worth summarising."""
    segments = [
        {"start": 0.0, "end": 8.0, "text": "Parliamo del budget del progetto ISO."},
        {"start": 8.0, "end": 16.0, "text": "Il budget del progetto ISO va deciso."},
        {"start": 16.0, "end": 24.0, "text": "Ha piovuto tutta la notte."},
        {"start": 24.0, "end": 32.0, "text": "La decisione spetta al comitato."},
    ]
    entry = queue.library.create(title=title)
    entry.write_transcript(" ".join(s["text"] for s in segments), segments)
    entry.update(transcription={"language": "it"}, audio={"duration_seconds": 32})
    return entry


def test_the_library_pane_has_a_summary_tab(window, queue):
    entry = filed_entry(queue)
    window.library.reload()
    assert window.library.show_entry(entry.id)

    tabs = [window.library.tabs.tabText(i) for i in range(window.library.tabs.count())]
    assert i18n.t("gui.tab_summary") in tabs
    # Nothing written yet, and the pane says that rather than sitting empty.
    assert window.library.summary.toPlainText() == ""
    assert "No summary yet" in window.library.summary_note.text()


def test_summarising_goes_through_the_queue_and_comes_back_in_the_pane(window, queue):
    """Not run on the thread that draws the window: a model reading an hour of
    transcript would stop the window responding for minutes."""
    entry = filed_entry(queue)
    window.library.reload()
    window.library.show_entry(entry.id)
    window.library.summarise.click()

    assert wait_for(lambda: bool(window.library.summary.toPlainText()))
    assert "budget" in window.library.summary.toPlainText().lower()
    assert "extractive" in window.library.summary_note.text()
    # The button offers the obvious next thing rather than the same word twice.
    assert window.library.summarise.text() == i18n.t("gui.summary_again")
    assert queue.library.get(entry.id).has_summary()


def test_a_summary_that_fails_says_so_and_frees_the_button(window, queue):
    entry = filed_entry(queue)
    entry.write_transcript("", [])
    window.library.reload()
    window.library.show_entry(entry.id)
    window.library.summarise.click()

    assert wait_for(lambda: window.library.summarise.isEnabled()
                    and window.library._summary_job is None)
    assert not queue.library.get(entry.id).has_summary()


def test_the_pane_does_not_change_under_somebody_who_moved_on(window, queue):
    """A summary that finishes while another entry is being read belongs to
    the entry it was asked for, not to the one on screen."""
    first = filed_entry(queue, title="Prima riunione")
    second = filed_entry(queue, title="Seconda riunione")
    window.library.reload()
    window.library.show_entry(first.id)
    window.library.summarise.click()
    window.library.show_entry(second.id)

    assert wait_for(lambda: queue.library.get(first.id).has_summary())
    QApplication.processEvents()
    assert window.library.entry.id == second.id
    assert window.library.summary.toPlainText() == ""


# --- where the two branches meet: summaries in the same queue --------------

def summary_job(window, queue, status="failed"):
    """A summary of a filed entry, in the queue beside the transcriptions."""
    entry = queue.library.create(title="Comitato")
    entry.write_transcript("una parola " * 40,
                           [{"start": 0.0, "end": 2.0, "text": "una parola"}])
    job = queue.summarize(entry.id, start=False)
    job.status = status
    if status == "failed":
        job.error = "no model"
    window.transcribe.refresh()
    return job


def test_a_summary_in_the_queue_is_not_asked_about_transcribing(window, queue,
                                                                fake_dialog):
    """The four questions are about transcribing. A summary job pushed through
    them would have its settings replaced with answers about something else."""
    job = summary_job(window, queue)
    fake_dialog.seen = {}

    window.transcribe.act_on_row(job.id)
    assert fake_dialog.seen == {}                 # no dialog was opened
    assert job.status in ("held", "queued", "running", "done")


def test_a_summary_row_says_what_it_is(window, queue):
    """Its "model" is the one that transcribed the entry, which has nothing to
    do with what this job is doing to it."""
    job = summary_job(window, queue, status="queued")
    row = window.transcribe._row_for(job.id)

    assert "summary of the transcript" in row["details"]
    assert row["asks"] is False


def test_a_transcription_is_still_asked(window, tmp_path, queue, fake_dialog):
    window.transcribe.add_files([sample(tmp_path)])
    window.transcribe.refresh()
    row = window.transcribe._row_for(queue.jobs()[0].id)

    assert row["asks"] is True
