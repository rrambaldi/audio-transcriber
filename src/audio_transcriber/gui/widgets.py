"""Small widgets the window needs and Qt does not have, and one errand.

Most of them come out of the same finding: the tab asked everything at once. A
:class:`Disclosure` puts what is rarely changed away without hiding that it
exists — the closed row says what is inside — and :class:`JobDelegate` gives
a queue row two lines and a drawing, so the facts about a recording, and the
shape of the recording itself, can sit under its title instead of in four
columns that are empty for most of a job's life. :class:`TraceMeter` is the
last few seconds of what a microphone is giving, beside the meter that says
how loud it is this instant.

They live here rather than in the panels because more than one tab wants them,
and a second copy is how two lists start looking different.
"""
import os
import subprocess
import sys

from PySide6.QtCore import QRectF, QSize, Qt, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QPainter,
    QPalette,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..i18n import t
from . import style, theme, wave

#: Where the second line of a queue row is kept.
DETAILS_ROLE = Qt.ItemDataRole.UserRole + 1

#: Where a row keeps the shape of its recording, when it has been measured.
LOUDNESS_ROLE = Qt.ItemDataRole.UserRole + 2


def reveal(path):
    """Show a file in the system's file manager, folder open around it.

    Opening the folder is the part every platform can do; *selecting* the file
    in it is what makes the difference between "here is a folder of
    recordings" and "here is the one you just made", and only Windows and
    macOS have a way to ask for it. Elsewhere — and whenever the file has
    moved on, which a recording does the moment its transcription files it —
    the folder alone is the honest answer.

    Returns the path actually opened, or None when there was nothing to open.
    """
    if not str(path or "").strip():
        # abspath("") is the working directory, which is nobody's recording.
        return None
    path = os.path.abspath(str(path))
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    if os.path.isfile(path):
        try:
            if sys.platform == "win32":
                # Explorer wants this exact spelling: no space after the
                # comma, and the path is not quoted by us because the list
                # form of subprocess does not go through a shell.
                subprocess.run(["explorer", f"/select,{path}"], check=False)
                return path
            if sys.platform == "darwin":
                subprocess.run(["open", "-R", path], check=False)
                return path
        except OSError:
            pass                    # no file manager: the folder still opens
    if not os.path.isdir(folder):
        return None
    QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
    return folder


def separator():
    """A hairline: what makes a column of sections read as one list."""
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Plain)
    return line


def separator_line():
    """The same, standing up: two things side by side in one box."""
    line = QFrame()
    line.setFrameShape(QFrame.Shape.VLine)
    line.setFrameShadow(QFrame.Shadow.Plain)
    return line


