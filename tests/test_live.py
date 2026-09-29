"""Transcribing a recording while it is still being written.

The engine is a fake that notes every piece it is handed; the recording is a
real WAV, written with the same module the recorder uses and read back through
the same ffmpeg the pipeline uses, because the header that grows under the
reader is the thing being tested."""
import threading
import time
import wave

import numpy as np
import pytest

from audio_transcriber import live
from audio_transcriber.audio import SAMPLE_RATE

#: The rate a sound card records at; the pieces come back at 16 kHz.
DEVICE_RATE = 48000


def tone(seconds, rate=DEVICE_RATE, level=0.3):
    samples = np.arange(int(seconds * rate)) / rate
    return (level * np.sin(2 * np.pi * 220 * samples)).astype(np.float32)


def speech_with_pauses(seconds, pause_every=10.0, pause=0.6, rate=DEVICE_RATE):
    """A tone that stops for ``pause`` seconds every ``pause_every``."""
    audio = tone(seconds, rate)
    for start in np.arange(pause_every, seconds, pause_every):
        audio[int(start * rate):int((start + pause) * rate)] = 0.0
    return audio


def pcm16(audio):
    return (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()


def write_wav(path, audio, rate=DEVICE_RATE):
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(pcm16(audio))


class Engine:
    """Says one sentence a piece, and keeps what it was handed."""

    def __init__(self, info=None):
        self.pieces = []
        self.info = info or {"backend": "fake", "device": "CPU", "model": "small",
                             "model_dir": "", "language": "it"}

    def __call__(self, audio, language, model, progress=None):
        self.pieces.append({"samples": len(audio), "language": language,
                            "model": model})
        if progress is not None:
            progress(50)
        seconds = len(audio) / SAMPLE_RATE
        segment = {"text": f"piece {len(self.pieces)}", "start": 1.0,
                   "end": seconds - 1.0,
                   "words": [{"word": "piece", "start": 1.0, "end": 1.5}]}
        return [segment], segment["text"], dict(self.info)


def finished():
    growing = live.Growing()
    growing.finish()
    return growing


def test_the_cut_falls_in_the_pause():
    audio = tone(30, SAMPLE_RATE)
    audio[int(22 * SAMPLE_RATE):int(22.5 * SAMPLE_RATE)] = 0.0
    cut = live.quietest_cut(audio)
    assert 22 * SAMPLE_RATE <= cut <= 22.5 * SAMPLE_RATE


def test_a_piece_shorter_than_the_shortest_cut_is_taken_whole():
    audio = tone(10, SAMPLE_RATE)
    assert live.quietest_cut(audio) == len(audio)


def test_a_file_with_no_header_yet_has_nothing_recorded(tmp_path):
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    assert live.recorded_seconds(str(empty)) == 0.0
    assert live.recorded_seconds(str(tmp_path / "missing.wav")) == 0.0


def test_a_finished_recording_is_cut_into_pieces_that_cover_it_once(tmp_path):
    path = tmp_path / "meeting.wav"
    write_wav(path, speech_with_pauses(75))
    engine = Engine()

    segments, text, info = live.transcribe_growing(str(path), finished(), engine)

    lengths = [piece["samples"] / SAMPLE_RATE for piece in engine.pieces]
    assert all(length <= live.PIECE_SECONDS + 0.01 for length in lengths)
    assert all(length >= live.MIN_PIECE_SECONDS for length in lengths[:-1])
    # Every second of it, and no second twice.
    assert sum(lengths) == pytest.approx(75, abs=0.05)
    assert text == " ".join(f"piece {n}" for n in range(1, len(lengths) + 1))
    assert info["model"] == "small"
    # Each piece's times are on the recording's clock, not the piece's.
    starts = np.cumsum([0.0] + lengths[:-1])
    for segment, offset in zip(segments, starts, strict=True):
        assert segment["start"] == pytest.approx(offset + 1.0)
        assert segment["words"][0]["start"] == pytest.approx(offset + 1.0)


def test_the_first_piece_settles_the_model_and_the_language(tmp_path):
    """An "auto" worked out again on every piece could load a second model
    halfway through a meeting, or hear a quiet piece of Italian as English."""
    path = tmp_path / "meeting.wav"
    write_wav(path, speech_with_pauses(65))
    engine = Engine()

    live.transcribe_growing(str(path), finished(), engine, language=None)

    assert engine.pieces[0]["model"] is None and engine.pieces[0]["language"] is None
    assert all(piece["model"] == "small" and piece["language"] == "it"
               for piece in engine.pieces[1:])


def test_a_recording_is_transcribed_while_it_grows(tmp_path):
    """The recorder's own way of writing: one block at a time, the header
    brought up to date after each, and the end said separately."""
    path = tmp_path / "meeting.wav"
    audio = speech_with_pauses(70)
    growing = live.Growing()
    engine = Engine()
    seen_while_recording = []

    def record():
        with wave.open(str(path), "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(DEVICE_RATE)
            block = DEVICE_RATE * 5
            for start in range(0, len(audio), block):
                writer.writeframes(pcm16(audio[start:start + block]))
                time.sleep(0.05)
            # Still recording: the first pieces have to go through now, not
            # once the stop is pressed.
            deadline = time.time() + 20
            while not engine.pieces and time.time() < deadline:
                time.sleep(0.01)
            seen_while_recording.append(len(engine.pieces))
        growing.finish()

    recorder = threading.Thread(target=record)
    recorder.start()
    segments, _text, _info = live.transcribe_growing(str(path), growing, engine,
                                                     poll=0.01)
    recorder.join()

    assert seen_while_recording[0] >= 1          # work done before the stop
    lengths = [piece["samples"] / SAMPLE_RATE for piece in engine.pieces]
    assert sum(lengths) == pytest.approx(70, abs=0.05)
    assert len(segments) == len(engine.pieces)


def test_until_the_recording_stops_it_reports_no_percentage(tmp_path):
    """Nobody knows how long a meeting will be while it is going."""
    path = tmp_path / "meeting.wav"
    write_wav(path, speech_with_pauses(40))
    growing = live.Growing()
    reported = []

    def progress(percent, stage=None):
        reported.append((percent, stage))
        if len(reported) == 3:
            growing.finish()

    live.transcribe_growing(str(path), growing, Engine(), progress=progress, poll=0.01)

    live_marks = [mark for mark in reported if mark[1] == live.STAGE_LIVE]
    assert live_marks and all(percent == 0 for percent, _stage in live_marks)
    assert reported[-1][1] is None and reported[-1][0] > 0


def test_a_cancelled_job_stops_between_pieces(tmp_path):
    path = tmp_path / "meeting.wav"
    write_wav(path, speech_with_pauses(90))
    engine = Engine()

    class Stop(Exception):
        pass

    def progress(percent, stage=None):
        if engine.pieces:
            raise Stop

    with pytest.raises(Stop):
        live.transcribe_growing(str(path), finished(), engine, progress=progress)
    assert len(engine.pieces) == 1
