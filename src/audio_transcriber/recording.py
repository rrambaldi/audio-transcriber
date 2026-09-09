"""Recording from this machine's own audio devices.

Qt offers the flat list of inputs its backend happens to expose: no host API to
choose, and no way to record what the speakers are playing. Both matter. A
meeting held over Teams is only half recorded if the other participants are
missing, and which host API a device is opened through is exactly the choice
Audacity puts in front of people who have a reason to care.

So recording has a second, optional engine. It needs two libraries, because on
Windows no single one does both:

``sounddevice`` (PortAudio)
    the host APIs — MME, DirectSound, WASAPI, WDM-KS — and their input
    devices: the same enumeration Audacity shows, because it is the same
    PortAudio.
``soundcard`` (the platform's own audio API)
    the *loopback* of an output device, which the PortAudio build shipped in
    the wheel does not expose — it refuses to open a render endpoint as an
    input. This one goes to the platform directly: on Windows it opens the
    endpoint with ``AUDCLNT_STREAMFLAGS_LOOPBACK``, on Linux it records a
    PulseAudio monitor source, and on macOS it does not, because Core Audio
    has no loopback without a virtual device — so there it offers nothing
    rather than a menu entry that cannot record.

Nothing here imports either library at module level, and the two engines are
objects rather than function calls, so enumeration, mixing and what ends up in
the WAV are all tested with fakes instead of with a microphone.

The file written is a plain 16-bit PCM WAV at the device's own sample rate,
downmixed to mono. No resampling happens here on purpose: the transcription
pipeline already hands every recording to ffmpeg, which resamples to 16 kHz
better than a few lines of numpy would, and an archived recording is worth
keeping at the rate it was captured.
"""
import math
import os
import sys
import threading
import wave
from dataclasses import dataclass, field

import numpy as np

#: A device that records what goes into it.
INPUT = "input"
#: An output device recorded backwards: what the machine is playing.
LOOPBACK = "loopback"

#: Engine names, which are also the two optional libraries.
PORTAUDIO = "portaudio"
SYSTEM = "system"

#: What the platform's own audio API is called in the menu, since that is what
#: ``soundcard`` talks to. On Windows the name deliberately matches the one
#: PortAudio uses for the same thing, so the loopbacks appear among that host
#: API's devices instead of in a group of their own.
SYSTEM_HOST_API = {"win32": "Windows WASAPI",
                   "darwin": "Core Audio"}.get(sys.platform, "PulseAudio")

#: Rate asked of the platform API, which resamples for us. PortAudio devices
#: are opened at their own default instead, because it does not.
SYSTEM_RATE = 48000

#: How much audio is read at a time. A tenth of a second keeps the elapsed
#: counter lively without waking the thread pointlessly.
BLOCK_SECONDS = 0.1

#: A peak below this never made it past the noise floor of a quiet room; a
#: recording that stayed under it for its whole length is silence, and saying
#: so is more use than filing it and finding out after the transcription.
SILENCE_PEAK = 0.001

#: How far the second source of a mix may run ahead before frames are dropped.
#: Two devices have two clocks: over an hour they drift, and something has to
#: give. Dropping keeps the mix aligned with the primary source — the one whose
#: voice is usually in the room — instead of letting the offset grow.
MAX_LAG_SECONDS = 0.5


class RecordingError(Exception):
    """Anything that stops a recording from starting or continuing."""


@dataclass(frozen=True)
class Source:
    """One thing that can be recorded from, as the menus present it."""

    key: str                  #: stable identity, remembered between sessions
    label: str                #: what the menu shows
    host_api: str             #: "Windows WASAPI", "MME", ...
    kind: str = INPUT         #: INPUT or LOOPBACK
    channels: int = 1
    samplerate: int = SYSTEM_RATE
    engine: str = PORTAUDIO
    handle: object = field(default=None, compare=False)  #: engine's own id

    @property
    def is_loopback(self):
        return self.kind == LOOPBACK


# --------------------------------------------------------------------------
# engines
# --------------------------------------------------------------------------

