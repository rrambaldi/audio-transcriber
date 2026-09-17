"""The "this machine" tab: what the tool found, how busy it is, and where it
keeps things.

The same three questions ``audio-transcriber hardware``, ``paths`` and
``config`` answer on the command line, because they are the questions people
actually ask when a transcription is slower than expected or when they cannot
find their recordings. Nothing here can be changed from the window:
``config.toml`` is edited in an editor, and the button opens it.

The two meters answer the fourth question, the one the command line cannot:
*is it working now, and on what*. They are sampled only while the tab is on
screen — a window minimised for an hour must not spend the cores it is
measuring — and a figure this system cannot measure is not drawn at all.
"""
import os

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFontDatabase
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import logs, paths
from ..hardware import Meter
from ..i18n import t
from .meters import SAMPLE_MS, TIGHT_PERCENT, gib, paint_tight

#: How many lines of the log the panel shows before it starts scrolling.
LOG_LINES = 12


class SystemPanel(QWidget):
    """Hardware, engines, how busy they are, and the directories in use."""

    def __init__(self, settings=None, library=None, parent=None, meter=None):
        super().__init__(parent)
        self.settings = dict(settings or {})
        self.library = library
        # Shared with the footer when the window hands one over, so the two
        # places that draw these numbers never disagree about them.
        self.meter = meter or Meter()

        hardware = QGroupBox(t("gui.group_hardware"))
        self.hardware_form = QFormLayout(hardware)
        for label, value in self._hardware_rows():
            self.hardware_form.addRow(f"{label}:", _value(value))

        load = QGroupBox(t("gui.group_load"))
        load_form = QFormLayout(load)
        self.cpu_bar, self.cpu_reading = _meter_row(load_form, t("gui.row_cpu"))
        self.ram_bar, self.ram_reading = _meter_row(load_form, t("gui.row_ram"))
        self.load_note = _value("")
        load_form.addRow("", self.load_note)
        self.sampler = QTimer(self)
        self.sampler.setInterval(SAMPLE_MS)
        self.sampler.timeout.connect(self.read_meters)
        self.sampler.timeout.connect(self.read_log)

        locations = QGroupBox(t("gui.group_paths"))
        form = QFormLayout(locations)
        for label, path, exists, configured in paths.describe(self.settings):
            note = "" if exists else f"  ({t('gui.path_missing')})"
            if configured:
                note += f"  ({t('gui.path_configured')})"
            form.addRow(f"{label}:", _value(f"{path}{note}"))

        buttons = QHBoxLayout()
        config_button = QPushButton(t("gui.open_config"))
        config_button.clicked.connect(self.open_config)
        library_button = QPushButton(t("gui.open_library"))
        library_button.clicked.connect(self.open_library)
        buttons.addWidget(config_button)
        buttons.addWidget(library_button)
        buttons.addStretch(1)

        # Everything on this tab at its own height, and the tab scrolled when
        # they do not all fit: the directory rows are word-wrapped paths, and
        # a layout that shares out the height instead squeezes them to one
        # line each and cuts the rest off. That was invisible while the tab
        # was four short groups; the log is what made it fit badly.
        inside = QWidget()
        layout = QVBoxLayout(inside)
        layout.setContentsMargins(0, 0, 0, 0)   # the pane's gutter is the only one
        layout.addWidget(hardware)
        layout.addWidget(load)
        layout.addWidget(locations)
        layout.addLayout(buttons)
        layout.addWidget(self._log_group())
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(inside)
        outside = QVBoxLayout(self)
        outside.setContentsMargins(0, 0, 0, 0)
        outside.addWidget(scroll)
        self.read_meters()

    # --- what the window would otherwise have printed ---------------------

    def _log_group(self):
        """The tail of the log, and the two things anybody does with it.

        Here rather than in a window of its own because this is the tab
        somebody is already on when they want it: the question the log
        answers — "why did that not work" — is the question this whole tab
        exists for."""
        group = QGroupBox(t("gui.group_log"))
        inside = QVBoxLayout(group)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        # A fixed pitch, because a log is columns: the stamp, then the line.
        self.log_view.setFont(QFontDatabase.systemFont(
            QFontDatabase.SystemFont.FixedFont))
        self.log_view.setPlaceholderText(t("gui.log_empty"))
        # Tall enough that a traceback is a traceback and not a keyhole; not
        # taller, because the tab is scrolled and the rest of it has to stay
        # reachable without going past this.
        self.log_view.setMinimumHeight(
            self.log_view.fontMetrics().lineSpacing() * LOG_LINES)
        inside.addWidget(self.log_view, 1)

        self.log_path = _value(logs.path())
        inside.addWidget(self.log_path)

        row = QHBoxLayout()
        open_log = QPushButton(t("gui.open_log"))
        open_log.clicked.connect(self.open_log)
        clear_log = QPushButton(t("gui.clear_log"))
        clear_log.clicked.connect(self.clear_log)
        row.addWidget(open_log)
        row.addWidget(clear_log)
        row.addStretch(1)
        inside.addLayout(row)
        self._log_seen = None
        self.read_log()
        return group

    def read_log(self):
        """Redraw the tail, but only when the file has actually changed.

        This runs on the same timer as the meters, and a window left open on
        this tab must not re-read the log every second for nothing. Size and
        modification time together are enough: the file is only ever appended
        to, or truncated by the button below it."""
        try:
            stat = os.stat(logs.path())
            state = (stat.st_size, stat.st_mtime_ns)
        except OSError:
            state = None
        if state == self._log_seen:
            return
        self._log_seen = state
        bar = self.log_view.verticalScrollBar()
        at_end = bar.value() >= bar.maximum() - 1
        self.log_view.setPlainText("\n".join(logs.tail()))
        # Follow the end unless the reader has scrolled up to look at
        # something: a view that jumps back every second cannot be read.
        if at_end:
            self.log_view.verticalScrollBar().setValue(
                self.log_view.verticalScrollBar().maximum())

    def open_log(self):
        """Open the log in whatever the system uses for text files."""
        path = logs.path()
        if not os.path.exists(path):
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(paths.ensure(paths.log_dir())))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def clear_log(self):
        """Empty it, after asking. Kept next to the view because that is where
        it is wanted: somebody about to reproduce a problem wants the next
        lines alone. Asked about because, small as it is, it destroys
        something — and what it destroys is the hour before a crash."""
        answer = QMessageBox.question(
            self, t("gui.clear_log_title"),
            t("gui.clear_log_confirm", path=logs.path()),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        logs.clear()
        self._log_seen = None
        self.read_log()

    def _hardware_rows(self):
        """What the machine can do, asked the same way the CLI asks it.

        The imports are local because :mod:`audio_transcriber.hardware` only
        probes on demand: nothing heavy is loaded to draw this tab."""
        from ..backends import resolve_backend
        from ..diarization import NO_MODEL, NOT_INSTALLED, availability
        from ..hardware import summary
        from ..transcription import recommend_model

        device = self.settings.get("device") or "auto"
        try:
            backend = resolve_backend("auto", device)
        except SystemExit as exc:
            # No engine installed: the modules underneath say so the way a
            # command line does, and a tab must not take the window with it.
            return [(t("gui.row_machine"), summary()),
                    (t("gui.row_backend"), str(exc))]
        state, detail = availability(self.settings.get("diar_model"))
        diarization = t({NOT_INSTALLED: "gui.diar_missing",
                         NO_MODEL: "gui.diar_unconfigured"}.get(state, "gui.diar_ready"),
                        detail=detail)
        return [
            (t("gui.row_machine"), summary()),
            (t("gui.row_backend"), backend),
            (t("gui.row_model"), recommend_model(backend, device)),
            (t("gui.row_diarization"), diarization),
        ]

    # --- the meters -------------------------------------------------------

    def read_meters(self):
        """One reading, drawn. Called by the timer and once at build time."""
        reading = self.meter.read()
        cpu, ram = reading["cpu_percent"], reading["ram_percent"]
        # No number yet is not the same as no number ever: a meter that has
        # not covered an interval says it is reading, and one on a system
        # that counts no CPU time says that instead.
        waiting = t("gui.load_sampling") if self.meter.measurable \
            else t("gui.load_unmeasured")
        _draw(self.cpu_bar, self.cpu_reading, cpu,
              t("gui.cpu_reading", percent=round(cpu), cores=reading["cores"])
              if cpu is not None else waiting)
        _draw(self.ram_bar, self.ram_reading, ram,
              t("gui.ram_reading", used=gib(reading["ram_used_gb"]),
                total=gib(reading["ram_total_gb"]))
              if ram is not None else t("gui.load_unmeasured"))
        # Memory is the reading worth a colour: a job that runs out of it dies
        # halfway through, while a CPU at 100% is simply a CPU doing its job.
        paint_tight(self.ram_bar, ram is not None and ram >= TIGHT_PERCENT)
        self.load_note.setText(self._context(reading))

    def _context(self, reading):
        """The line under the bars: the run queue, and what is running where.

        A percentage says how hard something is working and never at what; on
        a machine with an iGPU that is the whole question. The engine and its
        device cannot change while the program runs, so they are asked once."""
        if not hasattr(self, "_engine"):
            from ..hardware import engine_in_use
            self._engine = engine_in_use(self.settings)
        engine, device = self._engine
        if engine is None:
            where = t("gui.engine_missing")
        elif device is None:
            where = t("gui.engine_only", engine=engine)
        else:
            where = t("gui.engine_on", engine=engine, device=device)
        queue = reading["load"]
        if queue is None:
            return where
        return t("gui.load_queue", load=f"{queue[0]:.2f}", where=where)

    # --- only while it is on screen ---------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        self.read_meters()
        self.read_log()
        self.sampler.start()

    def hideEvent(self, event):
        self.sampler.stop()
        super().hideEvent(event)

    def open_config(self):
        """Open ``config.toml`` in whatever the system uses for text files."""
        path = paths.config_file()
        if not os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(paths.ensure(paths.config_dir())))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def open_library(self):
        root = self.library.root if self.library is not None else paths.library_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(paths.ensure(root)))


def _value(text):
    """A read-only field the user can still select and copy."""
    label = QLabel(str(text))
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _meter_row(form, title):
    """A bar with its reading beside it, added to ``form`` as one row."""
    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(0)
    bar.setTextVisible(False)          # the number is next to it, in words
    bar.setFixedWidth(160)
    bar.setAccessibleName(title)       # a nameless bar announces a bare number
    reading = _value("")
    line = QHBoxLayout()
    line.addWidget(bar)
    line.addWidget(reading, 1)
    holder = QWidget()
    holder.setLayout(line)
    line.setContentsMargins(0, 0, 0, 0)
    form.addRow(f"{title}:", holder)
    return bar, reading


def _draw(bar, label, percent, text):
    """Draw one reading, or nothing at all when there is no number.

    A system that cannot say how busy it is gets an empty bar and a line
    saying so, rather than a zero that would read as an idle machine."""
    bar.setEnabled(percent is not None)
    bar.setValue(0 if percent is None else int(round(percent)))
    label.setText(text)



