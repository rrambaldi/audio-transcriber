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


def settings_key(settings=None, chosen=None):
    """What shapes an answer without appearing in the question.

    Most of what could be listed here does not belong here, and the reason is
    worth writing down once. The key is taken over the *whole prompt*, so
    anything that changes the prompt already changes the key: a different
    chunk length cuts different text, a different set of categories writes
    different instructions, a longer overlap moves the seams. None of those
    need naming twice.

    What is left is the handful of things that leave the question identical
    and the answer different. The context window is the one there is today: a
    model asked the same thing with four thousand tokens of room and with
    eight does not answer the same way, and nothing in the prompt says which
    it had.

    Deliberately absent: the length and the style. A reading pass does not
    depend on either — only the page written at the end does — and asking
    again at a different length re-using every pass is the point of this
    cache on a machine where one pass is minutes. There is a test that says
    so."""
    settings = settings or {}
    fields = {
        "context": (settings.get("summary_context_tokens")
                    or getattr(chosen, "context_tokens", None)),
    }
    return ",".join(f"{name}={'' if value is None else value}"
                    for name, value in sorted(fields.items()))


def key(text, model, quant, stage, answer_tokens=0, language="it",
        settings_fingerprint=""):
    """The name one answer is filed under.

    Everything that could change the answer goes in: the material, the model
    and its precision, which stage asked, how much it was allowed to say, the
    language it was asked in, the version of the prompts themselves, and the
    settings that decided the shape of the request.

    That last one was missing, and it is not a small omission: two runs over
    the same recording with different settings handed each other their
    partials, so a run that had gone wrong came back out of the cache looking
    like a fresh one and no comparison between two attempts meant anything.
    Any diagnosis of what a change did has to start from a key that tells the
    two apart."""
    digest = hashlib.sha256()
    for part in (str(prompting.PROMPT_VERSION), str(model), str(quant),
                 str(stage), str(answer_tokens), str(language),
                 str(settings_fingerprint), text or ""):
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


def clear(cache_dir=None):
    """Throw the whole cache away, and say how many answers went.

    It belongs here and not in whoever asks, because the layout is here: the
    files are filed two levels deep, and a caller that lists the top of the
    directory finds two-character folders, fails to unlink them, and reports
    that it cleared nothing while every answer is still there. That is exactly
    what happened the first time a diagnosis was run against a stale cache."""
    root = directory(cache_dir)
    gone = 0
    for here, _folders, files in os.walk(root):
        for name in files:
            try:
                os.unlink(os.path.join(here, name))
                gone += 1
            except OSError:
                pass
    return gone


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
