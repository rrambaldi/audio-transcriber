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
from PySide6.QtGui import QDesktopServices, QPixmap
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
from . import style, theme

#: How tall the licence gets to be before it starts scrolling. The file is
#: forty lines; this shows about half of it, which is enough to see that it
#: begins with something other than boilerplate.
LICENCE_LINES = 16

#: How wide the banner is drawn, in logical pixels, and so how wide the box
#: is: the banner runs edge to edge, and a box wider than its head would show
#: where the picture stops.
BANNER_WIDTH = 640


class AboutDialog(QDialog):
    """The mark, the version, the licence, and what is bundled."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.facts = about.facts()
        self.setWindowTitle(t("about.title"))
        self.setModal(True)
        self.setFixedWidth(BANNER_WIDTH)

        # The mark and the name, drawn once for the README and used here as
        # they are. It carries the name, so the label is named after it for
        # whoever cannot see the picture.
        self.banner = QLabel()
        self.banner.setPixmap(self._banner_pixmap())
        self.banner.setAccessibleName(t("gui.wordmark"))

        # The version goes directly under the name, where somebody looking for
        # it looks; the licence's own name goes under the "license" heading,
        # with the text it names.
        version = QLabel(t("about.version", version=__version__))
        style.note(version)

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
        buttons.addWidget(self.open_file)
        buttons.addStretch(1)
        buttons.addWidget(close)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.banner)
        layout = QVBoxLayout()
        layout.setContentsMargins(theme.GUTTER, theme.GUTTER,
                                  theme.GUTTER, theme.GUTTER)
        layout.setSpacing(10)
        outer.addLayout(layout, 1)
        layout.addWidget(version)
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
        self.setMinimumHeight(outer.totalHeightForWidth(BANNER_WIDTH))

    def _banner_pixmap(self):
        """The banner at the box's width, sharp on a high-DPI screen."""
        ratio = self.devicePixelRatioF() or 1.0
        pixmap = QPixmap(branding.path(branding.BANNER))
        if pixmap.isNull():
            return pixmap
        pixmap = pixmap.scaledToWidth(round(BANNER_WIDTH * ratio),
                                      Qt.TransformationMode.SmoothTransformation)
        pixmap.setDevicePixelRatio(ratio)
        return pixmap

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
