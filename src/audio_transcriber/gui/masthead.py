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
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont, QIcon, QPalette
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import branding
from ..i18n import LANGUAGE_NAMES, language, t
from . import style, symbols, theme

#: How tall the mark is drawn, in logical pixels. The band is one line now -
#: it took 130 pixels of an 800-pixel laptop screen as three - so the mark is
#: sized to the name beside it, and 32 is a render Qt ships at 1x and 2x, so
#: it is always drawn from one rather than blown up.
MARK_PX = 32

#: How much larger than the interface font the name is. A ratio rather than a
#: point size: the desktop's own font size is somebody's decision, often an
#: accessibility one, and this has to grow with it. Large enough to be the
#: name of the program, small enough to share a line with its promise.
NAME_SCALE = 1.8

#: And the promise beside it: a hair over the interface font, no more. It is
#: a line to be read once, next to a name that is meant to be seen.
TAGLINE_SCALE = 1.05

#: The weight of that italic: regular, which is what the page sets. The italic
#: itself is synthesised, here and on the page - neither has an italic face of
#: this typeface to draw from.
TAGLINE_WEIGHT = QFont.Weight.Normal

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

    The way into the About box is here, on the right, because the window has
    no menu bar to hide one behind. The version number used to sit next to it
    and does not any more: it belongs with the licence and the rest of what
    this program is, one click away, rather than on a band somebody reads all
    day. The title bar still carries it, for reading out over the phone."""

    #: The version was clicked: the window should show the About box.
    about_requested = Signal()

    #: "This machine" was clicked: the window should show what it knows.
    system_requested = Signal()

    #: A language was picked from the menu under it, by its code.
    language_chosen = Signal(str)

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

        self.name = QLabel(t("gui.wordmark"))
        # The page's own h1: the display cut of the serif, at display size,
        # tracked in a little. See theme.title_font.
        self.name.setFont(theme.title_font(self.font(), NAME_SCALE,
                                           display=theme.DISPLAY,
                                           tracking=theme.TITLE_TRACKING))

        self.tagline = QLabel(t("gui.tagline"))
        # On the name's line, and the first thing to give way when the window
        # is narrow: it is cut rather than allowed to widen the window.
        self.tagline.setSizePolicy(QSizePolicy.Policy.Ignored,
                                   QSizePolicy.Policy.Preferred)
        # Regular, not medium: the page's standfirst sets no weight, and at
        # this size the serif's italic is meant to be read, not announced.
        self.tagline.setFont(theme.title_font(self.font(), TAGLINE_SCALE,
                                              italic=True,
                                              weight=TAGLINE_WEIGHT))
        style.note(self.tagline)

        # Links rather than buttons: in the masthead a bordered button would
        # read as an action on the recordings, which neither is. What this
        # machine can do is here too, and no longer a tab beside the library:
        # it is looked at once, when something does not work, not all day.
        self.system = self._link("#system", t("gui.system_link"),
                                 t("gui.system_open_tip"), self.system_requested)
        self.about = self._link("#about", t("about.open"), t("about.open_tip"),
                                self.about_requested)

        # Each language by its own name, under the About link: the other
        # thing somebody looks for in a corner of a window, and the one a
        # reader who cannot read the current language has to be able to find.
        self.language = QComboBox()
        for code, name in LANGUAGE_NAMES.items():
            self.language.addItem(name, code)
        self.language.setCurrentIndex(max(0, self.language.findData(language())))
        self.language.setToolTip(t("gui.language"))
        self.language.setAccessibleName(t("gui.language"))
        self.language.currentIndexChanged.connect(
            lambda _index: self.language_chosen.emit(self.language.currentData()))

        # One line: the mark, the name, the promise, and on the right the two
        # links and the language. The eyebrow is kept for whoever reads it
        # from code, and not shown: on one line it said the name twice.
        self.eyebrow.hide()
        band = QHBoxLayout()
        # The same side gutter the panels get, so the mark and the library's
        # first button start on one line.
        band.setContentsMargins(theme.GUTTER, 8, theme.GUTTER, 8)
        band.setSpacing(14)
        band.addWidget(self.mark, 0, Qt.AlignmentFlag.AlignVCenter)
        band.addWidget(self.name, 0, Qt.AlignmentFlag.AlignVCenter)
        band.addWidget(self.tagline, 1, Qt.AlignmentFlag.AlignVCenter)
        # Each link with its symbol, the way every button has one: a gear-less
        # desktop for the machine, an "i" for what the program is.
        self.system_icon, self.about_icon = QLabel(), QLabel()
        for icon, link in ((self.system_icon, self.system),
                           (self.about_icon, self.about)):
            pair = QHBoxLayout()
            pair.setSpacing(4)
            pair.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)
            pair.addWidget(link, 0, Qt.AlignmentFlag.AlignVCenter)
            band.addLayout(pair)
        # The language with its symbol too, the translation mark: it is the
        # one control here somebody who cannot read the current language has
        # to find.
        self.language_icon = QLabel()
        pair = QHBoxLayout()
        pair.setSpacing(4)
        pair.addWidget(self.language_icon, 0, Qt.AlignmentFlag.AlignVCenter)
        pair.addWidget(self.language, 0, Qt.AlignmentFlag.AlignVCenter)
        band.addLayout(pair)
        self._paint_icons()

        # The page draws this rule in the ink colour, not in the divider grey:
        # it is the edge of the masthead, and the tab bar below has a grey one
        # of its own. Without it the band reads as the first panel.
        self.rule = QFrame()
        self.rule.setFrameShape(QFrame.Shape.HLine)
        self.rule.setFrameShadow(QFrame.Shadow.Plain)
        self.rule.setFixedHeight(1)

        # The rule is held off the frame like everything else: on the page it
        # is the bottom edge of the masthead, and the masthead sits in the
        # page's own gutter rather than running out to the window frame.
        ruled = QHBoxLayout()
        ruled.setContentsMargins(theme.GUTTER, 0, theme.GUTTER, 0)
        ruled.addWidget(self.rule)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(band)
        layout.addLayout(ruled)
        self.setObjectName("masthead")
        self._paint_rule()
        self._paint_link()

    def changeEvent(self, event):
        """Redraw the mark when the desktop changes theme under us.

        Both GNOME and Windows switch between light and dark without
        restarting anything, and Qt hands the change over as a palette event.
        Without this the plate would be right at start-up and wrong for the
        rest of the day."""
        super().changeEvent(event)
        # The band is built in this order, and Qt can deliver the event
        # before the last of it exists.
        if event.type() != event.Type.PaletteChange or not hasattr(self, "about"):
            return
        if self._icon is not None:
            self.mark.setPixmap(mark_pixmap(self._icon, self))
        for label in (self.eyebrow, self.tagline, self.about, self.system):
            style.note(label)
        self._paint_link()
        self._paint_rule()
        self._paint_icons()

    def _paint_icons(self):
        """The links' symbols, in the accent the links are written in."""
        if not hasattr(self, "language_icon"):
            return
        which = "dark" if self.palette().color(
            QPalette.ColorRole.Window).lightnessF() < 0.5 else "light"
        size = max(symbols.MINIMUM, round(self.about.fontMetrics().height() * symbols.BESIDE))
        for label, name, token in ((self.system_icon, "desktop", "signal"),
                                   (self.about_icon, "info", "signal"),
                                   (self.language_icon, "language", "ink")):
            drawn = symbols.icon(name, size, which, ratio=self.devicePixelRatioF(),
                                 normal=token)
            label.setPixmap(drawn.pixmap(QSize(size, size)))
            label.setVisible(not drawn.isNull())

    def _link(self, href, text, tip, signal):
        link = QLabel(f'<a href="{href}">{text}</a>')
        link.setFont(theme.label_font(self.font()))
        link.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        link.setToolTip(tip)
        link.setOpenExternalLinks(False)
        link.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard)
        link.setCursor(Qt.CursorShape.PointingHandCursor)
        link.linkActivated.connect(lambda _href: signal.emit())
        style.note(link)
        return link

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

    def _paint_link(self):
        """The accent, for the one link in the window.

        A note's ink is written into the widget's own style sheet, and Qt
        draws a link in the palette's link colour unless a style sheet says
        otherwise - which ours does, for the surrounding text. So the link
        colour is put back here, explicitly, in the accent it should be."""
        which = "dark" if self.palette().color(
            QPalette.ColorRole.Window).lightnessF() < 0.5 else "light"
        signal = theme.colour("signal", which).name()
        for link in (self.about, self.system):
            ink = style.note_colour(link).name()
            link.setStyleSheet(
                f"color: {ink}; a {{ color: {signal}; text-decoration: none; }}")
