"""The HTTP interface: a handful of JSON endpoints and one static page.

Everything the browser can ask for is something the command line can already
do. The page uploads a file, picks a model and one or more keyword sets, and
polls the resulting job; the transcription itself goes through the same
:mod:`audio_transcriber.pipeline` the CLI uses.

The keyword sets come from two places and the distinction matters. Sets served
by ``/api/vocabularies`` are the ones installed on this machine, chosen by
whoever set the tool up; a visitor's own sets never leave their browser, where
the page keeps them, and reach the server only as the text of the job they are
used for. That way there is no endpoint that writes to the server's
configuration, and no shared state between two people using the same instance.
"""
import mimetypes
import os

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__, i18n, vocabularies
from ..backends import BACKENDS
from ..diarization import availability as diarization_availability
from ..jobs import MAX_UPLOAD_BYTES, JobQueue, safe_filename
from ..library import MAX_NOTES, LibraryError
from ..transcription import (
    AUTO,
    LANGUAGE_CHOICES,
    MODEL_CHOICES,
    MODEL_RAM_GB,
    recommend_model,
)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

#: The menus this page offers, shared with the desktop window.
MODELS = MODEL_CHOICES
LANGUAGES = LANGUAGE_CHOICES

#: What a visitor's own keyword set may weigh; see the module docstring for
#: why theirs never reaches the server's configuration.
MAX_CUSTOM_VOCABULARY = vocabularies.MAX_CUSTOM_VOCABULARY


def create_app(settings=None, queue=None):
    """Build the application. ``settings`` are the resolved CLI defaults."""
    settings = dict(settings or {})
    app = FastAPI(title="audio-transcriber", version=__version__,
                  docs_url="/api/docs", redoc_url=None)
    app.state.settings = settings
    app.state.queue = queue or JobQueue(settings)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    register_routes(app)
    return app


