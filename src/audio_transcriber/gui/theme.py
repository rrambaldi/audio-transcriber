"""The web page's look, in Qt: the same palette, the same two typefaces.

The window used to be painted by the desktop, on purpose, and that decision is
now reversed: the browser and the window are one program and should look like
it. So the tokens below are *the stylesheet's* tokens - the light scheme is the
brand inverted, the dark scheme is the mark's own colours - written once here
and checked against ``web/static/style.css`` by the test suite, because two
copies of a palette are two palettes waiting to drift apart.

What survives from the old approach is the part that was never taste: the
contrast floor in :mod:`audio_transcriber.gui.style`, which still lifts the
disabled colours until the words are readable, and now has a palette of its
own to lift rather than the desktop's.

The translation is not literal, because Qt is not CSS. Three things are worth
knowing:

* Which scheme is used still follows the desktop, exactly as the page follows
  ``prefers-color-scheme``: neither is a default and nobody is asked to pick.
* The uppercase, letter-spaced label - buttons, tabs, table headings - is a
  ``QFont``, not a stylesheet rule, because Qt style sheets have neither
  ``text-transform`` nor ``letter-spacing``. It cannot be installed per widget
  class either: a widget matched by any style-sheet rule has its font re-set
  from the application's default when the sheet is applied, which drops both
  the case and the tracking. So it is set on each widget as it is polished -
  see :class:`Labels` - which is late enough to survive, and catches the
  buttons a queue row grows later on.
* Group-box titles keep the sans face at their normal case. A font set on a
  container in Qt - by stylesheet or by hand - is inherited by everything
  inside it, so the uppercase legend of the web page cannot be had here
  without shouting the whole panel.

Everything is applied to the ``QApplication``, once, by :func:`apply`.
"""
import os

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QHeaderView, QPushButton, QTabBar

from .. import branding

#: The palette, one entry per scheme, in the stylesheet's own names. Any
#: change here belongs in ``web/static/style.css`` at the same time;
#: ``tests/test_gui_theme.py`` fails when they differ.
TOKENS = {
    "light": {
        "paper": "#F1F4FA",
        "sheet": "#FAFBFE",
        "ink": "#0C1526",
        "muted": "#4A5A73",
        "rule": "#D3DBE8",
        "line": "#7C8AA3",
        "signal": "#1C4FD8",
        "signal-wash": "#E4EBFA",
        "clay": "#A6371B",
    },
    "dark": {
        "paper": "#0C1526",
        "sheet": "#122036",
        "ink": "#EAF3FF",
        "muted": "#9FB3CE",
        "rule": "#26364F",
        "line": "#6E88AE",
        "signal": "#22D3EE",
        "signal-wash": "#132A42",
        "clay": "#F2957A",
    },
}

#: What to fall back to, in order, when the bundled face is not there: the
#: same stacks the stylesheet names, so a machine without the fonts and a
#: browser without them land on the same face.
FALLBACKS = {
    branding.SERIF: ("Iowan Old Style", "Palatino Linotype", "Palatino",
                     "Georgia", "serif"),
    branding.SANS: ("Avenir Next", "Corbel", "Segoe UI", "sans-serif"),
}

#: How much smaller the uppercase label is than the interface font, and how
#: far its letters are spaced. The tracking is the stylesheet's 0.14em. The
#: size is not its 0.72rem, and cannot be: that ratio was written against a
#: 16 px body, and a desktop's interface font is nine points to begin with -
#: 0.72 of it is six and a half, which is a size nobody reads. What is kept is
#: the *relation* - a label is smaller than the prose next to it - at a size
#: that lands near the page's own 11.5 px.
LABEL_SCALE = 0.9
LABEL_TRACKING = 114

#: A tab is the same treatment at the interface font's own size. The page can
#: afford 0.72rem there because its tab strip sits inside a form that has just
#: asked a question; in a window the three tabs *are* the navigation, and at
#: 0.82 of a 9pt desktop font they came out at seven and a half points - a row
#: of captions rather than a row of tabs.
TAB_SCALE = 1.0

