"""The local web interface: the endpoints the page uses.

The queue itself lives in :mod:`audio_transcriber.jobs` and is tested in
``test_jobs.py``, which needs no web framework. What is left here needs
FastAPI, an optional extra, and is skipped without it."""
import os

import pytest

from audio_transcriber import jobs as jobs_module
from audio_transcriber import paths

fastapi = pytest.importorskip("fastapi", reason="the [web] extra is not installed")
from fastapi.testclient import TestClient  # noqa: E402

from audio_transcriber.web.api import create_app  # noqa: E402

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


@pytest.fixture
def client(queue):
    return TestClient(create_app(SETTINGS, queue))


def wait_for(queue, job_id, statuses=("done", "failed"), timeout=5.0):
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = queue.get(job_id)
        if job and job.status in statuses:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} never finished")


def test_a_failed_upload_is_not_left_on_the_disk(client, queue):
    response = client.post("/api/jobs", files={"file": ("boom.wav", b"x")})
    job = wait_for(queue, response.json()["id"])
    assert job.status == "failed"
    assert not os.path.exists(job.source)
    assert os.listdir(queue.upload_dir()) == []


# --- the endpoints --------------------------------------------------------

def test_the_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "audio-transcriber" in response.text


def test_status_describes_the_installation(client):
    data = client.get("/api/status").json()
    assert data["defaults"]["model"] == "small"
    assert "small" in data["models"]
    assert data["max_prompt_chars"] > 0


def test_the_installed_sets_are_listed_with_their_text(client):
    data = client.get("/api/vocabularies").json()
    names = [item["name"] for item in data["vocabularies"]]
    assert "iso27001-it" in names
    assert all("text" in item for item in data["vocabularies"])


def test_one_set_can_be_fetched_by_name(client):
    data = client.get("/api/vocabularies/iso27001-it").json()
    assert data["language"] == "it" and data["terms"] > 0


def test_a_set_name_cannot_walk_out_of_the_directory(client):
    assert client.get("/api/vocabularies/..%2F..%2Fconfig.toml").status_code == 404
    assert client.get("/api/vocabularies/nope").status_code == 404


def test_uploading_a_file_creates_a_job(client, queue):
    response = client.post("/api/jobs", files={"file": ("meeting.wav", b"audio bytes")},
                           data={"title": "Weekly", "vocabulary": ["iso27001-it"]})
    assert response.status_code == 202
    body = response.json()
    assert body["title"] == "Weekly" and body["vocabularies"] == ["iso27001-it"]
    assert wait_for(queue, body["id"]).status == "done"
    assert client.get(f"/api/jobs/{body['id']}").json()["status"] == "done"


def test_an_unknown_set_is_refused_before_the_upload_is_queued(client, queue):
    response = client.post("/api/jobs", files={"file": ("a.wav", b"x")},
                           data={"vocabulary": ["nope"]})
    assert response.status_code == 400
    assert queue.jobs() == []


def test_an_empty_upload_is_refused(client):
    assert client.post("/api/jobs", files={"file": ("a.wav", b"")}).status_code == 400


def test_an_oversized_custom_vocabulary_is_refused(client):
    response = client.post("/api/jobs", files={"file": ("a.wav", b"x")},
                           data={"custom_vocabulary": "x" * 5000})
    assert response.status_code == 413


def test_an_unknown_model_is_refused(client):
    response = client.post("/api/jobs", files={"file": ("a.wav", b"x")},
                           data={"model": "enormous"})
    assert response.status_code == 400


def test_an_unknown_job_is_a_404(client):
    assert client.get("/api/jobs/nope").status_code == 404


def test_the_library_is_empty_to_begin_with(client):
    assert client.get("/api/library").json()["entries"] == []


def test_a_library_entry_can_be_read_and_downloaded(client, queue):
    entry = queue.library.create(title="Board meeting")
    entry.write_transcript("hello\n", [])
    listed = client.get("/api/library").json()["entries"]
    assert [item["title"] for item in listed] == ["Board meeting"]
    shown = client.get(f"/api/library/{entry.id}").json()
    assert shown["transcript"] == "hello\n"
    download = client.get(f"/api/library/{entry.id}/transcript.txt")
    assert download.text == "hello\n"
    assert "attachment" in download.headers["content-disposition"]


def test_an_unknown_library_entry_is_a_404(client):
    assert client.get("/api/library/2099-01-01_0000_nope").status_code == 404


