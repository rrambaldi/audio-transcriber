"""The "transcribe" tab: what to transcribe, how, and what the queue is doing.

The panel owns no transcription logic at all. It collects choices, hands a file
to :class:`audio_transcriber.jobs.JobQueue` — the very queue the web interface
uses — and then polls it on a timer, exactly as the web page polls over HTTP.
Polling rather than signalling is deliberate: the queue runs the transcription
in a worker thread that knows nothing about Qt, and reading a few attributes
twice a second is cheaper than making that thread talk to the GUI.
"""
import os

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..i18n import t
from ..jobs import HELD
from ..library import STORE_COPY, STORE_MOVE, LibraryError
from . import multimedia, options, style, widgets
from .job_dialog import JobDialog
from .options_form import OptionsForm
from .recorder import make_recorder

#: How often the queue is re-read. Twice a second is imperceptible on a
#: transcription measured in minutes, and costs nothing.
REFRESH_MS = 500


class TranscribePanel(QWidget):
    """Recordings first, then what to do with them.

    The tab reads as a list down the left — where the recordings come from,
    then the four questions about them — with the queue beside it. A file
    that arrives waits in that queue; each row carries the buttons that act
    on it, and starting one asks what it is for, seeded from the answers on
    the left. That order is deliberate: you have the recording in front of
    you before deciding what to make of it."""

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
        self._actions = {}
        self._playing = None

        self.setAcceptDrops(True)
        self.recorder = make_recorder(self.queue.upload_dir(), store=self.store)
        self.recorder.recorded.connect(self._recorded)
        self.recorder.failed.connect(self.message.emit)

        # The same four questions the per-recording dialog asks. Here they are
        # what the next recording starts from; there they are one recording's
        # own answers. One widget, so the two cannot drift apart.
        self.options = OptionsForm(self.settings)

        self._build_player()
        self._build_queue_table()
        self._assemble()
        self._load_state()
        self.options.update_summaries()
        self.refresh()

        self._add_shortcuts()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(REFRESH_MS)

    def _build_player(self):
        """Listening to what is in the queue, before spending an hour on it.

        The recording somebody dropped in may be the wrong file, or half an
        hour of an empty room. Playing it is the cheapest way to find out, and
        the queue is where the question comes up."""
        self.player = None
        self._playable = multimedia.AVAILABLE
        if not multimedia.AVAILABLE:
            return
        self.player = multimedia.QMediaPlayer(self)
        self.audio_output = multimedia.QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.playbackStateChanged.connect(
            lambda _state: self._update_actions())

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
        """The Delete key: the same thing the row's own Remove button does."""
        row = self._selected_row()
        if row is not None:
            self.remove_row(row["id"])

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
        # The buttons are a widget in the cell, and a column sized to fit its
        # *cells* measures the empty item behind them: 80 pixels for 180
        # pixels of buttons, which on a machine with a wider font than this
        # one's is a column of nothing. It is sized from the widgets instead.
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.itemDoubleClicked.connect(self._open_selected_entry)
        # Not only on the refresh tick: clicking a row and finding the buttons
        # still describing the previous one is half a second of lying.
        self.table.itemSelectionChanged.connect(self._update_actions)
        self.summary = QLabel("")

    def _assemble(self):
        # Recordings first: you have the file in front of you before deciding
        # what to make of it, and the questions below are about something
        # that exists rather than about the next thing you might add.
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
        files_layout.setContentsMargins(0, 0, 0, 0)
        files_layout.addLayout(buttons)
        files_layout.addWidget(self.drop_hint, 1)
        record_page = QWidget()
        record_layout = QVBoxLayout(record_page)
        record_layout.setContentsMargins(0, 0, 0, 0)
        record_layout.addWidget(self.recorder)
        record_layout.addStretch(1)
        # A microphone is not an option of the file list, it is the other half
        # of the question, and the browser page has said so with two tabs
        # since it was written.
        self.sources = QTabWidget()
        self.sources.addTab(files_page, t("gui.tab_files"))
        self.sources.addTab(record_page, t("gui.tab_record"))
        queue_hint = QLabel(t("gui.queue_hint"))
        queue_hint.setWordWrap(True)        # a narrow window must not cut it
        style.note(queue_hint)
        sources_page = QWidget()
        sources_layout = QVBoxLayout(sources_page)
        sources_layout.setContentsMargins(0, 0, 0, 0)
        sources_layout.addWidget(self.sources)
        sources_layout.addWidget(queue_hint)
        self.step_sources = widgets.Disclosure(t("gui.step_sources"),
                                               sources_page, open_now=True,
                                               key="sources")

        self.steps = [self.step_sources] + self.options.sections
        steps = QWidget()
        steps_layout = QVBoxLayout(steps)
        steps_layout.setContentsMargins(0, 0, 8, 0)
        steps_layout.setSpacing(10)
        steps_layout.addWidget(self.step_sources)
        steps_layout.addWidget(self.options)
        steps_layout.addStretch(1)
        # Open, the list is taller than a laptop screen, and a window that
        # cannot show its own last section is worse than one that scrolls.
        left = QScrollArea()
        left.setWidget(steps)
        left.setWidgetResizable(True)
        left.setFrameShape(QFrame.Shape.NoFrame)
        # Wide enough for the widest section with its panel open: below that
        # the column scrolls sideways, which is the one thing a list of five
        # rows must never do.
        left.setMinimumWidth(400)

        self.start = QPushButton(t("gui.start"))
        # The one filled button on the tab: see gui/style.py. It is also the
        # default, so Enter does what the screen is for. It starts everything
        # that is waiting, with the answers on the left; a row's own button
        # starts that one, and asks first.
        self.start.setObjectName("primary")
        self.start.setDefault(True)
        self.start.setAutoDefault(True)
        self.start.setToolTip(t("gui.start_tip"))
        self.start.clicked.connect(self.start_queue)
        self.clear_finished = QPushButton(t("gui.clear_finished"))
        self.clear_finished.clicked.connect(self.forget_finished)
        actions = QHBoxLayout()
        actions.addWidget(self.start)
        actions.addStretch(1)
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
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(left)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setChildrenCollapsible(False)
        # Stretch factors only share out what is left over, and the table asks
        # for everything it can get: without a starting size the steps column
        # was squeezed to less than its own content and scrolled sideways.
        self.splitter.setSizes([440, 740])
        layout = QVBoxLayout(self)
        layout.addWidget(self.splitter)

    # --- what the options say ----------------------------------------------

    def chosen_output(self):
        return self.options.chosen_output()

    def chosen_vocabularies(self):
        return self.options.chosen_vocabularies()

    def choices(self):
        return self.options.choices()

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
        text = self.options.custom_text()
        problem = options.custom_vocabulary_problem(text)
        if problem:
            self.message.emit(problem)
            return False
        overrides = _overrides(self.choices())
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
        held = sum(1 for row in rows if row["held"])
        self.start.setText(options.start_label(held))
        self._sources_summary(held)
        self._update_actions()
        # After the labels are on the buttons, not before: an empty button
        # asks for a third of the width a labelled one does.
        self._size_actions_column()
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
        self._actions = {}
        self.table.setRowCount(0)       # Qt deletes the widgets it owned
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            title = _cell(row["title"], row["id"])
            title.setData(widgets.DETAILS_ROLE, row["details"])
            self.table.setItem(index, 0, title)
            self.table.setItem(index, 1, _cell(row["status"], row["id"]))
            self._set_progress(index, row)
            self.table.setItem(index, 3, _cell("", row["id"]))
            self.table.setCellWidget(index, 3, self._actions_for(row))
            self.table.item(index, 1).setToolTip(row["tooltip"] or "")
        self.table.resizeRowsToContents()
        if selected:
            # Looked up in the new rows, not the old ones: a job that
            # disappeared shifts every index after it.
            for index, row in enumerate(rows):
                if row["id"] == selected:
                    self.table.selectRow(index)
                    break

    def _actions_for(self, row):
        """The three buttons for one recording, made fresh for this rebuild.

        Not kept between rebuilds: the table owns a cell widget and deletes
        the one it replaces, so a cached widget that has moved to another row
        is a pointer to something Qt has already freed. The table is only
        rebuilt when a job appears or disappears, so this costs nothing."""
        widget = widgets.JobActions(row["id"])
        widget.transcribe.connect(self.act_on_row)
        widget.remove.connect(self.remove_row)
        widget.play.connect(self.play_row)
        self._actions[row["id"]] = widget
        return widget

    def _size_actions_column(self):
        """Give the buttons the width they ask for, once they exist."""
        needed = max([widget.sizeHint().width()
                      for widget in self._actions.values()] or [0])
        if needed and self.table.columnWidth(3) < needed + 12:
            self.table.setColumnWidth(3, needed + 12)

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

    def _sources_summary(self, held):
        """Step 2, closed: how much is waiting to be started."""
        self.step_sources.set_summary(
            t("gui.step_sources_waiting", count=held) if held
            else t("gui.step_sources_empty"))

    def _update_actions(self):
        """Say what every row's buttons do, for the state that row is in."""
        playing = self._playing if self._is_playing() else None
        for row in self._rows:
            widget = self._actions.get(row["id"])
            if widget is None:
                continue
            path = self._audio_of(row["id"])
            widget.update_for(row, playing=row["id"] == playing,
                              playable=bool(path) and self.player is not None,
                              reason=self._why_not_playable(path))
        # The button that starts everything, and the one that clears what is
        # over: both are about the list as a whole, so they stay under it.
        self.start.setEnabled(any(row["held"] for row in self._rows))
        self.clear_finished.setEnabled(
            any(row["finished"] for row in self._rows))

    def _why_not_playable(self, path):
        if self.player is None:
            return t("gui.row_no_multimedia")
        return "" if path else t("gui.row_no_audio")

    # --- what a row's buttons do -------------------------------------------

    def _audio_of(self, job_id):
        """The file to play for this recording, wherever it is by now.

        Before it is transcribed that is the file itself; after it, the copy
        inside the library entry, because an upload or a recording this
        program made is *moved* there."""
        job = self.queue.get(job_id)
        if job is None:
            return None
        if job.source and os.path.exists(job.source):
            return job.source
        if job.entry_id:
            try:
                entry = self.queue.library.get(job.entry_id)
            except LibraryError:
                return None
            stored = entry.stored_audio() if entry else None
            return stored if stored and os.path.exists(stored) else None
        return None

    def _is_playing(self):
        return (self.player is not None and self.player.playbackState()
                == multimedia.QMediaPlayer.PlaybackState.PlayingState)

    def play_row(self, job_id):
        """Listen to one recording, or stop listening to it."""
        if self.player is None:
            return
        if self._playing == job_id and self._is_playing():
            self.player.stop()
            self._playing = None
            self._update_actions()
            return
        path = self._audio_of(job_id)
        if not path:
            return
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(path))
        self._playing = job_id
        self.player.play()
        self._update_actions()

    def remove_row(self, job_id):
        """Take one recording out, whichever "out" applies to it."""
        row = self._row_for(job_id)
        if row is None:
            return
        if row["cancellable"]:
            self.cancel_selected(job_id)
        elif row["finished"] and self.queue.remove(job_id):
            if self._playing == job_id:
                self.play_row(job_id)
            self.refresh()

    def act_on_row(self, job_id):
        """The first button: start it, stop it, or open what it produced."""
        row = self._row_for(job_id)
        if row is None:
            return
        if row["running"] or row["cancellable"] and not row["held"]:
            self.stop_selected(job_id)
        elif row["held"] or row["retryable"]:
            self.transcribe_row(job_id)
        elif row["entry_id"]:
            self.entry_requested.emit(row["entry_id"])

    def transcribe_row(self, job_id):
        """Ask what this recording is for, then start it.

        The dialog opens on the answers from the list on the left, so a queue
        of six meetings takes one confirmation each and the odd one that
        needs subtitles is changed where it is noticed."""
        self.queue.retry(job_id)            # a failed one goes back to waiting
        job = self.queue.get(job_id)
        if job is None or job.status != HELD:
            return False
        dialog = JobDialog(job.title, self.settings, self.options.choices(),
                           self.options.chosen_vocabularies(),
                           self.options.custom_text(), parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        self.queue.reconfigure(job_id, overrides=_overrides(dialog.choices()),
                               vocabularies=dialog.vocabularies(),
                               custom_vocabulary=dialog.custom_text())
        started = self.queue.start(job_id)
        if started:
            self.message.emit(t("gui.started", count=started))
        self.refresh()
        return bool(started)

    def _row_for(self, job_id):
        for row in self._rows:
            if row["id"] == job_id:
                return row
        return None

    def _open_selected_entry(self):
        row = self._selected_row()
        if row and row["entry_id"]:
            self.entry_requested.emit(row["entry_id"])

    def cancel_selected(self, job_id=None):
        """Take a job that has not started back out of the list.

        It leaves no row behind: nothing happened to it, and the file is
        untouched."""
        row = self._row_for(job_id) if job_id else self._selected_row()
        if not (row and row["cancellable"]):
            return
        if self.queue.cancel(row["id"]):
            self.message.emit(t("gui.job_cancelled", title=row["title"]))
            self.refresh()

    def stop_selected(self, job_id=None):
        """Stop the transcription that is running, after asking.

        Worth a question: it may be forty minutes in, and what it has done so
        far is discarded rather than filed. The dialog also says what "stop"
        can honestly promise, which depends on the engine — the one place a
        transcription can be interrupted is its progress callback, and the
        OpenVINO backend never calls one."""
        row = self._row_for(job_id) if job_id else self._selected_row()
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
        """Restore the choices, which are a habit rather than a configuration."""
        self.options.load_state(self.store)
        if self.store is None:
            return
        where = self.store.value("splitter")
        if where is not None:
            self.splitter.restoreState(where)
        remembered_open = self.store.value("open_sources", None)
        if remembered_open is not None:
            self.step_sources.set_open(remembered_open in (True, "true"))

    def _save_state(self):
        if self.store is None:
            return
        self.options.save_state(self.store)
        self.store.setValue("open_sources", self.step_sources.is_open())
        self.store.setValue("splitter", self.splitter.saveState())

    def shutdown(self):
        """Stop polling, stop recording, remember the choices."""
        self.timer.stop()
        self.recorder.stop()
        self._save_state()


def _overrides(chosen):
    """Everything the option widgets say, as settings the queue understands."""
    overrides = options.overrides_from(chosen)
    overrides.update(options.subtitle_settings(chosen))
    overrides.update(options.output_settings(chosen))
    return overrides


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
