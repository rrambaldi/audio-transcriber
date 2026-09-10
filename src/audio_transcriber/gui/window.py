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

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, branding, paths
from ..i18n import t
from ..jobs import JobQueue
from . import style
from .library_panel import LibraryPanel
from .masthead import Masthead
from .system_panel import SystemPanel
from .transcribe_panel import TranscribePanel

#: Where the window remembers its size and the last options used. It sits with
#: config.toml rather than in the platform's registry-like default: this
#: program keeps everything it writes under its own directories.
SETTINGS_FILENAME = "gui.ini"

#: A first-run size that fits a 1366x768 laptop screen.
DEFAULT_SIZE = (1180, 760)


def app_icon():
    """The program's mark, at every size the desktop might want.

    The renders are handed over individually rather than as one large PNG:
    the title bar asks for 16 px and the alt-tab list for 256, and the small
    sizes are a simplified drawing of the lock, not a scaled-down master.
    A build with no icons at all yields an empty QIcon, which Qt treats as
    "no icon set" - the window still opens."""
    icon = QIcon()
    for size, file in branding.icon_files():
        icon.addFile(file, QSize(size, size))
    return icon


def claim_taskbar_identity():
    """Tell Windows these windows are a program of their own.

    A packaged .exe does not need this; a ``pip install`` does, and that is
    how nearly everyone runs this. Explorer decides which icon a task bar
    button gets from the process's Application User Model ID, which defaults
    to the interpreter's - so the mark set below would be honoured everywhere
    except the one place people click.

    Everything here is best effort: on any other platform, on a Windows
    without the call, or on a machine where it fails, the window still opens
    with the icon it was given."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            branding.WINDOWS_APP_ID)
        return True
    except Exception:               # pragma: no cover - Windows only
        return False


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
        # Set on the window as well as on the application: a window opened
        # inside somebody else's Qt process has no say over that one.
        self.setWindowIcon(app_icon())
        self.transcribe = TranscribePanel(self.queue, self.settings, self.store)
        self.library = LibraryPanel(self.queue.library, self.settings,
                                    queue=self.queue)
        self.system = SystemPanel(self.settings, self.queue.library)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.transcribe, t("gui.tab_transcribe"))
        self.tabs.addTab(self.library, t("gui.tab_library"))
        self.tabs.addTab(self.system, t("gui.tab_system"))

        # The mark and the promise sit above the tabs rather than inside one
        # of them: they are true of the whole window, and the title bar is
        # not somewhere to put them - it is 16 px tall, and on a maximised
        # window or a tiling desktop it is not drawn at all.
        self.masthead = Masthead(self.windowIcon())
        central = QWidget()
        frame = QVBoxLayout(central)
        frame.setContentsMargins(0, 0, 0, 0)
        frame.setSpacing(0)
        frame.addWidget(self.masthead)
        frame.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        self.transcribe.message.connect(self.announce)
        self.library.message.connect(self.announce)
        self.transcribe.entry_requested.connect(self.show_entry)
        self.transcribe.job_finished.connect(self._job_finished)
        self.statusBar().showMessage(self._library_line())
        self._restore_geometry()

    # --- moving between the tabs ------------------------------------------

    def announce(self, text):
        """Put a one-line message in the status bar."""
        self.statusBar().showMessage(text, 8000)

    def show_entry(self, entry_id):
        """Bring the library tab up on one entry."""
        if self.library.show_entry(entry_id):
            self.tabs.setCurrentWidget(self.library)

    def _library_line(self):
        """What the status bar says when it has nothing else to say.

        It used to hold the path of the library, permanently — a piece of
        configuration parked in the one place a message can appear, which is
        why every message it showed vanished back into a directory name.
        Where the files are is a question the "This machine" tab answers."""
        try:
            count = len(self.queue.library.entries())
        except OSError:             # a library on a disconnected drive
            count = 0
        return t("gui.ready", count=count)

    def _job_finished(self, entry_id):
        """A transcription has been filed: the library list is now stale."""
        self.library.reload()
        if entry_id:
            self.announce(t("gui.job_finished", entry=entry_id))
        self.statusBar().clearMessage()
        self.statusBar().showMessage(self._library_line())

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
    # Before the first window exists: Windows reads the identity when the
    # task bar button is created, and does not look again.
    claim_taskbar_identity()
    application.setApplicationName("audio-transcriber")
    application.setApplicationDisplayName(t("gui.app_name"))
    application.setApplicationVersion(__version__)
    application.setWindowIcon(app_icon())
    # Which .desktop file describes this program: how a Wayland compositor -
    # and GNOME's dock on X11 too - finds the icon to draw for these windows.
    application.setDesktopFileName(branding.DESKTOP_ENTRY)
    application.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
    # The desktop's own palette, with one floor imposed on it: text this
    # window disables is still text somebody has to read. See gui/style.py.
    style.apply(application)

    window = MainWindow(settings)
    window.show()
    return application.exec() if owned else 0