# --- the real runner, with the engine stubbed out -------------------------

def test_a_finished_job_leaves_the_recording_in_the_library(monkeypatch, tmp_path):
    """The queue's own runner, not a fake one: what the CLI does, in a thread."""
    from audio_transcriber import pipeline

    seen = {}

    def transcribe(audio, model, language, device, **options):
        seen.update(options)
        return ([{"text": "ciao", "start": 0.0, "end": 1.0}], "ciao",
                {"backend": "fake", "device": "CPU", "model": model, "model_dir": ""})

    monkeypatch.setattr(pipeline, "load_audio", lambda source: object())
    monkeypatch.setattr(pipeline, "duration_seconds", lambda audio: 5.0)
    monkeypatch.setattr(pipeline, "transcribe", transcribe)

    queue = jobs_module.JobQueue(SETTINGS)
    client = TestClient(create_app(SETTINGS, queue))
    response = client.post("/api/jobs", files={"file": ("meeting.wav", b"x")},
                           data={"title": "Weekly", "vocabulary": ["iso27001-it"],
                                 "custom_vocabulary": "pippo, pluto"})
    job = wait_for(queue, response.json()["id"])
    assert job.status == "done", job.error
    assert "pippo, pluto" in seen["prompt"]
    assert "piano di trattamento dei rischi" in seen["prompt"]

    entries = client.get("/api/library").json()["entries"]
    assert [entry["title"] for entry in entries] == ["Weekly"]
    assert entries[0]["vocabulary"] == ["iso27001-it"]
    assert client.get(f"/api/library/{job.entry_id}").json()["transcript"].strip() == "ciao"
    # The upload was moved into the entry rather than left in the cache.
    assert not os.path.exists(job.source)
    assert os.listdir(queue.upload_dir()) == []


# --- browsing one entry ---------------------------------------------------

@pytest.fixture
def entry(queue, tmp_path):
    """A library entry holding a recording, a transcript and segments."""
    source = tmp_path / "board.wav"
    source.write_bytes(b"RIFF....WAVEfake")
    made = queue.library.create(source=str(source), title="Board meeting")
    made.write_transcript("hello there\n", [{"text": "hello there", "start": 0.0, "end": 1.5,
                                             "speaker": "SPEAKER_00"}])
    made.update(audio={"duration_seconds": 90.0}, stats={"words": 2})
    return made


def test_the_library_can_be_searched(client, queue, entry):
    other = queue.library.create(title="Other")
    other.write_transcript("nothing to see\n", [])
    assert [e["title"] for e in client.get("/api/library?q=hello").json()["entries"]] \
        == ["Board meeting"]
    assert client.get("/api/library?q=absent").json()["entries"] == []
    assert len(client.get("/api/library").json()["entries"]) == 2


def test_an_entry_carries_its_segments_notes_and_audio_flag(client, entry):
    data = client.get(f"/api/library/{entry.id}").json()
    assert data["segments"][0]["speaker"] == "SPEAKER_00"
    # A new entry starts with notes.md holding just its title as a heading.
    assert data["notes"].startswith("# Board meeting")
    assert data["has_audio"] is True


def test_notes_are_saved_and_show_up_in_the_listing(client, entry):
    assert client.get("/api/library").json()["entries"][0]["has_notes"] is False
    response = client.put(f"/api/library/{entry.id}/notes",
                          json={"notes": "# Board meeting\n\ndecided: ship it"})
    assert response.status_code == 200
    assert "decided: ship it" in entry.read_notes()
    assert client.get("/api/library").json()["entries"][0]["has_notes"] is True


def test_notes_beyond_the_limit_are_refused(client, entry):
    response = client.put(f"/api/library/{entry.id}/notes", json={"notes": "x" * 200_000})
    assert response.status_code == 413


def test_an_entry_can_be_renamed_without_moving_its_folder(client, entry):
    response = client.patch(f"/api/library/{entry.id}", json={"title": "Board, June"})
    assert response.json() == {"id": entry.id, "title": "Board, June"}
    assert os.path.isdir(entry.path)
    assert client.patch(f"/api/library/{entry.id}", json={"title": "  "}).status_code == 400


def test_an_entry_can_be_deleted(client, queue, entry):
    assert client.delete(f"/api/library/{entry.id}").status_code == 200
    assert not os.path.exists(entry.path)
    assert queue.library.entries() == []


