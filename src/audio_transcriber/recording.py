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
``soundcard`` (WASAPI directly)
    the *loopback* of an output device, which the PortAudio build shipped in
    the wheel does not expose — it refuses to open a render endpoint as an
    input. This one opens it with ``AUDCLNT_STREAMFLAGS_LOOPBACK``, the way
    Windows means it to be done, and resamples on the way out.

Nothing here imports either library at module level, and the two engines are
objects rather than function calls, so enumeration, mixing and what ends up in
the WAV are all tested with fakes instead of with a microphone.

The file written is a plain 16-bit PCM WAV at the device's own sample rate,
downmixed to mono. No resampling happens here on purpose: the transcription
pipeline already hands every recording to ffmpeg, which resamples to 16 kHz
better than a few lines of numpy would, and an archived recording is worth
keeping at the rate it was captured.
"""
import os
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
WASAPI = "wasapi"

#: Rate asked of WASAPI, which resamples for us. PortAudio devices are opened
#: at their own default instead, because it does not.
WASAPI_RATE = 48000

#: How much audio is read at a time. A tenth of a second keeps the elapsed
#: counter lively without waking the thread pointlessly.
BLOCK_SECONDS = 0.1

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
    samplerate: int = WASAPI_RATE
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
                    samplerate=int(device["default_samplerate"] or WASAPI_RATE),
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


class WasapiEngine:
    """Loopback (and microphones) through ``soundcard``, i.e. WASAPI itself."""

    name = WASAPI

    #: Loopback sources are shown inside this host API, which is where they
    #: belong and where Audacity shows them too.
    HOST_API = "Windows WASAPI"

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
        """One loopback per output device.

        Microphones are left to PortAudio: it already lists them under every
        host API, and offering the same microphone twice under the same name
        would be a menu that lies about having two of them."""
        found = []
        for speaker in self.module.all_speakers():
            name = str(speaker.name)
            found.append(Source(
                key=f"{WASAPI}:loopback:{name}",
                label=name,
                host_api=self.HOST_API,
                kind=LOOPBACK,
                channels=max(1, int(getattr(speaker, "channels", 2) or 2)),
                samplerate=WASAPI_RATE,
                engine=WASAPI,
                handle=speaker.id,
            ))
        return found

    def open(self, source, channels, samplerate):
        microphone = self.module.get_microphone(source.handle, include_loopback=True)
        recorder = microphone.recorder(samplerate=samplerate, channels=channels)
        recorder.__enter__()
        return _WasapiStream(recorder)


class _WasapiStream:
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


def engines(portaudio=None, wasapi=None):
    """The engines to ask, in the order their sources are listed."""
    return (portaudio or PortAudioEngine(), wasapi or WasapiEngine())


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
    Audacity shows; the loopbacks join the WASAPI group they belong to."""
    grouped = {}
    for source in sources(backends):
        grouped.setdefault(source.host_api, []).append(source)
    return list(grouped.items())


def rescan(backends=None):
    """Ask the engines to notice devices that have appeared or gone.

    WASAPI enumerates live and needs nothing; PortAudio has to be restarted.
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


class Recording:
    """One recording in progress, writing a mono WAV in a worker thread.

    ``mix_with`` records a second source into the same file — a microphone and
    the loopback of the speakers, which together are the two halves of a call.
    It is opened at the primary's sample rate, and both are downmixed to mono
    before being added."""

    def __init__(self, path, source, mix_with=None, backends=None,
                 block_seconds=BLOCK_SECONDS):
        self.path = os.path.abspath(path)
        self.source = source
        self.mix_with = mix_with
        self.samplerate = int(source.samplerate or WASAPI_RATE)
        self.error = None
        self.frames = 0
        self._backends = backends
        self._block = max(1, int(self.samplerate * block_seconds))
        self._streams = []
        self._residual = np.zeros(0, dtype=np.float32)
        self._writer = None
        self._thread = None
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._lock = threading.Lock()

    # --- lifecycle --------------------------------------------------------

    def start(self):
        """Open the devices and begin writing. Raises on a device that will
        not open, because that is worth hearing about before the meeting."""
        if self._thread is not None:
            raise RecordingError("this recording has already been started")
        try:
            self._open()
        except Exception as exc:
            self._close()
            raise RecordingError(str(exc) or exc.__class__.__name__) from exc
        self._thread = threading.Thread(target=self._run, name="recorder",
                                        daemon=True)
        self._thread.start()
        return self

    def stop(self, timeout=5.0):
        """Finish the file and return its path, or ``None`` if it is empty."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None
        self._close()
        if not self.frames:
            try:
                os.unlink(self.path)
            except OSError:
                pass
            return None
        return self.path

    def pause(self):
        """Stop writing without closing the devices."""
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
    def elapsed_seconds(self):
        """Seconds actually written, which is what a paused recording holds."""
        with self._lock:
            return self.frames / float(self.samplerate)

    # --- internals --------------------------------------------------------

    def _engine_for(self, source):
        for engine in engines(*(self._backends or (None, None))):
            if engine.name == source.engine:
                return engine
        raise RecordingError(f"no engine for source '{source.key}'")

    def _open(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        primary = self._engine_for(self.source).open(
            self.source, self.source.channels, self.samplerate)
        self._streams.append(primary)
        if self.mix_with is not None:
            second = self._engine_for(self.mix_with).open(
                self.mix_with, self.mix_with.channels, self.samplerate)
            self._streams.append(second)
        # noqa below: the writer deliberately outlives this call - it is
        # closed by stop(), because a recording spans many blocks.
        self._writer = wave.open(self.path, "wb")   # noqa: SIM115
        self._writer.setnchannels(1)
        self._writer.setsampwidth(2)
        self._writer.setframerate(self.samplerate)

    def _close(self):
        while self._streams:
            stream = self._streams.pop()
            try:
                stream.close()
            except Exception:
                pass
        if self._writer is not None:
            try:
                self._writer.close()
            except Exception:
                pass
            self._writer = None

    def _run(self):
        """Read, mix, write, until stopped.

        Any failure ends the recording with a message rather than a traceback
        nobody sees: what has been written so far stays on disk and is still
        worth transcribing."""
        primary = self._streams[0]
        secondary = self._streams[1] if len(self._streams) > 1 else None
        try:
            while not self._stop.is_set():
                block = to_mono(primary.read(self._block))
                if secondary is not None:
                    block = mix(block, self._from_secondary(secondary, len(block)))
                if self._paused.is_set():
                    continue
                self._writer.writeframes(to_pcm16(block).tobytes())
                with self._lock:
                    self.frames += len(block)
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
