"""Two small widgets the window needs and Qt does not have.

Both come out of the same finding: the tab asked everything at once. A
:class:`Disclosure` puts what is rarely changed away without hiding that it
exists — the closed row says what is inside — and :class:`JobDelegate` gives
a queue row two lines, so the facts about a recording can sit under its title
instead of in four columns that are empty for most of a job's life.

They live here rather than in the panel because the library tab wants the
same two things, and a second copy is how two lists start looking different.
"""
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import style

#: Where the second line of a queue row is kept.
DETAILS_ROLE = Qt.ItemDataRole.UserRole + 1


def separator():
    """A hairline: what makes a column of sections read as one list."""
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
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


class JobDelegate(QStyledItemDelegate):
    """Paints a queue row as a title with its facts underneath.

    A delegate rather than a widget in the cell because a widget does not
    follow the view's palette: the moment a row is selected, a black title on
    the selection colour is unreadable. Here the two lines are drawn with the
    colours the style hands over, so selection, hover and disabled all keep
    working."""

    #: Space above and below the pair of lines.
    PADDING = 6

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
        role = (QPalette.ColorRole.HighlightedText if selected
                else QPalette.ColorRole.Text)
        ink = settings.palette.color(role)
        painter.save()
        painter.setPen(ink)
        area = settings.rect.adjusted(4, self.PADDING, -4, -self.PADDING)
        metrics = painter.fontMetrics()
        line = metrics.height()
        painter.drawText(
            area.left(), area.top(), area.width(), line,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            metrics.elidedText(title, Qt.TextElideMode.ElideRight, area.width()))
        # The second line is the same ink, muted as far as it can be while
        # still reading — on the selection colour too, which is why it is
        # mixed with the background actually behind it.
        ground = settings.palette.color(QPalette.ColorRole.Highlight if selected
                                        else QPalette.ColorRole.Base)
        painter.setPen(style.readable(ink, ground))
        painter.drawText(
            area.left(), area.top() + line, area.width(), line,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            metrics.elidedText(details, Qt.TextElideMode.ElideRight, area.width()))
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        if not index.data(DETAILS_ROLE):
            return size
        settings = QStyleOptionViewItem(option)
        self.initStyleOption(settings, index)
        line = settings.fontMetrics.height()
        return QSize(size.width(), line * 2 + self.PADDING * 2)