#: The gutter between the window's edge and what is in it, in pixels. The page
#: gives itself between 1rem and 4rem of side padding and a measure to sit in;
#: a window cannot indent as luxuriously as a sheet of paper, but it was
#: putting a group box's rule flush against the frame.
GUTTER = 24

#: How much larger a heading is than the interface font. The page's h1 goes up
#: to 4.2rem, which is a page to itself; a window has a queue to show under
#: its masthead. This is as large as the band can be without eating the tab
#: below it, and it is what makes the name read as a title rather than as bold
#: text.
TITLE_SCALE = 2.3

#: Fraunces is a variable font, and the axis that matters is the optical size:
#: at 9 it is a sturdy text face and at 144 the high-contrast display cut with
#: hairline serifs. The page asks for 144 in its h1 and 72 in a section
#: heading; asking for neither - which is what a plain QFont does - draws the
#: text cut at display size, which is the whole difference between the window
#: and the page.
DISPLAY_OPSZ = 144.0
SECTION_OPSZ = 72.0

#: The page sets -0.02em on its h1: at display size the default fit is loose.
TITLE_TRACKING = 98

#: The widgets that get the uppercase label font: the elements the stylesheet
#: gives it to - ``.button``, ``.tab`` and ``th``.
#:
#: QToolButton is deliberately not among them, although it is a button: the
#: only ones in this window are the rows of :class:`gui.widgets.Disclosure`,
#: whose titles carry a sentence ("Keyword sets - 3 chosen"). The page's
#: micro-label is for words; a sentence in it is shouting.
LABEL_WIDGETS = (QPushButton, QTabBar, QHeaderView)

#: Where this module's rules start in the application's style sheet, so they
#: can be replaced rather than piled up.
MARKER = "/* audio-transcriber: the brand, in Qt */"


def load_fonts():
    """Hand Qt the bundled typefaces; answer with the families it took.

    Qt does not read a font itself: it passes the bytes to the platform's font
    engine, and they do not agree on what a font is. FreeType takes WOFF2,
    DirectWrite refuses it - which is why these files are plain sfnt, and why
    ``branding.FONTS`` says so at some length.

    A face that still does not arrive - a build without the files, an engine
    that dislikes something else about them - is not an error here: the family
    is simply absent and :func:`family` falls through to the next name in the
    stack, exactly as the page does in a browser with no webfonts. The same
    design in a different face is a fallback; a traceback on start-up because
    of a typeface would not be."""
    loaded = []
    for _family, file in branding.font_files():
        handle = QFontDatabase.addApplicationFont(file)
        if handle < 0:
            continue
        loaded.extend(QFontDatabase.applicationFontFamilies(handle))
    return loaded


def family(wanted, available=None):
    """``wanted`` if Qt has it, otherwise the first fallback that it has."""
    have = set(available if available is not None else QFontDatabase.families())
    if wanted in have:
        return wanted
    for name in FALLBACKS.get(wanted, ()):
        if name in have:
            return name
    return wanted


def scheme(application=None):
    """"dark" or "light", as the desktop has it.

    Qt reports the desktop's preference through its style hints, the way a
    browser reports ``prefers-color-scheme``. Where it cannot say - an older
    Qt, a desktop with no preference to read - the answer is taken from the
    palette Qt built for itself, which is the same question asked of the
    result instead of the setting."""
    hints = application.styleHints() if application is not None else None
    reported = getattr(hints, "colorScheme", None)
    if reported is not None:
        try:
            if reported() == Qt.ColorScheme.Dark:
                return "dark"
            if reported() == Qt.ColorScheme.Light:
                return "light"
        except (AttributeError, TypeError):     # pragma: no cover - old Qt
            pass
    if application is None:
        return "light"
    window = application.palette().color(QPalette.ColorRole.Window)
    text = application.palette().color(QPalette.ColorRole.WindowText)
    return "dark" if window.lightnessF() < text.lightnessF() else "light"