class Disclosure(QWidget):
    """A row in a list of sections: a title that opens onto its content.

    The whole left half of the Transcribe tab is built out of these, so what
    the closed row says is the whole design. Three rules come out of that:

    * closed still reports. "Keyword sets" tells you nothing; "Keyword sets —
      3 chosen" is the same row doing the job the open panel was doing.
    * a section that does not apply *stays* in the list, disabled, saying why.
      Removing it would mean the list changes shape under the pointer, and
      the reason a thing is unavailable is worth more than the space it costs.
    * it opens itself the moment it becomes applicable, because a section that
      has just started to matter should not need a second click.
    """

    #: How far the content is indented under its title.
    INDENT = 16

    def __init__(self, title, content, open_now=False, key=None, parent=None):
        super().__init__(parent)
        #: Name this section is remembered under between sessions.
        self.key = key
        self._title = title
        self._summary = ""
        self._reason = ""

        self.button = QToolButton()
        self.button.setCheckable(True)
        self.button.setAutoRaise(True)
        self.button.setArrowType(Qt.ArrowType.RightArrow)
        self.button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.button.setSizePolicy(QSizePolicy.Policy.MinimumExpanding,
                                  QSizePolicy.Policy.Fixed)
        self.button.toggled.connect(self._toggled)

        self.content = content
        self.content.setVisible(False)
        holder = QWidget()
        inside = QVBoxLayout(holder)
        inside.setContentsMargins(self.INDENT, 0, 0, 8)
        inside.addWidget(self.content)
        self._holder = holder
        holder.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self.button)
        layout.addWidget(separator())
        layout.addWidget(holder)
        self._retitle()
        self.set_open(open_now)

    # --- what the row says -------------------------------------------------

    def set_summary(self, summary):
        """What the row says after its title when it is closed."""
        self._summary = summary or ""
        self._retitle()

    def _retitle(self):
        """Compose the row's text, and cut it to the width there is.

        A QToolButton does not elide, so a long summary — "3 · How to
        transcribe them — auto (small on this machine) · Italian (it) · auto"
        — used to widen the whole column past the window and put a horizontal
        scrollbar under a list of five rows. The full text stays in the
        tooltip."""
        note = self._reason or self._summary
        self._full = f"{self._title} — {note}" if note else self._title
        self.button.setToolTip(self._full if note else "")
        room = self.button.width() - self.INDENT * 2
        if room <= 0:
            self.button.setText(self._full)
            return
        self.button.setText(
            self.button.fontMetrics().elidedText(self._full,
                                                 Qt.TextElideMode.ElideRight,
                                                 room))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._retitle()

    # --- whether it applies at all ----------------------------------------

    def set_available(self, available, reason=""):
        """Enable the section, or disable it and say why in its own row.

        Opens it when it becomes available: a section that has just started
        to matter should not need a second click to be read."""
        was = self.button.isEnabled()
        self._reason = "" if available else reason
        self.button.setEnabled(bool(available))
        if not available:
            self.set_open(False)
        elif not was:
            self.set_open(True)
        self._retitle()

    def is_available(self):
        return self.button.isEnabled()

    # --- open and closed ---------------------------------------------------

    def _toggled(self, open_now):
        self.button.setArrowType(Qt.ArrowType.DownArrow if open_now
                                 else Qt.ArrowType.RightArrow)
        self._holder.setVisible(open_now)
        self.content.setVisible(open_now)

    def is_open(self):
        return self.button.isChecked()

    def set_open(self, open_now):
        self.button.setChecked(bool(open_now) and self.button.isEnabled())


class TraceMeter(QWidget):
    """The last few seconds of one source, drawn.

    Beside the level meter and not instead of it: the meter answers "is
    anything arriving at all", which is one question, and this answers "is
    that a voice or is that the room", which is another. A bar holding steady
    at two thirds and a bar moving with every syllable are the same bar.
    """

    #: Room for five seconds at a glance, and no more: it shares a line with
    #: the source menus, the buttons and the meter it belongs to.
    WIDTH_PX = 108
    HEIGHT_PX = 22

    def __init__(self, parent=None):
        super().__init__(parent)
        self._values = []
        self.setFixedSize(self.WIDTH_PX, self.HEIGHT_PX)
        self.setToolTip(t("gui.rec_trace_tip"))
        self.setAccessibleName(t("gui.rec_trace_name"))

    def show_trail(self, values):
        """Take one reading of the capture's trace, and redraw if it moved."""
        values = [float(value) for value in (values or [])]
        if values == self._values:
            return
        self._values = values
        self.update()

    def paintEvent(self, event):
        if not self._values:
            return
        painter = QPainter(self)
        # Highlight is this palette's accent — the same blue the level meter
        # fills with — so the trace and the bar beside it are one instrument.
        wave.draw_trace(painter, QRectF(self.rect()), self._values,
                        QColor(self.palette().color(QPalette.ColorRole.Highlight)))
        painter.end()


