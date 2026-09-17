"""The button symbols: somebody else's drawings, in this program's ink.

Two things here are worth a test and the rest is Qt's business. The first is
the recolour, because a symbol that does not follow the palette is invisible
in exactly one of the two schemes and visible in the one a developer happens
to be using. The second is the fallback: these files are package data and
package data goes missing, and the rule everywhere else in this program is
that a missing brand file is cosmetic — so a build without them must come out
with a legible button rather than an empty one.

The Windows trap is checked in ``test_gui_window.py`` for every button in the
window at once; what is checked here is that the fallback path specifically
sets a style that draws its text, since that is the path nobody sees.
"""
import os

import pytest

pytest.importorskip("PySide6", reason="the desktop window needs Qt")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QIcon, QPalette
    from PySide6.QtWidgets import QApplication
except ImportError as exc:      # pragma: no cover - depends on the machine
    pytest.skip(f"PySide6 cannot be loaded here: {exc}", allow_module_level=True)

from audio_transcriber import branding  # noqa: E402
from audio_transcriber.gui import style, symbols, theme  # noqa: E402


@pytest.fixture(scope="session")
def application():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def fresh(application):
    """The cache is module-wide, and these tests change what goes into it."""
    symbols.forget()
    before = (QPalette(application.palette()), QFont(application.font()),
              application.styleSheet())
    yield
    application.setPalette(before[0])
    application.setFont(before[1])
    application.setStyleSheet(before[2])
    symbols.forget()


#: How opaque a pixel has to be before it counts as painted. Not 255: these
#: drawings are hairlines at the size they are used, antialiased against
#: nothing, and at nineteen pixels a stroke can be almost entirely edge.
SOLID = 200


def inks(pixmap):
    """The colours actually painted, commonest first, ignoring the faint edges."""
    image = pixmap.toImage()
    seen = {}
    for y in range(image.height()):
        for x in range(image.width()):
            colour = image.pixelColor(x, y)
            if colour.alpha() >= SOLID:
                seen[colour.name()] = seen.get(colour.name(), 0) + 1
    return [name for name, _count in sorted(seen.items(),
                                            key=lambda pair: -pair[1])]


# --- the drawings themselves ----------------------------------------------

def test_every_named_symbol_shipped():
    for name, file in branding.SYMBOLS:
        assert branding.symbol_svg(name) == branding.symbol_path(file)


def test_the_licence_travels_with_them():
    """MIT asks for the notice to go with the copies. This is the copy."""
    _set, licence = branding.SYMBOL_SET
    path = branding.symbol_path(licence)
    assert os.path.exists(path)
    with open(path, encoding="utf-8") as handle:
        assert "MIT License" in handle.read()


def test_the_files_are_still_drawn_in_the_ink_we_replace():
    """The recolour is a substitution on the file's own colour, so a vendored
    file that came back from upstream in a different one would go on
    rendering — in near-black, on a dark window, where nobody would see it."""
    for name, _file in branding.SYMBOLS:
        with open(branding.symbol_svg(name), encoding="utf-8") as handle:
            assert branding.SYMBOL_INK in handle.read(), name


def test_an_unknown_name_is_nothing_rather_than_an_error(application):
    assert branding.symbol_svg("no-such-symbol") is None
    assert symbols.render("no-such-symbol", 16, "#000000") is None
    assert symbols.icon("no-such-symbol", 16).isNull()


# --- the recolour ---------------------------------------------------------

@pytest.mark.parametrize("which", ["light", "dark"])
def test_a_symbol_is_painted_in_the_scheme_s_ink(application, which):
    painted = symbols.render("copy", 24, theme.colour("ink", which).name())
    assert theme.colour("ink", which).name() in inks(painted)


def test_the_three_states_are_the_three_colours_the_style_sheet_uses(application):
    """Ink at rest, the accent under the mouse, the rule when it is off:
    the same three a push button's underline goes through, so that these
    behave like the buttons around them and not like clickable pictures."""
    drawn = symbols.icon("copy", 24, which="light")
    for mode, token in symbols.STATES:
        assert theme.colour(token, "light").name() in inks(
            drawn.pixmap(24, 24, mode)), mode


def test_two_asks_for_the_same_symbol_render_it_once(application):
    first = symbols.render("edit", 20, "#123456")
    assert symbols.render("edit", 20, "#123456") is first
    symbols.forget()
    assert symbols.render("edit", 20, "#123456") is not first


# --- the button -----------------------------------------------------------

def test_the_button_draws_the_symbol_and_says_nothing(application):
    button = symbols.Button("copy", "Copy", "⎘")
    assert not button.icon().isNull()
    assert button.text() == ""


def test_the_button_follows_the_desktop_into_the_dark(application):
    """A picture cannot follow a palette. This one is re-rendered when the
    palette changes, which is the whole reason the button is a class."""
    style.apply(application, which="light")
    button = symbols.Button("copy", "Copy", "⎘")
    assert theme.colour("ink", "light").name() in inks(
        button.icon().pixmap(24, 24, QIcon.Mode.Normal))

    style.apply(application, which="dark")
    QApplication.processEvents()
    assert theme.colour("ink", "dark").name() in inks(
        button.icon().pixmap(24, 24, QIcon.Mode.Normal))


def test_the_symbol_grows_with_the_interface_font(application):
    """Somebody who has set their interface font large did it to read."""
    small = symbols.Button("copy", "Copy", "⎘")
    was = small.iconSize().height()

    larger = QFont(small.font())
    larger.setPointSizeF(larger.pointSizeF() * 2)
    small.setFont(larger)
    QApplication.processEvents()
    assert small.iconSize().height() > was


def test_without_the_drawing_the_button_falls_back_to_its_glyph(application,
                                                                monkeypatch):
    """A build that lost its package data draws a character instead — as
    text, because a tool button's default is icon-only and an icon-only
    button with no icon is nothing at all on Windows."""
    monkeypatch.setattr(branding, "symbol_svg", lambda name: None)
    button = symbols.Button("copy", "Copy", "⎘")
    assert button.icon().isNull()
    assert button.text() == "⎘"
    assert button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextOnly
