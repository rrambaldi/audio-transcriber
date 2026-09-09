"""What to do with one recording, asked at the moment you start it.

The options used to belong to the tab: whatever the left column said when a
file was added became that file's settings, for good. That is the wrong shape
for the way the queue is actually used — half a dozen recordings dropped in
at once, and one of them is the interview that needs subtitles while the rest
are notes to read. So the column now holds the defaults, and this dialog is
where one recording's own answers are given, seeded from them.

It is the same :class:`OptionsForm` the column is built from, without the step
numbers: in a dialog about one recording there is no sequence to be at step
two of.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QScrollArea,
    QVBoxLayout,
)

from ..i18n import t
from . import style
from .options_form import OptionsForm


class JobDialog(QDialog):
    """The four questions, for one recording, with Transcribe at the bottom."""

    def __init__(self, title, settings=None, defaults=None, vocabularies=None,
                 custom_text=None, store=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("gui.job_dialog_title", title=title))
        self.setModal(True)

        heading = QLabel(t("gui.job_dialog_title", title=title))
        heading.setWordWrap(True)
        note = QLabel(t("gui.job_dialog_note"))
        note.setWordWrap(True)
        style.note(note)

        self.form = OptionsForm(settings)
        # Where the answers start from: config.toml, then whatever was
        # answered last time. Six meetings in the queue should be six
        # confirmations, not six forms.
        self._store = store
        self.form.load_state(store)
        if defaults:
            self.form.set_choices(defaults, vocabularies, custom_text)

        # Four sections open are taller than a laptop screen, and a dialog
        # whose buttons are off the bottom of the display cannot be answered.
        scroll = QScrollArea()
        scroll.setWidget(self.form)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMinimumWidth(460)
        scroll.setMinimumHeight(320)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        self.start = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.start.setText(t("gui.start"))
        self.start.setObjectName("primary")
        self.start.setDefault(True)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            t("gui.cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(note)
        layout.addWidget(scroll, 1)
        layout.addWidget(buttons)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

    def accept(self):
        """Keep the answers, so the next recording starts from them."""
        self.form.save_state(self._store)
        super().accept()

    # --- the answers -------------------------------------------------------

    def choices(self):
        return self.form.choices()

    def vocabularies(self):
        return self.form.chosen_vocabularies()

    def custom_text(self):
        return self.form.custom_text()
