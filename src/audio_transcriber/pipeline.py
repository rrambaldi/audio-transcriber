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
from .reference import ReferenceError
from .reference import correct as respell
from .reference import prompt_from as reference_prompt
from .subtitles import (
    OVERRIDABLE,
    SubtitleError,
    tally,
    timings_measured,
    to_srt,
    to_vtt,
    validate,
)
from .subtitles import cues as build_cues
from .subtitles import preset as subtitle_preset
from .transcription import transcribe
from .vocabularies import MAX_PROMPT_CHARS, split_names

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

#: What one run produces. ``info`` is the backend/device/model record, and
#: ``reference`` is what a given text corrected, on the runs that were handed
#: one, and ``None`` on every other.
Result = namedtuple("Result",
                    "text segments info audio_duration elapsed diarized prompt "
                    "reference",
                    defaults=(None,))


class EmptyTranscription(Exception):
    """The audio produced no text at all: empty or silent input.

    It carries its own message because it is reported in two places — the CLI
    prints it, the web queue stores it on the job — and a bare class name is
    not an explanation."""

    def __init__(self, message=None):
        super().__init__(message or t("transcribe.empty"))


def subtitle_formats(settings):
    """Which subtitle files were asked for: ``["srt"]``, both, or none.

    Cues are always available - they are computed from the segments whenever
    something wants them - so this is only about writing files."""
    wanted = settings.get("subtitles")
    if not wanted:
        return []
    if isinstance(wanted, (list, tuple)):
        parts = list(wanted)
    else:
        parts = str(wanted).replace(",", " ").split()
    kinds = []
    for part in parts:
        kind = part.strip().lower().lstrip(".")
        if kind in ("srt", "vtt") and kind not in kinds:
            kinds.append(kind)
        elif kind and kind not in ("srt", "vtt"):
            raise SubtitleError(f"unknown subtitle format '{part}' (srt, vtt)")
    return kinds


def subtitle_spec(settings):
    """The preset in effect, with the settings' own numbers applied over it."""
    overrides = {
        "max_chars_per_line": settings.get("subtitle_chars"),
        "max_lines": settings.get("subtitle_lines"),
        "max_words_per_cue": settings.get("subtitle_words"),
    }
    return subtitle_preset(settings.get("subtitle_preset"),
                           {key: value for key, value in overrides.items()
                            if key in OVERRIDABLE})


def subtitles_of(result, settings):
    """The cues for a finished run, cut by the preset in effect.

    A run that worked out who said what gets its cues marked, since that is
    the only reason to have asked."""
    return build_cues(result.segments, subtitle_spec(settings),
                      language=settings.get("language") or "it",
                      mark_speakers=bool(getattr(result, "diarized", False)))


def write_subtitles(entry, result, settings, kinds=None):
    """Write the subtitle files an entry was asked for, and report the cues.

    Returns ``(kinds written, cues, problems)``. The problems are what a
    subtitler would object to — a line too wide, speech too fast to read —
    reported rather than silently fixed, because fixing them means rewriting
    what was said."""
    kinds = kinds if kinds is not None else subtitle_formats(settings)
    if not kinds:
        return [], [], []
    spec = subtitle_spec(settings)
    cue_list = subtitles_of(result, settings)
    written = []
    for kind in kinds:
        text = to_srt(cue_list, spec.get("line_ending", "\n")) if kind == "srt" \
            else to_vtt(cue_list)
        entry.write_subtitles(text, kind)
        written.append(kind)
    return written, cue_list, validate(cue_list, spec)


def resolve_reference(settings):
    """The text somebody already has for this recording, if there is one.

    Pasted in - the web page and the window both have a box - or a file named
    on the command line. It is not what the run will say: it is used to help
    the engine spell and then to proof-read what it heard. See
    :mod:`audio_transcriber.reference`."""
    text = settings.get("reference") or ""
    path = settings.get("reference_file")
    if not text and path:
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except OSError as failure:
            raise ReferenceError(
                t("reference.unreadable", path=path, error=failure)) from failure
    return text.strip()


def prompt_with_reference(prompt, reference):
    """The prompt, with the reference text's distinctive words added to it.

    Whisper's prompt is a few hundred characters and the keyword sets have
    first claim on them: what a person asked for by name is worth more than
    what a module picked out of a text. The reference's own words get whatever
    is left, longest-standing first, and if nothing is left the reference
    still does its other job - proof-reading afterwards."""
    if not reference:
        return prompt
    room = MAX_PROMPT_CHARS - len(prompt or "") - 1
    extra = reference_prompt(reference, limit=room) if room > 0 else ""
    if not extra:
        return prompt
    return f"{prompt} {extra}".strip() if prompt else extra


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
    # Read before a minute of work is spent: a file that cannot be opened
    # should fail now, not after the transcription.
    reference = resolve_reference(settings)
    # What it buys before the engine runs: the spellings it would otherwise
    # invent. What it buys afterwards is further down.
    prompt = prompt_with_reference(prompt, reference)

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
        # Word timings make a subtitle cut fall where the speaker paused
        # instead of being interpolated: worth the time when subtitles are
        # wanted, not worth it otherwise.
        # Word timings make a subtitle cut fall where the speaker paused
        # instead of being interpolated: worth the time when subtitles are
        # wanted, not worth it otherwise.
        word_timestamps=bool(settings.get("subtitles")),
    )
    report(band[1], STAGE_LAYING_OUT)
    if not segments and not blob.strip():
        raise EmptyTranscription()   # its message is the translated one
    segments = clean_segments(segments, drop_fillers=not settings.get("keep_fillers"))

    proofed = None
    if reference:
        # The second job: what was heard stays what was heard, and only the
        # words the text plainly spells better are rewritten. A sentence the
        # speaker never said does not appear because the text expected it.
        segments, proofed = respell(segments, reference)

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
                  diarized=diarized, prompt=prompt, reference=proofed)



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
    if result.reference:
        # Kept with the entry and not only printed once: somebody coming back
        # in a month should be able to see that a text was used, how many
        # words it corrected, and how much of it turned up in the audio.
        entry.update(reference=result.reference)
    kinds, cue_list, problems = write_subtitles(entry, result, settings)
    if kinds:
        entry.update(subtitles={
            "formats": kinds, "cues": len(cue_list),
            "preset": subtitle_spec(settings).get("name"),
            # What a subtitler would object to, kept with the cues rather than
            # only printed once: the entry is what someone comes back to.
            "remarks": tally(problems),
            "timings": "measured" if timings_measured(result.segments)
                       else "interpolated",
        })
    return entry