def test_the_recording_is_served_with_range_support(client, entry):
    response = client.get(f"/api/library/{entry.id}/audio")
    assert response.status_code == 200
    assert response.headers["accept-ranges"] == "bytes"
    partial = client.get(f"/api/library/{entry.id}/audio", headers={"Range": "bytes=0-3"})
    assert partial.status_code == 206 and partial.content == b"RIFF"


def test_an_entry_that_only_references_a_file_serves_no_audio(client, queue, tmp_path):
    source = tmp_path / "elsewhere.wav"
    source.write_bytes(b"x")
    referenced = queue.library.create(source=str(source), title="Elsewhere",
                                      store="reference")
    referenced.write_transcript("x\n", [])
    assert client.get(f"/api/library/{referenced.id}").json()["has_audio"] is False
    assert client.get(f"/api/library/{referenced.id}/audio").status_code == 404


def test_the_segments_can_be_downloaded_and_are_optional(client, queue, entry):
    assert client.get(f"/api/library/{entry.id}/transcript.json").json()["segments"]
    bare = queue.library.create(title="Bare")
    bare.write_transcript("x\n")
    assert client.get(f"/api/library/{bare.id}/transcript.json").status_code == 404


def test_silence_fails_the_job_with_a_sentence_not_a_class_name(monkeypatch, tmp_path):
    """A job's error is read by a person in a browser, so it has to read."""
    from audio_transcriber import pipeline

    monkeypatch.setattr(pipeline, "load_audio", lambda source: object())
    monkeypatch.setattr(pipeline, "duration_seconds", lambda audio: 2.0)
    monkeypatch.setattr(pipeline, "transcribe",
                        lambda *a, **k: ([], "", {"backend": "fake", "device": "CPU",
                                                  "model": "tiny", "model_dir": ""}))
    queue = jobs_module.JobQueue(SETTINGS)
    source = tmp_path / "silence.wav"
    source.write_bytes(b"x")
    job = wait_for(queue, queue.submit(str(source)).id)
    assert job.status == "failed"
    assert "EmptyTranscription" not in job.error
    assert "silent" in job.error or "silenzioso" in job.error


def test_the_page_is_told_which_model_this_machine_would_pick(client):
    from audio_transcriber.transcription import MODEL_RAM_GB

    data = client.get("/api/status").json()
    assert data["recommended_model"] in MODEL_RAM_GB
    assert "auto" in data["models"]


def test_a_job_can_ask_for_the_automatic_model(client, queue):
    response = client.post("/api/jobs", files={"file": ("a.wav", b"x")},
                           data={"model": "auto"})
    assert response.status_code == 202
    assert queue.get(response.json()["id"]).settings["model"] == "auto"


# --- offering only what the machine can do --------------------------------

def test_the_page_is_told_when_diarization_cannot_run(client, monkeypatch):
    """pyannote is an extra. Without it the checkbox must be greyed out, not
    accepted and then failed after the upload."""
    from audio_transcriber import diarization

    monkeypatch.setattr(diarization, "module_available", lambda name: False)
    state = client.get("/api/status").json()["diarization"]
    assert state == {"available": False, "reason": diarization.NOT_INSTALLED,
                     "detail": "pyannote.audio"}


def test_diarization_is_offered_once_a_token_is_there(client, monkeypatch):
    from audio_transcriber import diarization

    monkeypatch.setattr(diarization, "module_available", lambda name: True)
    monkeypatch.setenv("HUGGINGFACE_TOKEN", "hf_pretend")
    assert client.get("/api/status").json()["diarization"]["available"] is True


def test_installed_but_unconfigured_is_its_own_answer(client, monkeypatch):
    from audio_transcriber import diarization

    monkeypatch.setattr(diarization, "module_available", lambda name: True)
    monkeypatch.delenv("HUGGINGFACE_TOKEN", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    state = client.get("/api/status").json()["diarization"]
    assert state["available"] is False and state["reason"] == diarization.NO_MODEL


def test_uploads_follow_the_configured_cache_directory(tmp_path):
    """A recording can be gigabytes: it must land on the disk that was chosen
    for it, not in the home directory."""
    elsewhere = tmp_path / "volume" / "cache"
    queue = jobs_module.JobQueue(dict(SETTINGS, cache_dir=str(elsewhere)))
    assert queue.upload_dir() == str(elsewhere / "uploads")
    assert os.path.isdir(queue.upload_dir())
