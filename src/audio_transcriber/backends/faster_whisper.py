"""faster-whisper backend: Whisper on CTranslate2, tuned for the CPU.

int8 quantisation roughly halves the memory and multiplies the speed compared
with the PyTorch/OpenVINO path on a CPU, which makes this the backend to use on
a server with no GPU. CUDA is supported as well.
"""
import os
import sys

from ..hardware import cpu_count, has_cuda
from ..i18n import t

#: Model sizes faster-whisper resolves on its own by downloading ready-made
#: CTranslate2 weights. Anything else is treated as a path or a repo id.
KNOWN_SIZES = frozenset({
    "tiny", "tiny.en", "base", "base.en", "small", "small.en",
    "medium", "medium.en", "large-v1", "large-v2", "large-v3", "large",
    "large-v3-turbo", "turbo", "distil-small.en", "distil-medium.en",
    "distil-large-v2", "distil-large-v3",
})

_HF_PREFIX = "openai/whisper-"


def resolve_model(model_name):
    """Normalise the model name.

    faster-whisper wants a size ('large-v3'), not OpenAI's Hugging Face id, so
    both spellings are accepted. Local paths and third-party CTranslate2 repos
    pass through untouched."""
    name = (model_name or "large-v3").strip()
    if name.startswith(_HF_PREFIX):
        name = name[len(_HF_PREFIX):]
    return name


def resolve_device(device):
    """Map the requested device onto CTranslate2's ('cpu' or 'cuda').

    Asking for a GPU that is not there warns and falls back to the CPU."""
    requested = (device or "auto").strip().upper()
    if requested in ("", "AUTO"):
        return "cuda" if has_cuda() else "cpu"
    if requested == "CPU":
        return "cpu"
    if requested in ("CUDA", "GPU", "NPU") or requested.startswith(("GPU.", "CUDA:")):
        if has_cuda():
            return "cuda"
        print(t("faster_whisper.no_cuda"), file=sys.stderr)
        return "cpu"
    return requested.lower()


def resolve_compute_type(compute_type, device):
    """Computation precision: int8 on CPU (half the memory, much faster),
    float16 on CUDA."""
    if compute_type:
        return compute_type
    return "float16" if device == "cuda" else "int8"


def transcribe(audio, model_name, language, device, model_dir, prompt,
               compute_type=None, threads=None, vad=True, beam_size=5,
               progress=None, **_unused):
    """Transcribe and return ``(segments, raw_text, device_description)``."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit(t("faster_whisper.missing"))

    name = resolve_model(model_name)
    device = resolve_device(device)
    compute_type = resolve_compute_type(compute_type, device)
    threads = int(threads) if threads else cpu_count()
    os.makedirs(model_dir, exist_ok=True)

    if name not in KNOWN_SIZES and not os.path.isdir(name) and "/" not in name:
        print(t("faster_whisper.unknown_size", model=name), file=sys.stderr)

    print(t("faster_whisper.loading", model=name, device=device,
            compute_type=compute_type, threads=threads))
    print(t("faster_whisper.cache", path=model_dir))
    if progress:
        # Loading a model is a download the first time and a few seconds every
        # time after: worth a mark of its own, or the bar sits at nothing while
        # it happens.
        progress(0, "stage.loading_model")

    def load(precision):
        return WhisperModel(name, device=device, compute_type=precision,
                            download_root=model_dir, cpu_threads=threads)

    try:
        model = load(compute_type)
    except ValueError as exc:
        # Some CPUs and builds do not support int8.
        fallback = "float32"
        if compute_type == fallback:
            sys.exit(t("faster_whisper.load_failed", error=exc))
        print(t("faster_whisper.compute_type_unsupported",
                compute_type=compute_type, error=exc, fallback=fallback),
              file=sys.stderr)
        compute_type = fallback
        model = load(compute_type)

    print(t("transcribe.running"))
    segment_iterator, info = model.transcribe(
        audio,
        language=language or None,
        task="transcribe",
        initial_prompt=prompt or None,
        beam_size=beam_size,
        vad_filter=bool(vad),
        condition_on_previous_text=False,  # avoids runaway repetition loops
    )

    duration = getattr(info, "duration", None) or 0.0
    if not language and getattr(info, "language", None):
        print(t("faster_whisper.detected_language", language=info.language,
                probability=getattr(info, "language_probability", 0.0)))

    segments, texts, last_percent = [], [], -1
    # The iterator is lazy: the actual work happens as it is consumed.
    for segment in segment_iterator:
        text = (segment.text or "").strip()
        if text:
            segments.append({"text": text, "start": segment.start, "end": segment.end})
            texts.append(text)
        # The console line is throttled to every five per cent; the callback
        # is not. An interface uses it to move a bar *and* as the one moment
        # it can stop a transcription, and a stop that waits for the next five
        # per cent of an hour of audio is not a stop.
        percent = int(min(segment.end / duration, 1.0) * 100) if duration else 0
        if progress:
            progress(percent)
        if duration and percent >= last_percent + 5:
            last_percent = percent
            print("\r" + t("transcribe.progress", percent=percent),
                  end="", file=sys.stderr, flush=True)
    if progress:
        progress(100)
    if duration and last_percent >= 0:
        if last_percent < 100:
            print("\r" + t("transcribe.progress", percent=100), end="", file=sys.stderr)
        print(file=sys.stderr)  # close the progress line

    return segments, " ".join(texts), f"{device}/{compute_type}"
