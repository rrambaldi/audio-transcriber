"""One transcription, end to end: audio in, finished text out.

The command line and the web interface both need the same sequence — decode,
pre-flight the diarization assets, transcribe, clean, lay the text out, file it
in the library — and they must produce exactly the same result. It therefore
lives here once, with no argparse and no HTTP in sight, and each front end only
decides where the text goes afterwards.
"""
import os
import time
from collections import namedtuple
from datetime import datetime

from . import paths
from .audio import duration_seconds, load_audio
from .cleaning import clean_segments, paragraphs_from_blob, to_paragraphs
from .config import read_prompt
from .diarization import assign_speakers, check_diar_assets, diarize, format_dialogue
from .i18n import t
from .transcription import transcribe
from .vocabularies import split_names

#: What one run produces. ``info`` is the backend/device/model record.
Result = namedtuple("Result",
                    "text segments info audio_duration elapsed diarized prompt")


class EmptyTranscription(Exception):
    """The audio produced no text at all: empty or silent input.

    It carries its own message because it is reported in two places — the CLI
    prints it, the web queue stores it on the job — and a bare class name is
    not an explanation."""

    def __init__(self, message=None):
        super().__init__(message or t("transcribe.empty"))


def resolve_prompt(settings):
    """The initial prompt in effect: keyword sets, then prompt file or string."""
    return read_prompt(settings.get("prompt"), settings.get("prompt_file"),
                       settings.get("vocabulary"), settings.get("vocab_dir"))


def diarization_assets(settings):
    """``(token, model)`` for diarization, checked before the long part.

    A missing model file must surface now rather than in an hour."""
    token = (settings.get("hf_token")
             or os.environ.get("HUGGINGFACE_TOKEN")
             or os.environ.get("HF_TOKEN"))
    model = settings.get("diar_model") or paths.diarization_config()
    check_diar_assets(model, token)
    return token, model


def run(source, settings, prompt=None, progress=None):
    """Transcribe ``source`` and return a :class:`Result`.

    ``progress`` is called with a percentage as the work advances, which is how
    the web interface can show a bar for a job that takes an hour."""
    if prompt is None:
        prompt = resolve_prompt(settings)

    audio = load_audio(source)
    audio_duration = duration_seconds(audio)

    token = diar_model = None
    if settings.get("diarize"):
        token, diar_model = diarization_assets(settings)

    started = time.time()
    segments, blob, info = transcribe(
        audio, settings["model"], settings["language"] or None, settings["device"],
        model_dir=settings.get("models_dir"), prompt=prompt,
        backend=settings["backend"], compute_type=settings.get("compute_type"),
        threads=settings.get("threads"), vad=settings.get("vad", True),
        progress=progress,
    )
    if not segments and not blob.strip():
        raise EmptyTranscription()   # its message is the translated one
    segments = clean_segments(segments, drop_fillers=not settings.get("keep_fillers"))

    text, diarized = None, False
    if settings.get("diarize"):
        turns = diarize(audio, token, settings.get("speakers"), diar_model)
        if segments and turns:
            segments = assign_speakers(segments, turns)
            text = format_dialogue(segments) + "\n"
            diarized = True
    if text is None:
        paragraphs = (to_paragraphs(segments, settings["para_gap"],
                                    settings["para_max_chars"])
                      if segments else paragraphs_from_blob(blob))
        text = "\n\n".join(paragraphs) + "\n"

    return Result(text=text, segments=segments, info=info,
                  audio_duration=audio_duration, elapsed=time.time() - started,
                  diarized=diarized, prompt=prompt)


def file_in_library(library, source, result, settings, title=None, store="copy"):
    """Create a library entry for ``result`` and return it."""
    entry = library.create(source=source, title=title, store=store)
    entry.write_transcript(result.text, result.segments)
    entry.update(
        audio={"duration_seconds": round(result.audio_duration, 2),
               "sample_rate": 16000},
        transcription={
            "backend": result.info["backend"],
            "device": result.info["device"],
            "model": result.info["model"],
            "language": settings.get("language") or "auto",
            "diarized": result.diarized,
            "speakers": settings.get("speakers"),
            "vocabulary": split_names(settings.get("vocabulary")) or None,
            "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "elapsed_seconds": round(result.elapsed, 1),
        },
        stats={"words": len(result.text.split()), "segments": len(result.segments)},
    )
    return entry
