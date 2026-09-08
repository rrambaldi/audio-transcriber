"""Recording through Qt, which is the fallback and the lowest common
denominator.

QtMultimedia offers whatever flat list of inputs its backend chose to expose:
no host API to pick, and no way to record what the speakers are playing. When
the ``[record]`` extra is installed, :mod:`audio_transcriber.gui.recorder`
takes over with both. This engine stays because it needs nothing beyond
PySide6, works on every platform Qt does, and asks no questions.

The file is written into the queue's upload directory, so it lives on whatever
volume the configuration points the cache at, and a job that fails cleans it
up like any other upload. A successful transcription moves it into the library
entry, which is why nothing here copies it anywhere.
"""
import os

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..formatting import format_clock
from ..i18n import t
from . import multimedia, options


class QtRecorder(QWidget):
    """Microphone chooser, a record button, and the elapsed time.

    Emits :attr:`recorded` with the path of the finished file. It does not
    queue anything itself: the panel decides what to do with the recording,
    which keeps "record" and "transcribe" two separate decisions."""

    recorded = Signal(str)
    failed = Signal(str)

    def __init__(self, target_dir, parent=None):
        super().__init__(parent)
        self._target_dir = target_dir
        self._session = None
        self._recorder = None
        self._audio_input = None
        self._watcher = None
        self._target = None
        #: Standing hint, restored whenever a transient message is cleared.
        self._note = ""

        self.devices = QComboBox()
        self.devices.setToolTip(t("gui.rec_device_tip"))
        # A device name is long ("Microphone Array (Intel Smart Sound...)") and
        # the menu is the only thing here that has to be read rather than
        # clicked, so it gets the width and its own line.
        self.devices.setMinimumWidth(220)
        self.devices.setSizePolicy(QSizePolicy.Policy.Expanding,
                                   QSizePolicy.Policy.Fixed)
        self.devices.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.button = QPushButton(t("gui.rec_start"))
        self.button.clicked.connect(self.toggle)
        self.pause_button = QPushButton(t("gui.rec_pause"))
        self.pause_button.clicked.connect(self.toggle_pause)
        self.pause_button.setEnabled(False)
        self.elapsed = QLabel(format_clock(0))
        self.message = QLabel("")
        self.message.setWordWrap(True)

        chooser = QHBoxLayout()
        chooser.addWidget(QLabel(t("gui.rec_device")))
        chooser.addWidget(self.devices, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(self.button)
        buttons.addWidget(self.pause_button)
        buttons.addStretch(1)
        buttons.addWidget(self.elapsed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(chooser)
        layout.addLayout(buttons)
        layout.addWidget(self.message)

        if not multimedia.AVAILABLE:
            self._disable(t("gui.rec_no_multimedia"))
            return
        # Worth saying once: this engine cannot record the speakers, and the
        # one that can is a pip install away.
        self._note = t("gui.rec_basic")
        self.message.setText(self._note)
        self._build_session()
        # Qt tells us when a microphone is plugged in or taken away, so the
        # menu is never a snapshot of what was there when the window opened.
        self._watcher = multimedia.QMediaDevices(self)
        self._watcher.audioInputsChanged.connect(self.refresh_devices)
        self.refresh_devices()

    # --- setup ------------------------------------------------------------

    def _build_session(self):
        """One capture session for the widget's lifetime.

        Qt wants the session, the input and the recorder to outlive the call
        that starts recording, so they are attributes rather than locals."""
        self._session = multimedia.QMediaCaptureSession(self)
        self._audio_input = multimedia.QAudioInput(self)
        self._recorder = multimedia.QMediaRecorder(self)
        self._session.setAudioInput(self._audio_input)
        self._session.setRecorder(self._recorder)
        self._recorder.durationChanged.connect(self._show_duration)
        self._recorder.recorderStateChanged.connect(self._state_changed)
        self._recorder.errorOccurred.connect(self._error)

        media_format, self._extension = multimedia.recording_format()
        self._recorder.setMediaFormat(media_format)
        self._recorder.setQuality(multimedia.QMediaRecorder.Quality.NormalQuality)
        # Speech, and Whisper resamples to 16 kHz anyway: one channel halves
        # the file for nothing lost.
        self._recorder.setAudioChannelCount(1)

    def refresh_devices(self):
        """Repopulate the microphone menu, keeping the current choice if it is
        still there.

        Also a slot: Qt calls it when the machine's microphones change, which
        is why the menu never needs the window to be reopened. It must
        therefore leave a recording in progress alone."""
        if not multimedia.AVAILABLE or self.recording:
            return
        previous = self.devices.currentData()
        self.devices.clear()
        found = multimedia.input_devices()
        for device in found:
            self.devices.addItem(device.description(), device)
        if not found:
            self._disable(t("gui.rec_no_device"))
            return
        self.button.setEnabled(True)
        self.devices.setEnabled(True)
        self.message.setText(self._note)
        for index in range(self.devices.count()):
            data = self.devices.itemData(index)
            if previous is not None and data == previous:
                self.devices.setCurrentIndex(index)
                break

    def _disable(self, reason):
        self.button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.devices.setEnabled(False)
        self.message.setText(reason)

    # --- state ------------------------------------------------------------

    @property
    def recording(self):
        if self._recorder is None:
            return False
        stopped = multimedia.QMediaRecorder.RecorderState.StoppedState
        return self._recorder.recorderState() != stopped

    def toggle(self):
        if self.recording:
            self.stop()
        else:
            self.start()

    def start(self):
        """Begin recording into a new file in the target directory."""
        if self._recorder is None or self.recording:
            return
        device = self.devices.currentData()
        if device is not None:
            self._audio_input.setDevice(device)
        try:
            os.makedirs(self._target_dir, exist_ok=True)
        except OSError as exc:
            self.failed.emit(str(exc))
            return
        stem = options.recording_stem()
        self._target = os.path.join(self._target_dir, f"{stem}.{self._extension}")
        self._recorder.setOutputLocation(QUrl.fromLocalFile(self._target))
        self._recorder.record()

    def stop(self):
        """Finish the recording; the file arrives with :attr:`recorded`."""
        if self._recorder is not None and self.recording:
            self._recorder.stop()

    def _show_duration(self, milliseconds):
        self.elapsed.setText(format_clock(milliseconds / 1000))

    def toggle_pause(self):
        if self._recorder is None or not self.recording:
            return
        paused = (self._recorder.recorderState()
                  == multimedia.QMediaRecorder.RecorderState.PausedState)
        if paused:
            self._recorder.record()
        else:
            self._recorder.pause()

    def _state_changed(self, state):
        """Follow the recorder: label the buttons, and publish a finished file."""
        states = multimedia.QMediaRecorder.RecorderState
        recording = state != states.StoppedState
        self.button.setText(t("gui.rec_stop") if recording else t("gui.rec_start"))
        self.pause_button.setEnabled(recording)
        self.pause_button.setText(t("gui.rec_resume")
                                  if state == states.PausedState
                                  else t("gui.rec_pause"))
        self.devices.setEnabled(not recording)
        if recording:
            return
        self.elapsed.setText(format_clock(0))
        path = self._finished_file()
        self._target = None
        if path:
            self.recorded.emit(path)

    def _finished_file(self):
        """The recording Qt actually wrote, once it is worth transcribing.

        Qt may add its own extension, so the recorder is asked where the file
        went rather than trusting the name we proposed. A zero-byte file means
        the microphone produced nothing, which is a failure, not a recording of
        silence to be queued."""
        if self._recorder is None:
            return None
        location = self._recorder.actualLocation().toLocalFile() or self._target
        if not location or not os.path.isfile(location):
            return None
        if os.path.getsize(location) == 0:
            try:
                os.unlink(location)
            except OSError:
                pass
            self.failed.emit(t("gui.rec_empty"))
            return None
        return location

    def _error(self, _error, message):
        self.message.setText(message or t("gui.rec_failed"))
        self.failed.emit(message or t("gui.rec_failed"))
