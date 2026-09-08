"""The recording engine: enumeration, mixing, and what lands in the WAV.

Both audio libraries are replaced by fakes here, so these tests need no
microphone, no PortAudio and no sound server — which is what lets them run on
the server as well as on the machine the window is used from. What is checked
is everything that is ours: how the two menus are built, how a four-channel
array becomes mono, how two sources with two clocks are kept together, and
that a stopped recording leaves a readable file behind."""
import time
import wave

import numpy as np
import pytest

from audio_fakes import FakeEngine, FakeStream
from audio_fakes import audio_source as source
from audio_transcriber import recording


def wait_until(condition, timeout=5.0):
    """Wait for the worker thread, with a deadline: a hung test is worse than
    a failing one, and this suite has to stay a few seconds long."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.001)
    raise AssertionError("the recording never got there")


# --- the menus ------------------------------------------------------------

def test_the_two_menus_keep_the_host_api_order_portaudio_reports():
    """It is the order Audacity shows, and people navigate menus by memory."""
    mme = source(key="portaudio:0:Mic", host_api="MME")
    wasapi = source(key="portaudio:2:Mic", host_api="Windows WASAPI")
    loopback = source(key="wasapi:loopback:Speakers", host_api="Windows WASAPI",
                      kind=recording.LOOPBACK, engine=recording.WASAPI)
    backends = (FakeEngine(recording.PORTAUDIO, [mme, wasapi]),
                FakeEngine(recording.WASAPI, [loopback]))
    assert recording.host_apis(backends) == [
        ("MME", [mme]),
        ("Windows WASAPI", [wasapi, loopback]),
    ]


def test_a_missing_library_costs_its_own_sources_and_nothing_else():
    """No soundcard means no loopbacks; the microphones are still there."""
    mic = source()
    backends = (FakeEngine(recording.PORTAUDIO, [mic]),
                FakeEngine(recording.WASAPI, [source(kind=recording.LOOPBACK)],
                           available=False))
    assert recording.sources(backends) == [mic]
    assert recording.available(backends) is True


def test_an_engine_that_fails_to_enumerate_does_not_empty_the_menu():
    class Broken(FakeEngine):
        def sources(self):
            raise OSError("the audio stack said no")

    mic = source()
    backends = (FakeEngine(recording.PORTAUDIO, [mic]),
                Broken(recording.WASAPI))
    assert recording.sources(backends) == [mic]


def test_neither_library_means_nothing_can_be_recorded():
    backends = (FakeEngine(recording.PORTAUDIO, available=False),
                FakeEngine(recording.WASAPI, available=False))
    assert recording.available(backends) is False
    assert recording.sources(backends) == []


def test_a_remembered_device_that_is_gone_resolves_to_nothing():
    """The choice is stored between sessions, and a USB microphone travels."""
    backends = (FakeEngine(recording.PORTAUDIO, [source()]),
                FakeEngine(recording.WASAPI))
    assert recording.find("portaudio:0:Mic", backends) is not None
    assert recording.find("portaudio:9:Gone", backends) is None


def test_loopback_sources_say_that_is_what_they_are():
    assert source(kind=recording.LOOPBACK).is_loopback is True
    assert source().is_loopback is False


# --- turning what a device gives into what a WAV holds --------------------

def test_a_microphone_array_is_averaged_not_cropped():
    """Four microphones with one channel picked would throw away the room."""
    block = np.array([[1.0, 0.0, 0.0, 0.0], [0.5, 0.5, 0.5, 0.5]], dtype=np.float32)
    assert recording.to_mono(block).tolist() == [0.25, 0.5]


def test_mono_stays_mono_whatever_shape_it_arrives_in():
    assert recording.to_mono(np.array([0.5, -0.5], dtype=np.float32)).tolist() == [0.5, -0.5]
    assert recording.to_mono(np.array([[0.5], [-0.5]], dtype=np.float32)).tolist() == [0.5, -0.5]


def test_samples_are_clipped_before_they_wrap_around():
    """Adding two sources can exceed full scale, and int16 wraps: 1.2 would
    come back as a loud crack instead of a loud voice."""
    pcm = recording.to_pcm16(np.array([0.0, 1.0, -1.0, 1.4, -1.4], dtype=np.float32))
    assert pcm.tolist() == [0, 32767, -32767, 32767, -32767]


# --- mixing two clocks ----------------------------------------------------

def test_mixing_adds_the_two_sources():
    mixed = recording.mix(np.array([0.1, 0.2], dtype=np.float32),
                          np.array([0.3, 0.4], dtype=np.float32))
    assert np.allclose(mixed, [0.4, 0.6])


def test_a_short_second_source_is_padded_not_stretched():
    """The primary sets the clock: a gap is honest, a stretch is not."""
    mixed = recording.mix(np.array([0.1, 0.1, 0.1], dtype=np.float32),
                          np.array([0.2], dtype=np.float32))
    assert np.allclose(mixed, [0.3, 0.1, 0.1])


def test_a_long_second_source_is_cut_to_the_primary():
    mixed = recording.mix(np.array([0.1], dtype=np.float32),
                          np.array([0.2, 0.9, 0.9], dtype=np.float32))
    assert np.allclose(mixed, [0.3])


def test_a_missing_second_source_leaves_the_primary_alone():
    primary = np.array([0.1, 0.2], dtype=np.float32)
    assert np.allclose(recording.mix(primary, None), primary)
    assert np.allclose(recording.mix(primary, np.zeros(0, dtype=np.float32)), primary)


# --- recording ------------------------------------------------------------

def read_wav(path):
    with wave.open(str(path), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
        return {"channels": handle.getnchannels(), "width": handle.getsampwidth(),
                "rate": handle.getframerate(),
                "samples": np.frombuffer(frames, dtype="<i2")}


def test_a_recording_writes_a_mono_wav_at_the_devices_rate(tmp_path):
    mic = source(samplerate=44100)
    block = np.full((4410, 1), 0.5, dtype=np.float32)
    engine = FakeEngine(recording.PORTAUDIO, [mic], stream=FakeStream([block]))
    session = recording.Recording(str(tmp_path / "a.wav"), mic,
                                  backends=(engine, FakeEngine(recording.WASAPI)))
    session.start()
    wait_until(lambda: session.frames >= 4410)
    path = session.stop()

    written = read_wav(path)
    assert written["channels"] == 1 and written["width"] == 2
    assert written["rate"] == 44100
    assert written["samples"][0] == int(0.5 * 32767)
    assert engine.opened == [(mic, 1, 44100)]


def test_a_recording_that_captured_nothing_leaves_no_file_behind(tmp_path):
    """An empty WAV is not a recording of silence, it is a failure to record,
    and it should not sit in the cache directory waiting to be transcribed."""
    class Silent(FakeStream):
        def read(self, frames):
            raise OSError("the device went away")

    mic = source()
    engine = FakeEngine(recording.PORTAUDIO, [mic], stream=Silent())
    target = tmp_path / "empty.wav"
    session = recording.Recording(str(target), mic,
                                  backends=(engine, FakeEngine(recording.WASAPI)))
    session.start()
    assert session.stop() is None
    assert not target.exists()
    assert "went away" in session.error


def test_a_device_that_will_not_open_says_so_before_the_meeting(tmp_path):
    class Refusing(FakeEngine):
        def open(self, *args):
            raise OSError("Invalid number of channels")

    mic = source()
    session = recording.Recording(str(tmp_path / "a.wav"), mic,
                                  backends=(Refusing(recording.PORTAUDIO, [mic]),
                                            FakeEngine(recording.WASAPI)))
    with pytest.raises(recording.RecordingError) as raised:
        session.start()
    assert "Invalid number of channels" in str(raised.value)
    assert not (tmp_path / "a.wav").exists()


def test_the_two_sources_of_a_mix_are_both_opened_at_the_primarys_rate(tmp_path):
    """A loopback resamples for us; a microphone opened at another rate would
    make the two impossible to add together."""
    mic = source(samplerate=44100)
    speakers = source(key="wasapi:loopback:Speakers", kind=recording.LOOPBACK,
                      engine=recording.WASAPI, channels=2, samplerate=48000)
    portaudio = FakeEngine(recording.PORTAUDIO, [mic],
                           stream=FakeStream([np.full((10, 1), 0.25, dtype=np.float32)]))
    wasapi = FakeEngine(recording.WASAPI, [speakers],
                        stream=FakeStream(ready=[np.full((10, 2), 0.25, dtype=np.float32)]))
    session = recording.Recording(str(tmp_path / "mix.wav"), mic, mix_with=speakers,
                                  backends=(portaudio, wasapi), block_seconds=10 / 44100)
    session.start()
    wait_until(lambda: session.frames >= 10)
    session.stop()

    assert portaudio.opened == [(mic, 1, 44100)]
    assert wasapi.opened == [(speakers, 2, 44100)]
    assert read_wav(tmp_path / "mix.wav")["samples"][0] == int(0.5 * 32767)


def test_a_stopped_recording_closes_every_device(tmp_path):
    mic = source()
    stream = FakeStream()
    session = recording.Recording(str(tmp_path / "a.wav"), mic,
                                  backends=(FakeEngine(recording.PORTAUDIO, [mic],
                                                       stream=stream),
                                            FakeEngine(recording.WASAPI)))
    session.start()
    wait_until(lambda: session.frames >= 1)
    session.stop()
    assert stream.closed is True
    assert session.running is False


def test_a_paused_recording_keeps_the_devices_but_writes_nothing(tmp_path):
    mic = source()
    session = recording.Recording(str(tmp_path / "a.wav"), mic,
                                  backends=(FakeEngine(recording.PORTAUDIO, [mic]),
                                            FakeEngine(recording.WASAPI)))
    session.start()
    wait_until(lambda: session.frames >= 1)
    session.pause()
    assert session.paused is True
    time.sleep(0.05)                 # let the block already in flight land
    written = session.frames
    time.sleep(0.05)                 # and now nothing more may be written
    assert session.frames == written, "a paused recording kept writing"
    session.resume()
    assert session.paused is False
    session.stop()


def test_the_elapsed_time_counts_what_was_written_not_wall_clock(tmp_path):
    """It is the length of the recording, so a pause has to stop it."""
    mic = source(samplerate=1000)
    engine = FakeEngine(recording.PORTAUDIO, [mic],
                        stream=FakeStream([np.zeros((500, 1), dtype=np.float32)]))
    session = recording.Recording(str(tmp_path / "a.wav"), mic,
                                  backends=(engine, FakeEngine(recording.WASAPI)),
                                  block_seconds=0.5)
    session.start()
    wait_until(lambda: session.frames >= 500)
    assert session.elapsed_seconds >= 0.5
    session.stop()


def test_starting_twice_is_refused(tmp_path):
    mic = source()
    session = recording.Recording(str(tmp_path / "a.wav"), mic,
                                  backends=(FakeEngine(recording.PORTAUDIO, [mic]),
                                            FakeEngine(recording.WASAPI)))
    session.start()
    with pytest.raises(recording.RecordingError):
        session.start()
    session.stop()
