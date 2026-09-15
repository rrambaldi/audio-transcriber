"""Transcription backends and the rules for choosing between them.

Two engines expose the same ``transcribe()`` signature:

``openvino``
    Whisper on Intel hardware (iGPU, NPU, CPU). Fast when an Intel iGPU is
    present; the historical backend of this project.
``faster-whisper``
    Whisper on CTranslate2, int8-quantised on CPU. The right choice on a
    GPU-less server, and usable on CUDA too.

``resolve_backend`` never imports either engine: it only asks whether the
packages are installed and what accelerators exist, so ``--hardware`` stays
instant even when a full OpenVINO stack is present.
"""
import sys

from ..hardware import has_openvino_accelerator, module_available
from ..i18n import t

OPENVINO = "openvino"
FASTER_WHISPER = "faster-whisper"

#: Values accepted by ``--backend``.
BACKENDS = ("auto", FASTER_WHISPER, OPENVINO)

#: Spellings tolerated for each backend name.
_ALIASES = {
    OPENVINO: OPENVINO,
    "ov": OPENVINO,
    FASTER_WHISPER: FASTER_WHISPER,
    "faster_whisper": FASTER_WHISPER,
    "fasterwhisper": FASTER_WHISPER,
    "ct2": FASTER_WHISPER,
    "ctranslate2": FASTER_WHISPER,
}


def is_installed(name):
    """Whether the packages a backend needs are importable."""
    if name == FASTER_WHISPER:
        return module_available("faster_whisper")
    if name == OPENVINO:
        return module_available("optimum") and module_available("openvino")
    return False


def resolve_backend(backend, device):
    """Pick the backend to use.

    With ``auto``: an explicitly requested Intel or CUDA device decides, then
    OpenVINO if it can see an Intel accelerator, then whatever is installed —
    preferring faster-whisper, which is the better CPU engine."""
    requested = (backend or "auto").strip().lower()
    if requested != "auto":
        name = _ALIASES.get(requested)
        if name is None:
            sys.exit(t("backend.unknown", name=backend, valid=", ".join(BACKENDS)))
        return name

    wanted_device = (device or "auto").strip().upper()
    if (wanted_device == "NPU" or wanted_device.startswith("GPU.")) and is_installed(OPENVINO):
        return OPENVINO
    if wanted_device.startswith("CUDA") and is_installed(FASTER_WHISPER):
        return FASTER_WHISPER

    if is_installed(OPENVINO) and has_openvino_accelerator():
        return OPENVINO
    if is_installed(FASTER_WHISPER):
        return FASTER_WHISPER
    if is_installed(OPENVINO):
        return OPENVINO
    sys.exit(t("backend.none_installed"))


def import_failure(message_key, error):
    """What to say when an engine will not import, which is two things.

    A package that is not there is an install away. One that *is* there and
    will not load is a broken install — a ctranslate2 without its runtime, an
    OpenVINO whose DLLs lost their place in the search path — and telling
    somebody to install what they have just installed is how an afternoon
    goes. The failing module names itself in the exception, so which of the
    two it is can be established rather than guessed."""
    culprit = getattr(error, "name", None) or ""
    if culprit and module_available(culprit.split(".")[0]):
        return t("backend.will_not_load", module=culprit, error=error)
    return t(message_key)


def load(name):
    """Import and return the module implementing ``name``."""
    if name == OPENVINO:
        from . import openvino as module
    elif name == FASTER_WHISPER:
        from . import faster_whisper as module
    else:
        sys.exit(t("backend.unknown", name=name, valid=", ".join(BACKENDS)))
    return module
