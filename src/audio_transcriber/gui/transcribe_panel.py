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
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..diarization import availability as diarization_availability
from ..i18n import t
from ..library import STORE_COPY, STORE_MOVE
from ..vocabularies import MAX_PROMPT_CHARS
from . import options
from .recorder import Recorder

#: How often the queue is re-read. Twice a second is imperceptible on a
#: transcription measured in minutes, and costs nothing.
REFRESH_MS = 500


class FileList(QListWidget):
    """The list of files to transcribe, which also accepts a drop."""

    files_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAcceptDrops(True)
        self.setToolTip(t("gui.drop_hint"))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls()]
        kept = options.playable_files(paths)
        if kept:
            self.files_dropped.emit(kept)
            event.acceptProposedAction()

    def paths(self):
        """Every file currently listed, in order."""
        return [self.item(row).data(Qt.ItemDataRole.UserRole)
                for row in range(self.count())]

    def add(self, paths):
        """Add files that are not in the list yet."""
        known = set(self.paths())
        for path in paths:
            if path in known:
                continue
            item = QListWidgetItem(os.path.basename(path))
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self.addItem(item)


class TranscribePanel(QWidget):
    """Sources, options, and the queue table."""

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

        self.files = FileList()
        self.files.files_dropped.connect(self.add_files)
        self.recorder = Recorder(self.queue.upload_dir())
        self.recorder.recorded.connect(self._recorded)
        self.recorder.failed.connect(self.message.emit)

        self._build_options()
        self._build_queue_table()
        self._assemble()
        self._load_state()
        self.refresh()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(REFRESH_MS)

    # --- construction -----------------------------------------------------

    def _build_options(self):
        defaults = options.defaults_from(self.settings)

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
        if state != "ready":
            # Offering a checkbox this machine cannot honour only produces a
            # job that fails after the wait, which is a worse way to find out.
            self.diarize.setChecked(False)
            self.diarize.setEnabled(False)
            self.speakers.setEnabled(False)
            self.diarize.setToolTip(t("gui.diarize_unavailable", detail=detail))

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
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self.table.itemDoubleClicked.connect(self._open_selected_entry)
        self.summary = QLabel("")

    def _assemble(self):
        sources = QGroupBox(t("gui.group_sources"))
        buttons = QHBoxLayout()
        add = QPushButton(t("gui.add_files"))
        add.clicked.connect(self.choose_files)
        remove = QPushButton(t("gui.remove_files"))
        remove.clicked.connect(self.remove_selected_files)
        clear = QPushButton(t("gui.clear_files"))
        clear.clicked.connect(self.files.clear)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addWidget(clear)
        buttons.addStretch(1)
        source_layout = QVBoxLayout(sources)
        source_layout.addLayout(buttons)
        source_layout.addWidget(self.files, 1)
        source_layout.addWidget(self.recorder)

        settings_box = QGroupBox(t("gui.group_options"))
        form = QFormLayout(settings_box)
        form.addRow(t("gui.label_model"), self.model)
        form.addRow(t("gui.label_language"), self.language)
        form.addRow(t("gui.label_backend"), self.backend)
        speakers_row = QHBoxLayout()
        speakers_row.addWidget(self.diarize)
        speakers_row.addWidget(QLabel(t("gui.label_speakers")))
        speakers_row.addWidget(self.speakers)
        speakers_row.addStretch(1)
        form.addRow("", _wrap(speakers_row))

        vocab_box = QGroupBox(t("gui.group_vocabulary"))
        vocab_layout = QVBoxLayout(vocab_box)
        vocab_layout.addWidget(self.vocabularies, 2)
        vocab_layout.addWidget(QLabel(t("gui.vocab_custom")))
        vocab_layout.addWidget(self.custom, 1)
        vocab_layout.addWidget(self.prompt_size)

        self.start = QPushButton(t("gui.start"))
        self.start.clicked.connect(self.submit)
        self.open_entry = QPushButton(t("gui.open_entry"))
        self.open_entry.clicked.connect(self._open_selected_entry)
        self.forget = QPushButton(t("gui.forget_job"))
        self.forget.clicked.connect(self.forget_selected)
        actions = QHBoxLayout()
        actions.addWidget(self.start)
        actions.addStretch(1)
        actions.addWidget(self.open_entry)
        actions.addWidget(self.forget)

        top = QWidget()
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(sources, 3)
        top_layout.addWidget(settings_box, 2)
        top_layout.addWidget(vocab_box, 3)

        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addLayout(actions)
        bottom_layout.addWidget(self.table, 1)
        bottom_layout.addWidget(self.summary)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(top)
        splitter.addWidget(bottom)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

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
            "diarize": self.diarize.isChecked(),
            "speakers": self.speakers.value(),
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

    # --- sources ----------------------------------------------------------

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, t("gui.choose_files"), "",
                                                options.media_filter())
        self.add_files(paths)

    def add_files(self, paths):
        kept = options.playable_files(paths)
        if kept:
            self.files.add(kept)

    def remove_selected_files(self):
        for item in self.files.selectedItems():
            self.files.takeItem(self.files.row(item))

    def _recorded(self, path):
        """A finished recording goes straight into the queue.

        Whoever pressed "stop" has just finished a meeting; making them then
        find the file and press "transcribe" would be a pointless extra
        step."""
        self.submit_paths([path], store=STORE_MOVE,
                          title=options.recording_title())
        self.message.emit(t("gui.rec_queued"))

    # --- the queue --------------------------------------------------------

    def submit(self):
        """Queue every listed file, then empty the list."""
        paths = self.files.paths()
        if not paths:
            self.message.emit(t("gui.nothing_to_do"))
            return
        if self.submit_paths(paths, store=STORE_COPY):
            self.files.clear()

    def submit_paths(self, paths, store=STORE_COPY, title=None):
        """Hand files to the queue; returns whether anything was queued."""
        text = self.custom.toPlainText()
        problem = options.custom_vocabulary_problem(text)
        if problem:
            self.message.emit(problem)
            return False
        overrides = options.overrides_from(self.choices())
        names = self.chosen_vocabularies()
        self._save_state()
        queued = 0
        for path in paths:
            self.queue.submit(
                path, title=title or options.title_from_path(path),
                filename=os.path.basename(path), overrides=overrides,
                vocabularies=names, custom_vocabulary=text, store=store)
            queued += 1
        if queued:
            self.message.emit(t("gui.queued", count=queued))
            self.refresh()
        return bool(queued)

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
            for column, key in enumerate(("title", "status")):
                self.table.setItem(index, column, _cell(row[key], row["id"]))
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(row["progress"])
            bar.setTextVisible(True)
            self.table.setCellWidget(index, 2, bar)
            for column, key in enumerate(("model", "duration", "words"), start=3):
                self.table.setItem(index, column, _cell(row[key], row["id"]))
            self.table.item(index, 1).setToolTip(row["tooltip"] or "")
        if selected:
            # Looked up in the new rows, not the old ones: a job that
            # disappeared shifts every index after it.
            for index, row in enumerate(rows):
                if row["id"] == selected:
                    self.table.selectRow(index)
                    break

    def _update_table(self, rows):
        for index, row in enumerate(rows):
            self.table.item(index, 0).setText(row["title"])
            self.table.item(index, 1).setText(row["status"])
            self.table.item(index, 1).setToolTip(row["tooltip"] or "")
            bar = self.table.cellWidget(index, 2)
            if bar is not None:
                bar.setValue(row["progress"])
            self.table.item(index, 3).setText(row["model"])
            self.table.item(index, 4).setText(row["duration"])
            self.table.item(index, 5).setText(row["words"])

    def selected_job_id(self):
        items = self.table.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items else None

    def _selected_row(self):
        job_id = self.selected_job_id()
        return next((row for row in self._rows if row["id"] == job_id), None)

    def _update_buttons(self):
        row = self._selected_row()
        self.open_entry.setEnabled(bool(row and row["entry_id"]))
        self.forget.setEnabled(bool(row and row["finished"]))

    def _open_selected_entry(self):
        row = self._selected_row()
        if row and row["entry_id"]:
            self.entry_requested.emit(row["entry_id"])

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
