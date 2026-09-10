"""The window's palette and typefaces, checked against the web page's.

The point of this module is one program with one identity, so the interesting
tests are the ones that fail when the two front ends drift: the tokens are
compared with ``web/static/style.css`` itself rather than with a copy of it,
and every pair is measured against the same WCAG floors the page's own tests
use — a palette the program chose has no desktop to blame for its greys.

The rest covers what Qt does badly. A style sheet rule re-resolves the font of
every widget it matches, which quietly drops the uppercase letter-spaced label
the page sets its buttons in; that behaviour is why ``theme.Labels`` exists,
and the test for it is the one that would catch a Qt release changing its
mind. Everything runs on Qt's offscreen platform.
"""
import os

import pytest

pytest.importorskip("PySide6", reason="the desktop window needs Qt")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtGui import QColor, QFont, QPalette
    from PySide6.QtWidgets import (
        QApplication,
        QLabel,
        QPushButton,
        QTableWidget,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:      # pragma: no cover - depends on the machine
    pytest.skip(f"PySide6 cannot be loaded here: {exc}", allow_module_level=True)

from audio_transcriber import branding  # noqa: E402
from audio_transcriber.gui import style, theme  # noqa: E402

#: (foreground, background, minimum), exactly the rules the page is held to:
#: 4.5 is AA for text, 3.0 is AA for the boundary of a control — and a field
#: drawn as a single underline is all boundary.
CONTRAST_RULES = [
    ("ink", "paper", 4.5), ("ink", "sheet", 4.5),
    ("muted", "paper", 4.5), ("muted", "sheet", 4.5),
    ("signal", "paper", 4.5), ("signal", "sheet", 4.5),
    ("clay", "paper", 4.5), ("clay", "sheet", 4.5),
    ("line", "paper", 3.0), ("line", "sheet", 3.0),
    ("ink", "signal-wash", 4.5), ("muted", "signal-wash", 4.5),
]


@pytest.fixture(scope="session")
def application():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def restored(application):
    """Palette, font and style sheet are application-wide: put them back."""
    before = (QPalette(application.palette()), QFont(application.font()),
              application.styleSheet())
    yield
    application.setPalette(before[0])
    application.setFont(before[1])
    application.setStyleSheet(before[2])


# --- one palette, in two places -------------------------------------------

@pytest.mark.parametrize("which", ["light", "dark"])
def test_the_tokens_are_the_stylesheet_s_own(which):
    """Read out of style.css, not copied from it: two copies of a palette are
    two palettes waiting to drift apart."""
    css = theme.stylesheet_tokens()[which]
    for name, value in theme.TOKENS[which].items():
        assert name in css, f"{which}: --{name} is not in style.css"
        assert css[name] == value.upper(), f"{which}: --{name}"


@pytest.mark.parametrize("which", ["light", "dark"])
def test_the_palette_meets_wcag_aa(which):
    failures = []
    for foreground, background, minimum in CONTRAST_RULES:
        ratio = style.contrast(theme.colour(foreground, which),
                               theme.colour(background, which))
        if ratio < minimum:
            failures.append(f"{which}: {foreground} on {background} "
                            f"is {ratio:.2f}:1, needs {minimum}")
    assert failures == []


@pytest.mark.parametrize("which", ["light", "dark"])
def test_the_qt_palette_says_what_the_tokens_say(which):
    """Where CSS has one surface Qt has two: --paper is the window and --sheet
    is anything you type in or scroll."""
    palette = theme.palette(which)
    for role, token in (
        (QPalette.ColorRole.Window, "paper"),
        (QPalette.ColorRole.WindowText, "ink"),
        (QPalette.ColorRole.Base, "sheet"),
        (QPalette.ColorRole.Text, "ink"),
        (QPalette.ColorRole.Highlight, "signal"),
        (QPalette.ColorRole.PlaceholderText, "muted"),
        (QPalette.ColorRole.BrightText, "clay"),
    ):
        assert palette.color(role) == theme.colour(token, which), role
    # What is written on the accent is the ground the accent was lifted off,
    # and it has to be readable there.
    assert style.contrast(palette.color(QPalette.ColorRole.HighlightedText),
                          palette.color(QPalette.ColorRole.Highlight)) >= 4.5


def test_both_schemes_carry_the_same_names():
    assert set(theme.TOKENS["light"]) == set(theme.TOKENS["dark"])


# --- the typefaces --------------------------------------------------------

def test_the_bundled_faces_actually_arrive(application):
    """The files ship as plain sfnt precisely so that this holds on every
    platform - see tests/test_branding.py for the Windows bug that says why.

    A build that lost the files is still allowed to run: the family is absent,
    the stack takes over, and the window looks like the page does in a browser
    with no webfonts."""
    loaded = theme.load_fonts()
    if branding.font_files():
        assert branding.SANS in loaded and branding.SERIF in loaded
        assert theme.family(branding.SANS) == branding.SANS
        assert theme.family(branding.SERIF) == branding.SERIF
    else:                       # pragma: no cover - a build without the data
        assert loaded == []


def test_a_missing_face_falls_back_along_the_stylesheet_s_own_stack():
    """The stacks are the ones style.css names, so a machine without the
    fonts and a browser without them land on the same face."""
    available = {"Corbel", "Georgia"}
    assert theme.family(branding.SANS, available) == "Corbel"
    assert theme.family(branding.SERIF, available) == "Georgia"
    # Nothing at all: the name is handed back, and Qt substitutes.
    assert theme.family(branding.SANS, set()) == branding.SANS


def test_the_label_font_is_the_page_s_uppercase_micro_label(application):
    base = QFont(application.font())
    label = theme.label_font(base)

    assert label.capitalization() == QFont.Capitalization.AllUppercase
    assert label.letterSpacing() == theme.LABEL_TRACKING
    assert label.weight() >= QFont.Weight.DemiBold
    assert label.pointSizeF() < base.pointSizeF()


def test_a_tab_gets_the_same_treatment_at_full_size(application, restored):
    """Three tabs are the whole navigation of this window, and at the label's
    own ratio they came out around seven points: a row of captions, which is
    what "they do not look like tabs" means. The strip therefore keeps the
    case and the tracking and gives up the shrinking."""
    theme.apply(application, "light")
    base = QFont(application.font())
    tab = theme.tab_font(base)

    assert tab.capitalization() == QFont.Capitalization.AllUppercase
    assert tab.pointSizeF() == pytest.approx(base.pointSizeF())
    assert tab.pointSizeF() > theme.label_font(base).pointSizeF()

    host = QWidget()
    tabs = QTabWidget(host)
    tabs.addTab(QWidget(), "Transcribe")
    host.show()
    for _ in range(3):
        QApplication.processEvents()
    strip = tabs.tabBar().font()
    assert strip.capitalization() == QFont.Capitalization.AllUppercase
    assert strip.pointSizeF() == pytest.approx(tab.pointSizeF())
    host.deleteLater()


def test_the_selected_tab_is_marked_in_the_accent_not_in_the_ink(application):
    """An underline the colour of the text reads as underlined text, which is
    the other half of why the strip did not look like tabs."""
    sheet = theme.qss("light")
    selected = sheet.split("QTabBar::tab:selected")[1].split("}")[0]

    assert theme.colour("signal", "light").name().upper() in selected.upper()
    assert "border-bottom: 3px solid transparent" in sheet


def test_the_content_is_held_off_the_frame(application):
    """The gutter: a group box's rule was flush against the window."""
    sheet = theme.qss("light")
    pane = sheet.split("QTabWidget::pane")[1].split("}")[0]

    assert f"{theme.GUTTER}px" in pane
    assert f"QTabWidget::tab-bar {{ left: {theme.GUTTER}px; }}" in sheet
    assert theme.GUTTER >= 16


def test_a_heading_is_the_serif_and_a_note_is_not(application):
    base = QFont(application.font())
    title = theme.title_font(base, 1.45)

    assert title.family() == theme.family(branding.SERIF)
    assert title.pointSizeF() > base.pointSizeF()
    assert theme.title_font(base, 1.0, italic=True).italic() is True


def test_a_display_heading_asks_for_the_display_cut(application):
    """Fraunces is variable, and the optical size is the axis that matters:
    at 9 it is a sturdy text face, at 144 the high-contrast display cut with
    hairline serifs. The page asks for 144 in its h1, and a plain QFont asks
    for neither - which drew the text cut at display size, and is the whole
    difference between the window and the page."""
    if not hasattr(QFont, "setVariableAxis"):   # pragma: no cover - Qt < 6.7
        pytest.skip("this Qt cannot set a variable axis")
    tag = QFont.Tag("opsz")
    base = QFont(application.font())

    display = theme.title_font(base, theme.TITLE_SCALE, opsz=theme.DISPLAY_OPSZ)
    assert display.variableAxisValue(tag) == theme.DISPLAY_OPSZ
    section = theme.title_font(base, 1.35, opsz=theme.SECTION_OPSZ)
    assert section.variableAxisValue(tag) == theme.SECTION_OPSZ
    # Small type asks for nothing and gets the text cut, which is the one that
    # holds up at fifteen pixels. A row's title is set that way; Qt reports an
    # axis nobody set as zero.
    assert theme.title_font(base, 1.15).variableAxisValue(tag) == 0.0


def test_a_display_heading_is_tracked_in(application):
    """The page sets -0.02em on its h1: at display size the default fit is
    loose enough to read as gappy."""
    base = QFont(application.font())
    title = theme.title_font(base, theme.TITLE_SCALE, tracking=theme.TITLE_TRACKING)

    assert title.letterSpacing() == theme.TITLE_TRACKING
    assert title.letterSpacing() < 100


def test_the_label_font_survives_the_style_sheet(application, restored):
    """The Qt behaviour this depends on, pinned down: a widget matched by a
    style-sheet rule has its font re-resolved from the application default,
    which drops the case and the tracking. theme.Labels puts it back when the
    widget is polished — and again if something takes it away."""
    theme.apply(application, "light")
    host = QWidget()
    layout = QVBoxLayout(host)
    button = QPushButton("Transcribe", host)
    table = QTableWidget(1, 2, host)
    table.setHorizontalHeaderLabels(["Recording", "Status"])
    layout.addWidget(button)
    layout.addWidget(table)
    host.show()
    for _ in range(3):
        QApplication.processEvents()

    assert button.font().capitalization() == QFont.Capitalization.AllUppercase
    assert (table.horizontalHeader().font().capitalization()
            == QFont.Capitalization.AllUppercase)
    # A button the queue grows later gets it too, which is why this is an
    # event filter and not a walk of the tree at start-up.
    late = QPushButton("Stop", host)
    layout.addWidget(late)
    late.show()
    QApplication.processEvents()
    assert late.font().capitalization() == QFont.Capitalization.AllUppercase
    host.deleteLater()


def test_a_container_does_not_pass_the_label_font_to_its_contents(application, restored):
    """A font set on a widget in Qt is inherited by everything inside it, and
    a panel of uppercase prose is not the design. Only the three classes the
    page gives the treatment to may have it."""
    theme.apply(application, "light")
    host = QWidget()
    layout = QVBoxLayout(host)
    button = QPushButton("Transcribe", host)
    layout.addWidget(button)
    host.show()
    QApplication.processEvents()

    assert host.font().capitalization() == QFont.Capitalization.MixedCase
    assert isinstance(button, theme.LABEL_WIDGETS)
    assert not isinstance(host, theme.LABEL_WIDGETS)
    host.deleteLater()


# --- applying it ----------------------------------------------------------

def test_apply_installs_the_scheme_it_is_asked_for(application, restored):
    assert theme.apply(application, "dark") == "dark"
    assert application.palette().color(QPalette.ColorRole.Window) \
        == theme.colour("paper", "dark")
    assert theme.qss("dark").split("{")[0] in application.styleSheet()
    assert application.font().family() == theme.family(branding.SANS)


def test_applying_twice_does_not_pile_up_stylesheets(application, restored):
    theme.apply(application, "light")
    once = len(application.styleSheet())
    theme.apply(application, "light")

    assert len(application.styleSheet()) == once


def test_a_second_apply_does_not_install_a_second_filter(application, restored):
    """The label font is kept by an event filter; two of them would fight."""
    theme.apply(application, "light")
    first = theme._labels
    theme.apply(application, "dark")

    assert theme._labels is first


def test_the_scheme_follows_what_the_desktop_reports(application):
    """Neither scheme is a default and nobody is asked to pick, exactly as the
    page follows prefers-color-scheme.

    The desktop is asked through Qt's style hints, which is what a real
    session answers; the offscreen platform these tests run on has no theme
    and reports nothing, so the hint is stood in for here."""
    from PySide6.QtCore import Qt

    class Desktop:
        def __init__(self, reported):
            self._reported = reported

        def styleHints(self):
            return self

        def colorScheme(self):
            return self._reported

        def palette(self):
            return theme.palette("light")

    assert theme.scheme(Desktop(Qt.ColorScheme.Dark)) == "dark"
    assert theme.scheme(Desktop(Qt.ColorScheme.Light)) == "light"


def test_a_desktop_that_reports_nothing_is_read_from_its_palette(application, restored):
    """An older Qt, or a desktop with no preference to read: the same question
    asked of the result instead of of the setting. This is the path the test
    suite itself takes, because Qt's offscreen platform reports Unknown."""
    application.setPalette(theme.palette("dark"))
    assert theme.scheme(application) == "dark"
    application.setPalette(theme.palette("light"))
    assert theme.scheme(application) == "light"


def test_the_chrome_is_the_page_s_chrome(application):
    """Spot-checks of the translation, on the decisions the page actually
    makes: a field is a rule under the text, a button is typographic and never
    boxy, and the primary action is the accent rather than a filled box."""
    sheet = theme.qss("light")
    line = theme.colour("line", "light").name().upper()
    signal = theme.colour("signal", "light").name().upper()

    assert f"border-bottom: 1px solid {line}".lower() in sheet.lower()
    assert "QPushButton, QToolButton { background: transparent" in sheet
    assert f"QPushButton#primary {{ color: {signal}".lower() in sheet.lower()
    assert "background:" not in sheet.split("QPushButton#primary")[1].split("}")[0]
    # The dashed drop area, and the accent wash while a file is over it.
    assert "QFrame#drop { border: 1px dashed" in sheet
    assert theme.colour("signal-wash", "light").name().upper() in sheet.upper()


def test_style_apply_leaves_the_brand_palette_with_a_floor(application, restored):
    """style.apply installs this theme and then lifts the disabled colours:
    the two are meant to compose, not to overwrite each other."""
    palette = style.apply(application, which="dark")

    assert palette.color(QPalette.ColorRole.Window) == theme.colour("paper", "dark")
    for role, ground_role in style._PAIRS:
        ink = palette.color(QPalette.ColorGroup.Disabled, role)
        ground = palette.color(QPalette.ColorGroup.Disabled, ground_role)
        assert style.contrast(ink, ground) >= style.MIN_CONTRAST, role
    assert theme.MARKER in application.styleSheet()
    assert style.MARKER in application.styleSheet()


def test_a_note_is_the_page_s_muted_ink(application, restored):
    """The colour the page writes its notes in, not a grey worked out from
    whatever palette happened to be in force."""
    style.apply(application, which="light")
    host = QWidget()
    label = style.note(QLabel("una nota", host))
    ink = QColor(label.styleSheet().split("color:")[1].strip(" ;"))

    assert ink == theme.colour("muted", "light")
    assert style.contrast(ink, theme.colour("paper", "light")) >= style.MIN_CONTRAST
    host.deleteLater()


def test_notes_are_repainted_when_the_scheme_changes(application, restored):
    """A note's ink is written into the widget's own style sheet, so a new
    palette does not reach it: renote is what the window calls when the
    desktop switches to dark."""
    style.apply(application, which="light")
    host = QWidget()
    label = style.note(QLabel("una nota", host))
    was = label.styleSheet()

    style.apply(application, which="dark")
    assert style.renote(host) >= 1
    assert label.styleSheet() != was
    assert QColor(label.styleSheet().split("color:")[1].strip(" ;")) \
        == theme.colour("muted", "dark")
    host.deleteLater()


def test_the_fonts_are_part_of_the_brand_not_of_the_web_page(application):
    """They are shared data, like the icons: the window must not have to reach
    into web/static to be painted."""
    families = [name for name, _ in branding.font_files()]

    assert branding.SANS in families and branding.SERIF in families
    for _, path in branding.font_files():
        assert os.path.dirname(path).endswith(os.path.join("brand", "fonts"))
        assert os.path.exists(path)
