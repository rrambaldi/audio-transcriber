"""Where the program's messages go when nobody is watching a terminal.

A command line is watched: what it prints is the interface, and this module
leaves it alone. The window and the server are not. They print the same
things — which model was chosen, how far a job has got, what pyannote thought
of a recording, and the traceback when something falls over — into whatever
terminal they happened to be started from, which is a terminal the person
using them has usually closed. On Windows, started from a shortcut, there is
no terminal at all and the messages go nowhere.

So :func:`start` puts them in a file instead, and the window and the page both
have somewhere to show it.

Three things are worth knowing about how it is done.

**It is a redirection, not a logging framework.** ``sys.stdout`` and
``sys.stderr`` are replaced by a writer that goes to the file, and everything
follows from that: this program's own ``print``, ``logging``'s last-resort
handler, uvicorn's access lines, and whatever torch decides to say about a
tensor. Converting eighty ``print`` calls to a logger would have caught the
first of those and none of the rest, and the rest is where the mysteries are.

**Each line is stamped, and the writes are not lines.** ``print`` writes the
text and the newline separately, so the stamp is applied by holding a partial
line until its newline arrives rather than by stamping every write.

**It rolls over.** A server left running for a month must not fill a disk, so
the file is capped and exactly one older copy is kept beside it. A log that
deleted itself at a size would lose the hour before a crash, which is the hour
worth having; a log that kept everything would eventually be the reason for
the next crash.
"""
import datetime
import io
import os
import sys
import threading

from . import paths

#: How large the log may get before it is rolled over, in bytes.
MAX_BYTES = 2 * 1024 * 1024

#: How many rolled-over copies are kept beside it. One: the point is the hour
#: before a crash, not the history of the installation.
KEEP = 1

#: Set this to anything non-empty to keep the terminal copy in the window and
#: the server — for somebody debugging, who has a terminal and is watching it.
ENV_CONSOLE = "AUDIO_TRANSCRIBER_LOG_CONSOLE"

#: How many lines a viewer asks for when it does not say.
TAIL_LINES = 300

#: How much of the file is read to find those lines. A tail does not need the
#: whole log, and the whole log may be two megabytes.
TAIL_BYTES = 256 * 1024

#: The stamp in front of every line. Local time, seconds, no date on the line
#: itself — the date is on the first line of the session.
STAMP = "%H:%M:%S"

#: Written when a process starts, so a log with three days in it can be read
#: as three days rather than as one long run.
SESSION = "=== {when} — audio-transcriber {version} ({what}) ==="


class _Sink:
    """The log file itself: one per process, written to under a lock.

    Two things end up here at once — both standard streams, and the queue's
    worker thread alongside the one drawing the window — and a lock around
    the file is not enough to keep them apart. ``print`` writes the text and
    the newline as two calls, so a lock held for the length of one call still
    lets a second thread write between them, and the two half-lines are then
    flushed as one line that neither thread wrote. So the partial line is
    held *per thread* and only finished lines reach the file, where the lock
    does the rest."""

    def __init__(self, path, max_bytes=None, keep=None):
        self.path = path
        # Read now rather than bound as a default, so that a caller - or a
        # test - that changes the module's mind is obeyed.
        self.max_bytes = MAX_BYTES if max_bytes is None else max_bytes
        self.keep = KEEP if keep is None else keep
        self.lock = threading.Lock()
        self.pending = {}
        paths.ensure(os.path.dirname(path))
        # Held open for the life of the process, which is what a log is: a
        # context manager here would mean opening and closing the file for
        # every line a chatty library decides to write.
        self.handle = open(path, "a", encoding="utf-8",  # noqa: SIM115
                           errors="replace")

    def write(self, text):
        """Add ``text`` to this thread's line, writing out what it finishes."""
        who = threading.get_ident()
        held = self.pending.get(who, "") + text
        if "\n" not in held:
            self.pending[who] = held
            return
        finished, _, rest = held.rpartition("\n")
        if rest:
            self.pending[who] = rest
        else:
            self.pending.pop(who, None)
        self._put(finished.split("\n"))

    def flush(self):
        """Write out the lines that never got their newline, and go to disk.

        Called when the process is on its way down, which is exactly when an
        unfinished line matters: a crash mid-sentence is still a sentence."""
        leftover = [line for line in self.pending.values() if line]
        self.pending = {}
        self._put(leftover)
        with self.lock:
            self.handle.flush()

    def _put(self, lines):
        """Stamp and write finished lines, and roll the file over if it is due."""
        if not lines:
            return
        stamp = datetime.datetime.now().strftime(STAMP)
        with self.lock:
            for line in lines:
                self.handle.write(f"{stamp}  {line}\n")
            self.handle.flush()
            self._roll_over_if_full()

    def _roll_over_if_full(self):
        """Move the file aside once it is too big, and start another."""
        if self.handle.tell() < self.max_bytes:
            return
        self.handle.close()
        try:
            for index in range(self.keep, 0, -1):
                older = f"{self.path}.{index}"
                newer = f"{self.path}.{index - 1}" if index > 1 else self.path
                if os.path.exists(older):
                    os.remove(older)
                if os.path.exists(newer):
                    os.replace(newer, older)
        except OSError:             # pragma: no cover - a locked or gone file
            pass
        self.handle = open(self.path, "a", encoding="utf-8",  # noqa: SIM115
                           errors="replace")