def colour(name, which="light"):
    """One token as a QColor."""
    return QColor(TOKENS[which][name])


def palette(which="light"):
    """The scheme as a QPalette, before the contrast floor is applied.

    The mapping is where CSS and Qt stop lining up. A page has one surface;
    Qt has *Window* for a panel and *Base* for anything you type in or scroll,
    so the page's ``--paper`` becomes the window and ``--sheet`` - which the
    page keeps for dialogs - becomes the field and list surface. Everything
    else follows the stylesheet: the accent is the highlight, the rules are
    the frame colours, and the error colour is the one the page calls clay."""
    ink = colour("ink", which)
    paper = colour("paper", which)
    sheet = colour("sheet", which)
    muted = colour("muted", which)
    signal = colour("signal", which)
    wash = colour("signal-wash", which)
    result = QPalette()
    for role, value in (
        (QPalette.ColorRole.Window, paper),
        (QPalette.ColorRole.WindowText, ink),
        (QPalette.ColorRole.Base, sheet),
        # The zebra of a long list, in the page's own second surface.
        (QPalette.ColorRole.AlternateBase, paper),
        (QPalette.ColorRole.Text, ink),
        (QPalette.ColorRole.PlaceholderText, muted),
        (QPalette.ColorRole.Button, paper),
        (QPalette.ColorRole.ButtonText, ink),
        (QPalette.ColorRole.ToolTipBase, sheet),
        (QPalette.ColorRole.ToolTipText, ink),
        (QPalette.ColorRole.Highlight, signal),
        # What is written *on* the accent: the ground it was lifted off.
        (QPalette.ColorRole.HighlightedText, paper),
        (QPalette.ColorRole.Link, signal),
        (QPalette.ColorRole.LinkVisited, signal),
        (QPalette.ColorRole.BrightText, colour("clay", which)),
        (QPalette.ColorRole.Light, sheet),
        (QPalette.ColorRole.Midlight, wash),
        (QPalette.ColorRole.Mid, colour("rule", which)),
        (QPalette.ColorRole.Dark, colour("line", which)),
        (QPalette.ColorRole.Shadow, colour("rule", which)),
    ):
        result.setColor(role, value)
    return result


def base_font(template=None, available=None):
    """The interface face: Karla, at the size the desktop asked for.

    Built by taking the font Qt was going to use and changing the family, so
    the size survives whichever unit it is expressed in - points usually,
    pixels on some Linux desktops. The page's 16 px is deliberately not
    imposed: somebody who has set their interface font large has done it for a
    reason, and every other size here is a ratio of this one."""
    font = QFont(template) if template is not None else QFont()
    font.setFamily(family(branding.SANS, available))
    return font


def tab_font(base):
    """The label treatment at full size, for the tab strip. See TAB_SCALE."""
    return label_font(base, TAB_SCALE)


def label_font(base, scale=LABEL_SCALE):
    """The page's uppercase, letter-spaced label, as a font.

    ``.button``, ``.tab``, ``th`` and ``legend`` are one treatment in the
    stylesheet - 0.72rem, 600, uppercase, 0.14em of tracking - and this is
    that treatment. Qt style sheets can do neither the case nor the tracking,
    so it has to be a font."""
    font = QFont(base)
    font.setCapitalization(QFont.Capitalization.AllUppercase)
    font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, LABEL_TRACKING)
    font.setWeight(QFont.Weight.DemiBold)
    _scale(font, scale)
    return font


