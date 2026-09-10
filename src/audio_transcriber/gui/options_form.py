"""The questions about a transcription, as a list of sections that open.

Four of them — what do you want out of it, how to transcribe it, how to cut
the subtitles, which keywords to expect — and they are asked in two places:
down the left of the Transcribe tab, where they are the settings a new
recording gets, and in the dialog that starts one recording, where they are
that recording's own. Two places, one widget: the alternative is two
implementations of the same four questions, which is how they start to
disagree.

Every section reports what it holds while it is shut ("3 · How to transcribe
them — auto · Italiano (it) · auto"), because closing a section must not hide
a choice. A section that does not apply — subtitles, when the answer is plain
text — stays in the list and goes quiet instead of vanishing: a row that
waits can be learned, a list that changes shape under the pointer has to be
re-read.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..diarization import NO_MODEL
from ..diarization import availability as diarization_availability
from ..i18n import t
from ..vocabularies import MAX_PROMPT_CHARS
from . import options, style, widgets


class OptionsForm(QWidget):
    """The sections that say what to do with a recording."""

    def __init__(self, settings=None, parent=None):
        super().__init__(parent)
        self.settings = dict(settings or {})
        self._build()
        self._assemble()
        self._output_chosen()

    # --- the controls ------------------------------------------------------

    def _build(self):
        defaults = options.defaults_from(self.settings)

        # The first thing to decide, and until now the one thing the window
        # never asked: what is wanted out of the run. Everything below is a
        # detail of one of these three.
        self.outputs = QButtonGroup(self)
        self.output_buttons = {}
        for label, note, value in options.output_choices():
            button = QRadioButton(label)
            button.setToolTip(note)
            button.setChecked(value == defaults["output"])
            self.outputs.addButton(button)
            self.output_buttons[value] = button
            button.toggled.connect(self._output_chosen)

        self.output_note = QLabel("")
        self.output_note.setWordWrap(True)
        # A note, not a disabled control: greying it out is the cheap way to
        # make it look secondary and it drops the contrast to 1.75:1, on the
        # one sentence that has to be read before choosing.
        style.note(self.output_note)
        self.output_note.setAlignment(Qt.AlignmentFlag.AlignTop)

        # And the reason an answer is missing belongs on the screen, not only
        # in a tooltip nobody hovers.
        self.output_unavailable = QLabel("")
        self.output_unavailable.setWordWrap(True)
        style.note(self.output_unavailable)

        self.model = QComboBox()
        for label, value in options.model_choices():
            self.model.addItem(label, value)
        self.language = QComboBox()
        for label, value in options.language_choices():
            self.language.addItem(label, value)
        self.backend = QComboBox()
        for label, value in options.backend_choices():
            self.backend.addItem(label, value)
        _select(self.model, defaults["model"])
        _select(self.language, defaults["language"])
        _select(self.backend, defaults["backend"])
        for box in (self.model, self.language, self.backend):
            box.currentIndexChanged.connect(lambda _index: self.update_summaries())

        self.diarize = QCheckBox(t("gui.diarize"))
        self.diarize.setChecked(defaults["diarize"])
        self.speakers = QSpinBox()
        self.speakers.setRange(0, 20)
        self.speakers.setSpecialValueText(t("gui.speakers_unknown"))
        self.speakers.setValue(defaults["speakers"])
        state, detail = diarization_availability(self.settings.get("diar_model"))
        self._diarization_ready = state == "ready"
        if state != "ready":
            # Offering a checkbox this machine cannot honour only produces a
            # job that fails after the wait, which is a worse way to find out.
            self.diarize.setChecked(False)
            self.diarize.setEnabled(False)
            self.speakers.setEnabled(False)
            self.diarize.setToolTip(t("gui.diarize_unavailable", detail=detail))
            # And "who said what" is then not an output this machine can
            # produce at all: the answer is refused here, with the reason on
            # the button, rather than by a job that fails after the wait.
            unavailable = self.output_buttons["speakers"]
            unavailable.setEnabled(False)
            unavailable.setToolTip(t("gui.diarize_unavailable", detail=detail))
            if unavailable.isChecked():
                self.output_buttons["text"].setChecked(True)
            # Written on screen, and written as something to do about it: the
            # tooltip's "pyannote.audio" is the name of a module, which is not
            # what somebody who wanted a dialogue needs to read.
            self.output_unavailable.setText(t(
                "gui.output_speakers_unconfigured" if state == NO_MODEL
                else "gui.output_speakers_missing", detail=detail))

        self.vocabularies = QListWidget()
        self.vocabularies.setToolTip(t("gui.vocab_hint"))
        for item in options.vocabulary_items(self.settings.get("vocab_dir")):
            row = QListWidgetItem(item["label"])
            row.setData(Qt.ItemDataRole.UserRole, item["name"])
            row.setToolTip(item["tooltip"])
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            row.setCheckState(Qt.CheckState.Checked
                              if item["name"] in defaults["vocabulary"]
                              else Qt.CheckState.Unchecked)
            self.vocabularies.addItem(row)
        self.vocabularies.itemChanged.connect(lambda _item: self.update_summaries())

        self.subtitle_preset = QComboBox()
        self.subtitle_preset.setToolTip(t("gui.sub_preset_tip"))
        for label, name in options.subtitle_preset_choices():
            self.subtitle_preset.addItem(label, name)
        _select(self.subtitle_preset, defaults["subtitle_preset"])
        self.subtitle_chars = QSpinBox()
        self.subtitle_chars.setRange(0, 120)
        self.subtitle_chars.setSpecialValueText(t("gui.sub_from_preset"))
        self.subtitle_chars.setToolTip(t("gui.sub_chars_tip"))
        self.subtitle_words = QSpinBox()
        self.subtitle_words.setRange(0, 60)
        self.subtitle_words.setSpecialValueText(t("gui.sub_from_preset"))
        self.subtitle_words.setToolTip(t("gui.sub_words_tip"))
        # A text somebody already has for this recording: it helps the engine
        # spell and then proof-reads it. See audio_transcriber/reference.py.
        self.reference = QPlainTextEdit()
        self.reference.setPlaceholderText(t("gui.reference_hint"))
        self.reference.setToolTip(t("gui.reference_tip"))
        self.save_srt = QCheckBox(t("gui.sub_save_srt"))
        self.save_vtt = QCheckBox(t("gui.sub_save_vtt"))
        for box in (self.save_srt, self.save_vtt):
            box.setToolTip(t("gui.sub_save_tip"))
        self.save_srt.setChecked("srt" in defaults["subtitles"])
        self.save_vtt.setChecked("vtt" in defaults["subtitles"])
        self.subtitle_preset.currentIndexChanged.connect(
            lambda _index: self.update_summaries())
        for spin in (self.subtitle_chars, self.subtitle_words):
            spin.valueChanged.connect(lambda _value: self.update_summaries())
        for box in (self.save_srt, self.save_vtt):
            box.toggled.connect(lambda _on: self.update_summaries())

        self.custom = QPlainTextEdit()
        self.custom.setPlaceholderText(t("gui.vocab_custom_hint"))
        self.custom.textChanged.connect(self._count_prompt)
        self.prompt_size = QLabel("")

    # --- the sections ------------------------------------------------------

    def _assemble(self):
        output_page = QWidget()
        output_layout = QVBoxLayout(output_page)
        output_layout.setContentsMargins(0, 0, 0, 0)
        for _label, _note, value in options.output_choices():
            output_layout.addWidget(self.output_buttons[value])
        # One note, for the answer that is chosen. Three notes at once is a
        # paragraph to read before the first click.
        output_layout.addWidget(self.output_note)
        self._reserve_note_lines(3)
        output_layout.addWidget(self.output_unavailable)
        self.step_output = widgets.Disclosure(t("gui.step_output"),
                                              output_page, open_now=True,
                                              key="output")

        options_page = QWidget()
        self.form = QFormLayout(options_page)
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.addRow(t("gui.label_model"), self.model)
        self.form.addRow(t("gui.label_language"), self.language)
        self.form.addRow(t("gui.label_backend"), self.backend)
        speakers_row = QHBoxLayout()
        speakers_row.addWidget(self.diarize)
        speakers_row.addWidget(QLabel(t("gui.label_speakers")))
        speakers_row.addWidget(self.speakers)
        speakers_row.addStretch(1)
        self.form.addRow("", _wrap(speakers_row))
        self._speakers_row = self.form.rowCount() - 1
        self.step_options = widgets.Disclosure(t("gui.step_options"),
                                               options_page, key="options")

        subtitle_page = QWidget()
        subtitle_form = QFormLayout(subtitle_page)
        subtitle_form.setContentsMargins(0, 0, 0, 0)
        subtitle_form.addRow(t("gui.label_sub_preset"), self.subtitle_preset)
        subtitle_form.addRow(t("gui.label_sub_chars"), self.subtitle_chars)
        subtitle_form.addRow(t("gui.label_sub_words"), self.subtitle_words)
        save_row = QHBoxLayout()
        save_row.addWidget(self.save_srt)
        save_row.addWidget(self.save_vtt)
        save_row.addStretch(1)
        subtitle_form.addRow(t("gui.label_sub_save"), _wrap(save_row))
        subtitle_form.addRow(style.note(QLabel(t("gui.reference_note"))))
        subtitle_form.addRow(t("gui.label_reference"), self.reference)
        self.step_subtitles = widgets.Disclosure(t("gui.group_subtitles"),
                                                 subtitle_page, key="subtitles")

        vocab_page = QWidget()
        vocab_layout = QVBoxLayout(vocab_page)
        vocab_layout.setContentsMargins(0, 0, 0, 0)
        vocab_layout.addWidget(self.vocabularies, 2)
        vocab_layout.addWidget(QLabel(t("gui.vocab_custom")))
        vocab_layout.addWidget(self.custom, 1)
        vocab_layout.addWidget(self.prompt_size)
        self.vocab_panel = widgets.Disclosure(t("gui.group_vocabulary"),
                                              vocab_page, key="vocabulary")

        self.sections = [self.step_output, self.step_options,
                         self.step_subtitles, self.vocab_panel]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        for section in self.sections:
            layout.addWidget(section)

        # A combo box asks to be as wide as its longest item, and "auto
        # (small on this machine)" is a long item: left alone they set the
        # minimum width of the whole column. They may shrink; the menu still
        # opens at full width.
        for box in self.findChildren(QComboBox):
            box.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            box.setMinimumContentsLength(12)
        self._count_prompt()

    def _reserve_note_lines(self, lines):
        """Keep room for the longest note so the sections below do not move.

        The note is wrapped text that changes with the answer: sized to
        whatever it happens to say, choosing an answer would shift the rest of
        the list up or down under the pointer."""
        metrics = self.output_note.fontMetrics()
        self.output_note.setMinimumHeight(metrics.lineSpacing() * lines)

    # --- what the answers do to each other ---------------------------------

    def chosen_output(self):
        """Which of the three the radio buttons say."""
        for value, button in self.output_buttons.items():
            if button.isChecked():
                return value
        return "text"

    def _output_chosen(self):
        """Follow the chosen answer through the rest of the list.

        A subtitle preset next to "just the text" is a control that does
        nothing, and a control that does nothing is a question the window
        cannot answer. Inside a section, what belongs to another answer goes
        away; the subtitle *section* stays in the list and goes quiet
        instead, saying which answer would bring it to life."""
        chosen = self.chosen_output()
        self.output_note.setText(options.output_note(chosen))
        enables = options.output_enables(chosen)
        self.diarize.setEnabled(enables["diarize"] and self._diarization_ready)
        self.speakers.setEnabled(enables["speakers"] and self._diarization_ready)
        self.form.setRowVisible(self._speakers_row, enables["speakers"])
        for widget in (self.subtitle_preset, self.subtitle_chars,
                       self.subtitle_words, self.save_srt, self.save_vtt):
            widget.setEnabled(enables["subtitles"])
        self.step_subtitles.set_available(
            enables["subtitles"],
            t("gui.only_with_subtitles", answer=t("gui.output_subtitles")))
        if enables["subtitles"] and not (self.save_srt.isChecked()
                                         or self.save_vtt.isChecked()):
            # The chosen output is the files, so one is written either way:
            # showing it ticked is more honest than saving an .srt behind an
            # empty box.
            self.save_srt.setChecked(True)
        self.update_summaries()

    def update_summaries(self):
        """What each closed section says about itself."""
        self.step_output.set_summary(options.output_label(self.chosen_output()))
        # The value, not the label: "auto (small on this machine)" is the
        # right thing in a menu and too long for a row that has to fit.
        self.step_options.set_summary("  ·  ".join(str(value) for value in (
            self.model.currentData(), self.language.currentText(),
            self.backend.currentData()) if value))
        self.step_subtitles.set_summary(options.subtitle_summary_line(
            self.subtitle_preset.currentData(),
            self.subtitle_chars.value(), self.subtitle_words.value(),
            self.save_srt.isChecked(), self.save_vtt.isChecked()))
        chosen = len(self.chosen_vocabularies())
        typed = bool(self.custom.toPlainText().strip())
        if chosen and typed:
            summary = t("gui.vocab_chosen_terms", count=chosen)
        elif chosen:
            summary = t("gui.vocab_chosen", count=chosen)
        elif typed:
            summary = t("gui.vocab_terms_only")
        else:
            summary = t("gui.vocab_none")
        self.vocab_panel.set_summary(summary)

    def _count_prompt(self):
        """Show how long the prompt is getting, and warn past the limit.

        Whisper silently truncates a long initial prompt, so a vocabulary that
        is quietly too long is worse than one that complains."""
        text = self.custom.toPlainText()
        problem = options.custom_vocabulary_problem(text)
        if problem:
            self.prompt_size.setText(problem)
        else:
            self.prompt_size.setText(t("gui.vocab_chars", chars=len(text),
                                       limit=MAX_PROMPT_CHARS))
        self.update_summaries()

    # --- what it all amounts to --------------------------------------------

    def chosen_vocabularies(self):
        """Names of the ticked keyword sets, in the order they are listed."""
        names = []
        for row in range(self.vocabularies.count()):
            item = self.vocabularies.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                names.append(item.data(Qt.ItemDataRole.UserRole))
        return names

    def custom_text(self):
        return self.custom.toPlainText()

    def choices(self):
        """Everything the option widgets currently say."""
        return {
            "model": self.model.currentData(),
            "language": self.language.currentData(),
            "backend": self.backend.currentData(),
            "output": self.chosen_output(),
            "diarize": self.diarize.isChecked(),
            "speakers": self.speakers.value(),
            "subtitle_preset": self.subtitle_preset.currentData(),
            "subtitle_chars": self.subtitle_chars.value(),
            "subtitle_words": self.subtitle_words.value(),
            "srt": self.save_srt.isChecked(),
            "vtt": self.save_vtt.isChecked(),
            "reference": self.reference.toPlainText().strip(),
        }

    def set_choices(self, choices, vocabularies=None, custom_text=None):
        """Start from somebody else's answers — the tab's, for one recording."""
        _select(self.model, choices.get("model"))
        _select(self.language, choices.get("language"))
        _select(self.backend, choices.get("backend"))
        button = self.output_buttons.get(choices.get("output"))
        if button is not None and button.isEnabled():
            button.setChecked(True)
        if self._diarization_ready:
            self.diarize.setChecked(bool(choices.get("diarize")))
        self.speakers.setValue(int(choices.get("speakers") or 0))
        _select(self.subtitle_preset, choices.get("subtitle_preset"))
        self.subtitle_chars.setValue(int(choices.get("subtitle_chars") or 0))
        self.subtitle_words.setValue(int(choices.get("subtitle_words") or 0))
        self.save_srt.setChecked(bool(choices.get("srt")))
        self.save_vtt.setChecked(bool(choices.get("vtt")))
        if vocabularies is not None:
            wanted = set(vocabularies)
            for row in range(self.vocabularies.count()):
                item = self.vocabularies.item(row)
                item.setCheckState(
                    Qt.CheckState.Checked
                    if item.data(Qt.ItemDataRole.UserRole) in wanted
                    else Qt.CheckState.Unchecked)
        if custom_text is not None:
            self.custom.setPlainText(custom_text)
        self._output_chosen()

    # --- what is remembered between sessions -------------------------------

    def save_state(self, store):
        if store is None:
            return
        store.setValue("custom_vocabulary", self.custom.toPlainText())
        store.setValue("model", self.model.currentData())
        store.setValue("language", self.language.currentData())
        store.setValue("backend", self.backend.currentData())
        store.setValue("vocabulary", self.chosen_vocabularies())
        store.setValue("output", self.chosen_output())
        store.setValue("subtitle_preset", self.subtitle_preset.currentData())
        store.setValue("subtitle_chars", self.subtitle_chars.value())
        store.setValue("subtitle_words", self.subtitle_words.value())
        store.setValue("save_srt", self.save_srt.isChecked())
        store.setValue("save_vtt", self.save_vtt.isChecked())
        for section in self.sections:
            store.setValue(f"open_{section.key}", section.is_open())

    def load_state(self, store):
        """Restore the choices, which are a habit rather than a configuration.

        The vocabulary typed here is the desktop counterpart of the browser's
        local storage: it stays on this machine and never reaches
        ``config.toml``, which belongs to whoever set the tool up."""
        if store is None:
            self._count_prompt()
            return
        self.custom.setPlainText(store.value("custom_vocabulary", "", str))
        for name, widget in (("model", self.model), ("language", self.language),
                             ("backend", self.backend)):
            remembered = store.value(name, "", str)
            if remembered:
                _select(widget, remembered)
        remembered_output = store.value("output", "", str)
        button = self.output_buttons.get(remembered_output)
        if button is not None and button.isEnabled():
            button.setChecked(True)
        _select(self.subtitle_preset, store.value("subtitle_preset", "", str))
        self.subtitle_chars.setValue(int(store.value("subtitle_chars", 0, int) or 0))
        self.subtitle_words.setValue(int(store.value("subtitle_words", 0, int) or 0))
        self.save_srt.setChecked(bool(store.value("save_srt", False, bool)))
        self.save_vtt.setChecked(bool(store.value("save_vtt", False, bool)))
        for section in self.sections:
            # A section the machine cannot offer stays shut whatever the file
            # says; set_open() refuses it anyway, this is just honest.
            remembered_open = store.value(f"open_{section.key}", None)
            if remembered_open is not None:
                section.set_open(remembered_open in (True, "true"))
        remembered = store.value("vocabulary", None)
        if remembered is not None:
            wanted = set(remembered if isinstance(remembered, list)
                         else [remembered] if remembered else [])
            for row in range(self.vocabularies.count()):
                item = self.vocabularies.item(row)
                item.setCheckState(
                    Qt.CheckState.Checked
                    if item.data(Qt.ItemDataRole.UserRole) in wanted
                    else Qt.CheckState.Unchecked)
        self._count_prompt()


def _select(combo, value):
    """Select the entry whose data is ``value``, if there is one."""
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)


def _wrap(layout):
    """A layout as a widget, which is what QFormLayout rows want."""
    holder = QWidget()
    holder.setLayout(layout)
    return holder
