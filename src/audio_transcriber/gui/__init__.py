"""The desktop interface: the same transcriptions, in a window.

Qt is an optional extra, so it is imported only when the window is actually
opened; installing the package for the command line pulls in nothing of it.
The tabs are in :mod:`~audio_transcriber.gui.transcribe_panel`,
:mod:`~audio_transcriber.gui.library_panel` and
:mod:`~audio_transcriber.gui.system_panel`, and every decision they make that
is worth testing lives in :mod:`~audio_transcriber.gui.options`, which does
not import Qt at all.
"""
import sys


def available():
    """Whether the Qt binding needed for the window is installed."""
    from ..hardware import module_available

    return module_available("PySide6")


def run(settings=None):
    """Open the window and return the process exit code."""
    from ..i18n import t

    if not available():
        sys.exit(t("gui.missing"))
    try:
        from .window import launch
    except ImportError as exc:
        # PySide6 is there but not usable: a partial install, or a Linux box
        # missing the X/Wayland libraries Qt links against.
        sys.exit(t("gui.broken", error=exc))
    return launch(settings)
