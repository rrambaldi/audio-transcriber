"""The "transcribe" tab: what to transcribe, how, and what the queue is doing.

The panel owns no transcription logic at all. It collects choices, hands a file
to :class:`audio_transcriber.jobs.JobQueue` — the very queue the web interface
uses — and then polls it on a timer, exactly as the web page polls over HTTP.
Polling rather than signalling is deliberate: the queue runs the transcription
in a worker thread that knows nothing about Qt, and reading a few attributes
twice a second is cheaper than making that thread talk to the GUI.
"""
import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..diarization import NO_MODEL
from ..diarization import availability as diarization_availability
from ..i18n import t
from ..library import STORE_COPY, STORE_MOVE
from ..vocabularies import MAX_PROMPT_CHARS
from . import options, style, widgets
from .recorder import make_recorder

#: How often the queue is re-read. Twice a second is imperceptible on a
#: transcription measured in minutes, and costs nothing.
REFRESH_MS = 500


class TranscribePanel(QWidget):
    """Sources, options, and the queue.

    Adding a file queues it, and the queue runs on its own: there is no
    "start" to press. The first version kept the chosen files in a list of
    their own, waiting for a button, and the honest verdict on it was that
    nobody could tell how to begin — a list that looks like a queue and is
    not one is worse than no list."""

    #: A finished job was double-clicked: the window should show the entry.
    entry_requested = Signal(str)
    #: A job has just finished; the argument is its entry id, "" if it failed.
    job_finished = Signal(str)
    #: Something worth putting in the status bar happened.
    message = Signal(str)

    def __init__(self, queue, settings=None, store=None, parent=None):
        super().__init__(parent)
        self.queue = queue
        self.settings = dict(settings or {})
        self.store = store
        self._rows = []

        self.setAcceptDrops(True)
        self.recorder = make_recorder(self.queue.upload_dir(), store=self.store)
        self.recorder.recorded.connect(self._recorded)
        self.recorder.failed.connect(self.message.emit)

        self._build_options()
        self._build_queue_table()
        self._assemble()
        self._load_state()
        self._output_chosen()
        self.refresh()

        self._add_shortcuts()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(REFRESH_MS)

    # --- construction -----------------------------------------------------

    def _add_shortcuts(self):
        """The four keys somebody who uses this every day will reach for.

        There were none at all: not even Enter, on a tab whose whole purpose
        is one button."""
        for keys, slot in (
            (QKeySequence.StandardKey.Open, self.choose_files),
            (QKeySequence("Ctrl+Return"), self.start_queue),
            (QKeySequence("Ctrl+Enter"), self.start_queue),
        ):
            QShortcut(keys, self, activated=slot)
        # Delete belongs to the list, not to the whole tab: it must not fire
        # while somebody is writing their own terms.
        QShortcut(QKeySequence.StandardKey.Delete, self.table,
                  activated=self._delete_selected)

    def _delete_selected(self):
        """Take the selected job out, whichever "out" applies to it."""
        row = self._selected_row()
        if row is None:
            return
        if row["cancellable"]:
            self.cancel_selected()
        elif row["finished"]:
            self.forget_selected()

    def _build_options(self):
        defaults = options.defaults_from(self.settings)

        # The first thing to decide, and until now the one thing the window
        # never asked: what is wanted out of the run. Everything below is a
        # detail of one of these three, and is greyed out when it belongs to
        # another.
        self.outputs = QButtonGroup(self)
        self.output_buttons = {}
        for label, note, value in options.output_choices():
            button = QRadioButton(label)
            button.setToolTip(note)
            button.setChecked(value == defaults["output"])
            self.outputs.addButton(button)
            self.output_buttons[value] = button
            button.toggled.connect(self._output_chosen)

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
        self.vocabularies.itemChanged.connect(lambda _item: self._update_summary())

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
        self.save_srt = QCheckBox(t("gui.sub_save_srt"))
        self.save_vtt = QCheckBox(t("gui.sub_save_vtt"))
        for box in (self.save_srt, self.save_vtt):
            box.setToolTip(t("gui.sub_save_tip"))
        self.save_srt.setChecked("srt" in defaults["subtitles"])
        self.save_vtt.setChecked("vtt" in defaults["subtitles"])

        self.custom = QPlainTextEdit()
        self.custom.setPlaceholderText(t("gui.vocab_custom_hint"))
        self.custom.textChanged.connect(self._count_prompt)
        self.prompt_size = QLabel("")

    def _build_queue_table(self):
        self.table = QTableWidget(0, len(options.job_headers()))
        self.table.setHorizontalHeaderLabels(options.job_headers())
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        # The recording is a title with its facts under it, painted by a
        # delegate: model, duration and words were three columns that stood
        # empty for the whole of a job and filled a moment before the row
        # stopped being interesting.
        self.table.setItemDelegateForColumn(0, widgets.JobDelegate(self.table))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.itemDoubleClicked.connect(self._open_selected_entry)
        # Not only on the refresh tick: clicking a row and finding the buttons
        # still describing the previous one is half a second of lying.
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.summary = QLabel("")

    def _assemble(self):
        # The tab is a sequence, not a dashboard: what you want, what to run
        # it on, how to run it. It used to be three columns side by side with
        # the button that starts everything in the bottom-left corner, so the
        # eye crossed the window three times for a task that is a straight
        # line.
        output_box = QGroupBox(t("gui.step_output"))
        output_layout = QVBoxLayout(output_box)
        for _label, _note, value in options.output_choices():
            output_layout.addWidget(self.output_buttons[value])
        # One note, for the answer that is chosen. Three notes at once is a
        # paragraph to read before the first click, and it left the box no
        # room for the controls underneath.
        self.output_note = QLabel("")
        self.output_note.setWordWrap(True)
        # A note, not a disabled control: greying it out is the cheap way to
        # make it look secondary and it drops the contrast to 1.75:1, on the
        # one sentence that has to be read before choosing.
        style.note(self.output_note)
        self.output_note.setAlignment(Qt.AlignmentFlag.AlignTop)
        output_layout.addWidget(self.output_note)
        self._reserve_note_lines(3)

        # And the reason an answer is missing belongs on the screen, not only
        # in a tooltip nobody hovers.
        output_layout.addWidget(self.output_unavailable)

        # --- step 2: the two ways in, as two tabs rather than one under the
        # other. A microphone is not an option of the file list, it is the
        # other half of the question, and the browser page has said so with
        # two tabs since it was written.
        sources_box = QGroupBox(t("gui.step_sources"))
        add = QPushButton(t("gui.add_files"))
        add.clicked.connect(self.choose_files)
        buttons = QHBoxLayout()
        buttons.addWidget(add)
        buttons.addStretch(1)
        self.drop_hint = QLabel(t("gui.drop_hint"))
        self.drop_hint.setWordWrap(True)
        self.drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_hint.setFrameShape(QFrame.Shape.StyledPanel)
        self.drop_hint.setMinimumHeight(72)
        files_page = QWidget()
        files_layout = QVBoxLayout(files_page)
        files_layout.addLayout(buttons)
        files_layout.addWidget(self.drop_hint, 1)
        record_page = QWidget()
        record_layout = QVBoxLayout(record_page)
        record_layout.addWidget(self.recorder)
        record_layout.addStretch(1)
        self.sources = QTabWidget()
        self.sources.addTab(files_page, t("gui.tab_files"))
        self.sources.addTab(record_page, t("gui.tab_record"))
        queue_hint = QLabel(t("gui.queue_hint"))
        queue_hint.setWordWrap(True)        # a narrow window must not cut it
        style.note(queue_hint)
        sources_layout = QVBoxLayout(sources_box)
        sources_layout.addWidget(self.sources)
        sources_layout.addWidget(queue_hint)

        # --- step 3: the details, and the ones that are rarely touched put
        # away behind a row that says what is inside them.
        settings_box = QGroupBox(t("gui.step_options"))
        self.form = QFormLayout(settings_box)
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

        # How the cues are cut is a detail of one of the three answers, so it
        # is a box of its own that appears when that answer is chosen: kept in
        # the options form it was four rows of nothing for the other two.
        self.subtitle_box = QGroupBox(t("gui.group_subtitles"))
        subtitle_form = QFormLayout(self.subtitle_box)
        subtitle_form.addRow(t("gui.label_sub_preset"), self.subtitle_preset)
        subtitle_form.addRow(t("gui.label_sub_chars"), self.subtitle_chars)
        subtitle_form.addRow(t("gui.label_sub_words"), self.subtitle_words)
        save_row = QHBoxLayout()
        save_row.addWidget(self.save_srt)
        save_row.addWidget(self.save_vtt)
        save_row.addStretch(1)
        subtitle_form.addRow(t("gui.label_sub_save"), _wrap(save_row))

        vocab_content = QWidget()
        vocab_layout = QVBoxLayout(vocab_content)
        vocab_layout.setContentsMargins(0, 0, 0, 0)
        vocab_layout.addWidget(self.vocabularies, 2)
        vocab_layout.addWidget(QLabel(t("gui.vocab_custom")))
        vocab_layout.addWidget(self.custom, 1)
        vocab_layout.addWidget(self.prompt_size)
        self.vocab_panel = widgets.Disclosure(t("gui.group_vocabulary"),
                                              vocab_content)

        steps = QWidget()
        steps_layout = QVBoxLayout(steps)
        steps_layout.setContentsMargins(0, 0, 8, 0)
        steps_layout.addWidget(output_box)
        steps_layout.addWidget(sources_box)
        steps_layout.addWidget(settings_box)
        steps_layout.addWidget(self.subtitle_box)
        steps_layout.addWidget(self.vocab_panel)
        steps_layout.addStretch(1)
        # Three steps are taller than a laptop screen once the keyword panel
        # is open, and a window that cannot show its own third step is worse
        # than one that scrolls.
        left = QScrollArea()
        left.setWidget(steps)
        left.setWidgetResizable(True)
        left.setFrameShape(QFrame.Shape.NoFrame)

        self.start = QPushButton(t("gui.start"))
        # The one filled button on the tab: see gui/style.py. It is also the
        # default, so Enter does what the screen is for.
        self.start.setObjectName("primary")
        self.start.setDefault(True)
        self.start.setAutoDefault(True)
        self.start.setToolTip(t("gui.start_tip"))
        self.start.clicked.connect(self.start_queue)
        self.open_entry = QPushButton(t("gui.open_entry"))
        self.open_entry.clicked.connect(self._open_selected_entry)
        self.cancel_job = QPushButton(t("gui.cancel_job"))
        self.cancel_job.setToolTip(t("gui.cancel_job_tip"))
        self.cancel_job.clicked.connect(self.cancel_selected)
        self.stop_job = QPushButton(t("gui.stop_job"))
        self.stop_job.setToolTip(t("gui.stop_job_tip"))
        self.stop_job.clicked.connect(self.stop_selected)
        self.forget = QPushButton(t("gui.forget_job"))
        self.forget.clicked.connect(self.forget_selected)
        self.clear_finished = QPushButton(t("gui.clear_finished"))
        self.clear_finished.clicked.connect(self.forget_finished)
        actions = QHBoxLayout()
        actions.addWidget(self.start)
        actions.addWidget(self.stop_job)
        actions.addStretch(1)
        actions.addWidget(self.open_entry)
        actions.addWidget(self.cancel_job)
        actions.addWidget(self.forget)
        actions.addWidget(self.clear_finished)

        # The queue is a box with a name on it: it is the one place work
        # actually is, and before it had neither a title nor any way to take
        # something out of it.
        right = QGroupBox(t("gui.group_queue"))
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.table, 1)
        right_layout.addWidget(self.summary)
        right_layout.addLayout(actions)

        # Side by side, not one over the other: pressing Transcribe has to
        # produce something visible, and the list is what it produces.
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 5)
        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

    def chosen_output(self):
        """Which of the three the radio buttons say."""
        for value, button in self.output_buttons.items():
            if button.isChecked():
                return value
        return "text"

    def _output_chosen(self):
        """Show only the controls the chosen output uses, greyed if it cannot.

        A subtitle preset next to "just the text" is a control that does
        nothing, and a control that does nothing is a question the window
        cannot answer. What belongs to another answer goes away entirely; what
        belongs to this one but this machine cannot do stays, greyed, so the
        reason can be read in its tooltip."""
        chosen = self.chosen_output()
        self.output_note.setText(options.output_note(chosen))
        enables = options.output_enables(chosen)
        self.diarize.setEnabled(enables["diarize"] and self._diarization_ready)
        self.speakers.setEnabled(enables["speakers"] and self._diarization_ready)
        self.form.setRowVisible(self._speakers_row, enables["speakers"])
        for widget in (self.subtitle_preset, self.subtitle_chars,
                       self.subtitle_words, self.save_srt, self.save_vtt):
            widget.setEnabled(enables["subtitles"])
        self.subtitle_box.setVisible(enables["subtitles"])
        if enables["subtitles"] and not (self.save_srt.isChecked()
                                         or self.save_vtt.isChecked()):
            # The chosen output is the files, so one is written either way:
            # showing it ticked is more honest than saving an .srt behind an
            # empty box.
            self.save_srt.setChecked(True)

    def _reserve_note_lines(self, lines):
        """Keep room for the longest note so the boxes below do not move.

        The note is wrapped text that changes with the answer: sized to
        whatever it happens to say, choosing an answer would shift the options
        box up or down under the pointer."""
        metrics = self.output_note.fontMetrics()
        self.output_note.setMinimumHeight(metrics.lineSpacing() * lines)

    # --- choices ----------------------------------------------------------

    def chosen_vocabularies(self):
        """Names of the ticked keyword sets, in the order they are listed."""
        names = []
        for row in range(self.vocabularies.count()):
            item = self.vocabularies.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                names.append(item.data(Qt.ItemDataRole.UserRole))
        return names

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
        }

    def _count_prompt(self):
        """Show how long the prompt is getting, and warn past the limit.

        Whisper silently truncates a long initial prompt, so a vocabulary that
        is quietly too long is worse than one that complains."""
        text = self.custom.toPlainText()
        problem = options.custom_vocabulary_problem(text)
        if problem:
            self.prompt_size.setText(problem)
            return
        self.prompt_size.setText(t("gui.vocab_chars", chars=len(text),
                                   limit=MAX_PROMPT_CHARS))
        self._update_summary()

    # --- sources ----------------------------------------------------------

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, t("gui.choose_files"), "",
                                                options.media_filter())
        self.add_files(paths)

    def add_files(self, paths):
        """Put every file given into the queue, without starting it.

        One list, and one button that starts it. Adding a file used to start
        it there and then, which read as magic and left no room to change the
        model or tick a keyword set after choosing the files."""
        kept = options.playable_files(paths)
        if not kept:
            return False
        return self.submit_paths(kept, store=STORE_COPY)

    # --- files dropped anywhere on the tab --------------------------------

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """A drop anywhere on this tab queues the files.

        The whole tab rather than one list widget: the list is gone, and
        aiming at a small target is not part of the job."""
        paths = [url.toLocalFile() for url in event.mimeData().urls()]
        if self.add_files(paths):
            event.acceptProposedAction()

    def _recorded(self, path):
        """A finished recording goes straight into the queue.

        Whoever pressed "stop" has just finished a meeting; making them then
        find the file and press "transcribe" would be a pointless extra
        step."""
        self.submit_paths([path], store=STORE_MOVE,
                          title=options.recording_title())
        self.message.emit(t("gui.rec_queued"))

    # --- the queue --------------------------------------------------------

    def submit_paths(self, paths, store=STORE_COPY, title=None):
        """Hand files to the queue; returns whether anything was queued."""
        text = self.custom.toPlainText()
        problem = options.custom_vocabulary_problem(text)
        if problem:
            self.message.emit(problem)
            return False
        chosen = self.choices()
        overrides = options.overrides_from(chosen)
        overrides.update(options.subtitle_settings(chosen))
        overrides.update(options.output_settings(chosen))
        names = self.chosen_vocabularies()
        self._save_state()
        queued = 0
        for path in paths:
            self.queue.submit(
                path, title=title or options.title_from_path(path),
                filename=os.path.basename(path), overrides=overrides,
                vocabularies=names, custom_vocabulary=text, store=store,
                start=False)
            queued += 1
        if queued:
            self.message.emit(t("gui.queued", count=queued))
            self.refresh()
        return bool(queued)

    def start_queue(self):
        """Run everything that is waiting to be started."""
        started = self.queue.start()
        if not started:
            return False
        self.message.emit(t("gui.started", count=started))
        self.refresh()
        return True

    def refresh(self):
        """Re-read the queue and update the table in place."""
        jobs = self.queue.jobs()
        rows = [options.job_row(job) for job in jobs]
        if [row["id"] for row in rows] != [row["id"] for row in self._rows]:
            self._rebuild_table(rows)
        else:
            self._update_table(rows)
        finished = self._newly_finished(rows)
        self._rows = rows
        self.summary.setText(options.queue_summary(jobs))
        self.start.setText(options.start_label(
            sum(1 for row in rows if row["held"])))
        self._update_buttons()
        for row in finished:
            self.job_finished.emit(row["entry_id"] or "")

    def _newly_finished(self, rows):
        """Rows that were still working the last time the table was read.

        This is how the library tab learns that it has something new to show,
        without either panel knowing about the other."""
        was_working = {row["id"] for row in self._rows if not row["finished"]}
        return [row for row in rows if row["finished"] and row["id"] in was_working]

    def _rebuild_table(self, rows):
        """Recreate the rows, keeping whichever job was selected.

        Only done when jobs appear or disappear: while one is running the cells
        are updated in place, so the selection and the scroll position survive
        a progress update."""
        selected = self.selected_job_id()
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            title = _cell(row["title"], row["id"])
            title.setData(widgets.DETAILS_ROLE, row["details"])
            self.table.setItem(index, 0, title)
            self.table.setItem(index, 1, _cell(row["status"], row["id"]))
            self._set_progress(index, row)
            self.table.item(index, 1).setToolTip(row["tooltip"] or "")
        self.table.resizeRowsToContents()
        if selected:
            # Looked up in the new rows, not the old ones: a job that
            # disappeared shifts every index after it.
            for index, row in enumerate(rows):
                if row["id"] == selected:
                    self.table.selectRow(index)
                    break

    def _set_progress(self, index, row):
        """A bar for the job that is running, and nothing for the others.

        A bar at 0% on a row that failed, or on one that has not started, is
        a measurement of something that is not happening."""
        bar = self.table.cellWidget(index, 2)
        if not row["running"]:
            if bar is not None:
                self.table.removeCellWidget(index, 2)
            if self.table.item(index, 2) is None:
                self.table.setItem(index, 2, _cell("", row["id"]))
            return
        if bar is None:
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setTextVisible(True)
            self.table.setCellWidget(index, 2, bar)
        bar.setValue(row["progress"])

    def _update_table(self, rows):
        for index, row in enumerate(rows):
            self.table.item(index, 0).setText(row["title"])
            self.table.item(index, 0).setData(widgets.DETAILS_ROLE, row["details"])
            self.table.item(index, 1).setText(row["status"])
            self.table.item(index, 1).setToolTip(row["tooltip"] or "")
            self._set_progress(index, row)

    def selected_job_id(self):
        items = self.table.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items else None

    def _selected_row(self):
        job_id = self.selected_job_id()
        return next((row for row in self._rows if row["id"] == job_id), None)

    def _update_summary(self):
        """The keyword panel, closed, still has to say what was chosen."""
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

    def _update_buttons(self):
        """Only what applies to the selected job is offered.

        Four buttons that are always clickable would each need a dialog to
        explain why they did nothing."""
        row = self._selected_row()
        self.start.setEnabled(any(r["held"] for r in self._rows))
        self.open_entry.setEnabled(bool(row and row["entry_id"]))
        self.cancel_job.setEnabled(bool(row and row["cancellable"]))
        self.stop_job.setEnabled(bool(row and row["running"]))
        self.forget.setEnabled(bool(row and row["finished"]))
        self.clear_finished.setEnabled(any(r["finished"] for r in self._rows))

    def _open_selected_entry(self):
        row = self._selected_row()
        if row and row["entry_id"]:
            self.entry_requested.emit(row["entry_id"])

    def cancel_selected(self):
        """Take a job that has not started back out of the list.

        It leaves no row behind: nothing happened to it, and the file is
        untouched."""
        row = self._selected_row()
        if not (row and row["cancellable"]):
            return
        if self.queue.cancel(row["id"]):
            self.message.emit(t("gui.job_cancelled", title=row["title"]))
            self.refresh()

    def stop_selected(self):
        """Stop the transcription that is running, after asking.

        Worth a question: it may be forty minutes in, and what it has done so
        far is discarded rather than filed. The dialog also says what "stop"
        can honestly promise, which depends on the engine — the one place a
        transcription can be interrupted is its progress callback, and the
        OpenVINO backend never calls one."""
        row = self._selected_row()
        if not (row and row["running"]):
            return
        answer = QMessageBox.question(
            self, t("gui.stop_job_title"),
            t("gui.stop_job_confirm", title=row["title"]),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        if self.queue.cancel(row["id"]):
            self.message.emit(t("gui.job_stopping", title=row["title"]))
            self.refresh()

    def forget_finished(self):
        """Clear every finished job out of the table at once."""
        removed = 0
        for row in list(self._rows):
            if row["finished"] and self.queue.remove(row["id"]):
                removed += 1
        if removed:
            self.message.emit(t("gui.forgot_jobs", count=removed))
            self.refresh()

    def forget_selected(self):
        """Drop a finished job from the list; the transcription stays filed.

        Only the queue is touched: the refresh then sees a job missing and
        rebuilds the table, which is the one path that changes its shape."""
        job_id = self.selected_job_id()
        if job_id and self.queue.remove(job_id):
            self.refresh()

    # --- what is remembered between sessions ------------------------------

    def _load_state(self):
        """Restore the choices, which are a habit rather than a configuration.

        The vocabulary typed here is the desktop counterpart of the browser's
        local storage: it stays on this machine and never reaches
        ``config.toml``, which belongs to whoever set the tool up."""
        if self.store is None:
            self._count_prompt()
            return
        self.custom.setPlainText(self.store.value("custom_vocabulary", "", str))
        for name, widget in (("model", self.model), ("language", self.language),
                             ("backend", self.backend)):
            remembered = self.store.value(name, "", str)
            if remembered:
                _select(widget, remembered)
        remembered_output = self.store.value("output", "", str)
        button = self.output_buttons.get(remembered_output)
        if button is not None and button.isEnabled():
            button.setChecked(True)
        _select(self.subtitle_preset, self.store.value("subtitle_preset", "", str))
        self.subtitle_chars.setValue(int(self.store.value("subtitle_chars", 0, int) or 0))
        self.subtitle_words.setValue(int(self.store.value("subtitle_words", 0, int) or 0))
        self.save_srt.setChecked(bool(self.store.value("save_srt", False, bool)))
        self.save_vtt.setChecked(bool(self.store.value("save_vtt", False, bool)))
        remembered = self.store.value("vocabulary", None)
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

    def _save_state(self):
        if self.store is None:
            return
        self.store.setValue("custom_vocabulary", self.custom.toPlainText())
        self.store.setValue("model", self.model.currentData())
        self.store.setValue("language", self.language.currentData())
        self.store.setValue("backend", self.backend.currentData())
        self.store.setValue("vocabulary", self.chosen_vocabularies())
        self.store.setValue("output", self.chosen_output())
        self.store.setValue("subtitle_preset", self.subtitle_preset.currentData())
        self.store.setValue("subtitle_chars", self.subtitle_chars.value())
        self.store.setValue("subtitle_words", self.subtitle_words.value())
        self.store.setValue("save_srt", self.save_srt.isChecked())
        self.store.setValue("save_vtt", self.save_vtt.isChecked())

    def shutdown(self):
        """Stop polling, stop recording, remember the choices."""
        self.timer.stop()
        self.recorder.stop()
        self._save_state()


def _cell(text, job_id):
    item = QTableWidgetItem(str(text))
    item.setData(Qt.ItemDataRole.UserRole, job_id)
    return item


def _select(combo, value):
    """Select the entry whose data is ``value``, if there is one."""
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)


def _wrap(layout):
    """A widget around a layout, for the rows of a QFormLayout."""
    holder = QWidget()
    holder.setLayout(layout)
    return holder
