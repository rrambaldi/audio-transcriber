"""What this program is, and the licence it is given under.

The window has no menu bar - nothing in it is hidden behind one - so the way
in is the version, in the masthead, where a version already was. Clicking it
opens this, and so does F1, which is the only key anybody presses looking for
help.

This is also the only place the version number is written down, apart from the
title bar: it used to sit in the masthead, where nobody needs it all day, and
it belongs with the rest of what this program is.

The whole licence is shown rather than its name. It is the MIT license with a
wish in front of it, and a dialog that said "MIT" and stopped would show the
half nobody needs to read: see :mod:`audio_transcriber.about`. The text is
selectable and read-only, because the one thing somebody may actually want to
do with a licence is copy it.
"""
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from .. import __version__, about, branding
from ..i18n import t
from . import style, symbols, theme
from .masthead import NAME_SCALE, TAGLINE_SCALE, TAGLINE_WEIGHT, mark_pixmap

#: How tall the licence gets to be before it starts scrolling. The file is
#: forty lines; this shows about half of it, which is enough to see that it
#: begins with something other than boilerplate.
LICENCE_LINES = 16

#: How wide the box is, in logical pixels: the licence is wrapped at seventy
#: columns, and this is what shows a line of it whole.
WIDTH = 640

#: The mark beside the name, larger than the masthead's: here it is the head
#: of the box, not a detail of a band.
ABOUT_MARK_PX = 64


class AboutDialog(QDialog):
    """The mark, the version, the licence, and what is bundled."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.facts = about.facts()
        self.setWindowTitle(t("about.title"))
        self.setModal(True)
        self.setFixedWidth(WIDTH)

        # The mark, the name and the promise, set by the window in its own two
        # faces and in the interface language - the masthead's three things. The
        # README's banner used to be here: a picture with English words in it,
        # promising an Intel iGPU to a machine that may well transcribe on CPU.
        self.mark = QLabel()
        self.mark.setPixmap(mark_pixmap(QIcon(branding.path(branding.ICON_SVG)),
                                        self, ABOUT_MARK_PX))
        self.name = QLabel(t("gui.wordmark"))
        self.name.setFont(theme.title_font(self.font(), NAME_SCALE,
                                           display=theme.DISPLAY,
                                           tracking=theme.TITLE_TRACKING))
        self.tagline = QLabel(t("gui.tagline"))
        self.tagline.setWordWrap(True)
        self.tagline.setFont(theme.title_font(self.font(), TAGLINE_SCALE,
                                              italic=True, weight=TAGLINE_WEIGHT))
        style.note(self.tagline)

        # The version goes directly under the name, where somebody looking for
        # it looks; the licence's own name goes under the "license" heading,
        # with the text it names.
        version = QLabel(t("about.version", version=__version__))
        style.note(version)

        self.source = QLabel(
            f'{t("about.source")} <a href="{about.REPOSITORY}">'
            f'{about.REPOSITORY.removeprefix("https://")}</a>')
        self.source.setOpenExternalLinks(True)
        style.note(self.source)

        licence_heading = QLabel(t("about.licence"))
        licence_heading.setFont(theme.label_font(self.font()))
        style.note(licence_heading)

        self.licence_name = QLabel(self.facts["licence_title"])
        self.licence_name.setWordWrap(True)
        style.note(self.licence_name)

        self.licence = QPlainTextEdit()
        self.licence.setReadOnly(True)
        self.licence.setPlainText(self.facts["licence_text"]
                                  or t("about.licence_missing"))
        self.licence.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        # A floor, not a ceiling: the licence is the one thing in here worth
        # more room, so it is what grows when the dialog is made taller.
        # The file is wrapped at seventy columns already, and showing it in
        # the interface face keeps it prose rather than a printout.
        self.licence.setMinimumHeight(
            self.licence.fontMetrics().lineSpacing() * LICENCE_LINES)

        bundled_heading = QLabel(t("about.bundled"))
        bundled_heading.setFont(theme.label_font(self.font()))
        style.note(bundled_heading)
        self.bundled = QLabel(self._bundled_text())
        self.bundled.setWordWrap(True)
        style.note(self.bundled)

        buttons = QHBoxLayout()
        self.open_file = QPushButton(t("about.open_licence"))
        self.open_file.setEnabled(bool(self.facts["licence_path"]))
        self.open_file.clicked.connect(self.open_licence_file)
        close = QPushButton(t("gui.close"))
        close.setObjectName("primary")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        symbols.dress(self.open_file, "document")
        symbols.dress(close, "checkmark")
        buttons.addWidget(self.open_file)
        buttons.addStretch(1)
        buttons.addWidget(close)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        layout = QVBoxLayout()
        layout.setContentsMargins(theme.GUTTER, theme.GUTTER,
                                  theme.GUTTER, theme.GUTTER)
        layout.setSpacing(10)
        outer.addLayout(layout, 1)
        head = QHBoxLayout()
        head.setSpacing(theme.GUTTER)
        head.addWidget(self.mark, 0, Qt.AlignmentFlag.AlignTop)
        names = QVBoxLayout()
        names.setSpacing(2)
        names.addWidget(self.name)
        names.addWidget(self.tagline)
        names.addStretch(1)
        head.addLayout(names, 1)
        layout.addLayout(head)
        layout.addWidget(version)
        layout.addWidget(self.source)
        layout.addWidget(licence_heading)
        layout.addWidget(self.licence_name)
        layout.addWidget(self.licence, 1)
        layout.addWidget(bundled_heading)
        layout.addWidget(self.bundled)
        layout.addLayout(buttons)
        # A top-level window is sized from its layout's minimum, which knows
        # nothing of text that wraps: the paragraph under "what is bundled"
        # was given one line and drawn over the licence. The width is fixed,
        # so the height that width needs can be asked for outright.
        self.setMinimumHeight(outer.totalHeightForWidth(WIDTH))

    def _bundled_text(self):
        """One sentence about somebody else's work that ships in here.

        The typefaces are OFL and the licence travels with them; the packages
        the program imports are installed separately and are nobody's to
        relicense here, which is worth saying so that this dialog is not read
        as covering them."""
        faces = ", ".join(f"{font['family']} ({font['licence']})"
                          for font in self.facts["fonts"])
        lines = []
        if faces:
            lines.append(f"{t('about.fonts')} {faces}.")
        lines.append(t("about.dependencies"))
        return "\n".join(lines)

    def open_licence_file(self):
        """Hand the file to whatever the desktop opens text with."""
        path = self.facts["licence_path"]
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
