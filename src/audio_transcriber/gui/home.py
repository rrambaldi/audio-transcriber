"""The library as the window's home: its folders, the work under way, and the
two ways a new recording comes in.

A recording used to live in two places. It was born in a "Transcribe" tab, a
queue with the recorder on top, and it grew up in "Library", where nothing
could be started again. Two tabs showing one thing at two ages, each with
actions the other lacked, is the confusion this module ends: there is one
place, the library, and the work still under way is a folder at the top of
it - *In progress* - that empties itself as each job lands where it belongs.

What is here is the frame and nothing else. The list and the reading pane
are :class:`~audio_transcriber.gui.library_panel.LibraryPanel`, the queue is
:class:`~audio_transcriber.gui.transcribe_panel.TranscribePanel`, and the
folders themselves are :class:`~audio_transcriber.library.Library`'s.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..i18n import t
from ..library import LibraryError
from . import options, symbols
from .library_panel import ask_linked_folder

#: The tree's key for the work under way. Not a folder name: a folder can be
#: called anything, but not something that starts with a NUL.
WORKING = "\0working"


class FolderTree(QTreeWidget):
    """The work under way, then the library and its folders.

    A row of the library list dropped on a folder moves there."""

    #: An entry was dropped on a folder: its id, and the folder ("" = top).
    entry_dropped = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QTreeWidget.DragDropMode.DropOnly)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def fill(self, folders, working, keep=None, targets=None):
        """Rebuild the tree, and select ``keep`` if it is still there.

        ``targets`` maps a folder that is a link to where it really is: it
        is drawn with the link symbol, and its tooltip says where."""
        targets = targets or {}
        keep = self.current_key() if keep is None else keep
        self.blockSignals(True)
        self.clear()
        self.working = QTreeWidgetItem([t("gui.tree_working", count=working)])
        self.working.setData(0, Qt.ItemDataRole.UserRole, WORKING)
        self.root = QTreeWidgetItem([t("gui.tree_library")])
        self.root.setData(0, Qt.ItemDataRole.UserRole, "")
        self.addTopLevelItems([self.working, self.root])
        items = {"": self.root}
        for folder in folders:
            parent = items.get(folder.rpartition("/")[0], self.root)
            item = QTreeWidgetItem(parent, [folder.rpartition("/")[2]])
            item.setData(0, Qt.ItemDataRole.UserRole, folder)
            if targets.get(folder):
                item.setIcon(0, symbols.icon("folder_link", symbols.size_for(self)))
                item.setToolTip(0, t("gui.folder_linked_tip", path=targets[folder]))
            items[folder] = item
        self.expandAll()
        self.blockSignals(False)
        found = self.item_for(keep) or self.root
        self.setCurrentItem(found)

    def count_working(self, working):
        if getattr(self, "working", None) is not None:
            self.working.setText(0, t("gui.tree_working", count=working))

    def item_for(self, key):
        if key is None:
            return None
        for item in self._items():
            if item.data(0, Qt.ItemDataRole.UserRole) == key:
                return item
        return None

    def _items(self):
        stack = [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        while stack:
            item = stack.pop()
            yield item
            stack.extend(item.child(i) for i in range(item.childCount()))

    def current_key(self):
        item = self.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item else None

    def select_key(self, key):
        item = self.item_for(key)
        if item is not None:
            self.setCurrentItem(item)
        return item is not None

    # --- a row of the list dropped on a folder ------------------------------

    def _target(self, event):
        if not event.mimeData().hasFormat(options.ENTRY_MIME):
            return None
        item = self.itemAt(event.position().toPoint())
        key = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        return None if key is None or key == WORKING else key

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(options.ENTRY_MIME):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if self._target(event) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        folder = self._target(event)
        if folder is None:
            event.ignore()
            return
        entry_id = bytes(event.mimeData().data(options.ENTRY_MIME)).decode("utf-8")
        event.acceptProposedAction()
        self.entry_dropped.emit(entry_id, folder)


class Home(QWidget):
    """Add a file or record one, the folders on the left, and what is in them."""

    message = Signal(str)

    def __init__(self, library_panel, transcribe_panel, library, parent=None):
        super().__init__(parent)
        self.panel = library_panel
        self.transcribe = transcribe_panel
        self.library = library
        self.setAcceptDrops(True)

        # The two ways in, always in sight: a file from disk goes to the top
        # of the library once transcribed, a recording to the folder chosen
        # beside the recorder.
        self.add = QPushButton(t("gui.add_files"))
        self.add.clicked.connect(self.choose_files)
        self.record = QPushButton(t("gui.recorder"))
        self.record.setCheckable(True)
        self.record.toggled.connect(self._show_recorder)
        symbols.dress(self.add, "add_file", "go")
        symbols.dress(self.record, "mic", "record")
        toolbar = QHBoxLayout()
        toolbar.addWidget(self.add)
        toolbar.addWidget(self.record)
        toolbar.addStretch(1)

        # The recorder is the queue's - a finished recording goes into it -
        # but it is shown here, and only when asked for: most of the time a
        # recording arrives as a file, and a recorder with no microphone was
        # a hundred pixels of the window saying so.
        self.record_folder = QComboBox()
        self.record_folder.setToolTip(t("gui.record_into_tip"))
        self.record_folder.currentIndexChanged.connect(self._record_folder_chosen)
        into = QHBoxLayout()
        into.addWidget(QLabel(t("gui.record_into")))
        into.addWidget(self.record_folder)
        into.addStretch(1)
        self.recorder_box = QGroupBox(t("gui.group_record"))
        recorder_layout = QVBoxLayout(self.recorder_box)
        recorder_layout.addWidget(self.transcribe.recorder)
        recorder_layout.addLayout(into)
        self.recorder_box.hide()

        self.tree = FolderTree()
        self.tree.currentItemChanged.connect(self._folder_chosen)
        self.tree.entry_dropped.connect(self.panel.move_entry)
        self.panel.folders_changed.connect(lambda _made: self.refresh_folders())
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        self.new_folder_button = QPushButton(t("gui.folder_new"))
        self.new_folder_button.clicked.connect(self.new_folder)
        symbols.dress(self.new_folder_button, "folder_add")
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.tree, 1)
        left_layout.addWidget(self.new_folder_button)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.panel)
        self.stack.addWidget(self.transcribe)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([150, 1130])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(toolbar)
        layout.addWidget(self.recorder_box)
        layout.addWidget(splitter, 1)

        QShortcut(QKeySequence.StandardKey.Open, self, activated=self.choose_files)
        self.transcribe.queue_changed.connect(self.tree.count_working)
        self.refresh_folders(keep="")
        self.tree.count_working(len(self.transcribe._rows))

    # --- the way in ---------------------------------------------------------

    def choose_files(self):
        self.transcribe.choose_files()
        if self.transcribe._rows:
            self.show_working()

    def add_files(self, paths):
        """Queue files from disk, and show them waiting."""
        if not self.transcribe.add_files(paths):
            return False
        self.show_working()
        return True

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Files dropped anywhere on the library are queued."""
        paths = [url.toLocalFile() for url in event.mimeData().urls()]
        if self.add_files(paths):
            event.acceptProposedAction()

    def _show_recorder(self, shown):
        # Not hidden while it records: that would be hiding the Stop button.
        recording = getattr(self.transcribe.recorder, "recording", None)
        if not shown and callable(recording) and recording():
            self.record.blockSignals(True)
            self.record.setChecked(True)
            self.record.blockSignals(False)
            return
        self.recorder_box.setVisible(shown)

    def _record_folder_chosen(self):
        folder = self.record_folder.currentData()
        self.transcribe.record_folder = folder or ""

    # --- the tree -----------------------------------------------------------

    def refresh_folders(self, keep=None):
        """Read the folders again, keeping the one selected where it can."""
        try:
            folders = self.library.folders()
        except (LibraryError, OSError):
            folders = []
        self.tree.fill(folders, len(self.transcribe._rows), keep=keep,
                       targets={folder: self.library.folder_target(folder)
                                for folder in folders})
        chosen = self.record_folder.currentData()
        self.record_folder.blockSignals(True)
        self.record_folder.clear()
        for folder, label in options.folder_choices(folders):
            self.record_folder.addItem(label, folder)
        index = self.record_folder.findData(chosen if chosen is not None else "")
        self.record_folder.setCurrentIndex(max(0, index))
        self.record_folder.blockSignals(False)
        self._record_folder_chosen()

    def _folder_chosen(self, current, _previous=None):
        key = current.data(0, Qt.ItemDataRole.UserRole) if current else ""
        if key == WORKING:
            self.stack.setCurrentWidget(self.transcribe)
            return
        self.stack.setCurrentWidget(self.panel)
        moved = key != self.panel.folder
        self.panel.set_folder(key)
        if self.panel.folder != key:
            # Notes left unsaved, and the answer was Cancel: stay put.
            self.tree.blockSignals(True)
            self.tree.select_key(self.panel.folder)
            self.tree.blockSignals(False)
            return
        # A recording made now goes where the reader is looking, unless the
        # menu is changed: the folder somebody opened is the likeliest answer.
        # Only on a real change - the tree is rebuilt after every job, and
        # that must not undo a choice made in the menu.
        index = self.record_folder.findData(key)
        if moved and index >= 0:
            self.record_folder.setCurrentIndex(index)

    def show_working(self):
        self.tree.select_key(WORKING)

    def show_entry(self, entry_id):
        """Open the folder an entry is in, and the entry."""
        try:
            entry = self.library.get(entry_id)
        except LibraryError:
            return False
        self.tree.select_key(options.folder_of(entry.id))
        return self.panel.show_entry(entry.id)

    def _tree_menu(self, point):
        item = self.tree.itemAt(point)
        key = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if key is None or key == WORKING:
            return
        self.tree.setCurrentItem(item)
        menu = QMenu(self)
        menu.addAction(t("gui.folder_new"), self.new_folder)
        menu.addAction(t("gui.folder_link"), self.link_folder)
        if key:
            menu.addAction(t("gui.folder_rename"), self.rename_folder)
            menu.addAction(t("gui.folder_unlink" if self.library.folder_target(key)
                             else "gui.folder_delete"), self.delete_folder)
        menu.exec(self.tree.viewport().mapToGlobal(point))

    def _chosen_folder(self):
        key = self.tree.current_key()
        return "" if key in (None, WORKING) else key

    def new_folder(self):
        """A folder inside the one selected, or at the top."""
        parent = self._chosen_folder()
        name, accepted = QInputDialog.getText(self, t("gui.folder_new"),
                                              t("gui.folder_name"))
        if not accepted or not name.strip():
            return None
        return self.make_folder(parent, name.strip())

    def link_folder(self):
        """A folder on the disk, linked inside the one selected or at the top."""
        try:
            made = ask_linked_folder(self, self.library, self._chosen_folder())
        except (LibraryError, OSError) as exc:
            self.message.emit(t("gui.folder_failed", error=exc))
            return None
        if made:
            self.refresh_folders(keep=made)
        return made

    def make_folder(self, parent, name):
        path = f"{parent}/{name}" if parent else name
        try:
            made = self.library.create_folder(path)
        except (LibraryError, OSError) as exc:
            self.message.emit(t("gui.folder_failed", error=exc))
            return None
        self.refresh_folders(keep=made)
        return made

    def rename_folder(self):
        folder = self._chosen_folder()
        if not folder:
            return None
        name, accepted = QInputDialog.getText(
            self, t("gui.folder_rename"), t("gui.folder_name"),
            text=folder.rpartition("/")[2])
        if not accepted or not name.strip():
            return None
        return self.rename_folder_to(folder, name.strip())

    def rename_folder_to(self, folder, name):
        # Notes written and a recording playing both hold on to a path inside
        # the folder, and Windows will not rename a folder with a file open.
        if not self.panel._offer_to_save_notes():
            return None
        self.panel._load_audio(None)
        try:
            renamed = self.library.rename_folder(folder, name)
        except (LibraryError, OSError) as exc:
            self.message.emit(t("gui.folder_failed", error=exc))
            if self.panel.entry is not None:
                self.panel._load_audio(self.panel.entry.stored_audio())
            return None
        # What was being read inside it has a new id now.
        self.panel.entry = None
        self.panel.folder = None
        self.refresh_folders(keep=renamed)
        return renamed

    def delete_folder(self):
        """Only an empty folder, and only after asking. A linked one is only
        unlinked, full or not: its recordings stay where they are."""
        folder = self._chosen_folder()
        if not folder:
            return False
        target = self.library.folder_target(folder)
        if target is None and (self.library.entries(folder) or any(
                other.startswith(folder + "/") for other in self.library.folders())):
            self.message.emit(t("gui.folder_not_empty", folder=folder))
            return False
        answer = QMessageBox.question(
            self, t("gui.folder_unlink" if target else "gui.folder_delete"),
            t("gui.folder_unlink_confirm", folder=folder, path=target) if target
            else t("gui.folder_delete_confirm", folder=folder),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return False
        try:
            self.library.remove_folder(folder)
        except (LibraryError, OSError) as exc:
            self.message.emit(t("gui.folder_failed", error=exc))
            return False
        self.refresh_folders(keep=folder.rpartition("/")[0])
        return True
