"""Transcribing a recording while it is still being made.

The recorder writes a WAV and brings its header up to date after every block,
so the file is at any moment a whole WAV of what has been said so far. This
reads it a piece at a time: once thirty seconds are waiting, it cuts them at
the quietest pause of their second half - between two sentences, with luck,
rather than inside a word - and hands the piece to the engine; what follows
the cut waits for the next piece. When the recording stops, what is left goes
through the same way, and all that remains is the part that needs the whole
recording at once: who said what, the drawing, the filing.

Nothing here knows which engine runs, or anything about Qt: the pipeline hands
in a function that transcribes one piece, and so do the tests.
"""
import threading
import wave

import numpy as np

from .audio import SAMPLE_RATE, load_audio
from .backends import models_kept

#: The longest piece: the window Whisper sees anyway. A longer one is cut
#: again inside the engine, and a shorter one costs as much to encode.
PIECE_SECONDS = 30.0

#: The shortest piece a cut may leave, so that a pause near the start does
#: not turn one piece into two half-empty ones.
MIN_PIECE_SECONDS = 15.0

#: How often the file is looked at while less than a piece is waiting.
POLL_SECONDS = 2.0

#: What is left when the recording stops, below which there is nothing to say.
TAIL_SECONDS = 0.3

#: How loud a moment is, is measured over this long...
FRAME_SECONDS = 0.02
#: ... and a pause is the quietest stretch this long.
PAUSE_SECONDS = 0.3

#: The stage shown while the recording is still going.
STAGE_LIVE = "stage.live"


class Growing:
    """A recording that is still being made, until :meth:`finish` says not."""

    def __init__(self):
        self._finished = threading.Event()

    def finish(self):
        self._finished.set()

    @property
    def finished(self):
        return self._finished.is_set()

    def wait(self, seconds):
        """Sleep for ``seconds``, or until the recording finishes."""
        self._finished.wait(seconds)


def recorded_seconds(path):
    """How much of the WAV at ``path`` has been written, from its header.

    ``0.0`` while there is no header yet to read."""
    try:
        with wave.open(path, "rb") as reader:
            return reader.getnframes() / float(reader.getframerate())
    except (OSError, EOFError, wave.Error):
        return 0.0


def quietest_cut(audio, low=MIN_PIECE_SECONDS, high=PIECE_SECONDS,
                 sample_rate=SAMPLE_RATE):
    """The sample to cut ``audio`` at: its quietest pause between ``low`` and
    ``high`` seconds, or its end when it is shorter than ``low``."""
    frame = int(FRAME_SECONDS * sample_rate)
    first = int(low * sample_rate)
    part = audio[first:int(high * sample_rate)]
    count = len(part) // frame
    if count == 0:
        return min(len(audio), int(high * sample_rate))
    energy = np.square(part[:count * frame].reshape(count, frame)).mean(axis=1)
    width = max(1, int(round(PAUSE_SECONDS / FRAME_SECONDS)))
    smoothed = np.convolve(energy, np.ones(width) / width, mode="same")
    return first + int(np.argmin(smoothed)) * frame + frame // 2


def transcribe_growing(path, growing, engine, language=None, progress=None,
                       poll=POLL_SECONDS):
    """Transcribe the WAV at ``path`` while it is written: ``(segments, text, info)``.

    ``engine(audio, language, model, progress)`` transcribes one piece and
    returns what :func:`audio_transcriber.transcription.transcribe` does. The
    first piece settles the model and, when none was given, the language, and
    every later piece is held to them: an "auto" worked out again on each one
    could change its mind halfway through a meeting - a second model loaded
    beside the first, a quiet piece of Italian heard as English.

    ``progress(percent, stage)`` is called while it waits and as each piece
    goes through, which is where a cancelled job stops. Until the recording
    stops the percentage is 0: nobody knows yet how long it will be."""
    report = progress or (lambda percent, stage=None: None)
    segments, texts, info, model = [], [], {}, None
    done = 0.0
    with models_kept():
        while True:
            # Read before the length, so that a finished recording's length
            # is its last one.
            finished = growing.finished
            total = recorded_seconds(path)
            waiting = total - done
            stage = None if finished else STAGE_LIVE
            percent = 100.0 * done / total if finished and total else 0.0
            if not finished and waiting < PIECE_SECONDS:
                report(percent, stage)
                growing.wait(poll)
                continue
            if finished and waiting < TAIL_SECONDS:
                break
            piece = load_audio(path, start=done, seconds=min(waiting, PIECE_SECONDS))
            if not len(piece):
                if finished:
                    break
                growing.wait(poll)
                continue
            if waiting > PIECE_SECONDS or not finished:
                piece = piece[:quietest_cut(piece)]
            heard, text, info = engine(
                piece, language, model,
                lambda _percent, engine_stage=None, percent=percent, stage=stage:
                    report(percent, engine_stage or stage))
            model = model or info.get("model")
            language = language or info.get("language")
            segments.extend(_later(segment, done) for segment in heard)
            if text.strip():
                texts.append(text.strip())
            done += len(piece) / float(SAMPLE_RATE)
    return segments, " ".join(texts), info


def _later(segment, offset):
    """``segment`` and its words moved ``offset`` seconds on."""
    moved = {**segment, "start": _plus(segment.get("start"), offset),
             "end": _plus(segment.get("end"), offset)}
    if segment.get("words"):
        moved["words"] = [{**word, "start": _plus(word.get("start"), offset),
                           "end": _plus(word.get("end"), offset)}
                          for word in segment["words"]]
    return moved


def _plus(value, offset):
    return None if value is None else value + offset
