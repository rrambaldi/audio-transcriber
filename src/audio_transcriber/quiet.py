"""Upstream lines this program has read, understood, and does not pass on.

A transcription prints a lot for a person who is waiting for it, and every
line they cannot act on makes the ones they can act on harder to find. What is
dropped here is not this program's own reporting and not a failure of any
kind: each entry is a library talking to its own maintainers — about an
argument it passed itself, or a corner of its own arithmetic — over a run that
is proceeding normally.

Nothing here is a blanket filter. Each is matched on the exact wording of the
line it silences, so a new message from the same library, or a changed one,
comes through as it should. And each is installed once: a filter added per
recording would pile up over a queue.
"""
import logging
import re
import warnings

#: optimum-intel builds Whisper's token-suppression processors itself and
#: hands them to ``generate()``, which builds the same ones from the
#: generation config and then says it will use the ones it was given. Both
#: copies do the same thing, nothing is lost, and there is no argument anybody
#: running a transcription can change to stop it being said - twice, on every
#: single run.
DUPLICATE_PROCESSOR = "but it was also created in `.generate()`"

#: The logger that says it. Named exactly, because a filter on a logger
#: applies to what that logger handles and not to what its children send past
#: it.
GENERATION_LOGGER = "transformers.generation.utils"

#: pyannote's pooling takes the standard deviation of each speaker window, and
#: a window one frame long has no deviation to take: torch says so, from C++,
#: with a sentence about degrees of freedom. It happens on ordinary recordings
#: - a very short turn is enough - and the embedding it produces is discarded
#: anyway.
POOLING_STD = "std(): degrees of freedom is <= 0"

_installed = set()


class _Without(logging.Filter):
    """Drops the records whose message contains one of these fragments."""

    def __init__(self, fragments):
        super().__init__()
        self.fragments = fragments

    def filter(self, record):
        try:
            message = record.getMessage()
        except Exception:
            return True             # unformattable: not ours to judge
        return not any(fragment in message for fragment in self.fragments)


def hush_duplicate_logits_processors():
    """Stop transformers reporting an argument optimum-intel passed it."""
    if "processors" in _installed:
        return
    logging.getLogger(GENERATION_LOGGER).addFilter(_Without([DUPLICATE_PROCESSOR]))
    _installed.add("processors")


def hush_pooling_deviation():
    """Stop torch explaining degrees of freedom over every short turn."""
    if "pooling" in _installed:
        return
    warnings.filterwarnings("ignore", message=re.escape(POOLING_STD),
                            category=UserWarning)
    _installed.add("pooling")
