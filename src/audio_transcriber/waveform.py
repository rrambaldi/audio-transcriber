"""The shape of a recording: how loud it was, moment by moment.

Two drawings are made from what is in here, and they are the same drawing at
two lengths. While a recording is being made, the last few seconds of it
scroll past next to the level meter: a bar sitting at one height and a bar
moving with every syllable are told apart at a glance, and a clock counting up
tells them apart not at all. And under the name of a recording already filed,
the whole of it at once, which is what distinguishes an hour of meeting from
an hour of empty room before anybody opens either.

What is measured of a whole recording is the *loudness* of each slice — the
root mean square — and not its loudest instant. The loudest instant was the
first attempt and it is worth saying why it failed: over four hundred slices a
nineteen-minute recording gets three seconds each, and there is a bang, a
cough or a hard consonant in almost every three seconds of anything. The
picture came out a solid block. Over a tenth of a second, which is what the
live trace holds, the peak *is* the shape, and it is also exactly what the
level meter beside it is showing — so the trace keeps it.

Either way the number is a level from 0 to :data:`SCALE`, and what is *drawn*
is that level in decibels, floored at -60 dBFS, by the two functions the level
meters already use (``gui.options.level_percent`` and ``levelPercent`` in the
page). A linear drawing of speech would barely leave the axis — talking sits
around a hundredth of full scale in RMS — so the reading has to be
logarithmic; the measurement stored on disk stays the plain one, and the one
scale rule lives in one place instead of being baked into the file.
"""
import json
import subprocess
import threading

import numpy as np

from . import audio

#: How many slices one drawing is cut into. Four hundred is more columns than
#: any row is pixels wide, so the picture is stretched down rather than up,
#: and it is under two kilobytes of JSON.
SLICES = 400

#: Levels are whole numbers out of this. A thousand makes the floor of the
#: meter — -60 dBFS, a thousandth of full scale — exactly 1 rather than a
#: rounding error.
SCALE = 1000

#: How much of the recent past the live trace holds.
TRAIL_SECONDS = 5.0

#: What a whole file is measured at. The drawing does not need
#: sixteen thousand samples a second, and an hour of audio is 57 MB at this
#: rate against 230 MB at the transcription's — which matters on a machine
#: with under two gigabytes free. Resampling is a low-pass, so a peak measured
#: here can sit a hair under one measured at the full rate; over a slice of a
#: long recording the difference does not reach a pixel.
MEASURE_RATE = 4000

#: Version of the ``waveform.json`` written beside an entry.
SCHEMA = 1


def loudness(samples, slices=SLICES, scale=SCALE):
    """How loud each of ``slices`` equal stretches was, 0..``scale``.

    The root mean square of each stretch: what it sounded like over that
    second or three, rather than the single loudest sample in it. Pure
    arithmetic on an array — no file, no ffmpeg, no model — which is what
    makes it testable anywhere. A recording shorter than the number of slices
    asked for gets one slice per sample and is stretched when it is drawn.

    Anything that is not a run of numbers measures as nothing rather than
    raising: this is a picture, and a picture must never be the reason a
    transcription fails."""
    try:
        data = np.asarray(samples, dtype=np.float32).reshape(-1)
    except (TypeError, ValueError):
        return []
    if not data.size:
        return []
    slices = max(1, min(int(slices), int(data.size)))
    # Slice starts. With at least one sample per slice the floors are strictly
    # increasing, which is what reduceat needs: a repeated index there would
    # quietly hand back one sample instead of the sum over a stretch.
    edges = np.linspace(0, data.size, slices, endpoint=False).astype(np.intp)
    squares = np.add.reduceat(np.square(data, dtype=np.float64), edges)
    counts = np.diff(np.append(edges, data.size))
    found = np.sqrt(squares / np.maximum(counts, 1))
    found = np.nan_to_num(found, nan=0.0, posinf=1.0, neginf=0.0)
    return [int(value) for value in np.rint(np.clip(found, 0.0, 1.0) * scale)]


def loudness_of_file(path, slices=SLICES, sample_rate=MEASURE_RATE):
    """The shape of a whole recording, or ``None`` if it cannot be read.

    ``None`` and not an exception on purpose. Everything below reports a
    failure by leaving through :func:`sys.exit` — see ``audio.load_audio`` —
    and a picture that cannot be drawn must not take the program with it: the
    row simply has no drawing under its name."""
    try:
        samples = audio.load_audio(str(path), sample_rate=sample_rate)
    except (SystemExit, OSError, ValueError, subprocess.SubprocessError):
        return None
    found = loudness(samples, slices)
    return found or None


#: One measurement at a time. Two ffmpeg runs on two cores do not finish any
#: sooner than one after the other, and this machine has a transcription to
#: get on with.
_MEASURING = threading.Lock()


def entry_loudness(entry, measure=True):
    """What a library entry looks like, measuring it once if nobody has yet.

    ``measure=False`` answers only from what is already on disk, which is what
    a list of forty entries wants: an index page must not decode forty
    recordings to draw itself.

    An entry filed with ``--library-store reference`` keeps its recording
    somewhere else, and ``stored_audio`` refuses it on purpose; such an entry
    has no drawing, and that is the honest answer rather than a guess."""
    stored = entry.read_waveform()
    if stored is not None or not measure:
        return stored
    source = entry.stored_audio()
    if not source:
        return None
    with _MEASURING:
        # Somebody may have measured it while this call waited for the lock.
        stored = entry.read_waveform()
        if stored is not None:
            return stored
        found = loudness_of_file(source)
        if found:
            entry.write_waveform(found)
        return found


def trail_length(block_seconds, seconds=TRAIL_SECONDS):
    """How many capture blocks make up :data:`TRAIL_SECONDS` of trace.

    Taken from the block length rather than assumed, because the block length
    is a parameter: a capture opened with 50 ms blocks needs twice as many of
    them to hold the same five seconds."""
    return max(1, int(round(seconds / max(float(block_seconds), 0.001))))


def read_file(path):
    """The levels written at ``path``, or ``None``: the file is optional."""
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return None
    found = payload.get("loudness") if isinstance(payload, dict) else payload
    if not isinstance(found, list):
        return None
    return [int(value) for value in found if isinstance(value, (int, float))]


def as_document(found, scale=SCALE):
    """What goes into ``waveform.json``: the levels, and what they are out of."""
    return json.dumps({"schema": SCHEMA, "scale": scale, "loudness": list(found)})
