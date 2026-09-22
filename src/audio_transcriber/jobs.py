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

Measuring what a recording *looks* like is the one thing that does not wait
its turn, and has a thread of its own. It is ffmpeg reading a file through
once — seconds, where the jobs beside it are hours — and its whole purpose is
to put a drawing on a row while that row is still worth looking at. Behind the
queue it would arrive after the transcription it describes.

The queue outlives the process. A transcription is hours and a machine is
restarted — a service updated, a window closed by mistake, a laptop that ran
out of battery — so the list is written down beside the uploads after every
change and read back at startup: what was waiting is still waiting, with the
title and the options it was given, and what was running when the lights went
out goes back in the queue. Only twice, though: a job that takes the process
down with it, which on a small machine means an out-of-memory kill, would
otherwise be started again by every restart for ever.
"""
import json
import os
import queue
import re
import sys
import threading
import traceback
import uuid
from datetime import datetime

from . import audio, paths, pipeline, waveform
from .config import read_prompt, resolve_output
from .i18n import t
from .library import STORE_MODES, STORE_MOVE, Library, LibraryError

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

#: Where the queue is written down, next to the uploads it points at.
STATE_FILENAME = "queue.json"

#: How many times a restart may put a job back in the queue. A recording that
#: takes the process down with it — an out-of-memory kill on a small server —
#: would otherwise be picked up again by every restart, for ever.
MAX_RESTARTS = 2


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def file_facts(path):
    """``(size in bytes, when it was made)`` for a recording, or ``(None, None)``.

    Taken when the job is made, because the file does not stay put: a finished
    transcription moves its upload into the library entry, and a queue read
    back after a restart would have nothing left to ask.

    "When it was made" is as close as each platform gets. Windows records a
    creation time and Python reports it as ``st_ctime``; macOS and the BSDs
    have ``st_birthtime``; Linux has neither — its ``st_ctime`` is when the
    inode last changed, which copying resets — so there the modification time
    is the honest answer, and for a recording it is the moment the recorder
    stopped writing."""
    try:
        stats = os.stat(path)
    except (OSError, TypeError, ValueError):
        return None, None
    made = getattr(stats, "st_birthtime", None)
    if made is None:
        made = stats.st_ctime if sys.platform == "win32" else stats.st_mtime
    when = datetime.fromtimestamp(made).astimezone().isoformat(timespec="seconds")
    return stats.st_size, when


def entry_facts(entry):
    """``(how long, how big, when it was made)`` for a recording already filed.

    What :func:`file_facts` reads off the disk, read instead out of the
    metadata of a library entry. A summary has no file of its own, but the
    thing it is a summary *of* is a recording with a length, a size and a
    date, and those are what tell one row of the queue from another.
    """
    try:
        data = entry.metadata
    except (LibraryError, OSError, ValueError):
        return None, None, None
    return ((data.get("audio") or {}).get("duration_seconds"),
            (data.get("source") or {}).get("bytes"),
            data.get("created_at"))


def safe_filename(name, fallback="recording"):
    """A file name that is only a file name: no directories, no surprises."""
    name = os.path.basename(str(name or "")).strip().replace("\x00", "")
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(". ")
    return name[:120] or fallback


#: Raised inside a running job that has been asked to stop; defined next to
#: the pipeline, which has to let it through where it catches everything else.
Cancelled = pipeline.Cancelled


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
        #: How loud the recording is, slice by slice, for the drawing under
        #: the name. Measured in the background and deliberately *not* written
        #: down with the rest: four hundred numbers a job, rewritten on every
        #: change, would swamp a state file that is meant to be readable, and
        #: measuring one again after a restart costs a single pass of ffmpeg.
        self.loudness = None
        #: The recording as the disk describes it: how big, and when it was
        #: made. Read now, while the file is still where it was handed over.
        self.size_bytes, self.source_created_at = file_facts(source)
        #: How many restarts have found this job running. See MAX_RESTARTS.
        self.restarts = 0

    #: What a restart has to bring back: everything needed to run the job, and
    #: everything the list already showed about it. Deliberately not the
    #: progress or the stage, which belong to a run that is over.
    STATE_FIELDS = ("id", "kind", "source", "filename", "title", "settings",
                    "prompt", "vocabularies", "store", "status", "entry_id",
                    "words", "error", "created_at", "started_at", "finished_at",
                    "elapsed", "audio_duration", "restarts",
                    "size_bytes", "source_created_at")

    def to_state(self):
        return {name: getattr(self, name) for name in self.STATE_FIELDS}

    @classmethod
    def from_state(cls, state):
        """The job a previous run wrote down, or None if it makes no sense."""
        if not isinstance(state, dict) or not state.get("id"):
            return None
        job = cls(source=state.get("source"), title=state.get("title"),
                  filename=state.get("filename"),
                  settings=state.get("settings") or {},
                  prompt=state.get("prompt") or "",
                  vocabularies=state.get("vocabularies"),
                  store=state.get("store") or STORE_MOVE,
                  kind=state.get("kind") or TRANSCRIPTION,
                  entry_id=state.get("entry_id"))
        for name in ("id", "status", "words", "error", "created_at",
                     "started_at", "finished_at", "elapsed", "audio_duration",
                     "size_bytes", "source_created_at"):
            if state.get(name) is not None:
                setattr(job, name, state[name])
        job.restarts = int(state.get("restarts") or 0)
        if job.status in FINISHED:
            job.progress = 100 if job.status == DONE else job.progress
        return job

    @property
    def running_seconds(self):
        """How long this job has been running, or None if it is not.

        A row has to prove it is alive even when nothing else moves: an
        engine that reports no progress, or a diarization step that takes
        twenty minutes, leaves the bar exactly where it was, and a clock that
        goes up is the difference between waiting and wondering."""
        if self.status != RUNNING or not self.started_at:
            return None
        try:
            started = datetime.fromisoformat(self.started_at)
        except ValueError:
            return None
        return max(0.0, (datetime.now().astimezone() - started).total_seconds())

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
            "running_seconds": self.running_seconds,
            "audio_duration": self.audio_duration,
            "loudness": self.loudness,
            "size_bytes": self.size_bytes,
            "source_created_at": self.source_created_at,
        }


class JobQueue:
    """Accepts jobs, runs them one at a time, remembers what happened."""

    def __init__(self, settings, library=None, runner=None, summariser=None,
                 measurer=None):
        self.settings = dict(settings or {})
        self.library = library or Library(self.settings.get("library_dir"))
        self._runner = runner or self._transcribe
        self._summariser = summariser or self._summarize
        self._measurer = measurer or waveform.loudness_of_file
        self._pending = queue.Queue()
        self._measuring = queue.Queue()
        self._measurer_thread = None
        self._jobs = {}
        self._order = []
        # Re-entrant: every change is written down before the lock is let go,
        # and the writing walks the same list.
        self._lock = threading.RLock()
        self._worker = None
        self._restore()
        self._restore_uploads()

    # --- what a restart finds -------------------------------------------

    def state_path(self):
        """The file the queue is written down in, beside the uploads."""
        root = self.settings.get("cache_dir") or paths.cache_dir()
        return os.path.join(paths.ensure(os.path.expanduser(root)), STATE_FILENAME)

    def _save(self):
        """Write the queue down. Called with the lock held, after a change.

        Failure is ignored on purpose: a queue that cannot be written down
        still runs, and a full disk must not take a transcription with it."""
        path = self.state_path()
        payload = {"version": 1,
                   "jobs": [self._jobs[known].to_state() for known in self._order
                            if known in self._jobs]}
        temporary = path + ".tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=1)
            os.replace(temporary, path)     # atomic: never a half-written list
        except (OSError, TypeError, ValueError):
            try:
                os.unlink(temporary)
            except OSError:
                pass

    def _read_state(self):
        """The jobs a previous run left behind, or nothing at all."""
        try:
            with open(self.state_path(), encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            return []
        jobs = payload.get("jobs") if isinstance(payload, dict) else None
        return jobs if isinstance(jobs, list) else []

    def _restore(self):
        """Bring back the queue the last run was in the middle of.

        A job that was waiting is still waiting. One that was running was
        interrupted rather than finished, so it goes back in the queue — the
        page will show it running again in a moment — unless it has already
        been interrupted twice, which is what a recording that kills the
        process looks like from here. A job whose file has gone is dropped:
        there is nothing left to run."""
        resume = []
        with self._lock:
            for state in self._read_state():
                job = Job.from_state(state)
                if job is None or job.id in self._jobs:
                    continue
                unrunnable = not job.source or not os.path.isfile(job.source)
                if (job.status not in FINISHED and job.kind == TRANSCRIPTION
                        and unrunnable):
                    continue                # nothing left to run: drop the row
                if job.status == RUNNING:
                    job.restarts += 1
                    job.progress, job.stage = 0, None
                    if job.restarts > MAX_RESTARTS:
                        job.status = FAILED
                        job.error = t("jobs.interrupted_again", count=job.restarts)
                        job.finished_at = now()
                    else:
                        job.status = QUEUED
                        job.started_at = None
                if job.kind == SUMMARY and job.audio_duration is None:
                    # Written down by a version that described a summary by
                    # its engine alone. The entry is still there, so the row
                    # can say what it is about rather than staying blank.
                    self._describe_entry(job)
                elif job.audio_duration is None and job.status not in FINISHED:
                    # Written down by a version that did not record it, or by
                    # one that could not read it then. The file is still here,
                    # so the row can say how long it is rather than staying
                    # blank for the rest of its life.
                    job.audio_duration = audio.probe_seconds(job.source)
                if job.status == QUEUED:
                    resume.append(job.id)
                self._jobs[job.id] = job
                self._order.append(job.id)
                self._measure(job)
            self._forget_old()
            self._save()
        for known in resume:
            self._pending.put(known)
        if resume:
            self._ensure_worker()

    def _restore_uploads(self):
        """Add any upload no restored job accounts for.

        A file in the uploads directory with nothing pointing at it is a job
        from before the queue was written down, or one whose entry was lost:
        it appears as not started, so nothing is transcribed by surprise and
        nothing is silently thrown away either."""
        uploads = self.upload_dir()
        if not os.path.isdir(uploads):
            return
        try:
            files = sorted(os.listdir(uploads))
        except OSError:
            return
        with self._lock:
            claimed = {os.path.abspath(job.source) for job in self._jobs.values()
                       if job.source}
            for filename in files:
                path = os.path.join(uploads, filename)
                if not os.path.isfile(path) or os.path.abspath(path) in claimed:
                    continue
                title = safe_filename(filename)
                job = Job(path, title=title, filename=filename,
                          settings=self.settings)
                job.audio_duration = audio.probe_seconds(path)
                job.status = HELD
                self._jobs[job.id] = job
                self._order.append(job.id)
                self._measure(job)
            self._save()

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
        # How long it is, from the header: a recording waiting its turn can
        # then say so, instead of being a name and a size until it runs.
        job.audio_duration = audio.probe_seconds(source)
        # The length comes off the header in milliseconds and is read here;
        # what the recording looks like takes a pass of ffmpeg, so it does not
        # hold up the answer to an upload.
        self._measure(job)
        if not start:
            job.status = HELD
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
            self._forget_old()
            self._save()
        if start:
            self._pending.put(job.id)
            self._ensure_worker()
        return job

    def _describe_entry(self, job):
        """Give a summary row the facts of the recording it is about.

        Separate from :meth:`summarize` because a queue read back from disk
        may hold summaries written before those facts were kept, and an entry
        that has since been deleted must leave the row as it was rather than
        take the whole restore down with it."""
        try:
            entry = self.library.get(job.entry_id)
        except LibraryError:
            return
        (job.audio_duration, job.size_bytes,
         job.source_created_at) = entry_facts(entry)
        self._measure(job)

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
        # The recording this is about, described the way every other row is:
        # a summary has no file of its own, but "an hour of audio from
        # Tuesday" is what tells its row from the next one.
        (job.audio_duration, job.size_bytes,
         job.source_created_at) = entry_facts(entry)
        if not start:
            job.status = HELD
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
            self._forget_old()
            self._save()
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
            if held:
                self._save()
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
            self._save()
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
            self._save()
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
            self._save()
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
            self._save()
            return True

    # --- internals --------------------------------------------------------

    def _forget_old(self):
        """Drop the oldest finished jobs once the list grows too long."""
        finished = [i for i in self._order
                    if self._jobs[i].status in FINISHED]
        for job_id in finished[:max(0, len(self._order) - MAX_HISTORY)]:
            del self._jobs[job_id]
            self._order.remove(job_id)

    def _persist(self):
        """Write the queue down from outside the lock-holding methods."""
        with self._lock:
            self._save()

    # --- what a recording looks like --------------------------------------

    def _measure(self, job):
        """Ask for this job's drawing, if it has not got one already."""
        if job.loudness is None:
            self._measuring.put(job.id)
            self._ensure_measurer()

    def _ensure_measurer(self):
        with self._lock:
            if self._measurer_thread and self._measurer_thread.is_alive():
                return
            self._measurer_thread = threading.Thread(
                target=self._measure_work, name="waveform", daemon=True)
            self._measurer_thread.start()

    def _measure_work(self):
        """One recording measured at a time, for as long as any are waiting."""
        while True:
            try:
                job_id = self._measuring.get(timeout=30)
            except queue.Empty:
                return      # nothing left to draw; a new job starts a new one
            job = self.get(job_id)
            if job is None or job.loudness is not None:
                continue
            try:
                job.loudness = self._shape_of(job)
            except Exception:       # noqa: BLE001 - a picture, not the work
                job.loudness = None

    def _shape_of(self, job):
        """Where this job's drawing comes from: its entry, or its file.

        A summary has no recording of its own — it is about one — and the
        entry it is about has very probably been measured already, when it was
        transcribed."""
        if job.entry_id:
            try:
                return waveform.entry_loudness(self.library.get(job.entry_id))
            except LibraryError:
                return None
        if not job.source or not os.path.isfile(job.source):
            return None
        return self._measurer(job.source)

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
                    self._persist()
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
        # Written down now, so a restart in the middle of this knows the job
        # was under way rather than waiting.
        self._persist()
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
        self._persist()
        self._summarise_after(job)

    def _summarise_after(self, job):
        """Queue the summary of what has just been transcribed, if asked.

        A separate job rather than a longer one: it is the same two cores
        either way, and as its own row it can be watched, cancelled and
        retried like anything else — and a summary that fails does not turn a
        finished transcription into a failed job."""
        if (job.status != DONE or job.kind != TRANSCRIPTION
                or not job.entry_id or not job.settings.get("summary_after")):
            return
        try:
            self.summarize(job.entry_id)
        except Exception as exc:       # noqa: BLE001 - the transcript is safe
            print(t("jobs.summary_not_queued", title=job.title, error=exc))

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
            "style": job.settings.get("summary_style") or summarising.DEFAULT_STYLE,
            "sentences_kept": result.kept,
            "sentences_total": result.of,
            "tier": result.tier,
            "caveat": result.note,
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
