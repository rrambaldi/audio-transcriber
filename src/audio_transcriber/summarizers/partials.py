"""Keeping the answers to the passes that have already been read.

A map pass is deterministic — the same chunk, the same prompt, the same model,
sampling off — and independent of every other pass. So the second time it is
asked it does not have to be read again, and that buys two concrete things on
a machine where reading is minutes rather than seconds:

* asking for the same recording at a different length re-uses every pass and
  only writes the page again;
* a job interrupted halfway — a closed browser, a restarted server, a
  cancelled queue — resumes where it stopped instead of at the beginning.

The key includes a version of the prompts, and that is not ceremony. A cache
that survives a change to the prompt it was filled under is not a saving but a
bug that accumulates: the answers stay plausible, they simply stop being
answers to the question now being asked.

Nothing here is required for a summary to be produced. Every failure — an
unwritable directory, a truncated file, a full disk — is answered by a miss
and a summary that takes as long as it used to.
"""
import hashlib
import os

from .. import paths
from . import prompting

#: Under the cache directory, which the configuration may point elsewhere and
#: which is safe to delete at any time.
NAMESPACE = "summary-passes"

#: Cached answers are small — a bulleted list each — but a long recording on a
#: busy server makes a lot of them. Files this old are removed when the cache
#: is next written to, so nothing has to remember to clean up.
KEEP_DAYS = 30


def directory(cache_dir=None):
    """Where the answers are kept."""
    return os.path.join(cache_dir or paths.cache_dir(), NAMESPACE)


def key(text, model, quant, stage, answer_tokens=0, language="it"):
    """The name one answer is filed under.

    Everything that could change the answer goes in: the material, the model
    and its precision, which stage asked, how much it was allowed to say, the
    language it was asked in, and the version of the prompts themselves."""
    digest = hashlib.sha256()
    for part in (str(prompting.PROMPT_VERSION), str(model), str(quant),
                 str(stage), str(answer_tokens), str(language), text or ""):
        digest.update(part.encode("utf-8", "replace"))
        digest.update(b"\x00")
    return digest.hexdigest()


def _path(name, cache_dir=None):
    """Two levels, so a directory listing stays usable after a few thousand."""
    return os.path.join(directory(cache_dir), name[:2], name[2:] + ".txt")


def get(name, cache_dir=None):
    """The answer filed under ``name``, or None."""
    try:
        with open(_path(name, cache_dir), encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return None


def put(name, answer, cache_dir=None):
    """File an answer, and say whether it could be filed.

    Written beside and renamed, so a process killed mid-write leaves no
    half-answer to be read back as a whole one."""
    target = _path(name, cache_dir)
    try:
        paths.ensure(os.path.dirname(target))
        partial = target + ".part"
        with open(partial, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(answer or "")
        os.replace(partial, target)
        return True
    except OSError:
        return False


def sweep(cache_dir=None, days=KEEP_DAYS):
    """Drop answers nobody has come back for, and return how many.

    Called when the cache is written to rather than on a timer: this program
    has no daemon, and a cache that only grows is a cache that eventually
    fills the disk of the small machine it was meant to help."""
    import time

    cutoff = time.time() - days * 86400
    removed = 0
    for root, _, names in os.walk(directory(cache_dir)):
        for name in names:
            path = os.path.join(root, name)
            try:
                if os.path.getmtime(path) < cutoff:
                    os.remove(path)
                    removed += 1
            except OSError:
                continue
    return removed
