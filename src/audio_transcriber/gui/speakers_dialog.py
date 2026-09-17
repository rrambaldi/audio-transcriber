"""Putting names to the voices a diarized transcript kept apart.

The machine can hear that two people are talking and cannot hear who they
are: that is in the room, not in the sound. So a transcript arrives addressed
to ``SPEAKER_00``, and this is where somebody who has read a line of it and
recognised a voice says so.

One field per voice, in the order they are first heard, which is the order
somebody reading the transcript meets them in. The line each field carries is
the first thing that voice actually says - a label is not a reminder of
anything, and "which one was SPEAKER_01" is a question the dialog should
answer rather than ask.

What it does not do is guess. A name in the audio ("thanks, Anna") is a
tempting hint and a bad one: the person addressed is not the person speaking,
and a wrong name written into a transcript is worse than a right label.
"""
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from ..i18n import t
from . import style, theme

#: How much of a speaker's first line is shown beside their field. Long enough
#: to recognise a voice by, short enough not to widen the dialog.
SAMPLE_CHARS = 60


class SpeakersDialog(QDialog):
    """One field per voice, prefilled with the name it already has."""

    def __init__(self, speakers, samples=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("gui.name_speakers_title"))
        self.setModal(True)
        self.speakers = list(speakers)
        self.fields = {}

        layout = QVBoxLayout(self)
        intro = QLabel(t("gui.name_speakers_intro"))
        intro.setWordWrap(True)
        layout.addWidget(style.note(intro))

        form = QFormLayout()
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        for label in self.speakers:
            field = QLineEdit()
            field.setPlaceholderText(t("gui.name_speakers_hint"))
            # Not prefilled with the label: a field holding SPEAKER_00 has to
            # be cleared before it can be typed in, and a name nobody changed
            # would then be written back as if it had been chosen.
            self.fields[label] = field
            name = QLabel(label)
            name.setFont(theme.label_font(self.font()))
            form.addRow(name, field)
            sample = (samples or {}).get(label)
            if sample:
                # On a row of its own rather than under the label, where a
                # form's first column is as narrow as its longest label and
                # a sentence would simply be cut off.
                said = QLabel(shorten(sample))
                said.setWordWrap(True)
                form.addRow(style.note(said))
        layout.addLayout(form)

        # Off the last speaker's own line: at the same indent and the same
        # weight it reads as one more thing that voice said.
        layout.addSpacing(8)
        same = QLabel(t("gui.name_speakers_same"))
        same.setWordWrap(True)
        layout.addWidget(style.note(same))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if self.speakers:
            self.fields[self.speakers[0]].setFocus()

    def names(self):
        """What was typed, by label, with the blanks left out."""
        return {label: field.text().strip()
                for label, field in self.fields.items()
                if field.text().strip()}


def shorten(text, limit=SAMPLE_CHARS):
    """One line of what somebody said, cut at a word if it has to be cut."""
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def first_lines(segments):
    """The first thing each speaker says, by label.

    From the segments rather than from the transcript, because the transcript
    has already had its turns merged and its text cleaned: what is wanted
    here is the earliest thing attributable to a voice, not the tidiest."""
    said = {}
    for segment in segments:
        label, text = segment.get("speaker"), (segment.get("text") or "").strip()
        if label and text and label not in said:
            said[label] = text
    return said
