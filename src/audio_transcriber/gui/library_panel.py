"""The "library" tab: browse what has been transcribed, and read it back.

The library is a folder of plain files, and this panel is only a reader for it:
the transcript, the timestamps, the notes and the recording all come straight
from the entry, and every change (a new title, edited notes, a deletion) goes
through :mod:`audio_transcriber.library` so the folder stays exactly as
readable without this program as with it.

Clicking a timestamp seeks the player, which is what makes a two-hour meeting
searchable: find the sentence, jump to the moment, hear what was actually
said.
"""
import html
import os
import threading

# Imported by name: this panel's own "queue" is the window's job queue, and a
# module of that name beside it is a trap set for the next reader.
from queue import Empty, Queue

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .. import waveform
from ..diarization import speakers_in
from ..formatting import format_clock
from ..i18n import t
from ..jobs import DONE, FAILED, FINISHED, RUNNING
from ..library import MAX_NOTES, Entry, LibraryError
from ..summarizers import plan
from ..summarizers import templates as summary_templates
from ..summary import SummaryError
from . import multimedia, options, symbols, theme, widgets
from .speakers_dialog import SpeakersDialog, first_lines

#: Typing in the search box is not a query per keystroke: searching reads every
#: transcript in the library, so it waits until the typing stops.
SEARCH_DELAY_MS = 350

#: How often a queued summary is asked whether it is finished. It may be
#: behind an hour of transcription, so this is a heartbeat, not a wait.
SUMMARY_POLL_MS = 1000

#: How often the list asks whether another recording has been measured. The
#: measuring happens on a thread of its own; this is only the hand-over, and
#: it stops as soon as there is nothing left to hand over.
WAVE_POLL_MS = 400

#: Gutter on either side of the splitter handle, so the list and the reading
#: pane are not flush against the bar that separates them.
SPLITTER_GUTTER = 10


class _ClickableLabel(QLabel):
    """A label that also reacts to a double click, for the title's rename."""

    doubleClicked = Signal()

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)


