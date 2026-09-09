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


# --- is anything arriving? ------------------------------------------------

def test_the_peak_of_a_block_is_the_loudest_sample_in_it():
    assert recording.peak(np.array([0.0, -0.4, 0.2], dtype=np.float32)) == pytest.approx(0.4)
    assert recording.peak(np.zeros(0, dtype=np.float32)) == 0.0
    assert recording.peak(None) == 0.0


# --- does it sound like speech? -------------------------------------------
#
# Synthetic signals rather than a recording of a voice: the point is to pin
# down what the heuristic distinguishes, and a fan, a tone and a hiss are
# exactly the things a level meter cannot tell from speech.

RATE = 48000
BLOCK = int(RATE * 0.1)


def band_noise(rng, frames=BLOCK, low=300, high=3400, level=0.1):
    """White noise with everything outside a speech band taken out."""
    spectrum = np.fft.rfft(rng.standard_normal(frames))
    frequencies = np.fft.rfftfreq(frames, 1 / RATE)
    spectrum[(frequencies < low) | (frequencies > high)] = 0
    shaped = np.fft.irfft(spectrum, frames)
    return (shaped / (np.abs(shaped).max() or 1) * level).astype(np.float32)


def tone(hz, level, index=0, frames=BLOCK):
    moment = (np.arange(frames) + index * frames) / RATE
    return (level * np.sin(2 * np.pi * hz * moment)).astype(np.float32)


def verdict_of(blocks):
    probe = recording.SpeechProbe(RATE)
    for block in blocks:
        probe.add(block)
    return probe.measure()


def test_digital_silence_reads_as_silence():
    assert verdict_of([np.zeros(BLOCK, dtype=np.float32)] * 60)[0] == recording.SILENCE


def test_a_quiet_room_reads_as_silence():
    rng = np.random.default_rng(1)
    room = [(rng.standard_normal(BLOCK) * 0.0003).astype(np.float32) for _ in range(60)]
    assert verdict_of(room)[0] == recording.SILENCE


def test_a_steady_tone_is_sound_but_not_speech():
    """A level meter cannot tell this from a voice. Speech pauses; a tone
    does not, and that is the whole difference being measured."""
    assert verdict_of([tone(1000, 0.1, i) for i in range(60)])[0] == recording.SOUND


def test_mains_hum_is_sound_but_not_speech():
    assert verdict_of([tone(50, 0.05, i) for i in range(60)])[0] == recording.SOUND


def test_constant_noise_inside_the_speech_band_is_still_not_speech():
    """The band alone proves nothing: this sits right where a voice sits and
    is rejected on its lack of pauses."""
    rng = np.random.default_rng(2)
    steady = [band_noise(rng, level=0.15) for _ in range(60)]
    assert verdict_of(steady)[0] == recording.SOUND


def test_bursts_and_pauses_in_the_speech_band_are_speech():
    rng = np.random.default_rng(3)
    blocks = []
    for index in range(60):
        room = (rng.standard_normal(BLOCK) * 0.001).astype(np.float32)
        talking = (index % 9) < 5
        blocks.append(band_noise(rng, level=0.15) + room if talking else room)
    verdict, detail = verdict_of(blocks)
    assert verdict == recording.SPEECH
    assert detail["dynamic_db"] > recording.MIN_DYNAMIC_DB
    assert detail["band_ratio"] > recording.MIN_BAND_RATIO


def test_quiet_distant_speech_is_still_speech():
    """Someone across the room, at a tenth of the level: the verdict must not
    depend on standing over the microphone."""
    rng = np.random.default_rng(4)
    blocks = []
    for index in range(60):
        room = (rng.standard_normal(BLOCK) * 0.0005).astype(np.float32)
        blocks.append(band_noise(rng, level=0.02) + room if (index % 9) < 5 else room)
    assert verdict_of(blocks)[0] == recording.SPEECH


def test_speech_without_long_pauses_is_still_speech():
    """Reading aloud without stopping: the pauses are between syllables, and
    that is why the threshold is six decibels and not twelve."""
    rng = np.random.default_rng(5)
    blocks = []
    for index in range(60):
        moment = (np.arange(BLOCK) + index * BLOCK) / RATE
        syllables = 0.55 + 0.45 * np.sin(2 * np.pi * 4.0 * moment)
        blocks.append((band_noise(rng, level=0.15) * syllables).astype(np.float32))
    assert verdict_of(blocks)[0] == recording.SPEECH


def test_speech_over_a_noisy_room_is_still_speech():
    rng = np.random.default_rng(6)
    blocks = []
    for index in range(60):
        air_conditioning = (rng.standard_normal(BLOCK) * 0.004).astype(np.float32)
        talking = (index % 9) < 5
        blocks.append(band_noise(rng, level=0.12) + air_conditioning
                      if talking else air_conditioning)
    assert verdict_of(blocks)[0] == recording.SPEECH


def test_half_a_second_is_not_enough_to_judge():
    """A pause between two words looks exactly like a dead microphone."""
    verdict, detail = verdict_of([np.zeros(BLOCK, dtype=np.float32)] * 5)
    assert verdict is None and detail["ready"] is False


