"""How busy this machine is, drawn small enough to leave on screen.

The same two readings the *This machine* tab shows in full — the CPU and the
memory — compressed to what fits in the window's footer, next to a status
message, where they can be watched while a transcription runs instead of
being somewhere you have to go and look.

There is deliberately no GPU percentage. OpenVINO publishes no utilisation
figure, so the honest answer to "and the graphics chip?" is the name of the
device a run would use, which is what the line ends with.
"""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QWidget

from ..hardware import Meter
from ..i18n import t
from . import style

#: How often the meters are read. Slower than a progress bar on purpose: this
#: is the background a job runs against, not the job.
SAMPLE_MS = 2000

#: Memory left below which the bar turns to the alarm colour. A model loads in
#: one go: at nine tenths full the next job is the one that does not fit.
TIGHT_PERCENT = 90


def gib(value):
    """Gibibytes to one decimal, or a dash when the figure is missing."""
    return "-" if value is None else f"{value:.1f}"


def bar(width):
    """A wordless meter: read as a length, with the number beside it."""
    meter = QProgressBar()
    meter.setRange(0, 100)
    meter.setValue(0)
    meter.setTextVisible(False)
    meter.setFixedWidth(width)
    return meter


def paint_tight(meter, tight):
    """Turn a bar to the alarm colour, or back, without repainting the world."""
    if meter.property("tight") != tight:
        meter.setProperty("tight", tight)
        meter.style().polish(meter)


class MachineMeters(QWidget):
    """CPU, memory and the device in use, on one line.

    ``meter`` is shared with whoever else is drawing the same numbers, so two
    places on screen never disagree about how busy the machine is.
    """

    #: Width of each bar in the footer. Room for the numbers matters more than
    #: room for the bars: a status line is not a dashboard.
    BAR_PX = 54

    def __init__(self, meter=None, settings=None, parent=None):
        super().__init__(parent)
        self.settings = dict(settings or {})
        self.meter = meter or Meter()
        self._engine = None

        self.cpu = bar(self.BAR_PX)
        self.cpu.setAccessibleName(t("gui.row_cpu"))
        self.ram = bar(self.BAR_PX)
        self.ram.setAccessibleName(t("gui.row_ram"))
        self.cpu_text = QLabel("")
        self.ram_text = QLabel("")
        self.device = QLabel("")
        self.setToolTip(t("gui.meter_tip"))

        line = QHBoxLayout(self)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        # Each number beside the bar it belongs to. Both numbers after both
        # bars reads as one four-part thing nobody can pair up at a glance.
        for name, meter_bar, reading in ((t("gui.row_cpu"), self.cpu, self.cpu_text),
                                         (t("gui.row_ram"), self.ram, self.ram_text)):
            label = QLabel(name)
            line.addWidget(style.note(label))
            line.addWidget(meter_bar)
            line.addWidget(style.note(reading))
        line.addWidget(style.note(self.device))

        self.timer = QTimer(self)
        self.timer.setInterval(SAMPLE_MS)
        self.timer.timeout.connect(self.refresh)
        self.refresh()

    # --- the reading ------------------------------------------------------

    def refresh(self):
        """One reading, drawn. Nothing measured means nothing drawn."""
        reading = self.meter.read()
        cpu, ram = reading["cpu_percent"], reading["ram_percent"]
        for meter_bar, value in ((self.cpu, cpu), (self.ram, ram)):
            meter_bar.setEnabled(value is not None)
            meter_bar.setValue(0 if value is None else int(round(value)))
        paint_tight(self.ram, ram is not None and ram >= TIGHT_PERCENT)
        self.cpu_text.setText("" if cpu is None else f"{round(cpu)}%")
        self.ram_text.setText("" if ram is None else
                              f"{gib(reading['ram_used_gb'])}/"
                              f"{gib(reading['ram_total_gb'])} GiB")
        self.device.setText(self._device_line())

    def _device_line(self):
        """What a transcription would run on. Asked once: it cannot change."""
        if self._engine is None:
            from ..hardware import engine_in_use

            self._engine = engine_in_use(self.settings)
        engine, device = self._engine
        if engine is None:
            return t("gui.engine_missing")
        if device is None:
            return engine
        return t("gui.meter_device", engine=engine, device=device)

    # --- only while it is on screen ---------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
        self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)
