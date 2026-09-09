"""The window itself: three tabs over one queue and one library.

The desktop interface is a third front end for the same core, next to the
command line and the web page. It owns nothing the others do not: the queue
comes from :mod:`audio_transcriber.jobs`, the transcription from
:mod:`audio_transcriber.pipeline`, the recordings from
:mod:`audio_transcriber.library`, and the defaults from ``config.toml``. What
it adds is a microphone, a player and a folder-free way of reaching them.
"""
import os
import sys

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QTabWidget

from .. import __version__, paths
from ..i18n import t
from ..jobs import JobQueue
from .library_panel import LibraryPanel
from .system_panel import SystemPanel
from .transcribe_panel import TranscribePanel

#: Where the window remembers its size and the last options used. It sits with
#: config.toml rather than in the platform's registry-like default: this
#: program keeps everything it writes under its own directories.
SETTINGS_FILENAME = "gui.ini"

#: A first-run size that fits a 1366x768 laptop screen.
DEFAULT_SIZE = (1180, 760)


class MainWindow(QMainWindow):
    """Transcribe, Library, This machine."""

    def __init__(self, settings=None, queue=None, parent=None):
        super().__init__(parent)
        self.settings = dict(settings or {})
        self.store = QSettings(os.path.join(paths.ensure(paths.config_dir()),
                                            SETTINGS_FILENAME),
                               QSettings.Format.IniFormat)
        self.queue = queue or JobQueue(self.settings)

        self.setWindowTitle(t("gui.window_title", version=__version__))
        self.transcribe = TranscribePanel(self.queue, self.settings, self.store)
        self.library = LibraryPanel(self.queue.library, self.settings,
                                    queue=self.queue)
        self.system = SystemPanel(self.settings, self.queue.library)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.transcribe, t("gui.tab_transcribe"))
        self.tabs.addTab(self.library, t("gui.tab_library"))
        self.tabs.addTab(self.system, t("gui.tab_system"))
        self.setCentralWidget(self.tabs)

        self.transcribe.message.connect(self.announce)
        self.library.message.connect(self.announce)
        self.transcribe.entry_requested.connect(self.show_entry)
        self.transcribe.job_finished.connect(self._job_finished)
        self.statusBar().showMessage(t("gui.ready", path=self.queue.library.root))
        self._restore_geometry()

    # --- moving between the tabs ------------------------------------------

    def announce(self, text):
        """Put a one-line message in the status bar."""
        self.statusBar().showMessage(text, 8000)

    def show_entry(self, entry_id):
        """Bring the library tab up on one entry."""
        if self.library.show_entry(entry_id):
            self.tabs.setCurrentWidget(self.library)

    def _job_finished(self, entry_id):
        """A transcription has been filed: the library list is now stale."""
        self.library.reload()
        if entry_id:
            self.announce(t("gui.job_finished", entry=entry_id))

    # --- geometry ---------------------------------------------------------

    def _restore_geometry(self):
        geometry = self.store.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(*DEFAULT_SIZE)

    # --- shutting down ----------------------------------------------------

    def closeEvent(self, event):
        """Ask before abandoning work, then put the timers down.

        The queue lives in this process: closing the window is the end of any
        transcription still running, and a job that has been going for forty
        minutes is worth one question."""
        if not self.library.shutdown():
            event.ignore()
            return
        pending = self.queue.pending_count()
        if pending and not self._confirm_abandon(pending):
            event.ignore()
            return
        self.transcribe.shutdown()
        self.store.setValue("geometry", self.saveGeometry())
        self.store.sync()
        event.accept()

    def _confirm_abandon(self, pending):
        answer = QMessageBox.question(
            self, t("gui.quit_title"), t("gui.quit_pending", count=pending),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes


def launch(settings=None, argv=None):
    """Show the window and run the event loop until it is closed."""
    application = QApplication.instance()
    owned = application is None
    if owned:
        # Qt parses argv itself (-style, -platform); the program's own options
        # have already been dealt with by argparse, so it is handed none.
        application = QApplication(list(argv or sys.argv[:1]))
    application.setApplicationName("audio-transcriber")
    application.setApplicationDisplayName(t("gui.app_name"))
    application.setApplicationVersion(__version__)
    application.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)

    window = MainWindow(settings)
    window.show()
    return application.exec() if owned else 0