class PortAudioEngine:
    """Host APIs and input devices, through ``sounddevice``."""

    name = PORTAUDIO

    def __init__(self, module=None):
        self._module = module

    @property
    def module(self):
        if self._module is None:
            import sounddevice

            self._module = sounddevice
        return self._module

    def available(self):
        try:
            return self.module is not None
        except Exception:
            # Missing package, or a PortAudio shared library that will not
            # load: both mean "this engine is not usable here".
            return False

    def sources(self):
        """Every input device, grouped by the host API it belongs to."""
        found = []
        devices = self.module.query_devices()
        for index, api in enumerate(self.module.query_hostapis()):
            for device_index in api["devices"]:
                device = devices[device_index]
                if device["max_input_channels"] < 1:
                    continue
                found.append(Source(
                    key=f"{PORTAUDIO}:{index}:{device['name']}",
                    label=device["name"],
                    host_api=api["name"],
                    kind=INPUT,
                    channels=int(device["max_input_channels"]),
                    samplerate=int(device["default_samplerate"] or SYSTEM_RATE),
                    engine=PORTAUDIO,
                    handle=device_index,
                ))
        return found

    def rescan(self):
        """Make PortAudio look at the machine's devices again.

        It reads them once, when it initialises, and a headset plugged in
        afterwards simply is not there — the only way to see it is to shut
        PortAudio down and bring it back up. Private helpers, hence the
        guard: if this stops working the menu is stale, which is a great deal
        better than a traceback."""
        try:
            self.module._terminate()
            self.module._initialize()
        except Exception:
            pass

    def open(self, source, channels, samplerate):
        stream = self.module.InputStream(
            device=source.handle, channels=channels, samplerate=samplerate,
            dtype="float32", blocksize=0)
        stream.start()
        return _PortAudioStream(stream)


class _PortAudioStream:
    """A PortAudio input stream, read in blocks."""

    def __init__(self, stream):
        self._stream = stream

    def read(self, frames):
        data, _overflowed = self._stream.read(frames)
        return np.asarray(data, dtype=np.float32)

    def read_ready(self):
        """Whatever is already there; never blocks."""
        available = self._stream.read_available
        if available < 1:
            return None
        data, _overflowed = self._stream.read(available)
        return np.asarray(data, dtype=np.float32)

    def close(self):
        try:
            self._stream.stop()
        finally:
            self._stream.close()


class SystemEngine:
    """Loopback through ``soundcard``, i.e. the platform's own audio API."""

    name = SYSTEM

    #: Loopback sources are shown inside this host API, which is where they
    #: belong and where Audacity shows them too.
    HOST_API = SYSTEM_HOST_API

    def __init__(self, module=None):
        self._module = module

    @property
    def module(self):
        if self._module is None:
            import soundcard

            self._module = soundcard
        return self._module

    def available(self):
        try:
            return self.module is not None
        except Exception:
            return False

    def sources(self):
        """Every loopback this platform can record, and nothing else.

        Real microphones are left to PortAudio: it already lists them under
        every host API, and offering the same microphone twice would be a menu
        that lies about having two of them.

        On macOS there are none. Core Audio cannot record what is being played
        without a virtual device in the way (BlackHole and its like), and
        ``soundcard`` says so with a warning and an empty list — better to
        offer nothing than an entry that fails when it is used."""
        if sys.platform == "darwin":
            return []
        found = []
        for microphone in self.module.all_microphones(include_loopback=True):
            if not getattr(microphone, "isloopback", False):
                continue
            name = str(microphone.name)
            found.append(Source(
                key=f"{SYSTEM}:loopback:{name}",
                label=name,
                host_api=self.HOST_API,
                kind=LOOPBACK,
                channels=max(1, int(getattr(microphone, "channels", 2) or 2)),
                samplerate=SYSTEM_RATE,
                engine=SYSTEM,
                handle=microphone.id,
            ))
        return found

    def open(self, source, channels, samplerate):
        microphone = self.module.get_microphone(source.handle, include_loopback=True)
        recorder = microphone.recorder(samplerate=samplerate, channels=channels)
        recorder.__enter__()
        return _SystemStream(recorder)


class _SystemStream:
    """A soundcard recorder, which already hands back numpy blocks."""

    def __init__(self, recorder):
        self._recorder = recorder

    def read(self, frames):
        return np.asarray(self._recorder.record(numframes=frames), dtype=np.float32)

    def read_ready(self):
        data = np.asarray(self._recorder.record(numframes=None), dtype=np.float32)
        return data if len(data) else None

    def close(self):
        self._recorder.__exit__(None, None, None)


