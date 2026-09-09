"""Summary engines, and the rules for choosing between them.

Every engine exposes the same three things — a ``NAME``, a ``LABEL`` for the
page, and ``summarize(material, settings)`` returning
``(Sections, note_or_None)`` — so :func:`audio_transcriber.summary.summarize`
never knows which one ran.

``extractive``
    No model at all: TextRank picks the sentences that carry the transcript
    and they are printed as they were said. Instant, needs nothing beyond
    numpy, and runs anywhere — including in CI and on a two-core server. It is
    also the reduction stage the model engines lean on, so it is never dead
    weight.

More engines are coming, and the shape of this module is the promise that
adding one is a file: a local model on the machine's GPU for the summaries
that have to be good, a small quantised model in-process for the machine that
has no GPU. Nothing here ever reaches the network, and that is deliberate —
the transcript does not leave the machine it was made on.

Like :mod:`audio_transcriber.backends`, resolution imports no engine: it asks
what is installed and answers, so listing the options stays instant.
"""
from ..hardware import module_available
from ..i18n import t
from ..summary import SummaryError

EXTRACTIVE = "extractive"

#: Values accepted for the engine, in the order ``auto`` prefers them: best
#: summary first, and the one that always works last.
ENGINES = (EXTRACTIVE,)

#: What an interface offers. "auto" first, because it is the honest default on
#: two machines that can do very different things.
CHOICES = ("auto",) + ENGINES

#: Spellings tolerated for each engine name.
_ALIASES = {
    EXTRACTIVE: EXTRACTIVE,
    "textrank": EXTRACTIVE,
    "sentences": EXTRACTIVE,
    "none": EXTRACTIVE,
}


def is_installed(name):
    """Whether the packages an engine needs are importable."""
    if name == EXTRACTIVE:
        return module_available("numpy")
    return False


def available():
    """The engines this machine could actually run, best first."""
    return [name for name in ENGINES if is_installed(name)]


def resolve_summarizer(engine=None):
    """Pick the engine to use.

    With ``auto``: the best one this machine has, which on a server with no
    accelerator is the extractive one and on a machine with a GPU will not be.
    """
    requested = str(engine or "auto").strip().lower()
    if requested == "auto":
        installed = available()
        if not installed:
            raise SummaryError(t("summary.none_installed"))
        return installed[0]

    name = _ALIASES.get(requested)
    if name is None:
        raise SummaryError(t("summary.unknown_engine", name=engine,
                             valid=", ".join(CHOICES)))
    if not is_installed(name):
        raise SummaryError(t("summary.engine_missing", name=name))
    return name


def load(name):
    """Import and return the module implementing ``name``."""
    if name == EXTRACTIVE:
        from . import extractive as module
    else:
        raise SummaryError(t("summary.unknown_engine", name=name,
                             valid=", ".join(CHOICES)))
    return module