def test_the_verdict_follows_the_last_few_seconds():
    """Point the microphone at something else and the answer has to change,
    without a minute of history outvoting it."""
    rng = np.random.default_rng(8)
    probe = recording.SpeechProbe(RATE)
    for _ in range(120):
        probe.add(np.zeros(BLOCK, dtype=np.float32))
    assert probe.measure()[0] == recording.SILENCE
    for index in range(60):
        room = (rng.standard_normal(BLOCK) * 0.001).astype(np.float32)
        probe.add(band_noise(rng, level=0.15) + room if (index % 9) < 5 else room)
    assert probe.measure()[0] == recording.SPEECH


def test_the_speech_band_ratio_measures_what_it_says():
    rng = np.random.default_rng(9)
    assert recording.band_ratio(band_noise(rng), RATE) > 0.9
    assert recording.band_ratio(tone(50, 0.5), RATE) < 0.1
    assert recording.band_ratio(np.zeros(BLOCK, dtype=np.float32), RATE) == 0.0


def test_loudness_in_decibels_has_a_floor_instead_of_an_infinity():
    assert recording.rms_db(np.zeros(BLOCK, dtype=np.float32)) == -120.0
    assert recording.rms_db(np.full(BLOCK, 1.0, dtype=np.float32)) == pytest.approx(0.0)


# --- monitoring: the meters without a file --------------------------------

def test_monitoring_holds_the_devices_and_writes_nothing(tmp_path):
    """What "test audio" does: the levels move, and nothing is kept."""
    mic = source(samplerate=1000)
    stream = FakeStream(fill=0.3)
    monitor = recording.Monitor(
        mic, backends=(FakeEngine(recording.PORTAUDIO, [mic], stream=stream),
                       FakeEngine(recording.WASAPI)),
        block_seconds=0.05)
    monitor.start()
    wait_until(lambda: monitor.levels[0] > 0)
    assert monitor.levels[0] == pytest.approx(0.3)
    monitor.stop()
    assert stream.closed is True
    assert monitor.running is False
    assert list(tmp_path.iterdir()) == []          # nothing written anywhere


def test_monitoring_reaches_a_verdict_about_what_it_hears(tmp_path):
    mic = source(samplerate=RATE)
    rng = np.random.default_rng(11)
    blocks = []
    for index in range(80):
        room = (rng.standard_normal(BLOCK) * 0.001).astype(np.float32)
        talking = (index % 9) < 5
        blocks.append((band_noise(rng, level=0.15) + room if talking
                       else room).reshape(-1, 1))
    monitor = recording.Monitor(
        mic, backends=(FakeEngine(recording.PORTAUDIO, [mic],
                                  stream=FakeStream(blocks=blocks, pace=0.001)),
                       FakeEngine(recording.WASAPI)))
    monitor.start()
    wait_until(lambda: monitor.measure()[0] == recording.SPEECH)
    monitor.stop()


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


def test_the_levels_are_measured_per_source(tmp_path):
    """One level per source, not one for the mix: a loopback that gives
    nothing has to be visible next to a microphone that works."""
    mic = source(samplerate=1000)
    speakers = source(key="wasapi:loopback:S", kind=recording.LOOPBACK,
                      engine=recording.WASAPI, channels=2, samplerate=1000)
    loud = FakeStream(fill=0.5)
    quiet = FakeStream(ready=[np.zeros((100, 2), dtype=np.float32)] * 50)
    session = recording.Recording(
        str(tmp_path / "a.wav"), mic, mix_with=speakers,
        backends=(FakeEngine(recording.PORTAUDIO, [mic], stream=loud),
                  FakeEngine(recording.WASAPI, [speakers], stream=quiet)),
        block_seconds=0.1)
    session.start()
    wait_until(lambda: session.frames >= 100)
    assert session.levels[0] == pytest.approx(0.5)
    assert session.levels[1] == 0.0          # the loopback is not delivering
    session.stop()


def test_a_recording_that_never_rose_above_silence_says_so(tmp_path):
    """A muted microphone writes a valid file full of zeros, which Whisper
    then transcribes into nothing at all."""
    mic = source(samplerate=1000)
    session = recording.Recording(
        str(tmp_path / "a.wav"), mic,
        backends=(FakeEngine(recording.PORTAUDIO, [mic],
                             stream=FakeStream(fill=0.0)),
                  FakeEngine(recording.WASAPI)),
        block_seconds=0.05)
    session.start()
    wait_until(lambda: session.frames >= 50)
    session.stop()
    assert session.silent is True


def test_a_recording_with_something_in_it_is_not_called_silent(tmp_path):
    mic = source(samplerate=1000)
    session = recording.Recording(
        str(tmp_path / "a.wav"), mic,
        backends=(FakeEngine(recording.PORTAUDIO, [mic],
                             stream=FakeStream(fill=0.2)),
                  FakeEngine(recording.WASAPI)),
        block_seconds=0.05)
    session.start()
    wait_until(lambda: session.frames >= 50)
    session.stop()
    assert session.silent is False


def test_nothing_recorded_at_all_is_not_reported_as_silence(tmp_path):
    """"Silent" is a judgement about audio that arrived; a device that never
    delivered a frame is a different failure, and has its own message."""
    mic = source()
    session = recording.Recording(
        str(tmp_path / "a.wav"), mic,
        backends=(FakeEngine(recording.PORTAUDIO, [mic]),
                  FakeEngine(recording.WASAPI)))
    assert session.silent is False


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
