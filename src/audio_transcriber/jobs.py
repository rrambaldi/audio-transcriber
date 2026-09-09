"""A queue of long jobs — transcriptions and summaries — run one at a time.

On the machines this tool targets a transcription is measured in hours, not
seconds: the browser cannot wait for it inside a request. Uploading therefore
only creates a job, and the page polls it.

Jobs run strictly one after another. A two-core server transcribing two files
at once finishes neither any sooner and risks running out of memory, so the
queue is deliberately a queue and not a pool.

Summaries share the queue rather than having one of their own, and that is the
point: a summary written by a local model is minutes of the same two cores a
transcription needs, and running both at once would make each slower without
finishing either sooner. One queue means the machine is never asked to do two
heavy things at the same time.

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
from .config import read_prompt, resolve_output
from .library import STORE_MODES, STORE_MOVE, Library

#: What a job is. Both kinds go through the same queue, the same statuses and
#: the same row on the page; what differs is what the worker calls and what
#: the job leaves behind.
TRANSCRIPTION = "transcription"
SUMMARY = "summary"

#: In the list, but deliberately not started: the desktop window fills the
#: queue first and runs it when told to, so the options can still be changed
#: after the files have been chosen.
HELD = "held"
QUEUED = "queued"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
CANCELLED = "cancelled"

#: Statuses that will not change again.
FINISHED = (DONE, FAILED, CANCELLED)

#: Statuses of a job that has not begun, and can therefore simply be dropped.
NOT_STARTED = (HELD, QUEUED)

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


class Cancelled(Exception):
    """Raised inside a running transcription that has been asked to stop.

    It travels out through the progress callback, which is the only place the
    engines hand control back often enough to notice."""


class Job:
    """One queued piece of work and everything the page needs to show it."""

    def __init__(self, source=None, title=None, filename=None, settings=None,
                 prompt="", vocabularies=None, store=STORE_MOVE,
                 kind=TRANSCRIPTION, entry_id=None):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.source = source
        self.filename = filename or (os.path.basename(source) if source else "")
        self.title = title or os.path.splitext(self.filename)[0]
        self.settings = settings or {}
        self.prompt = prompt
        self.vocabularies = list(vocabularies or [])
        self.store = store
        self.status = QUEUED
        self.progress = 0
        #: Message key of the stage the run is in, for the status column. A
        #: percentage alone stands still for the whole of a long
        #: transcription on an engine that cannot report its own progress.
        self.stage = None
        #: Set by :meth:`JobQueue.cancel`; read by the progress callback.
        self.cancel_requested = False
        self.error = None
        #: The library entry this job produced — or, for a summary, the one it
        #: was asked to summarise, which is known before it starts.
        self.entry_id = entry_id
        self.words = None
        self.created_at = now()
        self.started_at = None
        self.finished_at = None
        self.elapsed = None
        self.audio_duration = None

    def as_dict(self):
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "filename": self.filename,
            "status": self.status,
            "progress": self.progress,
            "stage": self.stage,
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

    def __init__(self, settings, library=None, runner=None, summariser=None):
        self.settings = dict(settings or {})
        self.library = library or Library(self.settings.get("library_dir"))
        self._runner = runner or self._transcribe
        self._summariser = summariser or self._summarize
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
               vocabularies=None, custom_vocabulary="", store=STORE_MOVE,
               start=True):
        """Queue one file and return its :class:`Job`.

        ``start=False`` puts it in the list without running it: the desktop
        window collects the files first and starts the queue when the person
        at it says so, which is what lets the options still be changed once
        the files are in. The web interface uploads and starts in one motion,
        so it takes the default.

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
        # An interface sends the output it was asked for; this is where that
        # choice becomes the flags the pipeline reads, exactly as it does for
        # the command line.
        settings = resolve_output(settings)
        names = list(vocabularies or [])
        settings["vocabulary"] = names

        prompt = build_prompt(settings, names, custom_vocabulary)
        job = Job(source, title=title, filename=filename, settings=settings,
                  prompt=prompt, vocabularies=names, store=store)
        if not start:
            job.status = HELD
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
            self._forget_old()
        if start:
            self._pending.put(job.id)
            self._ensure_worker()
        return job

    def summarize(self, entry_id, overrides=None, start=True):
        """Queue the summary of a library entry and return its :class:`Job`.

        It joins the same queue the transcriptions are in, behind whatever is
        already there. On the machine this was written for that is not a
        limitation but the reason the queue exists: a model reading an hour of
        transcript and a model transcribing an hour of audio are the same two
        cores, and asking for both at once serves neither.

        The entry has to exist now rather than when the job runs, so that a
        typo comes back as an error to the person who made it instead of as a
        failed job ten minutes later."""
        entry = self.library.get(entry_id)
        settings = dict(self.settings)
        settings.update({k: v for k, v in (overrides or {}).items() if v is not None})
        job = Job(kind=SUMMARY, entry_id=entry.id, settings=settings,
                  title=entry.metadata.get("title") or entry.id,
                  filename=entry.id)
        if not start:
            job.status = HELD
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
            self._forget_old()
        if start:
            self._pending.put(job.id)
            self._ensure_worker()
        return job

    def start(self, job_id=None):
        """Run what has been held back, and say how many were started.

        With no argument, everything, in the order it was added: a queue that
        reshuffled itself would be one more thing to explain. With one, only
        that recording — the desktop window starts them one at a time, from a
        button on the row, because each one is asked what it is for first."""
        with self._lock:
            if job_id is not None:
                job = self._jobs.get(job_id)
                held = [job_id] if job is not None and job.status == HELD else []
            else:
                held = [known for known in self._order
                        if self._jobs[known].status == HELD]
            for known in held:
                self._jobs[known].status = QUEUED
        for known in held:
            self._pending.put(known)
        if held:
            self._ensure_worker()
        return len(held)

    def retry(self, job_id):
        """Put a failed or cancelled recording back in the waiting list.

        Nothing was filed for either, and the recording is still where it
        was, so there is nothing to undo: the row goes back to "not started"
        and can be asked again what it is for."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status not in (FAILED, CANCELLED):
                return False
            job.status = HELD
            job.progress = 0
            job.stage = None
            job.error = None
            job.cancel_requested = False
            job.started_at = job.finished_at = None
        return True

    def reconfigure(self, job_id, overrides=None, vocabularies=None,
                    custom_vocabulary=""):
        """Change the settings of a recording that has not started yet.

        The window asks what a recording is for at the moment it is started,
        not when the file was dropped in, so the answers arrive after the job
        exists. Only a held job can be changed: once it is queued the worker
        may pick it up at any moment, and settings that change under a
        running transcription are worse than settings that cannot change."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != HELD:
                return False
        settings = dict(self.settings)
        settings.update({k: v for k, v in (overrides or {}).items()
                         if v is not None})
        settings = resolve_output(settings)
        names = list(vocabularies or [])
        settings["vocabulary"] = names
        with self._lock:
            job.settings = settings
            job.vocabularies = names
            job.prompt = build_prompt(settings, names, custom_vocabulary)
        return True

    def held_count(self):
        """How many jobs are waiting to be started."""
        with self._lock:
            return sum(1 for job in self._jobs.values() if job.status == HELD)

    def get(self, job_id):
        with self._lock:
            return self._jobs.get(job_id)

    def jobs(self):
        """Newest first, which is the order the page displays them in."""
        with self._lock:
            return [self._jobs[i] for i in reversed(self._order) if i in self._jobs]

    def cancel(self, job_id):
        """Take a job out of the queue, or ask a running one to stop.

        A job that has not started is dropped there and then. A running one can only be
        asked: the engines are a blocking call, and the one place they hand
        control back is the progress callback, so the transcription stops at
        its next segment. With an engine that reports no progress at all — the
        OpenVINO backend does not — it will run to the end, and what it
        produces is discarded rather than filed. Either way nothing reaches
        the library."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in FINISHED:
                return False
            job.cancel_requested = True
            if job.status in NOT_STARTED:
                # Nothing has happened to it, so it leaves no trace: the row
                # goes. "Cancelled" is for a transcription that really was
                # under way, where the time spent is worth seeing. If it had
                # already been handed to the worker, the worker skips an id it
                # can no longer find.
                del self._jobs[job_id]
                self._order.remove(job_id)
            return True

    def pending_count(self):
        """Jobs queued or running: what closing the program would throw away.

        The desktop interface asks before quitting, because there the queue
        lives in the window's own process."""
        with self._lock:
            return sum(1 for job in self._jobs.values()
                       if job.status in (HELD, QUEUED, RUNNING))

    def remove(self, job_id):
        """Forget a finished job. A queued or running one is left alone -
        :meth:`cancel` is what stops those."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status not in FINISHED:
                return False
            del self._jobs[job_id]
            self._order.remove(job_id)
            return True

    # --- internals --------------------------------------------------------

    def _forget_old(self):
        """Drop the oldest finished jobs once the list grows too long."""
        finished = [i for i in self._order
                    if self._jobs[i].status in FINISHED]
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
            if job.cancel_requested:
                # Cancelled while it waited its turn. cancel() has normally
                # said so already; this keeps the promise even when the flag
                # arrived another way, instead of leaving a job that will
                # never run sitting there as "queued".
                if job.status in NOT_STARTED:
                    job.status = CANCELLED
                    job.finished_at = now()
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
            (self._summariser if job.kind == SUMMARY else self._runner)(job)
            job.progress = 100
        except Cancelled:
            # Asked for, so not a failure. The source file is deliberately
            # left where it is: a recording nobody has transcribed yet may be
            # the only copy of that meeting.
            outcome, error = CANCELLED, None
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
        if not job.source:
            return
        source = os.path.abspath(job.source)
        if not source.startswith(os.path.abspath(self.upload_dir()) + os.sep):
            return
        try:
            os.unlink(source)
        except OSError:
            pass

    def _transcribe(self, job):
        """The real work: what the CLI does, minus the printing."""
        result = pipeline.run(
            job.source, job.settings, prompt=job.prompt,
            progress=lambda percent, stage=None: self._advance(job, percent, stage))
        entry = pipeline.file_in_library(self.library, job.source, result,
                                         job.settings, title=job.title,
                                         store=job.store)
        job.entry_id = entry.id
        job.words = len(result.text.split())
        job.elapsed = round(result.elapsed, 1)
        job.audio_duration = round(result.audio_duration, 1)


    def _summarize(self, job):
        """Summarise an entry that is already in the library, in place.

        The summary is written into the entry rather than handed back: a job
        finishes and the page it belongs to shows the result, exactly as a
        transcription does. Losing the queue on a restart therefore loses
        nothing that mattered."""
        from . import summary as summarising

        entry = self.library.get(job.entry_id)
        material = summarising.material_from_entry(entry)
        result = summarising.summarize(
            material, job.settings,
            progress=lambda percent, stage=None: self._advance(job, percent, stage))
        entry.write_summary(result.text)
        entry.update(summary={
            "engine": result.engine,
            "length": job.settings.get("summary_length") or summarising.DEFAULT_LENGTH,
            "sentences_kept": result.kept,
            "sentences_total": result.of,
            "created_at": now(),
        })
        job.words = len(result.text.split())
        job.elapsed = round(result.elapsed, 1)

    @staticmethod
    def _advance(job, percent, stage=None):
        """Record progress, and stop here if the job has been cancelled.

        The engines run inside one long blocking call; this callback is the
        only moment they give control back, so it is also the only place a
        cancellation can take effect."""
        job.progress = percent
        if stage:
            job.stage = stage
        if job.cancel_requested:
            raise Cancelled(job.id)


def build_prompt(settings, names, custom=""):
    """Configured prompt, then the selected sets, then the browser's own text.

    The custom part comes from the visitor's browser, where their private sets
    live, so it is parsed like any vocabulary file and simply appended."""
    from .vocabularies import parse

    configured = read_prompt(settings.get("prompt"), settings.get("prompt_file"),
                             names, settings.get("vocab_dir"))
    return " ".join(part for part in (configured, parse(custom)) if part)
