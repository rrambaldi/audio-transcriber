"""The band above the tabs: the mark, the name, and what the program promises.

The web page opens with the mark next to the title and one line under it —
"Local transcription. Nothing leaves this machine." — and the window had
neither: the icon was in the title bar, where a maximised window on Windows
shows it 16 px wide and where a tiling desktop shows it not at all, and the
promise was nowhere. Somebody who has the window open all day should be able
to see whose program it is and what it does *without* the title bar.

It is the page's masthead, in the same three lines and the same two faces:
the eyebrow in the letter-spaced sans, the name in Fraunces, the promise under
it in Fraunces italic and the brand's muted ink. The rule underneath is the
page's too — ``border-bottom: 1px solid var(--ink)`` — which is what makes the
band read as a masthead rather than as the first panel of the window. See
:mod:`audio_transcriber.gui.theme`.
"""
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPalette
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, branding
from ..i18n import t
from . import style, theme

#: How tall the mark is drawn, in logical pixels. At 40 the 48 px render is
#: the one Qt picks on a 1x screen and the 128 px one at 2x, so the drawing is
#: always downscaled from a larger render rather than blown up from a smaller.
MARK_PX = 40

#: How much larger than the interface font the name is. A ratio rather than a
#: point size: the desktop's own font size is somebody's decision, often an
#: accessibility one, and this has to grow with it.
NAME_SCALE = theme.TITLE_SCALE

#: And the promise under it, which the page sets at about 1.1rem against a
#: 0.72rem eyebrow.
TAGLINE_SCALE = 1.05

#: Below this relative luminance the window's background counts as dark, and
#: the mark is drawn without its plate. Halfway is where the plate - a very
#: dark navy - stops being a shape on the background and becomes a smudge of
#: almost the same colour with rounded corners.
DARK_GROUND = 0.5


def mark_pixmap(icon, widget, size=MARK_PX):
    """The mark at ``size`` logical pixels, sharp on a high-DPI screen.

    Qt is asked for the pixel size the screen actually has and then told what
    the ratio was, which is what makes it choose the 128 px render on a
    retina display instead of scaling the 48 px one.

    Which of the two drawings it renders depends on the theme: see
    :func:`drawing_for`."""
    ratio = widget.devicePixelRatioF() or 1.0
    edge = max(1, round(size * ratio))
    pixmap = drawing_for(icon, widget).pixmap(QSize(edge, edge))
    if pixmap.isNull():
        # The plateless drawing is an SVG and Qt's SVG plugin is not always
        # there. The renders always are.
        pixmap = icon.pixmap(QSize(edge, edge))
    if not pixmap.isNull():
        pixmap.setDevicePixelRatio(ratio)
    return pixmap


def drawing_for(icon, widget):
    """The mark on its plate, or the plateless one on a dark theme.

    The plate is a very dark navy, drawn to lift the mark off a light page.
    On a desktop that is already dark it does the opposite: it sinks into the
    background, leaving a rounded square of nearly-the-window-colour around
    the lock. ``icon-mark.svg`` exists for that background — the brand's own
    answer to it, not a second drawing invented here."""
    ground = widget.palette().color(QPalette.ColorRole.Window)
    if style.luminance(ground) >= DARK_GROUND:
        return icon
    return QIcon(branding.path(branding.MARK_SVG))


class Masthead(QWidget):
    """Mark, name and tagline on the left; the version on the right.

    The version is here as well as in the title bar because this is the line
    somebody reads out over the phone when a transcription went wrong, and a
    maximised window on Windows has no title bar text to read from."""

    def __init__(self, icon=None, parent=None):
        super().__init__(parent)

        # A picture and no text, which is the desktop equivalent of the web
        # page's empty alt: the name is written next to it, and a screen
        # reader that read both would say it twice.
        self.mark = QLabel()
        self.mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if icon is not None and not icon.isNull():
            self.mark.setPixmap(mark_pixmap(icon, self))
            self._icon = icon
        else:
            # A build with no icon files: the band still reads as a masthead,
            # it just has no picture in it. See branding.icon_files().
            self._icon = None
            self.mark.setVisible(False)

        self.eyebrow = QLabel(t("gui.eyebrow"))
        self.eyebrow.setFont(theme.label_font(self.font()))
        style.note(self.eyebrow)

        self.name = QLabel(t("gui.app_name"))
        self.name.setFont(theme.title_font(self.font(), NAME_SCALE))

        self.tagline = QLabel(t("gui.tagline"))
        self.tagline.setWordWrap(True)
        self.tagline.setFont(theme.title_font(self.font(), TAGLINE_SCALE,
                                              italic=True))
        style.note(self.tagline)

        self.version = QLabel(f"v{__version__}")
        self.version.setFont(theme.label_font(self.font()))
        self.version.setAlignment(Qt.AlignmentFlag.AlignRight
                                  | Qt.AlignmentFlag.AlignVCenter)
        style.note(self.version)

        titles = QVBoxLayout()
        titles.setContentsMargins(0, 0, 0, 0)
        titles.setSpacing(2)
        titles.addWidget(self.eyebrow)
        titles.addWidget(self.name)
        titles.addWidget(self.tagline)

        band = QHBoxLayout()
        band.setContentsMargins(12, 10, 12, 8)
        band.setSpacing(12)
        band.addWidget(self.mark, 0, Qt.AlignmentFlag.AlignVCenter)
        band.addLayout(titles, 1)
        band.addWidget(self.version, 0, Qt.AlignmentFlag.AlignTop)

        # The page draws this rule in the ink colour, not in the divider grey:
        # it is the edge of the masthead, and the tab bar below has a grey one
        # of its own. Without it the band reads as the first panel.
        self.rule = QFrame()
        self.rule.setFrameShape(QFrame.Shape.HLine)
        self.rule.setFrameShadow(QFrame.Shadow.Plain)
        self.rule.setFixedHeight(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(band)
        layout.addWidget(self.rule)
        self.setObjectName("masthead")
        self._paint_rule()

    def changeEvent(self, event):
        """Redraw the mark when the desktop changes theme under us.

        Both GNOME and Windows switch between light and dark without
        restarting anything, and Qt hands the change over as a palette event.
        Without this the plate would be right at start-up and wrong for the
        rest of the day."""
        super().changeEvent(event)
        # The band is built in this order, and Qt can deliver the event
        # before the last of it exists.
        if event.type() != event.Type.PaletteChange or not hasattr(self, "version"):
            return
        if self._icon is not None:
            self.mark.setPixmap(mark_pixmap(self._icon, self))
        for label in (self.eyebrow, self.tagline, self.version):
            style.note(label)
        self._paint_rule()

    def _paint_rule(self):
        """The rule under the band, and the hairline round the mark.

        The rule is drawn in the ink colour because it is the edge of the
        masthead, not a divider inside it - the page draws the same one.

        The ring round the mark is the page's too, and it is drawn only on the
        light scheme: it exists because the plate's own colour is nearly the
        dark ground, so the tile needs an edge to be a tile at all. On the
        dark scheme the mark has no plate to give an edge to - the plateless
        drawing is used there - and a ring would be a box round nothing."""
        ink = self.palette().color(QPalette.ColorRole.WindowText).name()
        self.rule.setStyleSheet(f"background: {ink}; border: none;")
        which = "dark" if self.palette().color(
            QPalette.ColorRole.Window).lightnessF() < 0.5 else "light"
        if which == "dark":
            self.mark.setStyleSheet("")
        else:
            self.mark.setStyleSheet(
                f"border: 1px solid {theme.colour('rule', which).name()};"
                f" border-radius: {round(MARK_PX * 0.22)}px;")
