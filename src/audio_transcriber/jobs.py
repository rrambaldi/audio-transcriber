"""A queue of transcription jobs, run one at a time in a worker thread.

On the machines this tool targets a transcription is measured in hours, not
seconds: the browser cannot wait for it inside a request. Uploading therefore
only creates a job, and the page polls it.

Jobs run strictly one after another. A two-core server transcribing two files
at once finishes neither any sooner and risks running out of memory, so the
queue is deliberately a queue and not a pool.

State lives in memory: restarting the server forgets the queue, while every
finished transcription is already safe in the library.
"""
import os
import queue
import re
import threading
import traceback
import uuid
from datetime import datetime

from . import paths, pipeline
from .config import read_prompt
from .library import STORE_MODES, STORE_MOVE, Library

QUEUED = "queued"
RUNNING = "running"
DONE = "done"
FAILED = "failed"

#: Refuse an upload larger than this (2 GiB); a long meeting is far smaller.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024

#: Keep at most this many finished jobs in the list shown by the page.
MAX_HISTORY = 50


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def safe_filename(name, fallback="recording"):
    """A file name that is only a file name: no directories, no surprises."""
    name = os.path.basename(str(name or "")).strip().replace("\x00", "")
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(". ")
    return name[:120] or fallback


class Job:
    """One queued transcription and everything the page needs to show it."""

    def __init__(self, source, title=None, filename=None, settings=None,
                 prompt="", vocabularies=None, store=STORE_MOVE):
        self.id = uuid.uuid4().hex[:12]
        self.source = source
        self.filename = filename or os.path.basename(source)
        self.title = title or os.path.splitext(self.filename)[0]
        self.settings = settings or {}
        self.prompt = prompt
        self.vocabularies = list(vocabularies or [])
        self.store = store
        self.status = QUEUED
        self.progress = 0
        self.error = None
        self.entry_id = None
        self.words = None
        self.created_at = now()
        self.started_at = None
        self.finished_at = None
        self.elapsed = None
        self.audio_duration = None

    def as_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "filename": self.filename,
            "status": self.status,
            "progress": self.progress,
            "error": self.error,
            "entry_id": self.entry_id,
            "words": self.words,
            "model": self.settings.get("model"),
            "language": self.settings.get("language") or "auto",
            "diarize": bool(self.settings.get("diarize")),
            "vocabularies": self.vocabularies,
            "prompt_chars": len(self.prompt),
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_seconds": self.elapsed,
            "audio_duration": self.audio_duration,
        }


