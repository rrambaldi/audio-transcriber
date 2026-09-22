"""Measuring what a recording looks like.

Arithmetic on an array, so all of this runs anywhere: no ffmpeg, no model, no
microphone. What is checked is the contract the two interfaces draw against —
four hundred slices out of a thousand, a quiet passage that is still a number,
and a file that cannot be read coming back as nothing rather than as an exit.
"""
import numpy as np
import pytest

from audio_transcriber import waveform


def tone(seconds, rate=1000, amplitude=1.0):
    steps = np.arange(int(seconds * rate), dtype=np.float32)
    return (np.sin(steps / 3.0) * amplitude).astype(np.float32)


# --- the measurement ------------------------------------------------------

def test_a_recording_is_cut_into_the_same_number_of_slices_whatever_its_length():
    """A row is a row: the drawing is stretched to it, not the other way."""
    for seconds in (2, 20, 200):
        assert len(waveform.loudness(tone(seconds))) == waveform.SLICES


def test_a_full_scale_tone_measures_its_root_mean_square():
    """A sine filling the scale is 0.707 of it in RMS, which is the figure
    every meter that is not a peak meter shows."""
    found = waveform.loudness(tone(100, amplitude=1.0))
    assert max(found) == pytest.approx(707, abs=10)
    assert min(found) > 0


def test_a_quieter_recording_measures_quieter_in_proportion():
    loud = max(waveform.loudness(tone(100, amplitude=1.0)))
    quiet = max(waveform.loudness(tone(100, amplitude=0.25)))
    assert quiet == pytest.approx(loud / 4, rel=0.05)


def test_silence_measures_as_zero_and_not_as_nothing():
    """Nothing measured and measured-and-silent are different answers: the
    first has no drawing, the second is a line through the middle."""
    found = waveform.loudness(np.zeros(4000, dtype=np.float32))
    assert len(found) == waveform.SLICES
    assert set(found) == {0}


def test_one_bang_in_a_quiet_stretch_does_not_make_it_a_loud_stretch():
    """Why this is loudness and not the loudest instant. A slice of a
    nineteen-minute recording is three seconds long, and there is a cough or a
    hard consonant in almost every three seconds of anything: measured by its
    peak, the whole drawing came out a solid block."""
    quiet = np.zeros(400_000, dtype=np.float32)
    quiet[200_000] = 0.8
    found = waveform.loudness(quiet)
    assert max(found) < 50
    assert max(found) > 0                       # but it is not nothing either


def test_a_stretch_of_talking_reads_above_a_stretch_of_room():
    speech = np.concatenate([tone(1, amplitude=0.05),
                             np.zeros(1000, dtype=np.float32)])
    found = waveform.loudness(speech, slices=2)
    assert found[0] > found[1] == 0


def test_a_recording_shorter_than_the_slices_asked_for_gets_one_each():
    found = waveform.loudness(np.array([0.5, 1.0, 0.25], dtype=np.float32))
    assert found == [500, 1000, 250]


def test_nothing_at_all_measures_as_nothing_at_all():
    assert waveform.loudness(np.zeros(0, dtype=np.float32)) == []


def test_something_that_is_not_audio_is_not_a_crash():
    """A picture must never be the reason a transcription fails: the pipeline
    measures the array it has just decoded, and a fake one in a test — or a
    backend that hands back something odd — has to pass straight through."""
    assert waveform.loudness(object()) == []


def test_a_sample_out_of_range_is_held_to_the_scale():
    found = waveform.loudness(np.array([4.0, -9.0], dtype=np.float32))
    assert found == [waveform.SCALE, waveform.SCALE]


# --- reading one off a file ------------------------------------------------

def test_a_file_that_cannot_be_read_leaves_the_row_without_a_drawing(tmp_path):
    """load_audio reports failure by leaving through sys.exit. Here that has
    to become None: the row simply has no picture under its name."""
    missing = tmp_path / "gone.wav"
    assert waveform.loudness_of_file(str(missing)) is None


def test_a_file_that_is_not_audio_leaves_the_row_without_a_drawing(tmp_path):
    rubbish = tmp_path / "notes.txt"
    rubbish.write_text("this is not a recording")
    assert waveform.loudness_of_file(str(rubbish)) is None


# --- the live trace --------------------------------------------------------

def test_the_trace_holds_five_seconds_however_long_a_block_is():
    """The block length is a parameter, so the number of them is not."""
    assert waveform.trail_length(0.1) == 50
    assert waveform.trail_length(0.05) == 100
    assert waveform.trail_length(0.5) == 10


# --- what goes on disk -----------------------------------------------------

def test_what_is_written_can_be_read_back(tmp_path):
    path = tmp_path / "waveform.json"
    path.write_text(waveform.as_document([1, 2, 3]))
    assert waveform.read_file(str(path)) == [1, 2, 3]


def test_a_missing_or_broken_file_is_no_drawing_rather_than_an_error(tmp_path):
    assert waveform.read_file(str(tmp_path / "absent.json")) is None
    broken = tmp_path / "waveform.json"
    broken.write_text("{ not json at all")
    assert waveform.read_file(str(broken)) is None
    wrong = tmp_path / "wrong.json"
    wrong.write_text('{"schema": 1, "loudness": "all of them"}')
    assert waveform.read_file(str(wrong)) is None
