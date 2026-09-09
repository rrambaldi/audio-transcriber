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


class Disclosure(QWidget):
    """A titled row that opens onto its content, and says what is inside.

    Closed is the point: the keyword sets are nineteen rows that matter on
    the third transcription, not the first, and they were taking a third of
    the window before anything had been chosen. What a collapsed panel must
    never do is hide that a choice was made, so the title carries the summary
    — "Keyword sets — 3 chosen" — and the panel opens itself when there is
    something to see."""

    def __init__(self, title, content, parent=None):
        super().__init__(parent)
        self._title = title
        self.button = QToolButton()
        self.button.setCheckable(True)
        self.button.setChecked(False)
        self.button.setAutoRaise(True)
        self.button.setArrowType(Qt.ArrowType.RightArrow)
        self.button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.button.toggled.connect(self._toggled)

        self.content = content
        self.content.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.button)
        layout.addWidget(self.content)
        self.set_summary("")

    def set_summary(self, summary):
        """What the closed row says after the title."""
        self.button.setText(f"{self._title} — {summary}" if summary else self._title)

    def _toggled(self, open_now):
        self.button.setArrowType(Qt.ArrowType.DownArrow if open_now
                                 else Qt.ArrowType.RightArrow)
        self.content.setVisible(open_now)

    def is_open(self):
        return self.button.isChecked()

    def set_open(self, open_now):
        self.button.setChecked(bool(open_now))


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


def separator():
    """A hairline, for the places a box would be too much."""
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Plain)
    return line
