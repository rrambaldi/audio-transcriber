"""One transcription, end to end: audio in, finished text out.

The command line and the web interface both need the same sequence — decode,
pre-flight the diarization assets, transcribe, clean, lay the text out, file it
in the library — and they must produce exactly the same result. It therefore
lives here once, with no argparse and no HTTP in sight, and each front end only
decides where the text goes afterwards.
"""
import inspect
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

#: The stages a run goes through, as ``(percentage reached, message key)``.
#: A transcription is minutes or hours of one blocking call, and a bar that
#: sits at nothing for all of it looks broken. These are real marks - each one
#: is only reported once the work behind it is done - and they are deliberately
#: small: the transcription itself is the job, and it owns the rest of the bar.
STAGE_STARTED = (1, "stage.starting")
STAGE_DECODED = (4, "stage.decoded")
STAGE_READY = (5, "stage.transcribing")

#: Stages whose percentage comes from the band they belong to rather than
#: from a number of their own.
STAGE_LAYING_OUT = "stage.laying_out"
STAGE_DIARIZING = "stage.diarizing"

#: The band of the bar the engine's own progress is mapped into, with and
#: without diarization. Mapping rather than passing it through: an engine
#: reporting 0% must not send the bar back to the beginning, and diarization
#: afterwards takes about as long again as the transcription did.
ENGINE_BAND = (5, 95)
ENGINE_BAND_WITH_DIARIZATION = (5, 60)
DIARIZATION_BAND = (60, 95)

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


def scale(band, callback, stage=None):
    """A progress callback that maps 0..100 into ``band``.

    Handed to a backend so that its own count of the audio it has got through
    lands inside the slice of the bar that belongs to transcribing, instead of
    overwriting the stages before it."""
    low, high = band

    def report(percent, stage_key=None):
        callback(low + (high - low) * max(0, min(100, percent)) / 100.0,
                 stage_key or stage)

    return report


def report_to(progress):
    """Normalise the optional callback into one that always takes a stage.

    The command line passes none; an interface passes one that takes a
    percentage and, if it cares, the message key of the stage reached. Which
    of the two it is, is settled once by looking at the signature — trying the
    two-argument call and catching TypeError would call a callback twice the
    first time it raised one of its own."""
    if progress is None:
        return lambda percent, stage=None: None
    try:
        wants_stage = len(inspect.signature(progress).parameters) >= 2
    except (TypeError, ValueError):
        wants_stage = False
    if wants_stage:
        return lambda percent, stage=None: progress(int(round(percent)), stage)
    return lambda percent, stage=None: progress(int(round(percent)))


def run(source, settings, prompt=None, progress=None):
    """Transcribe ``source`` and return a :class:`Result`.

    ``progress`` is called as the work advances, which is how an interface can
    show a bar for a job that takes an hour. It receives a percentage and,
    when the caller accepts a second argument, the message key of the stage
    reached — the percentage alone stands still for the whole of a long
    transcription on an engine that cannot report its own progress."""
    if prompt is None:
        prompt = resolve_prompt(settings)

    report = report_to(progress)
    report(*STAGE_STARTED)

    audio = load_audio(source)
    audio_duration = duration_seconds(audio)
    report(*STAGE_DECODED)

    token = diar_model = None
    diarizing = bool(settings.get("diarize"))
    if diarizing:
        token, diar_model = diarization_assets(settings)
    report(*STAGE_READY)

    started = time.time()
    band = ENGINE_BAND_WITH_DIARIZATION if diarizing else ENGINE_BAND
    segments, blob, info = transcribe(
        audio, settings["model"], settings["language"] or None, settings["device"],
        model_dir=settings.get("models_dir"), prompt=prompt,
        backend=settings["backend"], compute_type=settings.get("compute_type"),
        threads=settings.get("threads"), vad=settings.get("vad", True),
        progress=scale(band, report, STAGE_READY[1]),
    )
    report(band[1], STAGE_LAYING_OUT)
    if not segments and not blob.strip():
        raise EmptyTranscription()   # its message is the translated one
    segments = clean_segments(segments, drop_fillers=not settings.get("keep_fillers"))

    text, diarized = None, False
    if diarizing:
        report(DIARIZATION_BAND[0], STAGE_DIARIZING)
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

    report(DIARIZATION_BAND[1] if diarizing else ENGINE_BAND[1],
           STAGE_LAYING_OUT)
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