def engines(portaudio=None, system=None):
    """The engines to ask, in the order their sources are listed."""
    return (portaudio or PortAudioEngine(), system or SystemEngine())


# --------------------------------------------------------------------------
# what the menus show
# --------------------------------------------------------------------------

def available(backends=None):
    """Whether anything can be recorded through this module at all."""
    return any(engine.available() for engine in engines(*(backends or (None, None))))


def sources(backends=None):
    """Every source, in one list, PortAudio's devices before the loopbacks.

    An engine that is not installed, or whose library will not load, simply
    contributes nothing: a missing ``soundcard`` costs the loopbacks, not the
    microphones."""
    found = []
    for engine in engines(*(backends or (None, None))):
        if not engine.available():
            continue
        try:
            found.extend(engine.sources())
        except Exception:
            # Enumeration talks to the operating system's audio stack and can
            # fail on its own; one broken engine must not empty the menu.
            continue
    return found


def host_apis(backends=None):
    """``[(host api, [Source, ...]), ...]`` — the two menus, in that order.

    Host APIs keep the order PortAudio reports them in, which is the order
    Audacity shows; the loopbacks join the group of the platform's own API,
    which on Windows is the same WASAPI group PortAudio already lists."""
    grouped = {}
    for source in sources(backends):
        grouped.setdefault(source.host_api, []).append(source)
    return list(grouped.items())


def rescan(backends=None):
    """Ask the engines to notice devices that have appeared or gone.

    The platform API enumerates live and needs nothing; PortAudio has to be
    restarted.
    Never called while a recording is running, for the obvious reason."""
    for engine in engines(*(backends or (None, None))):
        if not engine.available():
            continue
        rescan_engine = getattr(engine, "rescan", None)
        if rescan_engine is not None:
            rescan_engine()


def find(key, backends=None):
    """The source with this key, or ``None`` if it is gone.

    A remembered choice can name a device that has since been unplugged, so
    every caller has to cope with ``None``."""
    return next((source for source in sources(backends) if source.key == key), None)


# --------------------------------------------------------------------------
# recording
# --------------------------------------------------------------------------

def to_mono(block):
    """Average the channels of a ``(frames, channels)`` block into one.

    Averaging rather than taking the first channel: a four-microphone array
    with one channel picked would throw away three quarters of the room."""
    data = np.asarray(block, dtype=np.float32)
    if data.ndim == 1:
        return data
    if data.shape[1] == 1:
        return data[:, 0]
    return data.mean(axis=1, dtype=np.float32)


def to_pcm16(block):
    """Mono float32 in -1..1 to the int16 a WAV file holds."""
    clipped = np.clip(np.asarray(block, dtype=np.float32), -1.0, 1.0)
    return (clipped * 32767.0).astype("<i2")


def peak(block):
    """The loudest sample in a block, 0..1.

    This is what answers "is anything arriving at all" — the question behind
    every silent recording, which is usually a muted microphone, the wrong
    device, or Windows refusing an application the microphone.

    ``None`` counts as silence rather than as ``nan``: numpy would turn the
    empty answer into one, and a single nan defeats the silence check for the
    rest of the recording, since every comparison against it is false."""
    if block is None:
        return 0.0
    data = np.asarray(block, dtype=np.float32)
    return float(np.abs(data).max()) if data.size else 0.0


def mix(primary, secondary):
    """Add two mono blocks, the primary's length winning.

    The primary source sets the clock. The secondary is padded with silence
    when it is short and cut when it is long, so a drift between two sound
    cards shows up as a few missing milliseconds rather than as a recording
    that slides further out of step every minute."""
    primary = np.asarray(primary, dtype=np.float32)
    if secondary is None or not len(secondary):
        return primary
    secondary = np.asarray(secondary, dtype=np.float32)
    if len(secondary) < len(primary):
        secondary = np.concatenate(
            [secondary, np.zeros(len(primary) - len(secondary), dtype=np.float32)])
    return primary + secondary[:len(primary)]

# --------------------------------------------------------------------------
# does this look like speech?
# --------------------------------------------------------------------------

#: What :class:`SpeechProbe` concluded.
SILENCE = "silence"        #: nothing above the noise floor
SOUND = "sound"            #: something, but it does not behave like a voice
SPEECH = "speech"          #: bursts and pauses in the band a voice lives in