class JobQueue:
    """Accepts jobs, runs them one at a time, remembers what happened."""

    def __init__(self, settings, library=None, runner=None):
        self.settings = dict(settings or {})
        self.library = library or Library(self.settings.get("library_dir"))
        self._runner = runner or self._transcribe
        self._pending = queue.Queue()
        self._jobs = {}
        self._order = []
        self._lock = threading.Lock()
        self._worker = None

    # --- public API -------------------------------------------------------

    def upload_dir(self):
        """Where an upload waits until its job runs.

        A recording can be gigabytes, so this follows the configured cache
        directory: on a server the volume with the room is rarely the one the
        home directory sits on."""
        root = self.settings.get("cache_dir") or paths.cache_dir()
        return paths.ensure(os.path.join(os.path.expanduser(root), "uploads"))

    def submit(self, source, title=None, filename=None, overrides=None,
               vocabularies=None, custom_vocabulary="", store=STORE_MOVE):
        """Queue one file and return its :class:`Job`.

        ``store`` says what becomes of the file once it is transcribed. An
        upload or a recording this program made is *moved* into the library
        entry, because nobody wants a second copy of two gigabytes; a file the
        user picked from their own disk is *copied*, because moving someone's
        recording out of their Documents folder is not this program's
        decision to make."""
        if store not in STORE_MODES:
            raise ValueError(f"unknown store mode: {store}")
        settings = dict(self.settings)
        settings.update({k: v for k, v in (overrides or {}).items() if v is not None})
        names = list(vocabularies or [])
        settings["vocabulary"] = names

        prompt = build_prompt(settings, names, custom_vocabulary)
        job = Job(source, title=title, filename=filename, settings=settings,
                  prompt=prompt, vocabularies=names, store=store)
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
            self._forget_old()
        self._pending.put(job.id)
        self._ensure_worker()
        return job

    def get(self, job_id):
        with self._lock:
            return self._jobs.get(job_id)

    def jobs(self):
        """Newest first, which is the order the page displays them in."""
        with self._lock:
            return [self._jobs[i] for i in reversed(self._order) if i in self._jobs]

    def pending_count(self):
        """Jobs queued or running: what closing the program would throw away.

        The desktop interface asks before quitting, because there the queue
        lives in the window's own process."""
        with self._lock:
            return sum(1 for job in self._jobs.values()
                       if job.status in (QUEUED, RUNNING))

    def remove(self, job_id):
        """Forget a finished job. A running one is left alone."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in (QUEUED, RUNNING):
                return False
            del self._jobs[job_id]
            self._order.remove(job_id)
            return True

    # --- internals --------------------------------------------------------

    def _forget_old(self):
        """Drop the oldest finished jobs once the list grows too long."""
        finished = [i for i in self._order
                    if self._jobs[i].status in (DONE, FAILED)]
        for job_id in finished[:max(0, len(self._order) - MAX_HISTORY)]:
            del self._jobs[job_id]
            self._order.remove(job_id)

    def _ensure_worker(self):
        with self._lock:
            if self._worker and self._worker.is_alive():
                return
            self._worker = threading.Thread(target=self._work, name="transcriber",
                                            daemon=True)
            self._worker.start()

    def _work(self):
        while True:
            try:
                job_id = self._pending.get(timeout=60)
            except queue.Empty:
                return          # nothing to do; a new job starts a new worker
            job = self.get(job_id)
            if job is None:
                continue
            self._run(job)

    def _run(self, job):
        """Run one job and record what happened, whatever happened.

        ``SystemExit`` is caught alongside the ordinary exceptions on purpose:
        the modules underneath were written for a command line and report a
        missing model or an undecodable file with ``sys.exit(message)``. In a
        worker thread that would kill the thread and leave the job stuck at
        "running" forever, so it is treated as what it is — a failure with a
        good error message."""
        job.status = RUNNING
        job.started_at = now()
        outcome, error = DONE, None
        try:
            self._runner(job)
            job.progress = 100
        except (Exception, SystemExit) as exc:       # noqa: BLE001 - reported, not raised
            outcome, error = FAILED, str(exc) or exc.__class__.__name__
            if not isinstance(exc, SystemExit):
                traceback.print_exc()
            self._discard_upload(job)
        job.error = error
        job.finished_at = now()
        # Last, so that a page which sees the final status also sees everything
        # that goes with it.
        job.status = outcome

    def _discard_upload(self, job):
        """Delete the copy we made of a failed job's file.

        Only inside the upload directory: a job submitted with a path of its
        own owns that file, and a two-gigabyte upload nobody can use should not
        sit on the disk until the next reboot."""
        source = os.path.abspath(job.source)
        if not source.startswith(os.path.abspath(self.upload_dir()) + os.sep):
            return
        try:
            os.unlink(source)
        except OSError:
            pass

    def _transcribe(self, job):
        """The real work: what the CLI does, minus the printing."""
        result = pipeline.run(job.source, job.settings, prompt=job.prompt,
                              progress=lambda percent: setattr(job, "progress", percent))
        entry = pipeline.file_in_library(self.library, job.source, result,
                                         job.settings, title=job.title,
                                         store=job.store)
        job.entry_id = entry.id
        job.words = len(result.text.split())
        job.elapsed = round(result.elapsed, 1)
        job.audio_duration = round(result.audio_duration, 1)


def build_prompt(settings, names, custom=""):
    """Configured prompt, then the selected sets, then the browser's own text.

    The custom part comes from the visitor's browser, where their private sets
    live, so it is parsed like any vocabulary file and simply appended."""
    from .vocabularies import parse

    configured = read_prompt(settings.get("prompt"), settings.get("prompt_file"),
                             names, settings.get("vocab_dir"))
    return " ".join(part for part in (configured, parse(custom)) if part)