class JobDelegate(QStyledItemDelegate):
    """Paints a queue row as a title with its facts underneath.

    A delegate rather than a widget in the cell because a widget does not
    follow the view's palette: the moment a row is selected, a black title on
    the selection colour is unreadable. Here the two lines are drawn with the
    colours the style hands over, so selection, hover and disabled all keep
    working."""

    #: Space above and below the pair of lines.
    PADDING = 6

    #: How much larger the title is than the facts under it. The page sets a
    #: row title at 1.15rem against a 0.85rem meta line.
    TITLE_SCALE = 1.15

    #: Height of the drawing under the facts. Room to read a shape in, and no
    #: more: this is a row in a list, not a waveform editor. The space is
    #: reserved whether or not the measurement has arrived, because a row that
    #: grows taller under the pointer when it does is worse than a row with a
    #: gap in it for a second.
    WAVE_PX = 18

    #: Air between the facts and the drawing, so the two read as two things.
    WAVE_GAP = 3

    def paint(self, painter, option, index):
        details = index.data(DETAILS_ROLE)
        if not details:
            super().paint(painter, option, index)
            return

        settings = QStyleOptionViewItem(option)
        self.initStyleOption(settings, index)
        title = settings.text
        settings.text = ""              # the background and selection only
        widget = settings.widget
        painting = widget.style() if widget else QApplication.style()
        painting.drawControl(QStyle.ControlElement.CE_ItemViewItem,
                             settings, painter, widget)

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        # The ink is the same whether the row is selected or not, because the
        # selection is a *wash* of the accent rather than the accent itself:
        # gui/theme.py paints a selected row in signal-wash and leaves the
        # text as it was. Reaching for HighlightedText here — the colour meant
        # for writing on the full accent — put a pale title on a pale ground
        # and made the selected row the one row nobody could read.
        ink = settings.palette.color(QPalette.ColorRole.Text)
        painter.save()
        painter.setPen(ink)
        area = settings.rect.adjusted(4, self.PADDING, -4, -self.PADDING)
        # The title in the serif, the facts under it in the interface face:
        # the same pair the web page's rows are set in.
        painter.setFont(theme.title_font(settings.font, self.TITLE_SCALE,
                                         weight=QFont.Weight.DemiBold))
        metrics = painter.fontMetrics()
        line = metrics.height()
        painter.drawText(
            area.left(), area.top(), area.width(), line,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            metrics.elidedText(title, Qt.TextElideMode.ElideRight, area.width()))
        # The second line is the same ink, muted as far as it can be while
        # still reading — on the selection colour too, which is why it is
        # mixed with the background actually behind it.
        # Midlight is where palette() keeps that wash, so the muting of the
        # second line is measured against the ground actually behind it.
        ground = settings.palette.color(QPalette.ColorRole.Midlight if selected
                                        else QPalette.ColorRole.Base)
        painter.setPen(style.readable(ink, ground))
        painter.setFont(settings.font)
        facts = painter.fontMetrics()
        painter.drawText(
            area.left(), area.top() + line, area.width(), facts.height(),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            facts.elidedText(details, Qt.TextElideMode.ElideRight, area.width()))
        # And the recording itself, in the colour the facts are set in: it
        # belongs with them, under the name, not over it.
        loudness = index.data(LOUDNESS_ROLE)
        if loudness:
            wave.draw_wave(painter,
                           QRectF(area.left(),
                                  area.top() + line + facts.height() + self.WAVE_GAP,
                                  area.width(), self.WAVE_PX - self.WAVE_GAP),
                           loudness, painter.pen().color())
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        if not index.data(DETAILS_ROLE):
            return size
        settings = QStyleOptionViewItem(option)
        self.initStyleOption(settings, index)
        title = theme.title_font(settings.font, self.TITLE_SCALE)
        line = QFontMetrics(title).height() + settings.fontMetrics.height()
        return QSize(size.width(), line + self.WAVE_PX + self.PADDING * 2)




