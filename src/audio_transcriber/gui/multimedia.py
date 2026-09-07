"""QtMultimedia, which may not be there even when Qt is.

``PySide6`` ships in two halves: ``PySide6-Essentials`` (widgets, and what the
window is built from) and ``PySide6-Addons``, which is where QtMultimedia
lives. The ``[gui]`` extra asks for the full ``PySide6``, so a normal install
has both — but someone who installed Essentials by hand should still get a
working window, minus the microphone and the playback controls, rather than an
ImportError on startup.

Hence this module: it answers "is multimedia available", and hides the
format-picking that recording needs. Nothing else in the package imports
QtMultimedia directly.
"""
try:
    from PySide6.QtMultimedia import (
        QAudioInput,
        QAudioOutput,
        QMediaCaptureSession,
        QMediaDevices,
        QMediaFormat,
        QMediaPlayer,
        QMediaRecorder,
    )

    AVAILABLE = True
except ImportError:                     # Essentials without Addons
    AVAILABLE = False
    QAudioInput = QAudioOutput = QMediaCaptureSession = None
    QMediaDevices = QMediaFormat = QMediaPlayer = QMediaRecorder = None

# Containers to record into, best first, each with the codec and the extension
# that go with it. AAC in an MP4 container comes first because an hour of
# speech is tens of megabytes rather than hundreds, and every one of these is
# something ffmpeg — which decodes the recording afterwards — reads natively.
_PREFERRED = (("Mpeg4Audio", "AAC", "m4a"),
              ("FLAC", "FLAC", "flac"),
              ("Wave", "Wave", "wav"))


def input_devices():
    """The microphones Qt can see; empty when there is no multimedia or no mic."""
    if not AVAILABLE:
        return []
    return list(QMediaDevices.audioInputs())


def default_input_device():
    """The system's default microphone, or ``None``."""
    if not AVAILABLE:
        return None
    device = QMediaDevices.defaultAudioInput()
    return None if device is None or device.isNull() else device


def recording_format():
    """``(QMediaFormat, extension)`` this machine can actually encode.

    What a Qt build supports depends on the multimedia backend it was compiled
    against, so the choice is made by asking rather than by assuming."""
    probe = QMediaFormat()
    encode = QMediaFormat.ConversionMode.Encode
    containers = set(probe.supportedFileFormats(encode))
    codecs = set(probe.supportedAudioCodecs(encode))
    for container_name, codec_name, extension in _PREFERRED:
        container = getattr(QMediaFormat.FileFormat, container_name, None)
        codec = getattr(QMediaFormat.AudioCodec, codec_name, None)
        if container is None or codec is None:
            continue
        if container in containers and codec in codecs:
            chosen = QMediaFormat(container)
            chosen.setAudioCodec(codec)
            return chosen, extension
    # Nothing recognised: let Qt use its own default and name the file after
    # the container it will most likely produce.
    return QMediaFormat(), "m4a"
