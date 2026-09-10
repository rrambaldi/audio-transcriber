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

``auto`` therefore means "the best this machine has", which is the honest
answer on two machines that can do very different things: a workstation with
an iGPU writes prose, and a two-core server quotes sentences. Nothing here
ever reaches the network, and that is deliberate — the transcript does not
leave the machine it was made on.

Like :mod:`audio_transcriber.backends`, resolution imports no runtime: it asks
what is installed and answers, so listing the options stays instant. The one
engine module it does import is the one that can be a binary rather than a
package, and that module imports no runtime either.
"""
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


def resolve_summarizer(engine=None, settings=None):
    """Pick the engine to use.

    With ``auto``: the best one this machine has, which on a server with no
    accelerator is llama.cpp where it is installed and the extractive one
    where it is not.
    """
    requested = str(engine or "auto").strip().lower()
    if requested == "auto":
        installed = available(settings)
        if not installed:
            raise SummaryError(t("summary.none_installed"))
        return installed[0]

    name = _ALIASES.get(requested)
    if name is None:
        raise SummaryError(t("summary.unknown_engine", name=engine,
                             valid=", ".join(CHOICES)))
    if not is_installed(name, settings):
        raise SummaryError(t("summary.engine_missing", name=name))
    return name


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