class _Tee(io.TextIOBase):
    """A stream that writes to the log, and to the terminal while there is one.

    A stand-in for ``sys.stdout``: anything asking it whether it is a terminal
    is asking in order to decide about colour or buffering, and the honest
    answer once this is installed is no."""

    def __init__(self, console, sink):
        self.console = console
        self.sink = sink

    def write(self, text):
        if not isinstance(text, str):   # pragma: no cover - bytes to a text stream
            text = str(text)
        self.sink.write(text)
        if self.console is not None:
            try:
                self.console.write(text)
            except (OSError, ValueError):    # pragma: no cover - closed console
                self.console = None
        return len(text)

    def flush(self):
        self.sink.flush()
        if self.console is not None:
            try:
                self.console.flush()
            except (OSError, ValueError):    # pragma: no cover - closed console
                self.console = None

    def isatty(self):
        return False

    def writable(self):
        return True

    @property
    def encoding(self):
        return getattr(self.console, "encoding", None) or "utf-8"


#: The sink in use, once :func:`start` has been called. One per process.
_sink = None

#: What was in ``sys.stdout`` and ``sys.stderr`` before, so :func:`stop` can
#: put them back — which is what the tests need and what nothing else does.
_replaced = None


def path():
    """Where the log is, whether or not anything has been written to it."""
    return paths.log_file()


def start(what="", console=None):
    """Send everything this process prints to the log file.

    ``what`` names the front end for the session line. ``console`` decides
    whether the terminal keeps its copy; by default it does not, because the
    callers are the window and the server and neither has a terminal anybody
    is reading — :data:`ENV_CONSOLE` is how somebody debugging asks for it
    back. Calling it twice is calling it once: a window that opens a second
    window has not started a second process.

    Returns the path of the log, and never raises: a program that would not
    start because it could not open its own log file would be a program made
    worse by having one."""
    global _sink, _replaced
    if _sink is not None:
        return _sink.path
    if console is None:
        console = bool((os.environ.get(ENV_CONSOLE) or "").strip())
    try:
        _sink = _Sink(path())
    except OSError:                 # pragma: no cover - unwritable data dir
        return path()
    _replaced = (sys.stdout, sys.stderr)
    sys.stdout = _Tee(sys.stdout if console else None, _sink)
    sys.stderr = _Tee(sys.stderr if console else None, _sink)
    _sink.write(SESSION.format(when=datetime.datetime.now().isoformat(
        timespec="seconds"), version=_version(), what=what or "?") + "\n")
    return _sink.path


def stop():
    """Put the streams back and close the file. For the tests, and for exit."""
    global _sink, _replaced
    if _sink is None:
        return
    _sink.flush()
    if _replaced is not None:
        sys.stdout, sys.stderr = _replaced
    try:
        _sink.handle.close()
    except OSError:                 # pragma: no cover - already gone
        pass
    _sink, _replaced = None, None


def started():
    """Whether this process is writing to the log."""
    return _sink is not None


def size():
    """How large the log is now, or zero when there is none yet."""
    try:
        return os.path.getsize(path())
    except OSError:
        return 0


def tail(lines=TAIL_LINES):
    """The last ``lines`` lines, oldest first, as a list of strings.

    Read from the end of the file rather than through it: a viewer refreshing
    every few seconds must not read two megabytes to show thirty lines. The
    first line of the window may be half a line, and is dropped for that
    reason unless it is all there is."""
    if _sink is not None:
        _sink.flush()
    try:
        with open(path(), "rb") as handle:
            handle.seek(0, os.SEEK_END)
            end = handle.tell()
            start_at = max(0, end - TAIL_BYTES)
            handle.seek(start_at)
            block = handle.read()
    except OSError:
        return []
    text = block.decode("utf-8", errors="replace")
    found = text.splitlines()
    if start_at and len(found) > 1:
        found = found[1:]
    return found[-lines:] if lines else found


def clear():
    """Empty the log, keeping the file itself. Answers whether it worked.

    Through the open handle when this process is the one writing, because
    truncating a file another handle is appending to leaves that handle
    writing past the end; through the path otherwise, which is the window
    looking at a log the server is keeping."""
    if _sink is not None and _sink.path == path():
        with _sink.lock:
            try:
                _sink.handle.truncate(0)
                _sink.handle.seek(0)
                _sink.handle.flush()
            except OSError:         # pragma: no cover - a file pulled away
                return False
        return True
    try:
        with open(path(), "w", encoding="utf-8"):
            pass
    except OSError:
        return False
    return True


def _version():
    """The program's version, without importing the package for it twice."""
    from . import __version__
    return __version__
