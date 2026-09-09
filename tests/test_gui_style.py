"""The contrast floor the window imposes on the desktop's palette.

The web page has had a palette checked against WCAG 1.4.3 since it was
written; the window had nothing, and a note drawn as disabled text came out
at 1.75:1 against its box. These tests are that check, for the desktop.
"""
import os

import pytest

pytest.importorskip("PySide6", reason="the desktop window needs Qt")

# Qt reads this when the application object is created: no window ever appears.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtWidgets import QApplication, QLabel
except ImportError as exc:      # pragma: no cover - depends on the machine
    pytest.skip(f"PySide6 cannot be loaded here: {exc}", allow_module_level=True)

from audio_transcriber.gui import style  # noqa: E402


@pytest.fixture(scope="session")
def application():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def palette_restored(application):
    """Both are application-wide: put them back for the other tests."""
    before, sheet = QPalette(application.palette()), application.styleSheet()
    yield
    application.setPalette(before)
    application.setStyleSheet(sheet)


def test_the_ratio_matches_the_wcag_formula():
    """Two known pairs, so a mistake in the arithmetic cannot hide."""
    white, black = QColor("#FFFFFF"), QColor("#000000")
    assert round(style.contrast(black, white), 2) == 21.0
    assert round(style.contrast(white, white), 2) == 1.0
    # The pair the web page uses for its secondary text.
    assert round(style.contrast(QColor("#565B4C"), QColor("#F4F0E6")), 2) == 6.16


def test_a_muted_colour_still_clears_the_floor():
    ground = QColor("#FFFFFF")
    muted = style.readable(QColor("#000000"), ground)

    assert style.contrast(muted, ground) >= style.MIN_CONTRAST
    # ...and it is actually muted, not the original colour handed back.
    assert muted.value() > 0


def test_muting_backs_off_when_the_theme_has_no_room():
    """A washed-out theme gets less muting, never unreadable text."""
    ground = QColor("#FFFFFF")
    tight = QColor("#767676")           # 4.54:1, barely over the floor
    assert style.readable(tight, ground) == tight

    below = QColor("#999999")           # 2.85:1 - the theme's own problem
    assert style.readable(below, ground) == below


def test_a_note_is_coloured_rather_than_disabled(application):
    """Greying a QLabel is the cheap way to make it look secondary, and it
    lands at 1.75:1 on the sentence that explains the choice."""
    label = style.note(QLabel("una nota"))

    assert label.isEnabled() is True
    assert "color:" in label.styleSheet()
    colour = QColor(label.styleSheet().split("color:")[1].strip(" ;"))
    ground = label.palette().color(QPalette.ColorRole.Window)
    assert style.contrast(colour, ground) >= style.MIN_CONTRAST


def test_disabled_text_stays_readable(application, palette_restored):
    """The window disables the answers the machine cannot produce; reading
    why is the only thing left to do with one of them."""
    style.apply(application)
    palette = application.palette()

    for role, ground_role in style._PAIRS:
        ink = palette.color(QPalette.ColorGroup.Disabled, role)
        ground = palette.color(QPalette.ColorGroup.Disabled, ground_role)
        assert style.contrast(ink, ground) >= style.MIN_CONTRAST, role


def test_the_floor_is_repeated_as_a_stylesheet(application, palette_restored):
    """The native Windows style draws disabled text from the system theme and
    never reads QPalette.Disabled, so the palette alone is honoured on Linux
    and dropped on the platform most of these users are on."""
    style.apply(application)
    sheet = application.styleSheet()

    assert "QRadioButton:disabled" in sheet
    assert "QPushButton:disabled" in sheet
    colour = QColor(sheet.split("color: ")[1].split(";")[0])
    ground = application.palette().color(QPalette.ColorGroup.Disabled,
                                         QPalette.ColorRole.Window)
    assert style.contrast(colour, ground) >= style.MIN_CONTRAST


def test_applying_twice_does_not_pile_up_stylesheets(application, palette_restored):
    style.apply(application)
    once = len(application.styleSheet())
    style.apply(application)

    assert len(application.styleSheet()) == once
