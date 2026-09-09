"""Choosing what to record from, the way Audacity lets you.

Two menus: the audio system (MME, DirectSound, WASAPI, WDM-KS) and, inside it,
the source. The loopback of an output device appears among the WASAPI sources,
which is what makes it possible to record a call — what the machine plays is
the other participants' half of it.

And a second source, optional, mixed into the same file: a microphone plus the
loopback of the speakers are the two halves of a meeting held over Teams. The
two sound cards run on independent clocks, so the primary source sets the pace
and the other is kept alongside it — see
:func:`audio_transcriber.recording.mix`.

The engine itself is in :mod:`audio_transcriber.recording`, with no Qt in it,
and the decisions about what the menus say are in
:mod:`audio_transcriber.gui.options`. What is here is the wiring: two combo
boxes, three buttons and a timer. When the ``[record]`` extra is not installed
this module steps aside for
:class:`~audio_transcriber.gui.qt_recorder.QtRecorder`, which needs nothing but
PySide6.
"""
import os
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import recording
from ..formatting import format_clock
from ..i18n import t
from . import options
from .qt_recorder import QtRecorder

#: How often the elapsed time, the levels and the engine's health are re-read.
TICK_MS = 200

#: An audio test stops itself after this long. It holds the microphone open,
#: and a test nobody remembered to stop would hold it all afternoon.
MAX_TEST_SECONDS = 30


def make_recorder(target_dir, store=None, parent=None, backends=None):
    """The best recorder this installation can offer.

    :class:`DeviceRecorder` when the audio libraries are there — host APIs,
    loopback, mixing — and the Qt one when they are not. Both expose the same
    handful of signals and methods, so the panel above does not care which one
    it was given."""
    if recording.available(backends):
        return DeviceRecorder(target_dir, store=store, parent=parent,
                              backends=backends)
    return QtRecorder(target_dir, parent=parent)


class DeviceRecorder(QWidget):
    """Audio system, source, an optional second source, and a record button."""

    recorded = Signal(str)
    #: Also carries a warning about a recording that was made and is silent:
    #: the file is real, and the user still needs to know.
    failed = Signal(str)

    def __init__(self, target_dir, store=None, parent=None, backends=None):
        super().__init__(parent)
        self._target_dir = target_dir
        self._store = store
        self._backends = backends
        self._session = None
        self._monitor = None
        self._test_started = 0.0
        self._sources = []

        self.host_apis = QComboBox()
        self.host_apis.setToolTip(t("gui.rec_host_api_tip"))
        self.sources = QComboBox()
        self.sources.setToolTip(t("gui.rec_source_tip"))
        self.mix_enabled = QCheckBox(t("gui.rec_mix"))
        self.mix_enabled.setToolTip(t("gui.rec_mix_tip"))
        self.mix_enabled.toggled.connect(self._mix_toggled)
        self.mix_sources = QComboBox()
        self.mix_sources.setEnabled(False)
        for combo in (self.host_apis, self.sources, self.mix_sources):
            # A device name is long and is the one thing here that has to be
            # read rather than clicked.
            combo.setMinimumWidth(220)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding,
                                QSizePolicy.Policy.Fixed)
        self.host_apis.currentIndexChanged.connect(self._host_api_chosen)
        self.sources.currentIndexChanged.connect(self._source_chosen)

        self.reload_button = QPushButton(t("gui.reload"))
        self.reload_button.setToolTip(t("gui.rec_reload_tip"))
        self.reload_button.clicked.connect(self.rescan)
        self.level = _level_bar()
        self.mix_level = _level_bar()
        self.test_button = QPushButton(t("gui.rec_test"))
        self.test_button.setToolTip(t("gui.rec_test_tip"))
        self.test_button.clicked.connect(self.toggle_test)
        self.verdict = QLabel("")
        self.verdict.setWordWrap(True)
        _reserve_two_lines(self.verdict)
        self.button = QPushButton(t("gui.rec_start"))
        self.button.clicked.connect(self.toggle)
        self.pause_button = QPushButton(t("gui.rec_pause"))
        self.pause_button.clicked.connect(self.toggle_pause)
        self.pause_button.setEnabled(False)
        self.elapsed = QLabel(format_clock(0))
        self.message = QLabel("")
        self.message.setWordWrap(True)
        _reserve_two_lines(self.message)

        self._assemble()
        self.refresh_devices()
        self._load_state()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(TICK_MS)

    def _assemble(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for label, widget in ((t("gui.rec_host_api"), self.host_apis),
                              (t("gui.rec_source"), self.sources)):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addWidget(widget, 1)
            # The meter sits on the row of the source it measures, which is
            # the only labelling it needs.
            row.addWidget(self.reload_button if widget is self.host_apis
                          else self.level)
            layout.addLayout(row)
        mix_row = QHBoxLayout()
        mix_row.addWidget(self.mix_enabled)
        mix_row.addWidget(self.mix_sources, 1)
        mix_row.addWidget(self.mix_level)
        layout.addLayout(mix_row)
        buttons = QHBoxLayout()
        buttons.addWidget(self.button)
        buttons.addWidget(self.pause_button)
        buttons.addWidget(self.test_button)
        buttons.addStretch(1)
        buttons.addWidget(self.elapsed)
        layout.addLayout(buttons)
        layout.addWidget(self.verdict)
        layout.addWidget(self.message)

    # --- the menus --------------------------------------------------------

    def refresh_devices(self):
        """Re-read the machine's audio devices into the two menus.

        Left alone while recording: pulling the ground out from under a running
        session would be worse than a slightly stale list."""
        if self.recording:
            return
        wanted_api = self.host_apis.currentData()
        wanted_source = self.sources.currentData()
        self._sources = recording.sources(self._backends)

        self.host_apis.blockSignals(True)
        self.host_apis.clear()
        for host_api, sources in recording.host_apis(self._backends):
            self.host_apis.addItem(host_api, host_api)
            self.host_apis.setItemData(self.host_apis.count() - 1,
                                       options.host_api_summary(sources),
                                       Qt.ItemDataRole.ToolTipRole)
        self.host_apis.blockSignals(False)

        if not self._sources:
            self.button.setEnabled(False)
            self.message.setText(t("gui.rec_no_device"))
            return
        self.button.setEnabled(True)
        self.message.setText("")
        _select(self.host_apis, wanted_api)
        self._host_api_chosen()
        _select(self.sources, wanted_source)
        self._source_chosen()

    def rescan(self):
        """Look for devices again: PortAudio only reads them at startup, so a
        headset plugged in after the window opened needs this button."""
        if self.recording:
            return
        recording.rescan(self._backends)
        self.refresh_devices()

    def _host_api_chosen(self):
        """Show the sources belonging to the chosen audio system."""
        host_api = self.host_apis.currentData()
        self.sources.blockSignals(True)
        self.sources.clear()
        for source in self._sources:
            if source.host_api != host_api:
                continue
            self.sources.addItem(options.source_label(source), source.key)
        self.sources.blockSignals(False)
        self._source_chosen()

    def _source_chosen(self):
        """Refill the "together with" menu, which cannot offer this source."""
        chosen = self.sources.currentData()
        wanted = self.mix_sources.currentData()
        self.mix_sources.blockSignals(True)
        self.mix_sources.clear()
        for source in options.mix_candidates(self._sources, chosen):
            self.mix_sources.addItem(
                options.source_label(source, with_host_api=True), source.key)
        self.mix_sources.blockSignals(False)
        _select(self.mix_sources, wanted)
        usable = self.mix_sources.count() > 0
        self.mix_enabled.setEnabled(usable)
        self.mix_sources.setEnabled(usable and self.mix_enabled.isChecked())

    def _mix_toggled(self, checked):
        self.mix_sources.setEnabled(checked and self.mix_sources.count() > 0)

    def chosen_source(self):
        """The primary source, or ``None`` when the menus are empty."""
        return recording.find(self.sources.currentData(), self._backends)

    def chosen_mix(self):
        """The second source, when one is asked for and possible."""
        if not (self.mix_enabled.isChecked() and self.mix_enabled.isEnabled()):
            return None
        return recording.find(self.mix_sources.currentData(), self._backends)

    # --- the audio test ---------------------------------------------------

    @property
    def testing(self):
        return self._monitor is not None and self._monitor.running

    def toggle_test(self):
        if self._monitor is not None:
            self.stop_test()
        else:
            self.start_test()

    def start_test(self):
        """Open the chosen source without recording anything.

        The meters move and, after a second and a half, the window says
        whether what is arriving behaves like somebody talking. Nothing is
        written: this is the question asked *before* an hour of meeting
        depends on the answer."""
        if self.recording or self._monitor is not None:
            return
        source = self.chosen_source()
        if source is None:
            self.message.setText(t("gui.rec_no_device"))
            return
        monitor = recording.Monitor(source, mix_with=self.chosen_mix(),
                                    backends=self._backends)
        try:
            monitor.start()
        except recording.RecordingError as exc:
            self.message.setText(str(exc))
            self.failed.emit(str(exc))
            return
        self._monitor = monitor
        self._test_started = time.monotonic()
        self.message.setText("")
        self.verdict.setText(t("gui.rec_test_listening"))
        self.test_button.setText(t("gui.rec_test_stop"))
        self._freeze(True)

    def stop_test(self, timed_out=False):
        """Let go of the device, keeping the verdict on screen."""
        monitor, self._monitor = self._monitor, None
        self.test_button.setText(t("gui.rec_test"))
        self._freeze(False)
        self._show_levels([])
        if monitor is None:
            return
        error = monitor.error
        monitor.stop()
        if error:
            self.message.setText(error)
            self.failed.emit(error)
        elif timed_out:
            self.message.setText(t("gui.rec_test_over"))

    # --- recording --------------------------------------------------------

    @property
    def recording(self):
        return self._session is not None and self._session.running

    def toggle(self):
        if self.recording:
            self.stop()
        else:
            self.start()

    def start(self):
        """Open the chosen devices and begin writing into the target folder."""
        if self.recording:
            return
        if self._monitor is not None:
            self.stop_test()          # the device cannot be in two hands
        source = self.chosen_source()
        if source is None:
            self.message.setText(t("gui.rec_no_device"))
            return
        path = os.path.join(self._target_dir, options.recording_stem() + ".wav")
        session = recording.Recording(path, source, mix_with=self.chosen_mix(),
                                      backends=self._backends)
        try:
            session.start()
        except recording.RecordingError as exc:
            # A device that will not open says so now, not in an hour.
            self.message.setText(str(exc))
            self.failed.emit(str(exc))
            return
        self._session = session
        self._save_state()
        self.message.setText("")
        self._show_recording(True)

    def stop(self):
        """Finish the file and hand it over, if anything was captured."""
        session, self._session = self._session, None
        self._show_recording(False)
        if session is None:
            return
        path = session.stop()
        self.elapsed.setText(format_clock(0))
        self._show_levels([])
        if session.silent:
            # A muted microphone writes a perfectly valid file full of zeros,
            # and Whisper turns that into nothing at all.
            self.message.setText(t("gui.rec_silent"))
            self.failed.emit(t("gui.rec_silent"))
        if session.error:
            self.message.setText(session.error)
            self.failed.emit(session.error)
        if path:
            self.recorded.emit(path)
        elif not session.error:
            self.message.setText(t("gui.rec_empty"))
            self.failed.emit(t("gui.rec_empty"))

    def toggle_pause(self):
        if not self.recording:
            return
        if self._session.paused:
            self._session.resume()
        else:
            self._session.pause()
        self.pause_button.setText(t("gui.rec_resume") if self._session.paused
                                  else t("gui.rec_pause"))

    def _show_recording(self, recording_now):
        self.button.setText(t("gui.rec_stop") if recording_now
                            else t("gui.rec_start"))
        self.pause_button.setEnabled(recording_now)
        self.pause_button.setText(t("gui.rec_pause"))
        self.test_button.setEnabled(not recording_now)
        self._freeze(recording_now)

    def _freeze(self, frozen):
        """Hold the menus still while a device of theirs is open."""
        for widget in (self.host_apis, self.sources, self.mix_enabled,
                       self.mix_sources, self.reload_button):
            widget.setEnabled(not frozen)
        if not frozen:
            self._source_chosen()      # restores what may and may not be mixed

    def _tick(self):
        """Follow the worker thread: the clock, the levels, the verdict, and a
        device that gave up."""
        if self._session is not None:
            self.elapsed.setText(format_clock(self._session.elapsed_seconds))
            self._show_levels(self._session.levels)
            if self._session.error or not self._session.running:
                self.stop()
            return
        if self._monitor is None:
            return
        self._show_levels(self._monitor.levels)
        self.verdict.setText(options.speech_verdict(*self._monitor.measure()))
        if self._monitor.error or not self._monitor.running:
            self.stop_test()
        elif time.monotonic() - self._test_started > MAX_TEST_SECONDS:
            self.stop_test(timed_out=True)

    def _show_levels(self, levels):
        """Draw the input levels: the answer to "is anything arriving at all".

        One bar per source, so a loopback that gives nothing is visible even
        when the microphone next to it is working — with a single mixed bar it
        would not be."""
        levels = list(levels or [])
        self.level.setValue(options.level_percent(levels[0] if levels else 0))
        self.mix_level.setValue(
            options.level_percent(levels[1] if len(levels) > 1 else 0))

    # --- what is remembered -----------------------------------------------

    def _load_state(self):
        """Restore the last choice. A device that has been unplugged simply
        does not match, and the menus keep their defaults."""
        if self._store is None:
            return
        _select(self.host_apis, self._store.value("record_host_api", "", str))
        self._host_api_chosen()
        _select(self.sources, self._store.value("record_source", "", str))
        self._source_chosen()
        _select(self.mix_sources, self._store.value("record_mix", "", str))
        self.mix_enabled.setChecked(
            bool(self._store.value("record_mix_enabled", False, bool))
            and self.mix_sources.count() > 0)

    def _save_state(self):
        if self._store is None:
            return
        self._store.setValue("record_host_api", self.host_apis.currentData())
        self._store.setValue("record_source", self.sources.currentData())
        self._store.setValue("record_mix", self.mix_sources.currentData())
        self._store.setValue("record_mix_enabled", self.mix_enabled.isChecked())


def _reserve_two_lines(label):
    """Keep room for a wrapped sentence before there is one.

    A word-wrapped label starts one line tall, and the box around it is sized
    from that: the moment a verdict arrives it needs two lines and the second
    one is simply cut off, which is how the first version of this shipped."""
    label.setMinimumHeight(2 * label.fontMetrics().height() + 2)
    return label


def _level_bar():
    """A narrow, wordless meter: it is read as a length, not as a number."""
    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(0)
    bar.setTextVisible(False)
    bar.setFixedWidth(64)
    bar.setToolTip(t("gui.rec_level_tip"))
    return bar


def _select(combo, value):
    """Select the entry whose data is ``value``, if it is still there."""
    if not value:
        return
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)