def register_routes(app):

    def library_of(request):
        return request.app.state.queue.library

    def vocab_dir(request):
        return request.app.state.settings.get("vocab_dir")

    # --- the page ---------------------------------------------------------

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

    # --- what this installation can do ------------------------------------

    @app.get("/api/status")
    def status(request: Request):
        settings = request.app.state.settings
        return {
            "version": __version__,
            "interface_language": i18n.language(),
            "models": list(MODELS),
            "languages": list(LANGUAGES),
            "backends": list(BACKENDS),
            "known_models": sorted(MODEL_RAM_GB),
            "recommended_model": recommend_model(),
            "diarization": diarization_state(settings),
            "defaults": {
                "model": settings.get("model") or AUTO,
                "language": settings.get("language") or "",
                "backend": settings.get("backend") or "auto",
                "diarize": bool(settings.get("diarize")),
                "vocabulary": vocabularies.split_names(settings.get("vocabulary")),
            },
            "library_dir": library_of(request).root,
            "max_upload_bytes": MAX_UPLOAD_BYTES,
            "max_custom_vocabulary": MAX_CUSTOM_VOCABULARY,
            "max_prompt_chars": vocabularies.MAX_PROMPT_CHARS,
        }

    # --- keyword sets installed on this machine ---------------------------

    @app.get("/api/vocabularies")
    def list_vocabularies(request: Request):
        items = vocabularies.available(vocab_dir(request))
        return {"vocabularies": [item.as_dict(include_text=True) for item in items],
                "directory": vocabularies.user_dir()}

    @app.get("/api/vocabularies/{name}")
    def show_vocabulary(name: str, request: Request):
        try:
            item = vocabularies.get(name, vocab_dir(request))
        except vocabularies.VocabularyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return item.as_dict(include_text=True)

    # --- jobs -------------------------------------------------------------

    @app.post("/api/jobs", status_code=202)
    async def create_job(
        request: Request,
        file: UploadFile = File(...),
        title: str = Form(""),
        model: str = Form(""),
        language: str | None = Form(None),
        backend: str = Form(""),
        diarize: bool = Form(False),
        speakers: int | None = Form(None),
        vocabulary: list[str] = Form(default=[]),
        custom_vocabulary: str = Form(""),
    ):
        queue = request.app.state.queue
        names = vocabularies.split_names(vocabulary)
        for name in names:
            try:
                vocabularies.get(name, vocab_dir(request))
            except vocabularies.VocabularyError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        if len(custom_vocabulary) > MAX_CUSTOM_VOCABULARY:
            raise HTTPException(
                status_code=413,
                detail=f"the custom vocabulary is limited to {MAX_CUSTOM_VOCABULARY} characters")
        if model and model != AUTO and model not in MODELS and model not in MODEL_RAM_GB:
            raise HTTPException(status_code=400, detail=f"unknown model '{model}'")
        if backend and backend not in BACKENDS:
            raise HTTPException(status_code=400, detail=f"unknown backend '{backend}'")

        target = await store_upload(file, queue.upload_dir())
        job = queue.submit(
            target, title=title.strip() or None,
            filename=safe_filename(file.filename),
            overrides={"model": model or None, "language": language,
                       "backend": backend or None, "diarize": diarize or None,
                       "speakers": speakers or None},
            vocabularies=names, custom_vocabulary=custom_vocabulary)
        return job.as_dict()

    @app.get("/api/jobs")
    def list_jobs(request: Request):
        return {"jobs": [job.as_dict() for job in request.app.state.queue.jobs()]}

    @app.get("/api/jobs/{job_id}")
    def show_job(job_id: str, request: Request):
        job = request.app.state.queue.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="unknown job")
        return job.as_dict()

    @app.delete("/api/jobs/{job_id}")
    def forget_job(job_id: str, request: Request):
        if not request.app.state.queue.remove(job_id):
            raise HTTPException(status_code=409,
                                detail="only a finished job can be forgotten")
        return JSONResponse({"removed": job_id})

    # --- the library ------------------------------------------------------

    @app.get("/api/library")
    def list_library(request: Request, q: str = ""):
        """The entries, newest first; ``q`` searches transcripts and notes."""
        library = library_of(request)
        found = library.search(q) if q.strip() else library.entries()
        entries = []
        for entry in found:
            try:
                data = entry.metadata
            except LibraryError:
                continue
            audio = data.get("audio") or {}
            stats = data.get("stats") or {}
            transcription = data.get("transcription") or {}
            entries.append({
                "id": entry.id,
                "title": data.get("title") or entry.id,
                "created_at": data.get("created_at"),
                "duration_seconds": audio.get("duration_seconds"),
                "words": stats.get("words"),
                "model": transcription.get("model"),
                "language": transcription.get("language"),
                "diarized": transcription.get("diarized"),
                "vocabulary": transcription.get("vocabulary"),
                "has_notes": entry.has_written_notes(),
            })
        return {"entries": entries, "query": q}

    def entry_or_404(request, entry_id):
        try:
            return library_of(request).get(entry_id)
        except LibraryError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/library/{entry_id}")
    def show_entry(entry_id: str, request: Request):
        entry = entry_or_404(request, entry_id)
        data = dict(entry.metadata)
        data["id"] = entry.id
        data["transcript"] = entry.read_transcript()
        data["notes"] = entry.read_notes()
        data["segments"] = entry.read_segments()
        data["has_audio"] = bool(entry.stored_audio())
        return data

    @app.patch("/api/library/{entry_id}")
    def rename_entry(entry_id: str, request: Request, title: str = Body(..., embed=True)):
        """Rename an entry. The folder keeps its id: the title is metadata."""
        title = title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="the title cannot be empty")
        entry = entry_or_404(request, entry_id)
        entry.update(title=title[:200])
        return {"id": entry.id, "title": entry.metadata.get("title")}

    @app.delete("/api/library/{entry_id}")
    def remove_entry(entry_id: str, request: Request):
        entry = entry_or_404(request, entry_id)
        try:
            path = library_of(request).remove(entry)
        except LibraryError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"removed": entry.id, "path": path}

    @app.put("/api/library/{entry_id}/notes")
    def save_notes(entry_id: str, request: Request, notes: str = Body(..., embed=True)):
        if len(notes) > MAX_NOTES:
            raise HTTPException(status_code=413,
                                detail=f"notes are limited to {MAX_NOTES} characters")
        entry = entry_or_404(request, entry_id)
        try:
            entry.write_notes(notes)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"id": entry.id, "notes": entry.read_notes()}

    @app.get("/api/library/{entry_id}/transcript.txt")
    def download_transcript(entry_id: str, request: Request):
        entry = entry_or_404(request, entry_id)
        return PlainTextResponse(
            entry.read_transcript(),
            headers={"Content-Disposition":
                     f'attachment; filename="{entry.id}.txt"'})

    @app.get("/api/library/{entry_id}/transcript.json")
    def download_segments(entry_id: str, request: Request):
        entry = entry_or_404(request, entry_id)
        if not os.path.exists(entry.segments_path):
            raise HTTPException(status_code=404, detail="this entry has no segments")
        return FileResponse(entry.segments_path, media_type="application/json",
                            filename=f"{entry.id}.json")

    @app.get("/api/library/{entry_id}/audio")
    def stream_audio(entry_id: str, request: Request):
        """The recording itself, so the page can play it while reading along.

        ``FileResponse`` answers range requests, which is what makes seeking in
        a two-hour recording work."""
        entry = entry_or_404(request, entry_id)
        source = entry.stored_audio()
        if not source:
            raise HTTPException(status_code=404, detail="this entry has no stored audio")
        media_type = mimetypes.guess_type(source)[0] or "application/octet-stream"
        return FileResponse(source, media_type=media_type)

def diarization_state(settings):
    """Whether the page should offer "who said what", and why not.

    Offering a checkbox for something this machine cannot do turns into a job
    that fails after the upload, which is a worse way to learn it."""
    state, detail = diarization_availability(settings.get("diar_model"))
    return {"available": state == "ready", "reason": state, "detail": detail}


async def store_upload(upload, directory, chunk_size=1024 * 1024):
    """Stream an upload to disk, refusing one that is too large.

    The name is rebuilt from the client's, which is why it is sanitised: a
    browser is free to send ``../../etc/passwd`` as a file name."""
    name = safe_filename(upload.filename)
    target = os.path.join(directory, f"{os.urandom(4).hex()}-{name}")
    written = 0
    try:
        with open(target, "wb") as handle:
            while True:
                chunk = await upload.read(chunk_size)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="file too large")
                handle.write(chunk)
    except HTTPException:
        os.unlink(target)
        raise
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        await upload.close()
    if written == 0:
        os.unlink(target)
        raise HTTPException(status_code=400, detail="the uploaded file is empty")
    return target

