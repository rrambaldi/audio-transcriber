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

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
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

from ..formatting import format_clock
from ..i18n import t
from ..library import MAX_NOTES, LibraryError
from . import multimedia, options

#: Typing in the search box is not a query per keystroke: searching reads every
#: transcript in the library, so it waits until the typing stops.
SEARCH_DELAY_MS = 350


class LibraryPanel(QWidget):
    """The entry table, the reading pane, the notes editor and the player."""

    message = Signal(str)

    def __init__(self, library, parent=None):
        super().__init__(parent)
        self.library = library
        self.entry = None
        self._rows = []
        self._notes_dirty = False
        self._audio_path = None

        self._build_table()
        self._build_reader()
        self._build_player()
        self._assemble()

        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.reload)
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
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._selection_changed)

    def _build_reader(self):
        self.transcript = QTextBrowser()
        self.transcript.setOpenLinks(False)
        self.transcript.setOpenExternalLinks(False)
        self.transcript.anchorClicked.connect(self._anchor_clicked)

        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText(t("gui.notes_hint"))
        self.notes.textChanged.connect(self._notes_changed)
        self.save_notes = QPushButton(t("gui.notes_save"))
        self.save_notes.clicked.connect(self.write_notes)
        self.save_notes.setEnabled(False)
        notes_page = QWidget()
        notes_layout = QVBoxLayout(notes_page)
        notes_layout.addWidget(self.notes, 1)
        notes_row = QHBoxLayout()
        notes_row.addStretch(1)
        notes_row.addWidget(self.save_notes)
        notes_layout.addLayout(notes_row)

        self.details = QWidget()
        self.details_form = QFormLayout(self.details)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.transcript, t("gui.tab_transcript"))
        self.tabs.addTab(notes_page, t("gui.tab_notes"))
        self.tabs.addTab(self.details, t("gui.tab_details"))

    def _build_player(self):
        self.play = QPushButton(t("gui.play"))
        self.play.clicked.connect(self.toggle_play)
        self.position = QSlider(Qt.Orientation.Horizontal)
        self.position.setRange(0, 0)
        self.position.sliderMoved.connect(self._seek_ms)
        self.clock = QLabel(f"{format_clock(0)} / {format_clock(0)}")
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
            self.play.setEnabled(False)
            self.play.setToolTip(t("gui.player_no_multimedia"))

    def _assemble(self):
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
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
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel("")
        self.title.setWordWrap(True)
        font = self.title.font()
        font.setBold(True)
        self.title.setFont(font)
        right_layout.addWidget(self.title)

        player_row = QHBoxLayout()
        player_row.addWidget(self.play)
        player_row.addWidget(self.position, 1)
        player_row.addWidget(self.clock)
        right_layout.addLayout(player_row)
        right_layout.addWidget(self.tabs, 1)

        self.rename = QPushButton(t("gui.rename"))
        self.rename.clicked.connect(self.rename_entry)
        self.export = QPushButton(t("gui.export"))
        self.export.clicked.connect(self.export_transcript)
        self.open_folder = QPushButton(t("gui.open_folder"))
        self.open_folder.clicked.connect(self.reveal_folder)
        self.delete = QPushButton(t("gui.delete"))
        self.delete.clicked.connect(self.delete_entry)
        actions = QHBoxLayout()
        for button in (self.rename, self.export, self.open_folder):
            actions.addWidget(button)
        actions.addStretch(1)
        actions.addWidget(self.delete)
        right_layout.addLayout(actions)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout = QVBoxLayout(self)
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
                self.table.setItem(index, column, item)
        self.table.blockSignals(False)

        if not self._rows:
            self.entry = None
            self._clear_reader()
            return
        index = next((i for i, row in enumerate(self._rows) if row["id"] == keep), 0)
        self.table.selectRow(index)
        self._selection_changed()

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
        self.transcript.setHtml(_transcript_html(entry.read_segments(),
                                                 entry.read_transcript()))
        self.notes.blockSignals(True)
        self.notes.setPlainText(entry.read_notes())
        self.notes.blockSignals(False)
        self._notes_dirty = False
        self.save_notes.setEnabled(False)
        _fill_form(self.details_form, options.entry_details(entry))
        self._load_audio(entry.stored_audio())
        self._enable_actions(True)

    def _clear_reader(self):
        self.title.setText("")
        self.transcript.clear()
        self.notes.blockSignals(True)
        self.notes.clear()
        self.notes.blockSignals(False)
        _fill_form(self.details_form, [])
        self._load_audio(None)
        self._enable_actions(False)

    def _enable_actions(self, enabled):
        for button in (self.rename, self.export, self.open_folder, self.delete):
            button.setEnabled(enabled)

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