class LibraryPanel(QWidget):
    """The entry table, the reading pane, the notes editor and the player."""

    message = Signal(str)

    def __init__(self, library, settings=None, parent=None, queue=None):
        super().__init__(parent)
        self.library = library
        self.settings = dict(settings or {})
        #: The window's queue, when there is one. A summary goes into it
        #: rather than running here: it is minutes of the same cores a
        #: transcription needs, and the window must not do both at once — nor
        #: freeze while one of them happens.
        self.queue = queue
        self.entry = None
        self._rows = []
        self._notes_dirty = False
        self._audio_path = None
        self._summary_job = None
        #: Recordings filed before this program could draw them have never
        #: been measured, and measuring one is a pass of ffmpeg over the whole
        #: file. So it happens on a thread, one at a time, and the drawings
        #: land in the rows as they are finished rather than holding the list.
        self._wanted = Queue()
        self._measured = Queue()
        self._measurer = None
        #: Asked for once and not again: the list is re-read on every search
        #: keystroke, and a recording that cannot be measured must not send
        #: ffmpeg after it each time.
        self._asked = set()

        self._build_table()
        self._build_reader()
        self._build_player()
        self._assemble()

        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.reload)
        #: A queued summary is watched rather than waited for: the queue runs
        #: it on its own thread and this only asks, now and then, whether it
        #: is done.
        self.summary_timer = QTimer(self)
        self.summary_timer.timeout.connect(self._check_summary)
        self.wave_timer = QTimer(self)
        self.wave_timer.setInterval(WAVE_POLL_MS)
        self.wave_timer.timeout.connect(self._take_measurements)
        self.reload()

    # --- construction -----------------------------------------------------

    def _build_table(self):
        self.search = QLineEdit()
        self.search.setPlaceholderText(t("gui.search_hint"))
        self.search.textChanged.connect(
            lambda _text: self.search_timer.start(SEARCH_DELAY_MS))
        self.search.returnPressed.connect(self.reload)
        self.count = QLabel("")

        self.table = QTableWidget(0, len(options.entry_headers()))
        self.table.setHorizontalHeaderLabels(options.entry_headers())
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(False)
        # Every column but the title is as wide as its content and no wider:
        # six columns in a narrow pane otherwise push the last three out of
        # sight behind a horizontal scrollbar, and the date is what people
        # look for first.
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        # The title column draws the name with the shape of the recording
        # under it. The rows have to be told to take their height from what
        # is in them, or the drawing is simply clipped away: the horizontal
        # header above has nothing to do with how tall a row is.
        self.table.setItemDelegateForColumn(1, widgets.WaveTitleDelegate(self.table))
        self.table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._selection_changed)

    def _build_reader(self):
        self.transcript = QTextBrowser()
        self.transcript.setOpenLinks(False)
        self.transcript.setOpenExternalLinks(False)
        self.transcript.anchorClicked.connect(self._anchor_clicked)
        self.copy_transcript = _copy_button(self._copy_transcript)
        transcript_page = QWidget()
        transcript_layout = QVBoxLayout(transcript_page)
        transcript_layout.addLayout(_with_copy(self.transcript,
                                               self.copy_transcript), 1)

        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText(t("gui.notes_hint"))
        self.notes.textChanged.connect(self._notes_changed)
        self.copy_notes = _copy_button(self._copy_notes)
        self.save_notes = QPushButton(t("gui.notes_save"))
        self.save_notes.clicked.connect(self.write_notes)
        self.save_notes.setEnabled(False)
        notes_page = QWidget()
        notes_layout = QVBoxLayout(notes_page)
        notes_layout.addLayout(_with_copy(self.notes, self.copy_notes), 1)
        notes_row = QHBoxLayout()
        notes_row.addStretch(1)
        notes_row.addWidget(self.save_notes)
        notes_layout.addLayout(notes_row)

        self.details = QWidget()
        self.details_form = QFormLayout(self.details)

        self.summary = QPlainTextEdit()
        self.summary.setReadOnly(True)
        self.summary_note = QLabel("")
        self.summary_note.setWordWrap(True)
        # A summary reads an hour of transcript through a model: the same bar
        # a queue row has, because "being written" says nothing about where
        # it has got to.
        self.summary_progress = QProgressBar()
        self.summary_progress.setRange(0, 100)
        self.summary_progress.setTextVisible(False)
        self.summary_progress.hide()
        self.summary_engine = QComboBox()
        self.summary_model = QComboBox()
        self.summary_model_label = QLabel(t("gui.summary_model"))
        self.summary_length = QComboBox()
        self.summary_style = QComboBox()
        self.summary_template = QComboBox()
        # Revealed by the last entry of the menu: a page wanted once and not
        # saved under a name, the same bargain the terms box makes.
        self.summary_template_text = QPlainTextEdit()
        self.summary_template_text.setPlaceholderText(
            t("gui.summary_template_help"))
        self.summary_template_text.setMaximumHeight(110)
        self.summary_template_text.hide()
        self.copy_summary = _copy_button(self._copy_summary)
        self.summarise = QPushButton(t("gui.summary_run"))
        self.summarise.clicked.connect(self.summarise_entry)
        summary_page = QWidget()
        summary_layout = QVBoxLayout(summary_page)
        summary_layout.addLayout(_with_copy(self.summary, self.copy_summary), 1)
        summary_layout.addWidget(self.summary_note)
        summary_layout.addWidget(self.summary_progress)
        summary_layout.addWidget(self.summary_template_text)
        summary_row = QHBoxLayout()
        engines = options.summary_engine_choices(self.settings)
        for name, label in engines:
            self.summary_engine.addItem(label, name)
        for name, label in options.summary_length_choices():
            self.summary_length.addItem(label, name)
        self.summary_length.setCurrentIndex(
            max(0, self.summary_length.findData(options.summary_default_length())))
        for name, label in options.summary_style_choices():
            self.summary_style.addItem(label, name)
        self.summary_style.setCurrentIndex(
            max(0, self.summary_style.findData(options.summary_default_style())))
        # One engine is not a choice, so the menu is not shown; the label on
        # the button is the whole story then.
        self.summary_engine_label = QLabel(t("gui.summary_engine"))
        # Who writes it on a line of its own: an engine and a model beside
        # the other four menus make a window no laptop screen is wide enough
        # for.
        engine_row = QHBoxLayout()
        for widget in (self.summary_engine_label, self.summary_engine):
            widget.setVisible(len(engines) > 1)
            engine_row.addWidget(widget)
        engine_row.addWidget(self.summary_model_label)
        engine_row.addWidget(self.summary_model)
        engine_row.addStretch(1)
        summary_layout.addLayout(engine_row)
        self.summary_engine.currentIndexChanged.connect(
            lambda _index: self._fill_models())
        self._fill_models()
        summary_row.addWidget(QLabel(t("gui.summary_length")))
        summary_row.addWidget(self.summary_length)
        summary_row.addWidget(QLabel(t("gui.summary_style")))
        summary_row.addWidget(self.summary_style)
        for name, label in options.summary_template_choices(
                self.settings, self.settings.get("language") or "it"):
            self.summary_template.addItem(label, name)
        self.summary_template.currentIndexChanged.connect(self._show_own_sections)
        summary_row.addWidget(QLabel(t("gui.summary_template")))
        summary_row.addWidget(self.summary_template)
        summary_row.addStretch(1)
        summary_row.addWidget(self.summarise)
        summary_layout.addLayout(summary_row)

        self.tabs = QTabWidget()
        self.tabs.addTab(transcript_page, t("gui.tab_transcript"))
        self.tabs.addTab(summary_page, t("gui.tab_summary"))
        self.tabs.addTab(notes_page, t("gui.tab_notes"))
        self.tabs.addTab(self.details, t("gui.tab_details"))

    def _build_player(self):
        self.play = QPushButton(t("gui.play"))
        self.play.clicked.connect(self.toggle_play)
        self.position = QSlider(Qt.Orientation.Horizontal)
        self.position.setRange(0, 0)
        self.position.sliderMoved.connect(self._seek_ms)
        self.clock = QLabel(f"{format_clock(0)} / {format_clock(0)}")
        self.player_note = QLabel("")
        self.player_note.setWordWrap(True)
        self.player_note.hide()
        self.player = None
        self.audio_output = None
        if multimedia.AVAILABLE:
            self.player = multimedia.QMediaPlayer(self)
            self.audio_output = multimedia.QAudioOutput(self)
            self.player.setAudioOutput(self.audio_output)
            self.player.positionChanged.connect(self._position_changed)
            self.player.durationChanged.connect(self._duration_changed)
            self.player.playbackStateChanged.connect(self._playback_changed)
        else:
            # A tooltip on a disabled button is not an explanation: on several
            # platforms it never appears at all. The reason goes on the page.
            self.play.setEnabled(False)
            self.position.setEnabled(False)
            self.player_note.setText(t("gui.player_no_multimedia"))
            self.player_note.show()

    def _assemble(self):
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, SPLITTER_GUTTER, 0)
        search_row = QHBoxLayout()
        search_row.addWidget(self.search, 1)
        reload_button = QPushButton(t("gui.reload"))
        reload_button.clicked.connect(lambda: self.reload())
        search_row.addWidget(reload_button)
        left_layout.addLayout(search_row)
        left_layout.addWidget(self.table, 1)
        left_layout.addWidget(self.count)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(SPLITTER_GUTTER, 0, 0, 0)
        self.title = _ClickableLabel("")
        self.title.setWordWrap(True)
        # The heading of what is being read, so it is set the way the page
        # sets one: the serif, a size up. See gui/theme.py.
        self.title.setFont(theme.title_font(self.font(), 1.35,
                                            weight=QFont.Weight.DemiBold))
        self.title.doubleClicked.connect(self.rename_entry)
        self.rename = _symbol_button("edit", "✎", t("gui.rename"),
                                     self.rename_entry)
        title_row = QHBoxLayout()
        title_row.addWidget(self.title, 1)
        title_row.addWidget(self.rename, 0, Qt.AlignmentFlag.AlignTop)
        right_layout.addLayout(title_row)

        player_row = QHBoxLayout()
        player_row.addWidget(self.play)
        player_row.addWidget(self.position, 1)
        player_row.addWidget(self.clock)
        right_layout.addLayout(player_row)
        right_layout.addWidget(self.player_note)
        right_layout.addWidget(self.tabs, 1)

        self.name_speakers = QPushButton(t("gui.name_speakers"))
        self.name_speakers.clicked.connect(self.name_speakers_of_entry)
        self.name_speakers.hide()
        self.export = QPushButton(t("gui.export"))
        self.export.clicked.connect(self.export_transcript)
        self.export_subtitles_button = QPushButton(t("gui.sub_export"))
        self.export_subtitles_button.clicked.connect(self.export_subtitles)
        self.open_folder = QPushButton(t("gui.open_folder"))
        self.open_folder.clicked.connect(self.reveal_folder)
        self.delete = QPushButton(t("gui.delete"))
        self.delete.clicked.connect(self.delete_entry)
        actions = QHBoxLayout()
        for button in (self.name_speakers, self.export,
                       self.export_subtitles_button, self.open_folder):
            actions.addWidget(button)
        actions.addStretch(1)
        actions.addWidget(self.delete)
        right_layout.addLayout(actions)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        # The list needs enough of the width to show its columns; the reading
        # pane keeps the larger share.
        splitter.setSizes([520, 660])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)   # the pane's gutter is the only one
        layout.addWidget(splitter)
        self._enable_actions(False)

    # --- the list ---------------------------------------------------------

    def reload(self, keep=None):
        """Re-read the library, honouring the search box.

        ``keep`` is the id to select afterwards; by default whatever was
        selected stays selected, which is what makes the timer-driven reload
        after a finished job unobtrusive."""
        self.search_timer.stop()
        query = self.search.text().strip()
        keep = keep or (self.entry.id if self.entry else None)
        entries = self.library.search(query) if query else self.library.entries()
        self._rows = options.entry_rows(entries)
        self.count.setText(options.search_summary(query, len(self._rows)))

        self.table.blockSignals(True)
        self.table.setRowCount(len(self._rows))
        for index, row in enumerate(self._rows):
            for column, key in enumerate(("date", "title", "duration", "words",
                                          "model", "notes")):
                item = QTableWidgetItem(row[key])
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                if column == 1:
                    item.setData(widgets.LOUDNESS_ROLE, row["loudness"])
                self.table.setItem(index, column, item)
        self.table.blockSignals(False)
        self._want_measurements()

        if not self._rows:
            self.entry = None
            self._clear_reader()
            return
        index = next((i for i, row in enumerate(self._rows) if row["id"] == keep), 0)
        self.table.selectRow(index)
        self._selection_changed()

    # --- what each recording looks like -----------------------------------

    def _want_measurements(self):
        """Ask for the drawings this list is missing, newest row first."""
        missing = [(row["id"], row["path"]) for row in self._rows
                   if not row["loudness"] and row["id"] not in self._asked]
        if not missing:
            return
        for wanted in missing:
            self._asked.add(wanted[0])
            self._wanted.put(wanted)
        if self._measurer is None or not self._measurer.is_alive():
            self._measurer = threading.Thread(target=self._measure,
                                              name="library-waveform",
                                              daemon=True)
            self._measurer.start()
        self.wave_timer.start()

    def _measure(self):
        """One recording read through at a time, off the interface's thread.

        Nothing here touches a widget: what it finds goes into a queue, and
        :meth:`_take_measurements` — which does run on the interface's thread
        — puts it in the row. Qt does not forgive the other arrangement."""
        while True:
            try:
                entry_id, path = self._wanted.get(timeout=5)
            except Empty:
                return
            try:
                found = waveform.entry_loudness(Entry(path))
            except Exception:       # noqa: BLE001 - a picture, not the work
                found = None
            if found:
                self._measured.put((entry_id, found))

    def _take_measurements(self):
        """Move finished drawings into the rows, and stop when there are none."""
        drawn = False
        while True:
            try:
                entry_id, found = self._measured.get_nowait()
            except Empty:
                break
            for index, row in enumerate(self._rows):
                if row["id"] != entry_id:
                    continue
                row["loudness"] = found
                item = self.table.item(index, 1)
                if item is not None:
                    item.setData(widgets.LOUDNESS_ROLE, found)
                    drawn = True
        if drawn:
            self.table.viewport().update()
        if (self._wanted.empty() and self._measured.empty()
                and (self._measurer is None or not self._measurer.is_alive())):
            self.wave_timer.stop()

    def selected_id(self):
        items = self.table.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items else None

    def show_entry(self, entry_id):
        """Select and display one entry by id, reloading if it is not listed.

        This is what the transcribe tab calls when a job has finished: the
        entry has just been created, so the list has to be re-read first."""
        if not any(row["id"] == entry_id for row in self._rows):
            self.search.clear()
            self.reload(keep=entry_id)
        for index, row in enumerate(self._rows):
            if row["id"] == entry_id:
                self.table.selectRow(index)
                return True
        return False

    def _selection_changed(self):
        entry_id = self.selected_id()
        if entry_id is None or (self.entry and self.entry.id == entry_id):
            return
        if not self._offer_to_save_notes():
            # Cancelled: the click has already moved the selection, so it is
            # put back on the entry whose notes are still being written.
            self._reselect(self.entry.id)
            return
        try:
            self.entry = self.library.get(entry_id)
        except LibraryError as exc:
            self.message.emit(str(exc))
            return
        self._display()

    # --- the reading pane -------------------------------------------------

    def _reselect(self, entry_id):
        """Move the selection back without displaying anything again."""
        self.table.blockSignals(True)
        for index, row in enumerate(self._rows):
            if row["id"] == entry_id:
                self.table.selectRow(index)
                break
        self.table.blockSignals(False)

    def _display(self):
        entry = self.entry
        try:
            data = entry.metadata
        except LibraryError as exc:
            self.message.emit(str(exc))
            return
        self.title.setText(f"{data.get('title') or entry.id}  ({entry.id})")
        segments = entry.read_segments()
        self.transcript.setHtml(_transcript_html(segments,
                                                 entry.read_transcript()))
        # Hidden rather than disabled on a run that was not diarized: there is
        # nobody to name, and a greyed-out button is a question about a
        # feature that does not apply to what is being read.
        self.name_speakers.setVisible(bool(speakers_in(segments)))
        self.notes.blockSignals(True)
        self.notes.setPlainText(entry.read_notes())
        self.notes.blockSignals(False)
        self._notes_dirty = False
        self.save_notes.setEnabled(False)
        _fill_form(self.details_form, options.entry_details(entry))
        self._show_summary()
        self._load_audio(entry.stored_audio())
        self._enable_actions(True)

    def _show_summary(self):
        """Fill the summary tab from the entry, caption included."""
        text, note = options.summary_state(self.entry)
        self.summary.setPlainText(text)
        self.summary_note.setText(note)
        self.summarise.setText(t("gui.summary_again" if text else "gui.summary_run"))

    def _clear_reader(self):
        self.title.setText("")
        self.transcript.clear()
        self.summary.clear()
        self.summary_note.setText("")
        self.notes.blockSignals(True)
        self.notes.clear()
        self.notes.blockSignals(False)
        _fill_form(self.details_form, [])
        self._load_audio(None)
        self.name_speakers.hide()
        self._enable_actions(False)

    def _enable_actions(self, enabled):
        for button in (self.rename, self.export, self.export_subtitles_button,
                       self.open_folder, self.delete, self.copy_transcript,
                       self.copy_summary, self.copy_notes,
                       self.name_speakers):
            button.setEnabled(enabled)
        self.summarise.setEnabled(enabled and self.queue is not None
                                  and self._summary_job is None)

    def _anchor_clicked(self, url):
        """A timestamp was clicked: jump there and start playing."""
        fragment = url.toString().lstrip("#")
        if not fragment.startswith("t="):
            return
        try:
            seconds = float(fragment[2:])
        except ValueError:
            return
        self.seek(seconds)

    # --- the player -------------------------------------------------------

    def _load_audio(self, path):
        self._audio_path = path
        if self.player is None:
            return
        self.player.stop()
        if path:
            self.player.setSource(QUrl.fromLocalFile(path))
            self.play.setEnabled(True)
            self.play.setToolTip("")
        else:
            self.player.setSource(QUrl())
            self.play.setEnabled(False)
            self.play.setToolTip(t("gui.player_no_audio"))
            self.position.setRange(0, 0)
            self.clock.setText(f"{format_clock(0)} / {format_clock(0)}")

    def seek(self, seconds):
        """Move playback to ``seconds`` and play from there."""
        if self.player is None or not self._audio_path:
            self.message.emit(t("gui.player_no_audio"))
            return
        self.player.setPosition(int(seconds * 1000))
        self.player.play()

    def toggle_play(self):
        if self.player is None:
            return
        states = multimedia.QMediaPlayer.PlaybackState
        if self.player.playbackState() == states.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _seek_ms(self, milliseconds):
        if self.player is not None:
            self.player.setPosition(milliseconds)

    def _position_changed(self, milliseconds):
        if not self.position.isSliderDown():
            self.position.setValue(milliseconds)
        self.clock.setText(f"{format_clock(milliseconds / 1000)} / "
                           f"{format_clock(self.position.maximum() / 1000)}")

    def _duration_changed(self, milliseconds):
        self.position.setRange(0, milliseconds)

    def _playback_changed(self, state):
        playing = state == multimedia.QMediaPlayer.PlaybackState.PlayingState
        self.play.setText(t("gui.pause") if playing else t("gui.play"))

    # --- notes ------------------------------------------------------------

    def _notes_changed(self):
        self._notes_dirty = True
        self.save_notes.setEnabled(self.entry is not None)

    def write_notes(self):
        """Save ``notes.md``, which is the one file here that is yours."""
        if self.entry is None:
            return False
        text = self.notes.toPlainText()
        if len(text) > MAX_NOTES:
            self.message.emit(t("gui.notes_too_long", limit=MAX_NOTES))
            return False
        try:
            self.entry.write_notes(text)
        except OSError as exc:
            self.message.emit(str(exc))
            return False
        self._notes_dirty = False
        self.save_notes.setEnabled(False)
        self.message.emit(t("gui.notes_saved"))
        self._refresh_notes_column()
        return True

    def _refresh_notes_column(self):
        """Update the "notes" cell without re-reading the whole library."""
        for index, row in enumerate(self._rows):
            if self.entry is not None and row["id"] == self.entry.id:
                row["notes"] = (t("gui.notes_yes")
                                if self.entry.has_written_notes() else "")
                item = self.table.item(index, 5)
                if item is not None:
                    item.setText(row["notes"])
                return

    def _offer_to_save_notes(self):
        """Ask before losing edited notes; ``False`` cancels what was asked.

        Notes are typed by hand and never regenerated, so silently discarding
        them — or silently writing them — are both wrong."""
        if not self._notes_dirty or self.entry is None:
            return True
        answer = QMessageBox.question(
            self, t("gui.notes_unsaved_title"),
            t("gui.notes_unsaved", title=_title_of(self.entry)),
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self.write_notes()
        self._notes_dirty = False
        return True

    # --- what can be done to an entry -------------------------------------

    def rename_entry(self):
        """Change the title. The folder keeps its id: the title is metadata."""
        if self.entry is None:
            return
        current = _title_of(self.entry)
        title, accepted = QInputDialog.getText(self, t("gui.rename_title"),
                                               t("gui.rename_prompt"),
                                               QLineEdit.EchoMode.Normal, current)
        if not accepted or not title.strip():
            return
        try:
            self.entry.update(title=title.strip()[:200])
        except OSError as exc:
            self.message.emit(str(exc))
            return
        self.reload(keep=self.entry.id)
        self._display()

    def name_speakers_of_entry(self):
        """Put names to the voices, and rewrite the transcript with them.

        The transcript is re-read afterwards rather than patched: the turns of
        two labels given the same name are run together by the rewrite, so
        what is on screen is no longer what was on screen."""
        if self.entry is None:
            return
        segments = self.entry.read_segments()
        speakers = speakers_in(segments)
        if not speakers:
            return
        dialog = SpeakersDialog(speakers, first_lines(segments), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        names = dialog.names()
        if not names:
            self.message.emit(t("gui.speakers_unchanged"))
            return
        try:
            named = self.entry.name_speakers(names)
        except (LibraryError, OSError) as exc:
            self.message.emit(str(exc))
            return
        self.reload(keep=self.entry.id)
        self._display()
        self.message.emit(t("gui.speakers_named", speakers=", ".join(named)))

    def _copy_transcript(self):
        """Put the whole transcript on the clipboard, plain and unlinked."""
        if self.entry is None:
            return
        QGuiApplication.clipboard().setText(self.entry.read_transcript())
        self.message.emit(t("gui.copied"))

    def _copy_summary(self):
        """Put whatever the summary pane shows on the clipboard."""
        text = self.summary.toPlainText()
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        self.message.emit(t("gui.copied"))

    def _copy_notes(self):
        """Put the notes as written on the clipboard."""
        text = self.notes.toPlainText()
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        self.message.emit(t("gui.copied"))

    def export_transcript(self):
        """Write the transcript wherever the user wants a copy of it."""
        if self.entry is None:
            return
        suggestion = os.path.join(os.path.expanduser("~"), f"{self.entry.id}.txt")
        path, _ = QFileDialog.getSaveFileName(self, t("gui.export"), suggestion,
                                              f"{t('gui.filter_text')} (*.txt)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(self.entry.read_transcript())
        except OSError as exc:
            self.message.emit(str(exc))
            return
        self.message.emit(t("gui.exported", path=path))

    def export_subtitles(self, settings=None):
        """Cut this entry's segments into subtitles and save them.

        From the segments, not from a file: an entry transcribed months ago can
        be cut again with today's numbers, which is the whole reason the cues
        are not stored as the only copy."""
        if self.entry is None:
            return
        from .. import pipeline
        from ..subtitles import SubtitleError

        segments = self.entry.read_segments()
        if not segments:
            self.message.emit(t("gui.sub_none"))
            return
        chosen = dict(self.settings)
        chosen.update(settings or {})
        suggestion = os.path.join(os.path.expanduser("~"), f"{self.entry.id}.srt")
        path, _ = QFileDialog.getSaveFileName(
            self, t("gui.sub_export"), suggestion,
            f"{t('gui.filter_srt')} (*.srt);;{t('gui.filter_vtt')} (*.vtt)")
        if not path:
            return
        kind = "vtt" if path.lower().endswith(".vtt") else "srt"
        try:
            spec = pipeline.subtitle_spec(chosen)
            cue_list = pipeline.subtitles_of(_AsResult(segments), chosen)
        except SubtitleError as exc:
            self.message.emit(str(exc))
            return
        text = (pipeline.to_srt(cue_list, spec.get("line_ending", "\n"))
                if kind == "srt" else pipeline.to_vtt(cue_list))
        try:
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
        except OSError as exc:
            self.message.emit(str(exc))
            return
        problems = pipeline.validate(cue_list, spec)
        self.message.emit(t("gui.sub_exported", path=path, cues=len(cue_list),
                            problems=len(problems)))

    def summarise_entry(self):
        """Put a summary of the selected entry in the queue and watch for it.

        Not run here: on the machine this was written for a model reading an
        hour of transcript is minutes, and a window that does it on the thread
        that draws it is a window that has stopped responding. It goes into
        the same queue the transcriptions use, so the two never compete."""
        if self.entry is None or self.queue is None or self._summary_job:
            return
        title = self.entry.metadata.get("title") or self.entry.id
        picked = self.summary_template.currentData()
        own = picked == options.SUMMARY_OWN_TEMPLATE
        overrides = {
            "summarizer": self.summary_engine.currentData(),
            "summary_model": self.summary_model.currentData(),
            "summary_length": self.summary_length.currentData(),
            "summary_style": self.summary_style.currentData(),
            "summary_template": None if own else (picked or None),
            "summary_template_text":
                self.summary_template_text.toPlainText().strip() if own else None,
        }
        # Refused here rather than three minutes into a reading pass: a
        # template that does not parse is a typing mistake.
        try:
            summary_templates.resolve(dict(self.settings, **{
                name: value for name, value in overrides.items()
                if value is not None}))
        except summary_templates.TemplateError as wrong:
            self.message.emit(t("gui.summary_failed", title=title, error=wrong))
            return
        try:
            self._summary_job = self.queue.summarize(self.entry.id, overrides)
        except (LibraryError, SummaryError) as exc:
            self.message.emit(t("gui.summary_failed", title=title, error=exc))
            return
        self.summarise.setEnabled(False)
        self.message.emit(t("gui.summary_queued", title=title))
        self.summary_timer.start(SUMMARY_POLL_MS)

    def _fill_models(self):
        """The models of the engine beside it, keeping the one picked.

        A model the configuration names outside the catalogue - a GGUF file
        of one's own - stays on the menu, or choosing an engine would quietly
        swap it for the plan's."""
        wanted = (self.summary_model.currentData()
                  or self.settings.get("summary_model") or "auto")
        known = plan.named(wanted)
        wanted = known.hf_id if known else wanted
        choices = options.summary_model_choices(self.summary_engine.currentData())
        self.summary_model.clear()
        for name, label in choices:
            self.summary_model.addItem(label, name)
        if choices and self.summary_model.findData(wanted) < 0:
            self.summary_model.addItem(str(wanted), wanted)
        self.summary_model.setCurrentIndex(
            max(0, self.summary_model.findData(wanted)))
        for widget in (self.summary_model_label, self.summary_model):
            widget.setVisible(bool(choices))

    def _show_own_sections(self):
        """The box under the row, shown only when the menu asks for it."""
        self.summary_template_text.setVisible(
            self.summary_template.currentData()
            == options.SUMMARY_OWN_TEMPLATE)

    def _check_summary(self):
        """Has the queued summary finished? Say so, and show it."""
        job = self._summary_job
        if job is None:
            self.summary_timer.stop()
            return
        if job.status not in FINISHED:
            # The state, the stage, and the clock — the same line the queue
            # shows, so a summary reports itself the way a transcription does.
            self.summary_note.setText(options.status_text(job))
            self.summary_progress.setValue(int(job.progress or 0))
            self.summary_progress.setVisible(job.status == RUNNING)
            return
        self.summary_progress.hide()
        self.summary_timer.stop()
        self._summary_job = None
        self.summarise.setEnabled(self.entry is not None)
        if job.status == DONE:
            self.message.emit(t("gui.summary_done", title=job.title))
            # Only if the entry on screen is still the one that was summarised:
            # somebody who moved on should not have the pane change under them.
            if self.entry is not None and self.entry.id == job.entry_id:
                self.entry = self.library.get(job.entry_id)
                self._show_summary()
        elif job.status == FAILED:
            self.message.emit(t("gui.summary_failed", title=job.title,
                                error=job.error or "-"))
            self._show_summary()

    def reveal_folder(self):
        """Open the entry's folder in the system's file manager."""
        if self.entry is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.entry.path))

    def delete_entry(self):
        """Delete a recording, transcript, notes and all, after confirming."""
        if self.entry is None:
            return
        title = _title_of(self.entry)
        answer = QMessageBox.question(
            self, t("gui.delete_title"),
            t("gui.delete_confirm", title=title, path=self.entry.path),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._load_audio(None)       # release the file before removing it
        try:
            self.library.remove(self.entry)
        except (LibraryError, OSError) as exc:
            self.message.emit(str(exc))
            return
        self.message.emit(t("gui.deleted", title=title))
        self._notes_dirty = False
        self.entry = None
        self.reload(keep=None)

    def shutdown(self):
        """Stop playing and give unsaved notes a last chance."""
        if self.player is not None:
            self.player.stop()
        return self._offer_to_save_notes()


class _AsResult:
    """The one field :mod:`pipeline`'s subtitle helpers read off a result.

    Cutting subtitles needs the segments and nothing else, and a library entry
    has those: this saves inventing a fake transcription around them."""

    __slots__ = ("segments",)

    def __init__(self, segments):
        self.segments = segments


def _symbol_button(name, glyph, tooltip, handler):
    """A small button drawn as one of the bundled symbols.

    ``glyph`` is what it falls back to on a build that shipped without the
    drawings — the character this button used to be, which is legible but
    thin: :mod:`audio_transcriber.gui.symbols` says why that was not good
    enough to keep."""
    button = symbols.Button(name, tooltip, glyph)
    button.clicked.connect(handler)
    return button


def _copy_button(handler):
    """The "copy to clipboard" button that sits beside a text pane."""
    return _symbol_button("copy", "⎘", t("gui.copy"), handler)


def _with_copy(box, button):
    """A text pane and its copy button, sharing the pane's bottom line.

    Beside the box rather than under it: a row of its own would cost height
    on every tab, and two of these tabs already have a row of controls."""
    row = QHBoxLayout()
    row.addWidget(box, 1)
    row.addWidget(button, 0, Qt.AlignmentFlag.AlignBottom)
    return row


def _title_of(entry):
    """An entry's title, falling back to its id when the metadata is unreadable."""
    try:
        return str(entry.metadata.get("title") or entry.id)
    except LibraryError:
        return entry.id


def _transcript_html(segments, text):
    """The transcript as HTML, with a clickable timestamp per block.

    Everything from the entry is escaped: a transcript is text that came out of
    a model, and it is displayed in a rich-text widget."""
    blocks = options.transcript_blocks(segments, text)
    if not blocks:
        return f"<p><i>{html.escape(t('gui.no_transcript'))}</i></p>"
    parts = []
    for start, clock, body in blocks:
        body_html = html.escape(body)
        if start is None:
            parts.append(f"<p>{body_html}</p>")
            continue
        parts.append(f'<p><a href="#t={start:.2f}">[{clock}]</a> {body_html}</p>')
    return "\n".join(parts)


def _fill_form(form, rows):
    """Replace the contents of a QFormLayout with ``(label, value)`` rows."""
    while form.rowCount():
        form.removeRow(0)
    for label, value in rows:
        field = QLabel(str(value))
        field.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        field.setWordWrap(True)
        form.addRow(f"{label}:", field)