#: Speech happens between roughly these frequencies. Below sits mains hum and
#: rumble, above sits hiss: a voice keeps most of its energy in between.
SPEECH_BAND_HZ = (100.0, 4000.0)

#: How much of the energy has to be in that band before this looks like a
#: voice rather than hum or hiss.
MIN_BAND_RATIO = 0.5

#: Decibels between the quiet moments and the loud ones. Speech pauses - for
#: breath, for the other person, between syllables - and that is what separates
#: it from a fan, a tone, or a steady hiss, which sit at one level all day.
#: Measured on synthetic signals: a constant tone and white noise come out
#: under 2 dB, someone talking without pausing at all still manages 8, and
#: normal conversation 20 to 40. Six leaves room for the awkward case without
#: letting noise through.
MIN_DYNAMIC_DB = 6.0

#: A fraction of the time outside those pauses. Below it something clicked
#: once; above it nothing ever paused, which is not conversation.
ACTIVE_FRACTION = (0.05, 0.95)

#: Nothing quieter than this counts as sound at all.
SILENCE_DB = -50.0

#: Enough audio to judge on. Under a second and a half, a pause between two
#: words looks exactly like a silent microphone.
MIN_SECONDS = 1.5

#: How much is kept: the verdict follows the last few seconds, so pointing the
#: microphone at something new does not have to outweigh a minute of history.
WINDOW_SECONDS = 6.0


def band_ratio(block, samplerate, band=SPEECH_BAND_HZ):
    """Fraction of a block's energy inside ``band``.

    A voice keeps most of it between 100 Hz and 4 kHz. Mains hum sits below,
    hiss and fan noise spread above: both come out low here, which is what
    makes this worth measuring at all."""
    data = np.asarray(block, dtype=np.float32)
    if data.size < 16:
        return 0.0
    spectrum = np.abs(np.fft.rfft(data)) ** 2
    total = float(spectrum.sum())
    if total <= 0.0:
        return 0.0
    frequencies = np.fft.rfftfreq(data.size, d=1.0 / float(samplerate))
    inside = (frequencies >= band[0]) & (frequencies <= band[1])
    return float(spectrum[inside].sum() / total)


def rms_db(block):
    """Loudness of a block in decibels below full scale, floored."""
    data = np.asarray(block, dtype=np.float32)
    if data.size == 0:
        return -120.0
    mean_square = float(np.mean(np.square(data, dtype=np.float64)))
    if mean_square <= 0.0:
        return -120.0
    return 10.0 * math.log10(mean_square)


class SpeechProbe:
    """Guesses whether what is arriving sounds like somebody talking.

    It is a guess, and the interface says so: three measurements over the last
    few seconds, not recognition. Whether the words are *words* is Whisper's
    job, and Whisper needs a model, a minute and a file.

    What it looks at is what separates a voice from the two things a level
    meter cannot tell it apart from. A fan, a tone or a hiss holds one level
    indefinitely, while speech pauses — so the gap between the quiet and the
    loud moments has to be there. And a voice puts its energy between 100 Hz
    and 4 kHz, while hum sits underneath and hiss spreads above."""

    def __init__(self, samplerate, window_seconds=WINDOW_SECONDS,
                 block_seconds=BLOCK_SECONDS):
        self.samplerate = int(samplerate or SYSTEM_RATE)
        self._keep = max(4, int(window_seconds / max(block_seconds, 0.01)))
        self._min_blocks = max(2, int(MIN_SECONDS / max(block_seconds, 0.01)))
        self._levels = []
        self._bands = []
        self._lock = threading.Lock()

    def add(self, block):
        """Take one block of mono audio into the window."""
        level, band = rms_db(block), band_ratio(block, self.samplerate)
        with self._lock:
            self._levels.append(level)
            self._bands.append(band)
            del self._levels[:-self._keep]
            del self._bands[:-self._keep]

    def reset(self):
        with self._lock:
            self._levels = []
            self._bands = []

    def measure(self):
        """``(verdict, detail)`` for the last few seconds.

        ``detail`` carries the three numbers behind the verdict, because a
        guess that cannot be argued with is not much use to whoever has to fix
        the microphone."""
        with self._lock:
            levels = list(self._levels)
            bands = list(self._bands)
        if len(levels) < self._min_blocks:
            return None, {"ready": False}

        loud = float(np.percentile(levels, 90))
        quiet = float(np.percentile(levels, 20))
        dynamic = loud - quiet
        threshold = quiet + 6.0
        active = float(np.mean([level > threshold for level in levels]))
        # Weighted towards the loud blocks: the band of a pause is noise, and
        # averaging it in would drag every verdict down.
        loud_bands = [band for band, level in zip(bands, levels, strict=True)
                      if level > threshold]
        band = float(np.mean(loud_bands or bands))
        detail = {"ready": True, "level_db": loud, "floor_db": quiet,
                  "dynamic_db": dynamic, "active": active, "band_ratio": band}

        if loud < SILENCE_DB:
            return SILENCE, detail
        if (dynamic >= MIN_DYNAMIC_DB
                and ACTIVE_FRACTION[0] <= active <= ACTIVE_FRACTION[1]
                and band >= MIN_BAND_RATIO):
            return SPEECH, detail
        return SOUND, detail


