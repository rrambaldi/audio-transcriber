"""The transcription queue, which the web interface and the window share.

The queue is tested with a fake runner: nothing here loads a model, touches the
network or takes longer than a few milliseconds. It needs neither FastAPI nor
Qt, because it belongs to neither front end."""
import pathlib
import threading
import time

import pytest

from audio_transcriber import jobs as jobs_module
from audio_transcriber import paths
from audio_transcriber.library import STORE_COPY, STORE_MOVE

SETTINGS = {"model": "small", "language": "it", "backend": "auto", "device": "auto",
            "para_gap": 1.2, "para_max_chars": 600, "prompt": "", "prompt_file": None,
            "vocabulary": None, "vocab_dir": None, "library_dir": None, "diarize": False}


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "home"))
    monkeypatch.delenv("AUDIO_TRANSCRIBER_LANG", raising=False)


@pytest.fixture
def queue():
    """A queue whose worker does nothing but record that it ran."""
    done = []

    def runner(job):
        if "boom" in job.filename:
            raise RuntimeError("the model exploded")
        if "exit" in job.filename:
            raise SystemExit("ffmpeg failed to decode the audio")
        job.entry_id = "2026-09-04_1200_" + job.id
        job.words = 3
        done.append(job)

    return jobs_module.JobQueue(SETTINGS, runner=runner)


def wait_for(queue, job_id, statuses=("done", "failed"), timeout=5.0):
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = queue.get(job_id)
        if job and job.status in statuses:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} never finished")


# --- the queue ------------------------------------------------------------

def test_a_submitted_job_runs_and_reports_its_entry(queue, tmp_path):
    source = tmp_path / "meeting.wav"
    source.write_bytes(b"not really audio")
    job = queue.submit(str(source), title="Weekly")
    assert wait_for(queue, job.id).status == "done"
    assert job.entry_id and job.words == 3


def test_a_failing_job_is_recorded_not_raised(queue, tmp_path):
    source = tmp_path / "boom.wav"
    source.write_bytes(b"x")
    job = queue.submit(str(source))
    assert wait_for(queue, job.id).status == "failed"
    assert "exploded" in job.error


def test_a_command_line_style_sys_exit_is_a_failed_job_not_a_dead_worker(queue, tmp_path):
    """The modules underneath report errors the way a CLI does; the queue must
    survive it and keep running the next job."""
    source = tmp_path / "exit.wav"
    source.write_bytes(b"x")
    job = queue.submit(str(source))
    assert wait_for(queue, job.id).status == "failed"
    assert "ffmpeg" in job.error

    good = tmp_path / "fine.wav"
    good.write_bytes(b"x")
    later = queue.submit(str(good))
    assert wait_for(queue, later.id).status == "done"


def test_jobs_are_listed_newest_first(queue, tmp_path):
    source = tmp_path / "a.wav"
    source.write_bytes(b"x")
    first = queue.submit(str(source), title="first")
    second = queue.submit(str(source), title="second")
    wait_for(queue, second.id)
    assert [job.id for job in queue.jobs()] == [second.id, first.id]


def test_only_a_finished_job_can_be_forgotten(queue, tmp_path):
    source = tmp_path / "a.wav"
    source.write_bytes(b"x")
    job = queue.submit(str(source))
    wait_for(queue, job.id)
    assert queue.remove(job.id) is True
    assert queue.get(job.id) is None


def test_the_prompt_combines_the_named_sets_and_the_browsers_own_text(queue, tmp_path):
    directory = tmp_path / "home" / "config" / "vocabularies"
    directory.mkdir(parents=True)
    (directory / "mine.txt").write_text("alpha, beta\n", encoding="utf-8")
    source = tmp_path / "a.wav"
    source.write_bytes(b"x")
    job = queue.submit(str(source), vocabularies=["mine"],
                       custom_vocabulary="# private\ngamma\n")
    assert job.prompt == "alpha, beta gamma"


@pytest.mark.parametrize("name,expected", [
    ("../../etc/passwd", "passwd"),
    ("meeting 2026.wav", "meeting 2026.wav"),
    ("", "recording"),
])
def test_an_uploaded_name_is_reduced_to_a_file_name(name, expected):
    assert jobs_module.safe_filename(name) == expected


# --- taking work back out -------------------------------------------------

def test_a_queued_job_can_be_taken_out_before_it_starts(tmp_path):
    """The queue runs one at a time, so anything behind the first job is
    waiting - and waiting is exactly when someone changes their mind."""
    blocked = threading.Event()

    def runner(job):
        blocked.wait(5)

    queue = jobs_module.JobQueue(SETTINGS, runner=runner)
    source = tmp_path / "a.wav"
    source.write_bytes(b"x")
    first = queue.submit(str(source), title="running")
    waiting = queue.submit(str(source), title="waiting")
    wait_for(queue, first.id, statuses=("running",))

    assert queue.cancel(waiting.id) is True
    assert waiting.status == "cancelled"
    assert queue.pending_count() == 1          # only the one still running
    blocked.set()
    wait_for(queue, first.id)
    assert first.status == "done"


