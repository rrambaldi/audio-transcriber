"""Audio decoding to 16 kHz mono float32 through ffmpeg."""
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


def duration_seconds(audio, sample_rate=SAMPLE_RATE):
    """Length of a decoded array in seconds."""
    return len(audio) / float(sample_rate) if len(audio) else 0.0