def title_font(base, scale=TITLE_SCALE, italic=False, weight=QFont.Weight.Medium,
               opsz=None, tracking=None):
    """A heading in the serif: the masthead, a section title, a row's title.

    ``opsz`` is the optical size to cut it at - :data:`DISPLAY_OPSZ` for the
    masthead, :data:`SECTION_OPSZ` for a heading, and ``None`` for anything
    small, which is what the page does too: a row's title asks for no optical
    size and gets the text cut, because that is the one that holds up at
    fifteen pixels.

    The weight is set twice, and the second time is the one that works:
    ``QFont.setWeight`` picks among the *named* instances a font declares and
    never touches the ``wght`` axis, so a variable face answers it with
    whichever instance it happens to have - which is how the masthead came out
    fatter than the page's own h1, and the promise under it came out bold when
    it had been asked for regular.

    Setting an axis needs Qt 6.7, and a font engine that honours it. Where
    either is missing the named weight is all there is, and the face still
    comes out - as its default instance, the way a browser without
    variable-font support would draw it."""
    font = QFont(base)
    font.setFamily(family(branding.SERIF))
    font.setWeight(weight)
    font.setItalic(italic)
    _scale(font, scale)
    if tracking:
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, tracking)
    if hasattr(font, "setVariableAxis"):
        if opsz is not None:
            font.setVariableAxis(QFont.Tag("opsz"), opsz)
        # Qt's own weight numbers are the CSS ones, so the enum is the axis
        # value. The sans is deliberately left to Qt's matching: its axis
        # starts at 400 and it comes out right without help.
        font.setVariableAxis(QFont.Tag("wght"), float(int(weight)))
    return font


def _scale(font, factor):
    """Multiply a font's size, whichever unit it is expressed in."""
    if font.pointSizeF() > 0:
        font.setPointSizeF(font.pointSizeF() * factor)
    else:                       # a font sized in pixels, as on some Linux
        font.setPixelSize(max(1, round(font.pixelSize() * factor)))
    return font


