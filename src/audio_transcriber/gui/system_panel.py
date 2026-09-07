"""The "this machine" tab: what the tool found, and where it keeps things.

The same three questions ``audio-transcriber hardware``, ``paths`` and
``config`` answer on the command line, because they are the questions people
actually ask when a transcription is slower than expected or when they cannot
find their recordings. Nothing here can be changed from the window:
``config.toml`` is edited in an editor, and the button opens it.
"""
import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import paths
from ..i18n import t


class SystemPanel(QWidget):
    """Hardware, engines, and the directories in use."""

    def __init__(self, settings=None, library=None, parent=None):
        super().__init__(parent)
        self.settings = dict(settings or {})
        self.library = library

        hardware = QGroupBox(t("gui.group_hardware"))
        self.hardware_form = QFormLayout(hardware)
        for label, value in self._hardware_rows():
            self.hardware_form.addRow(f"{label}:", _value(value))

        locations = QGroupBox(t("gui.group_paths"))
        form = QFormLayout(locations)
        for label, path, exists, configured in paths.describe(self.settings):
            note = "" if exists else f"  ({t('gui.path_missing')})"
            if configured:
                note += f"  ({t('gui.path_configured')})"
            form.addRow(f"{label}:", _value(f"{path}{note}"))

        buttons = QHBoxLayout()
        config_button = QPushButton(t("gui.open_config"))
        config_button.clicked.connect(self.open_config)
        library_button = QPushButton(t("gui.open_library"))
        library_button.clicked.connect(self.open_library)
        buttons.addWidget(config_button)
        buttons.addWidget(library_button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(hardware)
        layout.addWidget(locations)
        layout.addLayout(buttons)
        layout.addStretch(1)

    def _hardware_rows(self):
        """What the machine can do, asked the same way the CLI asks it.

        The imports are local because :mod:`audio_transcriber.hardware` only
        probes on demand: nothing heavy is loaded to draw this tab."""
        from ..backends import resolve_backend
        from ..diarization import NO_MODEL, NOT_INSTALLED, availability
        from ..hardware import summary
        from ..transcription import recommend_model

        device = self.settings.get("device") or "auto"
        try:
            backend = resolve_backend("auto", device)
        except SystemExit as exc:
            # No engine installed: the modules underneath say so the way a
            # command line does, and a tab must not take the window with it.
            return [(t("gui.row_machine"), summary()),
                    (t("gui.row_backend"), str(exc))]
        state, detail = availability(self.settings.get("diar_model"))
        diarization = t({NOT_INSTALLED: "gui.diar_missing",
                         NO_MODEL: "gui.diar_unconfigured"}.get(state, "gui.diar_ready"),
                        detail=detail)
        return [
            (t("gui.row_machine"), summary()),
            (t("gui.row_backend"), backend),
            (t("gui.row_model"), recommend_model(backend, device)),
            (t("gui.row_diarization"), diarization),
        ]

    def open_config(self):
        """Open ``config.toml`` in whatever the system uses for text files."""
        path = paths.config_file()
        if not os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(paths.ensure(paths.config_dir())))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def open_library(self):
        root = self.library.root if self.library is not None else paths.library_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(paths.ensure(root)))


def _value(text):
    """A read-only field the user can still select and copy."""
    label = QLabel(str(text))
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label
