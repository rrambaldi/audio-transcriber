"""Audio devices that do not exist, for tests that must not need one.

Both the engine tests and the window tests drive recording through these, so
the suite keeps running on a machine with no microphone, no PortAudio and no
sound server — which is the machine this project's tests have to pass on."""
import time

import numpy as np

from audio_transcriber import recording


class FakeStream:
    """Hands out prepared blocks, then silence, at the pace of a real device.

    The pause matters: a real ``read`` blocks until the samples exist, and that
    is what paces the recording thread. A fake that answers instantly turns the
    loop into a busy wait that writes hundreds of megabytes of WAV before the
    test gets around to stopping it."""

    def __init__(self, blocks=None, ready=None, pace=0.005):
        self.blocks = list(blocks or [])
        self.ready = list(ready or [])
        self.closed = False
        self._pace = pace

    def read(self, frames):
        time.sleep(self._pace)
        if self.blocks:
            return self.blocks.pop(0)
        return np.full((frames, 1), 0.25, dtype=np.float32)

    def read_ready(self):
        return self.ready.pop(0) if self.ready else None

    def close(self):
        self.closed = True


class FakeEngine:
    """One of the two engines, with the devices a test wants it to have."""

    def __init__(self, name, sources=(), stream=None, available=True):
        self.name = name
        self._sources = list(sources)
        self._stream = stream
        self._available = available
        self.opened = []

    def available(self):
        return self._available

    def sources(self):
        return list(self._sources)

    def open(self, source, channels, samplerate):
        self.opened.append((source, channels, samplerate))
        return self._stream or FakeStream()


def audio_source(key="portaudio:0:Mic", host_api="MME", kind=recording.INPUT,
                 engine=recording.PORTAUDIO, channels=1, samplerate=48000,
                 label=None):
    return recording.Source(key=key, label=label or key.split(":")[-1],
                            host_api=host_api, kind=kind, channels=channels,
                            samplerate=samplerate, engine=engine, handle=0)


def two_engines(inputs=(), loopbacks=(), stream=None, available=True):
    """The pair of engines :mod:`audio_transcriber.recording` expects."""
    return (FakeEngine(recording.PORTAUDIO, inputs, stream=stream,
                       available=available),
            FakeEngine(recording.WASAPI, loopbacks, stream=stream,
                       available=available))