def qss(which="light"):
    """The chrome: what the stylesheet does to controls, said in Qt's dialect.

    Fields are a rule under the text, buttons are typographic and never boxy,
    a tab is a word with a line under it, and the one filled thing on the page
    is nothing - the primary action is the accent and a heavier rule, as
    ``.button.send`` is. Only what the page decides is set here; the rest is
    left to the style, which is Fusion on all three platforms so that these
    rules land the same way on each."""
    token = dict(TOKENS[which])
    return f"""
QMainWindow, QDialog, QWidget#masthead {{ background: {token['paper']}; }}
QToolTip {{ background: {token['sheet']}; color: {token['ink']};
            border: 1px solid {token['rule']}; padding: 4px 6px; }}
QStatusBar {{ color: {token['muted']}; border-top: 1px solid {token['rule']};
              padding: 3px {GUTTER}px; }}
QStatusBar::item {{ border: none; }}

/* --- tabs: a word with the accent under it ------------------------------- */
/*  The page can draw a tab as a word with a hairline under it because its
    strip sits inside a form that has just asked a question. These three are
    the whole navigation of the window, so they are given the interface font's
    own size, room to be pressed, and an indicator in the accent rather than
    in the ink: an underline the colour of the text reads as underlined text.
    The strip keeps the page's rule along its foot, and the selected tab's
    marker sits on top of it.  */
QTabWidget::pane {{ border: none; border-top: 1px solid {token['rule']};
                    top: -1px; padding: {GUTTER // 2}px {GUTTER}px {GUTTER}px; }}
QTabWidget::tab-bar {{ left: {GUTTER}px; }}
QTabBar {{ qproperty-drawBase: 0; background: transparent; }}
QTabBar::tab {{ background: transparent; border: none;
                border-bottom: 3px solid transparent;
                color: {token['muted']}; padding: 10px 4px 9px;
                margin: 0 28px 0 0; }}
QTabBar::tab:selected {{ color: {token['ink']};
                         border-bottom-color: {token['signal']}; }}
QTabBar::tab:hover:!selected {{ color: {token['signal']};
                                border-bottom-color: {token['rule']}; }}
QTabBar::tab:focus {{ color: {token['ink']}; }}

/* --- buttons: typographic, never boxy ----------------------------------- */
QPushButton, QToolButton {{ background: transparent; border: none;
                            border-bottom: 1px solid {token['line']};
                            color: {token['ink']};
                            padding: 5px 2px; margin: 0 2px; }}
QPushButton:hover, QToolButton:hover {{ color: {token['signal']};
                                        border-bottom-color: {token['signal']}; }}
QPushButton:pressed, QToolButton:pressed {{ color: {token['signal']};
                                            border-bottom-width: 2px; }}
QPushButton:disabled, QToolButton:disabled {{ border-bottom-color: {token['rule']}; }}
/* The one action a screen is for: the accent and a heavier rule, which is
   what .button.send is on the page. Not a filled box - the page has none. */
QPushButton#primary {{ color: {token['signal']};
                       border-bottom: 2px solid {token['signal']}; }}
QPushButton#primary:hover {{ color: {token['ink']};
                             border-bottom-color: {token['ink']}; }}
QPushButton#primary:disabled {{ border-bottom-color: {token['rule']}; }}

/* --- fields: one rule under the text ------------------------------------ */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTimeEdit {{
    background: transparent; border: none;
    border-bottom: 1px solid {token['line']}; border-radius: 0;
    color: {token['ink']}; padding: 4px 2px; selection-background-color: {token['signal']};
    selection-color: {token['paper']}; }}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
    border-bottom-color: {token['ink']}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-bottom-color: {token['signal']}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
    border-bottom-color: {token['rule']}; }}
QComboBox::drop-down {{ border: none; width: 16px; }}
QComboBox QAbstractItemView {{ background: {token['sheet']};
                               border: 1px solid {token['rule']};
                               selection-background-color: {token['signal-wash']};
                               selection-color: {token['ink']};
                               outline: none; padding: 2px; }}
/* A page's textarea is the one field with a box round it, because there is no
   underline that would hold two dozen lines together. */
QPlainTextEdit, QTextEdit, QTextBrowser {{ background: {token['sheet']};
                                           border: 1px solid {token['line']};
                                           border-radius: 0;
                                           color: {token['ink']};
                                           selection-background-color: {token['signal']};
                                           selection-color: {token['paper']};
                                           padding: 6px; }}
QPlainTextEdit:focus, QTextEdit:focus {{ border-color: {token['signal']}; }}

/* --- lists: a rule between rows, no grid -------------------------------- */
QTableView, QTreeView, QListView {{ background: {token['sheet']};
                                    alternate-background-color: {token['paper']};
                                    border: 1px solid {token['rule']};
                                    gridline-color: {token['rule']};
                                    outline: none; }}
QTableView::item, QTreeView::item, QListView::item {{ padding: 2px 4px;
                                                      border: none; }}
QTableView::item:selected, QTreeView::item:selected, QListView::item:selected {{
    background: {token['signal-wash']}; color: {token['ink']}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {token['paper']}; color: {token['muted']};
                        border: none; border-bottom: 1px solid {token['ink']};
                        padding: 6px 4px; }}
QTableCornerButton::section {{ background: {token['paper']}; border: none; }}

/* --- a section is a rule with a name on it ------------------------------ */
QGroupBox {{ border: none; border-top: 1px solid {token['rule']};
             margin-top: 18px; padding: 14px 0 0; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left;
                    left: 0; padding: 0 6px 0 0; color: {token['muted']}; }}
QFrame[frameShape="4"], QFrame[frameShape="5"] {{ color: {token['rule']}; }}
/* The area a recording is dropped on: dashed, as on the page, and washed in
   the accent while something is over it. */
QFrame#drop {{ border: 1px dashed {token['line']}; border-radius: 0;
               background: transparent; }}
QFrame#drop[over="true"] {{ border-color: {token['signal']};
                            background: {token['signal-wash']}; }}

/* --- progress, and the level meter -------------------------------------- */
QProgressBar {{ border: none; background: {token['line']}; height: 4px;
                color: {token['muted']}; text-align: right; }}
QProgressBar::chunk {{ background: {token['signal']}; }}

/* --- scrollbars: a rule that thickens into a handle --------------------- */
QScrollBar:vertical, QScrollBar:horizontal {{ background: transparent;
                                              border: none; margin: 0; }}
QScrollBar:vertical {{ width: 10px; }}
QScrollBar:horizontal {{ height: 10px; }}
QScrollBar::handle {{ background: {token['line']}; border-radius: 5px;
                      min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {token['muted']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QCheckBox, QRadioButton {{ spacing: 8px; }}
QSplitter::handle {{ background: {token['rule']}; }}
QMenu {{ background: {token['sheet']}; color: {token['ink']};
         border: 1px solid {token['rule']}; }}
QMenu::item:selected {{ background: {token['signal-wash']}; }}
""".strip()


