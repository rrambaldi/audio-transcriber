"""The little drawings on buttons, painted in the window's own ink.

A button here says what it does, in words, because that is what the page does
and because a word needs no legend. The exceptions are the two that would
otherwise repeat themselves down a column - "rename" beside every title,
"copy" under every one of three panes - and those are drawn instead.

They used to be glyphs from the text font, which is the cheap way to have an
icon and looked it: a glyph is whatever weight the interface font happens to
draw it at (thin, at nine points, next to a hairline rule), some faces do not
have it at all, and no two platforms agree how much of the em it should fill.
So they are drawings now - :data:`branding.SYMBOLS`, Microsoft's Fluent set,
MIT - rendered here rather than shipped as pictures, and the difference is the
point of this module:

* **Ink, not black.** The file is recoloured on the way to the renderer, to
  whichever palette token the state calls for. A picture cannot follow a
  palette; a drawing re-rendered per scheme can, so the window switching to
  dark takes the symbols with it.
* **The font's size, not a fixed one.** Somebody who has set their interface
  font large did it to read, and a 16 px picture beside 20 px text is the
  detail that makes an interface look assembled from parts.
* **Three states, one drawing.** Normal is the ink, hover is the accent and
  disabled is the rule the button's own underline goes to - the same three
  colours the style sheet gives every other button, so these behave like
  buttons rather than like pictures that happen to be clickable.

Nothing here is required: a build without the files gets :data:`None` back and
:class:`Button` falls back to the glyph, exactly as a missing typeface falls
through to the next family in the stack.
"""
from PySide6.QtCore import QByteArray, QEvent, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QToolButton

from .. import branding
from . import theme

#: Which palette token each state is drawn in. Hover is the accent and
#: disabled is the rule, which is what ``theme.qss`` does to the underline of
#: every button in the window; normal is the ink of the text beside it.
STATES = ((QIcon.Mode.Normal, "ink"),
          (QIcon.Mode.Active, "signal"),
          (QIcon.Mode.Disabled, "rule"))

#: How large a symbol is, as a multiple of the interface font's line height.
#: Comfortably over it: a line height is the box a character is drawn *in*,
#: most of which is the space above and below it, so a drawing made exactly
#: that tall reads as smaller than the words beside it. This lands near the
#: 20 px the files are drawn for at a nine-point interface font.
SCALE = 1.35

#: What a symbol falls back to when the renderer is the one thing missing.
MINIMUM = 12

#: Rendered pixmaps, by everything that decides how one looks. Rendering an
#: SVG is not expensive, but a table redraw asks for the same symbol on every
#: row and a cache is four lines.
_rendered = {}


def render(name, size, colour, ratio=1.0):
    """One symbol as a pixmap: ``name`` at ``size`` points of ``colour``.

    ``None`` when the drawing did not ship. The recolour is a string
    substitution on the file's own ink - see :data:`branding.SYMBOL_INK` for
    why the files are not edited to say ``currentColor`` instead - and the
    pixmap is rendered at the screen's real pixel count and then told what it
    is, which is what keeps it sharp on a display that scales."""
    key = (name, size, colour, round(ratio, 2))
    if key in _rendered:
        return _rendered[key]
    path = branding.symbol_svg(name)
    if path is None:
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            drawing = handle.read()
    except OSError:                 # pragma: no cover - unreadable file
        return None
    drawing = drawing.replace(branding.SYMBOL_INK, colour)
    renderer = QSvgRenderer(QByteArray(drawing.encode("utf-8")))
    if not renderer.isValid():      # pragma: no cover - a damaged file
        return None
    pixels = max(MINIMUM, round(size * ratio))
    pixmap = QPixmap(pixels, pixels)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    _rendered[key] = pixmap
    return pixmap


def icon(name, size, which=None, ratio=1.0):
    """One symbol as a QIcon, with a pixmap for each of :data:`STATES`.

    A null icon - not an exception - when the drawing is not there, so that a
    caller can ask ``isNull()`` and draw its glyph instead."""
    which = which or theme.scheme(QApplication.instance())
    built = QIcon()
    for mode, token in STATES:
        pixmap = render(name, size, theme.colour(token, which).name(), ratio)
        if pixmap is None:
            return QIcon()
        built.addPixmap(pixmap, mode)
    return built


def size_for(widget):
    """How large a symbol should be beside ``widget``'s own text."""
    return max(MINIMUM, round(widget.fontMetrics().height() * SCALE))


def forget():
    """Drop the rendered pixmaps. For the tests, and for a change of screen."""
    _rendered.clear()


class Button(QToolButton):
    """A tool button that draws one symbol, and keeps it up to date.

    The icon is rebuilt on a palette change and on a font change, because it
    is a picture painted in a palette colour at a font's size and neither of
    those reaches a QPixmap on its own: without it, switching the desktop to
    dark leaves two dark-on-dark smudges where the buttons were.

    ``fallback`` is the glyph to draw when the drawing did not ship. It is
    set as *text only* on purpose: a QToolButton's default is icon-only, and
    with no icon to draw the Fusion style draws the text anyway while the
    Windows one draws nothing at all - an invisible button on the platform
    that has the problem. ``tests/test_gui_window.py`` holds the line.
    """

    def __init__(self, name, tooltip="", fallback="", parent=None):
        super().__init__(parent)
        self.symbol = name
        self.fallback = fallback
        self.setAutoRaise(True)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._redraw()

    def _redraw(self):
        """Ask for the symbol again, at this moment's palette and font."""
        wanted = size_for(self)
        drawn = icon(self.symbol, wanted, ratio=self.devicePixelRatioF())
        if drawn.isNull():
            self.setIcon(QIcon())
            self.setText(self.fallback)
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            return
        self.setText("")
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setIcon(drawn)
        # In device-independent pixels, which is what the pixmap was told its
        # ratio for: asking for its raw size here would draw it twice as
        # large on a display that scales.
        self.setIconSize(QSize(wanted, wanted))

    #: A palette change is the desktop switching scheme; a font change is
    #: somebody having resized the interface font, or a parent passing one
    #: down. Either one changes what the drawing should look like.
    WHEN = (QEvent.Type.PaletteChange, QEvent.Type.FontChange,
            QEvent.Type.ScreenChangeInternal)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in self.WHEN:
            self._redraw()