def test_a_cancelled_job_is_never_run(tmp_path):
    """Even the one already handed to the worker: it checks before starting."""
    started = []
    blocked = threading.Event()

    def runner(job):
        started.append(job.title)
        blocked.wait(5)

    queue = jobs_module.JobQueue(SETTINGS, runner=runner)
    source = tmp_path / "a.wav"
    source.write_bytes(b"x")
    first = queue.submit(str(source), title="first")
    second = queue.submit(str(source), title="second")
    wait_for(queue, first.id, statuses=("running",))
    queue.cancel(second.id)
    blocked.set()
    wait_for(queue, first.id)
    time.sleep(0.2)
    assert started == ["first"]


def test_a_running_job_stops_at_its_next_progress_report(tmp_path):
    """The engines are one long blocking call; the progress callback is the
    only moment they hand control back, so it is where a stop lands."""
    reported = []
    running = threading.Event()

    def runner(job):
        # What pipeline.run does with the callback the queue hands it.
        for percent in range(0, 101, 10):
            queue._advance(job, percent)
            reported.append(percent)
            running.set()
            time.sleep(0.02)

    queue = jobs_module.JobQueue(SETTINGS, runner=runner)
    source = tmp_path / "a.wav"
    source.write_bytes(b"x")
    job = queue.submit(str(source))
    assert running.wait(5)                     # it is under way
    assert queue.cancel(job.id) is True
    wait_for(queue, job.id, statuses=("cancelled",))
    assert job.error is None                   # asked for, so not a failure
    assert len(reported) < 11                  # it did not run to the end


def test_a_job_cancelled_by_flag_alone_does_not_sit_there_as_queued(tmp_path):
    """Belt and braces on the worker: whatever set the flag, a job that will
    never run must not keep saying it is waiting."""
    blocked = threading.Event()
    queue = jobs_module.JobQueue(SETTINGS, runner=lambda job: blocked.wait(5))
    source = tmp_path / "a.wav"
    source.write_bytes(b"x")
    first = queue.submit(str(source))
    waiting = queue.submit(str(source))
    wait_for(queue, first.id, statuses=("running",))
    waiting.cancel_requested = True
    blocked.set()
    wait_for(queue, waiting.id, statuses=("cancelled",))


def test_a_cancelled_job_leaves_its_recording_alone(tmp_path, monkeypatch):
    """A failure deletes the upload it can no longer use. A cancellation must
    not: a recording nobody has transcribed yet may be the only copy of that
    meeting."""
    queue = jobs_module.JobQueue(SETTINGS, runner=lambda job: None)
    upload = pathlib.Path(queue.upload_dir()) / "meeting.wav"
    upload.write_bytes(b"x")
    job = queue.submit(str(upload), store=STORE_MOVE)
    queue.cancel(job.id)
    assert upload.exists()


def test_a_finished_job_cannot_be_cancelled(tmp_path):
    queue = jobs_module.JobQueue(SETTINGS, runner=lambda job: None)
    source = tmp_path / "a.wav"
    source.write_bytes(b"x")
    job = queue.submit(str(source))
    wait_for(queue, job.id)
    assert queue.cancel(job.id) is False


def test_a_cancelled_job_can_then_be_forgotten(tmp_path):
    queue = jobs_module.JobQueue(SETTINGS, runner=lambda job: None)
    source = tmp_path / "a.wav"
    source.write_bytes(b"x")
    job = queue.submit(str(source))
    wait_for(queue, job.id)
    job.status = "cancelled"
    assert queue.remove(job.id) is True


# --- what becomes of the file ---------------------------------------------

def test_an_upload_is_moved_into_the_library_and_a_local_file_is_copied(queue, tmp_path):
    """Moving someone's own recording out of their folder is not the queue's
    decision; moving an upload that already sits in a temporary directory is."""
    source = tmp_path / "a.wav"
    source.write_bytes(b"x")
    assert queue.submit(str(source)).store == STORE_MOVE
    assert queue.submit(str(source), store=STORE_COPY).store == STORE_COPY


def test_an_unknown_store_mode_is_refused(queue, tmp_path):
    source = tmp_path / "a.wav"
    source.write_bytes(b"x")
    with pytest.raises(ValueError):
        queue.submit(str(source), store="teleport")


def test_pending_counts_only_what_is_still_to_come(queue, tmp_path):
    source = tmp_path / "a.wav"
    source.write_bytes(b"x")
    job = queue.submit(str(source))
    wait_for(queue, job.id)
    assert queue.pending_count() == 0