class Labels(QObject):
    """Keeps the uppercase label font on the widgets that should have it.

    An event filter rather than a class default, and the reason is a Qt
    behaviour worth writing down: when a style sheet rule matches a widget,
    Qt re-resolves that widget's font from the application default, which
    silently drops the capitalisation and the letter spacing this font is
    entirely made of. Setting the font when the widget is *polished* is late
    enough to stick, and a tab bar - which Qt refits from its tab widget once
    more after that - is caught by the font change it sends when it does.

    The guard is what stops the two of them from arguing forever: a widget
    that already has the label font is left alone."""

    #: Polish is every widget's "I am about to be shown"; a font change is a
    #: parent, a style sheet or a style having overwritten what we set.
    WHEN = (QEvent.Type.Polish, QEvent.Type.FontChange)

    def __init__(self, font, tabs=None, parent=None):
        super().__init__(parent)
        self.font = font
        self.tabs = tabs or font

    def font_for(self, watched):
        """The strip gets the larger of the two; see :data:`TAB_SCALE`."""
        return self.tabs if isinstance(watched, QTabBar) else self.font

    def eventFilter(self, watched, event):
        if (event.type() in self.WHEN
                and isinstance(watched, LABEL_WIDGETS)
                and watched.font().capitalization()
                != QFont.Capitalization.AllUppercase):
            watched.setFont(self.font_for(watched))
        return False                # never swallow it


#: The one filter per process, so that applying the theme twice does not
#: install a second one behind the first.
_labels = None


def apply(application, which=None):
    """Paint ``application`` in the program's own colours and faces.

    Returns the scheme actually used. Everything is replaceable: applying
    again - a second window, a test, the desktop switching to dark - replaces
    what this installed instead of adding to it."""
    which = which or scheme(application)
    loaded = load_fonts()
    available = set(QFontDatabase.families()) | set(loaded)

    base = base_font(application.font(), available)
    application.setFont(base)

    global _labels
    label, tabs = label_font(base), tab_font(base)
    if _labels is None:
        _labels = Labels(label, tabs, application)
        application.installEventFilter(_labels)
    else:
        _labels.font, _labels.tabs = label, tabs

    application.setPalette(palette(which))
    # Ours goes last and is replaced rather than appended, so a second call
    # does not pile the rules up. The disabled floor in style.py appends its
    # own marker after this one.
    kept = application.styleSheet().split(MARKER)[0].rstrip()
    application.setStyleSheet(f"{kept}\n{MARKER}\n{qss(which)}".strip())
    return which


def stylesheet_tokens(path=None):
    """The tokens as ``web/static/style.css`` declares them, for the test.

    Reading the stylesheet rather than trusting a copy of it is the whole
    point: the two front ends are supposed to be one palette."""
    import re

    if path is None:
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "web", "static", "style.css")
    with open(path, encoding="utf-8") as handle:
        css = handle.read()
    blocks = {}
    dark = css.split("prefers-color-scheme: dark")
    blocks["light"] = dark[0]
    blocks["dark"] = dark[1] if len(dark) > 1 else ""
    found = {}
    for which, block in blocks.items():
        found[which] = {name: value.upper() for name, value
                        in re.findall(r"--([a-z-]+):\s*(#[0-9A-Fa-f]{6})", block)}
    return found