class WaveTitleDelegate(QStyledItemDelegate):
    """Paints a library title with the shape of its recording under it.

    The library is a table and not a list of two-line rows, because the date,
    the length and the model are worth a column each there. So the drawing
    goes where the name is, under it, in the one column wide enough to hold a
    picture — which is also where somebody looking for a recording is already
    looking.
    """

    #: Space above and below the pair.
    PADDING = 3

    #: Height of the drawing. The same figure as :class:`JobDelegate`, and for
    #: the same reason: the queue and the library are one list seen twice.
    WAVE_PX = JobDelegate.WAVE_PX

    #: Air between the name and the drawing.
    WAVE_GAP = JobDelegate.WAVE_GAP

    def paint(self, painter, option, index):
        settings = QStyleOptionViewItem(option)
        self.initStyleOption(settings, index)
        title = settings.text
        settings.text = ""              # the background and selection only
        widget = settings.widget
        painting = widget.style() if widget else QApplication.style()
        painting.drawControl(QStyle.ControlElement.CE_ItemViewItem,
                             settings, painter, widget)

        area = settings.rect.adjusted(4, self.PADDING, -4, -self.PADDING)
        ink = settings.palette.color(QPalette.ColorRole.Text)
        painter.save()
        painter.setPen(ink)
        painter.setFont(settings.font)
        metrics = painter.fontMetrics()
        line = metrics.height()
        painter.drawText(
            area.left(), area.top(), area.width(), line,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            metrics.elidedText(title, Qt.TextElideMode.ElideRight, area.width()))
        loudness = index.data(LOUDNESS_ROLE)
        if loudness:
            # Muted against the ground actually behind it, so a selected row
            # keeps its drawing instead of losing it into the wash.
            selected = bool(option.state & QStyle.StateFlag.State_Selected)
            ground = settings.palette.color(QPalette.ColorRole.Midlight if selected
                                            else QPalette.ColorRole.Base)
            wave.draw_wave(painter,
                           QRectF(area.left(), area.top() + line + self.WAVE_GAP,
                                  area.width(), self.WAVE_PX - self.WAVE_GAP),
                           loudness, style.readable(ink, ground))
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(size.width(), size.height() + self.WAVE_PX)


class JobActions(QWidget):
    """The three things you can do to one recording, on its own row.

    They used to be four buttons under the table that acted on whatever was
    selected, which is one more step ("select, then press") and one more
    thing to get wrong (pressing them with nothing selected, or with the
    wrong row selected). On the row there is no selection to be wrong about.

    What the first button does depends on the state, because "start it" and
    "stop it" are the same place in the row and never both apply.

    They are push buttons, and the reason is worth writing down: the
    first version used ``QToolButton``, whose default style is
    *ToolButtonIconOnly*. With no icon and ``autoRaise`` on, the Fusion style
    drew the text anyway and the Windows one drew nothing at all — three
    invisible buttons in a column that was the right width, on the only
    platform that mattered. A push button draws its label on every style
    there is.
    """

    #: The recording's id, so the panel does not have to work out which row.
    transcribe = Signal(str)
    remove = Signal(str)
    play = Signal(str)

    def __init__(self, job_id, parent=None):
        super().__init__(parent)
        self.job_id = job_id
        self.run = QPushButton()
        self.listen = QPushButton()
        self.drop = QPushButton()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)
        for button, signal in ((self.run, self.transcribe),
                               (self.listen, self.play),
                               (self.drop, self.remove)):
            # Otherwise Enter in the table presses whichever of these has the
            # focus instead of the one button the tab is for.
            button.setAutoDefault(False)
            button.clicked.connect(
                lambda _checked=False, s=signal: s.emit(self.job_id))
            layout.addWidget(button)
        layout.addStretch(1)

    def update_for(self, row, playing=False, playable=True, reason=""):
        """Say what this row's buttons do now, for the state it is in."""
        self.run.setText(row["action"])
        self.run.setEnabled(bool(row["action"]))
        self.run.setVisible(bool(row["action"]))
        self.drop.setText(row["removable_label"])
        self.drop.setEnabled(row["removable"])
        self.listen.setText(row["stop_audio"] if playing else row["play_audio"])
        self.listen.setEnabled(playable)
        self.listen.setToolTip("" if playable else reason)
