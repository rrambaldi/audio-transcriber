"""Summary engines, and the rules for choosing between them.

Every engine exposes the same three things — a ``NAME``, a ``LABEL`` for the
page, and ``summarize(material, settings)`` returning
``(Sections, note_or_None)`` — so :func:`audio_transcriber.summary.summarize`
never knows which one ran.

``openvino``
    A local language model on an Intel device — the iGPU where there is one —
    through OpenVINO GenAI. This is the engine that actually writes: an
    abstract, the decisions, who agreed to do what. Needs the
    ``[summarize-ov]`` extra and a model, which the first run converts to int4
    and keeps.
``llamacpp``
    A GGUF through llama.cpp, on the CPU. The engine for the machine with no
    accelerator at all: nothing to convert, weights mapped from disk rather
    than read into memory, and a cache whose keys and values are quantised
    apart. Either the Python binding or the ``llama-server`` binary will do.
``extractive``
    No model at all: TextRank picks the sentences that carry the transcript
    and they are printed as they were said. Instant, needs nothing beyond
    numpy, and runs anywhere — including in CI and on a two-core server.

    It is also the arithmetic the model engines lean on, twice over, so it is
    never dead weight: it cuts a transcript down when reading all of it would
    take more passes than the machine should spend, and it produces the small
    extract of the original that every reduce pass checks its own partials
    against. And it is what writes the page when the plan says no model fits
    here at all.

``auto`` therefore means "the best this machine has *a model for*", which
is the honest answer on two machines that can do very different things: a
workstation with an iGPU writes prose, and a two-core server with a small GGUF
writes a shorter page. A machine with no model on its disk has no summary at
all — :func:`ready` says so, and every interface asks it before offering one.
Somebody who chose "transcription only" when installing did not ask for a
page of quoted sentences, nor for gigabytes downloaded in the middle of the
first summary. Nothing here ever reaches the network, and that is deliberate
— the transcript does not leave the machine it was made on.

Like :mod:`audio_transcriber.backends`, resolution imports no runtime: it asks
what is installed and answers, so listing the options stays instant. The one
engine module it does import is the one that can be a binary rather than a
package, and that module imports no runtime either.
"""
import glob
import os

from ..hardware import module_available
from ..i18n import t
from ..summary import SummaryError

EXTRACTIVE = "extractive"
OPENVINO = "openvino"
LLAMACPP = "llamacpp"

#: Values accepted for the engine, in the order ``auto`` prefers them: best
#: summary first, and the one that always works last. Where there is an Intel
#: device OpenVINO uses the iGPU and wins; where there is not, llama.cpp on a
#: GGUF beats the extractive engine because it actually writes; the extractive
#: one is last because it is the one that never fails.
ENGINES = (OPENVINO, LLAMACPP, EXTRACTIVE)

#: What an interface offers. "auto" first, because it is the honest default on
#: two machines that can do very different things.
CHOICES = ("auto",) + ENGINES

#: The engines that write with a model, in the order ``auto`` prefers them.
#: Only these make a machine :func:`ready`: the extractive engine needs no
#: model, and on its own it is not a summary anybody installed.
MODEL_ENGINES = (OPENVINO, LLAMACPP)

#: Spellings tolerated for each engine name.
_ALIASES = {
    EXTRACTIVE: EXTRACTIVE,
    "textrank": EXTRACTIVE,
    "sentences": EXTRACTIVE,
    "none": EXTRACTIVE,
    OPENVINO: OPENVINO,
    "ov": OPENVINO,
    "openvino-genai": OPENVINO,
    "openvino_genai": OPENVINO,
    "genai": OPENVINO,
    LLAMACPP: LLAMACPP,
    "llama": LLAMACPP,
    "llama.cpp": LLAMACPP,
    "llama-cpp": LLAMACPP,
    "llama_cpp": LLAMACPP,
    "gguf": LLAMACPP,
}


def is_installed(name, settings=None):
    """Whether what an engine needs is present.

    ``settings`` is only consulted by the one engine that can be a binary
    somewhere else on the disk rather than a package: a ``llama-server`` named
    in ``config.toml`` has to count as installed, or asking for it by name
    would be refused on the machine where it is deployed."""
    if name == EXTRACTIVE:
        return module_available("numpy")
    if name == OPENVINO:
        return module_available("openvino_genai")
    if name == LLAMACPP:
        from .llamacpp import is_available
        return is_available(settings)
    return False


def available(settings=None):
    """The engines this machine could actually run, best first."""
    return [name for name in ENGINES if is_installed(name, settings)]


def has_model(name, settings=None):
    """Whether a model for engine ``name`` is already on this disk.

    A GGUF for llama.cpp, a converted directory for OpenVINO — in the model
    store, or wherever ``summary_model`` points. Either engine would fetch or
    convert one on its first run; that is gigabytes and minutes nobody should
    meet halfway through a summary, so it happens when installing instead
    ("audio-transcriber setup summary") and this is how the rest can tell."""
    from .llamacpp import models_root

    settings = settings or {}
    asked = str(settings.get("summary_model") or "").strip()
    root = models_root(settings.get("models_dir"))
    if name == LLAMACPP:
        return ((asked.lower().endswith(".gguf") and os.path.isfile(asked))
                or bool(glob.glob(os.path.join(root, "*.gguf"))))
    if name == OPENVINO:
        return ((bool(asked) and os.path.isfile(os.path.join(asked, "openvino_model.xml")))
                or bool(glob.glob(os.path.join(root, "*", "openvino_tokenizer.xml"))))
    return False


def ready_engines(settings=None):
    """The model engines that are installed and have a model here, best first."""
    return [name for name in MODEL_ENGINES
            if is_installed(name, settings) and has_model(name, settings)]


def ready(settings=None):
    """Whether this machine can write a summary at all.

    The one question the window, the page and the command line ask before
    they offer a summary: without a model they offer none, and say how to
    install one."""
    return bool(ready_engines(settings))


def resolve_summarizer(engine=None, settings=None):
    """Pick the engine to use.

    With ``auto``: the best engine that has a model on this machine, and a
    refusal that says how to install one when none has. An engine named by
    hand is taken at its word — the extractive one included, which needs no
    model at all.
    """
    requested = str(engine or "auto").strip().lower()
    if requested == "auto":
        engines = ready_engines(settings)
        if not engines:
            raise SummaryError(t("summary.no_model"))
        return engines[0]

    name = _ALIASES.get(requested)
    if name is None:
        raise SummaryError(t("summary.unknown_engine", name=engine,
                             valid=", ".join(CHOICES)))
    if not is_installed(name, settings):
        raise SummaryError(t("summary.engine_missing", name=name)
                           + how_to_install(name))
    return name


#: What to do about an engine that is not here, per engine. The engine's own
#: module says it better than this one could, and says it in the language the
#: rest of the program is speaking.
_HOW_TO_INSTALL = {LLAMACPP: "summary.llamacpp_missing",
                   OPENVINO: "summary.openvino_missing"}


def how_to_install(name):
    """The line that turns a refusal into something somebody can act on.

    Being told an engine is not installed, and not being told what would
    install it, sent somebody looking through the source for the name of a
    configuration key. Twice."""
    key = _HOW_TO_INSTALL.get(name)
    return "\n" + t(key) if key else ""


def load(name):
    """Import and return the module implementing ``name``."""
    if name == EXTRACTIVE:
        from . import extractive as module
    elif name == OPENVINO:
        from . import openvino_genai as module
    elif name == LLAMACPP:
        from . import llamacpp as module
    else:
        raise SummaryError(t("summary.unknown_engine", name=name,
                             valid=", ".join(CHOICES)))
    return module