# --------------------------------------------------------------------------
# capturing: recording to a file, or only listening
# --------------------------------------------------------------------------

class _Capture:
    """Devices held open and read in a worker thread.

    What recording and monitoring have in common, which is nearly everything:
    resolving a source to an engine, opening one or two streams, reading them
    in step, measuring the levels, and shutting down without leaving a device
    held. The difference is what each does with the audio, which is the
    :meth:`_consume` hook."""

    def __init__(self, source, mix_with=None, backends=None,
                 block_seconds=BLOCK_SECONDS):
        self.source = source
        self.mix_with = mix_with
        self.samplerate = int(source.samplerate or SYSTEM_RATE)
        self.error = None
        #: Peak of the last block read, one per source, primary first. Read by
        #: the interface on a timer to draw a level meter.
        self.levels = [0.0]
        self._backends = backends
        self._block = max(1, int(self.samplerate * block_seconds))
        self._streams = []
        self._residual = np.zeros(0, dtype=np.float32)
        self._thread = None
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._lock = threading.Lock()
        self._loudest = 0.0

    # --- lifecycle --------------------------------------------------------

    def start(self):
        """Open the devices and begin reading. Raises on a device that will
        not open, because that is worth hearing about now."""
        if self._thread is not None:
            raise RecordingError("this capture has already been started")
        try:
            self._open()
        except Exception as exc:
            self._close()
            raise RecordingError(str(exc) or exc.__class__.__name__) from exc
        self._thread = threading.Thread(target=self._run, name="capture",
                                        daemon=True)
        self._thread.start()
        return self

    def stop(self, timeout=5.0):
        """Stop reading and let go of the devices."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None
        self._close()
        with self._lock:
            self.levels = [0.0] * len(self.levels)
        return None

    def pause(self):
        """Keep the devices and the meters, stop consuming what they give."""
        self._paused.set()

    def resume(self):
        self._paused.clear()

    @property
    def paused(self):
        return self._paused.is_set()

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    @property
    def silent(self):
        """Whether nothing louder than the noise floor ever arrived."""
        with self._lock:
            return self._loudest > 0.0 and self._loudest < SILENCE_PEAK

    # --- devices ----------------------------------------------------------

    def _engine_for(self, source):
        for engine in engines(*(self._backends or (None, None))):
            if engine.name == source.engine:
                return engine
        raise RecordingError(f"no engine for source '{source.key}'")

    def _open(self):
        primary = self._engine_for(self.source).open(
            self.source, self.source.channels, self.samplerate)
        self._streams.append(primary)
        if self.mix_with is not None:
            second = self._engine_for(self.mix_with).open(
                self.mix_with, self.mix_with.channels, self.samplerate)
            self._streams.append(second)
        self._prepare()

    def _close(self):
        while self._streams:
            stream = self._streams.pop()
            try:
                stream.close()
            except Exception:
                pass
        self._release()

    # --- the loop ---------------------------------------------------------

    def _run(self):
        """Read, measure, hand over, until stopped.

        Any failure ends the capture with a message rather than a traceback
        nobody sees."""
        primary = self._streams[0]
        secondary = self._streams[1] if len(self._streams) > 1 else None
        try:
            while not self._stop.is_set():
                block = to_mono(primary.read(self._block))
                levels = [peak(block)]
                if secondary is not None:
                    second = self._from_secondary(secondary, len(block))
                    levels.append(peak(second))
                    block = mix(block, second)
                # Measured before the pause check on purpose: a paused
                # recording is exactly when someone is looking at the meter to
                # see whether the microphone works.
                with self._lock:
                    self.levels = levels
                    self._loudest = max(self._loudest, *levels)
                if self._paused.is_set():
                    continue
                self._consume(block)
        except Exception as exc:       # noqa: BLE001 - reported, not raised
            self.error = str(exc) or exc.__class__.__name__

    def _from_secondary(self, stream, frames):
        """The next ``frames`` of the second source, at the primary's rate.

        The second source is a queue, not a snapshot: whatever has arrived is
        appended and the *oldest* frames are used, so nothing recent is thrown
        away while something old sits unused. Only when the queue grows past
        :data:`MAX_LAG_SECONDS` — two sound cards drifting, or a pause that
        let it fill — is the oldest audio dropped, which is the one way to
        catch up without letting the offset grow all afternoon."""
        arrived = stream.read_ready()
        if arrived is not None and len(arrived):
            self._residual = np.concatenate([self._residual, to_mono(arrived)])
        cap = int(self.samplerate * MAX_LAG_SECONDS) + frames
        if len(self._residual) > cap:
            self._residual = self._residual[-cap:]
        block = self._residual[:frames]
        self._residual = self._residual[len(block):]
        return block

    # --- hooks ------------------------------------------------------------

    def _prepare(self):
        """Called once the devices are open, before the thread starts."""

    def _consume(self, block):
        """Called with every mono block, unless paused."""

    def _release(self):
        """Called once the devices are closed."""


class Recording(_Capture):
    """One recording in progress, writing a mono WAV in a worker thread.

    ``mix_with`` records a second source into the same file — a microphone and
    the loopback of the speakers, which together are the two halves of a call.
    It is opened at the primary's sample rate, and both are downmixed to mono
    before being added."""

    def __init__(self, path, source, mix_with=None, backends=None,
                 block_seconds=BLOCK_SECONDS):
        super().__init__(source, mix_with=mix_with, backends=backends,
                         block_seconds=block_seconds)
        self.path = os.path.abspath(path)
        self.frames = 0
        self._writer = None

    def stop(self, timeout=5.0):
        """Finish the file and return its path, or ``None`` if it is empty."""
        super().stop(timeout)
        if not self.frames:
            try:
                os.unlink(self.path)
            except OSError:
                pass
            return None
        return self.path

    @property
    def elapsed_seconds(self):
        """Seconds actually written, which is what a paused recording holds."""
        with self._lock:
            return self.frames / float(self.samplerate)

    @property
    def silent(self):
        """Whether the recording is nothing but silence.

        A muted microphone writes a perfectly valid file full of zeros, which
        Whisper then transcribes into nothing at all. Better to say it while
        the meeting is still fresh."""
        with self._lock:
            return self.frames > 0 and self._loudest < SILENCE_PEAK

    def _prepare(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        # noqa below: the writer deliberately outlives this call - it is
        # closed by stop(), because a recording spans many blocks.
        self._writer = wave.open(self.path, "wb")   # noqa: SIM115
        self._writer.setnchannels(1)
        self._writer.setsampwidth(2)
        self._writer.setframerate(self.samplerate)

    def _consume(self, block):
        self._writer.writeframes(to_pcm16(block).tobytes())
        with self._lock:
            self.frames += len(block)

    def _release(self):
        if self._writer is not None:
            try:
                self._writer.close()
            except Exception:
                pass
            self._writer = None


class Monitor(_Capture):
    """The devices open, the meters live, and nothing written anywhere.

    What the "test audio" button does: it answers "is anything arriving, and
    does it sound like somebody talking" before an hour of meeting depends on
    the answer. Nothing is kept — no file, no library entry — which is the
    whole difference from :class:`Recording`."""

    def __init__(self, source, mix_with=None, backends=None,
                 block_seconds=BLOCK_SECONDS):
        super().__init__(source, mix_with=mix_with, backends=backends,
                         block_seconds=block_seconds)
        self.probe = SpeechProbe(self.samplerate, block_seconds=block_seconds)

    def measure(self):
        """``(verdict, detail)``: see :meth:`SpeechProbe.measure`."""
        return self.probe.measure()

    def _prepare(self):
        self.probe.reset()

    def _consume(self, block):
        self.probe.add(block)
