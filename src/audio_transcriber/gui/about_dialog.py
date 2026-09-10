"""What this program is, and the licence it is given under.

The window has no menu bar - nothing in it is hidden behind one - so the way
in is the version, in the masthead, where a version already was. Clicking it
opens this, and so does F1, which is the only key anybody presses looking for
help.

The whole licence is shown rather than its name. It is the MIT license with a
wish in front of it, and a dialog that said "MIT" and stopped would show the
half nobody needs to read: see :mod:`audio_transcriber.about`. The text is
selectable and read-only, because the one thing somebody may actually want to
do with a licence is copy it.
"""
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from .. import __version__, about
from ..i18n import t
from . import masthead, style, theme

#: How tall the licence gets to be before it starts scrolling. The file is
#: forty lines; this shows about half of it, which is enough to see that it
#: begins with something other than boilerplate.
LICENCE_LINES = 16


class AboutDialog(QDialog):
    """The mark, the version, the licence, and what is bundled."""

    def __init__(self, icon=None, parent=None):
        super().__init__(parent)
        self.facts = about.facts()
        self.setWindowTitle(t("about.title"))
        self.setModal(True)

        head = QHBoxLayout()
        head.setSpacing(14)
        if icon is not None and not icon.isNull():
            mark = QLabel()
            mark.setPixmap(masthead.mark_pixmap(icon, self))
            head.addWidget(mark, 0, Qt.AlignmentFlag.AlignTop)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        name = QLabel(t("gui.app_name"))
        name.setFont(theme.title_font(self.font(), theme.TITLE_SCALE))
        titles.addWidget(name)
        tagline = QLabel(t("gui.tagline"))
        tagline.setFont(theme.title_font(self.font(), 1.05, italic=True))
        titles.addWidget(style.note(tagline))
        version = QLabel(t("about.version", version=__version__,
                           licence=self.facts["licence_title"]))
        version.setWordWrap(True)
        titles.addWidget(style.note(version))
        head.addLayout(titles, 1)

        licence_heading = QLabel(t("about.licence"))
        licence_heading.setFont(theme.label_font(self.font()))
        style.note(licence_heading)

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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(theme.GUTTER, theme.GUTTER,
                                  theme.GUTTER, theme.GUTTER)
        layout.setSpacing(10)
        layout.addLayout(head)
        layout.addWidget(licence_heading)
        layout.addWidget(self.licence, 1)
        layout.addWidget(bundled_heading)
        layout.addWidget(self.bundled)
        layout.addLayout(buttons)

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
