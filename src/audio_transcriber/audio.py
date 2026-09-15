"""Audio decoding to 16 kHz mono float32 through ffmpeg."""
import re
import subprocess
import sys

import numpy as np

SAMPLE_RATE = 16000


def ffmpeg_exe():
    """Path to ffmpeg.

    Prefers the binary bundled by 'imageio-ffmpeg' — a self-contained static
    build with no external DLLs — and falls back to a system ffmpeg, which on
    some conda environments is broken (libintl_dgettext, fontconfig-1.dll)."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        from .i18n import t
        print(t("audio.no_bundled_ffmpeg"), file=sys.stderr)
        return "ffmpeg"


def load_audio(path, sample_rate=SAMPLE_RATE):
    """Decode any container ffmpeg reads (wav, mp3, m4a, mp4, mkv, ...) into a
    mono float32 array at ``sample_rate``."""
    from .i18n import t
    command = [ffmpeg_exe(), "-nostdin", "-loglevel", "error", "-i", path,
               "-f", "f32le", "-acodec", "pcm_f32le", "-ac", "1",
               "-ar", str(sample_rate), "-"]
    try:
        process = subprocess.run(command, capture_output=True, check=False)
    except FileNotFoundError:
        sys.exit(t("audio.ffmpeg_not_found"))
    if process.returncode != 0:
        sys.exit(t("audio.decode_failed",
                   details=process.stderr.decode(errors="ignore")[-1000:]))
    # .copy() makes the array writable, which torch.from_numpy needs later on
    # for pyannote.
    return np.frombuffer(process.stdout, dtype=np.float32).copy()


#: How long to wait for ffmpeg to read a header. It is milliseconds on any
#: ordinary file; the limit is for the one that is not ordinary.
PROBE_TIMEOUT = 20

_DURATION = re.compile(r"Duration:\s*(\d+):(\d\d):(\d\d(?:\.\d+)?)")


def probe_seconds(path):
    """How long a recording is, from its header, without decoding it.

    ffmpeg asked to do nothing with a file still prints what it found in it,
    and stops there — which on a four-hundred-megabyte recording is the
    difference between milliseconds and minutes. The queue uses this so that
    a recording waiting its turn can say how long it is; the transcription
    replaces the figure with the exact one afterwards.

    ``None`` when it cannot be read: a stream that carries no duration, a
    file ffmpeg will not open, no ffmpeg at all. A wrong number in a row
    people read is worse than a missing one."""
    try:
        process = subprocess.run(
            [ffmpeg_exe(), "-nostdin", "-hide_banner", "-i", str(path)],
            capture_output=True, check=False, timeout=PROBE_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    found = _DURATION.search(process.stderr.decode(errors="ignore"))
    if not found:
        return None
    hours, minutes, seconds = found.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def duration_seconds(audio, sample_rate=SAMPLE_RATE):
    """Length of a decoded array in seconds."""
    return len(audio) / float(sample_rate) if len(audio) else 0.0
