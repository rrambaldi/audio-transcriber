"""Orchestration: choose a backend, warn about bad fits, transcribe.

The engine-specific code lives in :mod:`audio_transcriber.backends`. What is
here is the part that should behave identically whichever engine runs: picking
one, telling the user when the chosen model does not fit the machine, and
returning a uniform result.
"""
import sys

from . import paths
from .backends import BACKENDS, FASTER_WHISPER, OPENVINO, load, resolve_backend
from .hardware import (
    available_ram_gb,
    cpu_count,
    has_cuda,
    has_openvino_accelerator,
)
from .i18n import t

__all__ = ["BACKENDS", "LANGUAGE_CHOICES", "MODEL_CHOICES", "transcribe",
           "resolve_backend", "warn_if_tight", "recommend_model", "resolve_model"]

#: What ``--model auto`` means: work it out from the machine.
AUTO = "auto"

# Rough peak RAM in GiB needed to hold the model, as (quantised, full
# precision). Only used to warn before a run turns into swapping or an OOM
# kill, so approximate numbers are fine.
MODEL_RAM_GB = {
    "tiny": (0.3, 0.6),
    "base": (0.4, 0.8),
    "small": (0.7, 1.6),
    "medium": (1.5, 4.0),
    "large-v3-turbo": (1.2, 3.0),
    "turbo": (1.2, 3.0),
    "large-v1": (2.5, 7.0),
    "large-v2": (2.5, 7.0),
    "large-v3": (2.5, 7.0),
    "large": (2.5, 7.0),
}

#: Models that are painful on a CPU with very few cores.
HEAVY_MODELS = frozenset({"medium", "large", "large-v1", "large-v2", "large-v3",
                          "large-v3-turbo", "turbo"})

#: Below this many cores, a heavy model is not worth starting.
FEW_CORES = 2

# Rough transcription speed of ONE CPU core, as a multiple of realtime, with
# faster-whisper and int8. Anchored on a measured machine — a 2 vCPU Xeon
# Skylake does 'small' at 0.6x realtime, 'base' at 1.0x, 'tiny' at 2.0x — and
# scaled down per core, which is close enough because the engine parallelises
# well. Only used to choose a default, never to promise anything.
CPU_SPEED_PER_CORE = {
    "tiny": 1.0,
    "base": 0.5,
    "small": 0.3,
    "large-v3-turbo": 0.15,
    "medium": 0.1,
    "large-v3": 0.045,
}

#: What the interfaces put in their model menu. "auto" comes first because it
#: is the honest default: the web page and the desktop window both show which
#: model it resolves to on this machine. Every other name in
#: :data:`MODEL_RAM_GB` still works when typed by hand.
MODEL_CHOICES = (AUTO, "tiny", "base", "small", "medium", "large-v3-turbo", "large-v3")

#: What the interfaces put in their spoken-language menu; "" means "detect it".
LANGUAGE_CHOICES = ("", "it", "en", "fr", "de", "es")

#: Models worth defaulting to, best first. 'large-v3-turbo' outranks 'medium':
#: it is distilled from large-v3 and is both better and faster.
MODELS_BY_QUALITY = ("large-v3", "large-v3-turbo", "medium", "small", "base", "tiny")

#: The slowest thing we will pick for someone who did not choose: one hour of
#: audio in two. Anyone who wants better quality for more time can say so.
TARGET_SPEED = 0.5

#: RAM to leave for everything that is not the model.
RAM_HEADROOM_GB = 0.8

#: "Go and measure it yourself", as opposed to ``None``, which means the
#: measurement was attempted and failed. The two must not be the same value:
#: a caller — a test, or a machine whose memory cannot be read — has to be able
#: to say "unknown" without being handed this machine's figure instead.
DETECT = object()

_HF_PREFIX = "openai/whisper-"


def model_key(model_name):
    """Size name used by the RAM table; accepts 'large-v3' or the HF id."""
    name = (model_name or "").strip()
    if name.startswith(_HF_PREFIX):
        name = name[len(_HF_PREFIX):]
    return name.replace(".en", "")


def recommend_model(backend=None, device=None, cores=None, ram=DETECT,
                    cuda=None, accelerator=None):
    """The best model this machine can run without the wait becoming absurd.

    Three situations, and they are genuinely different:

    * a CUDA GPU makes the size almost irrelevant, so take the best one;
    * an Intel iGPU or NPU through OpenVINO is limited by memory rather than by
      patience — it is slower than CUDA but it is not a CPU;
    * on a CPU the choice is arithmetic: pick the best model that still runs at
      :data:`TARGET_SPEED` given the cores, and that fits in the free RAM.

    Every argument can be passed in, which is what makes this testable without
    owning six machines."""
    cores = cpu_count() if cores is None else cores
    if ram is DETECT:
        ram = available_ram_gb()
    if cuda is None:
        cuda = has_cuda() if backend != OPENVINO else False
    if accelerator is None:
        accelerator = has_openvino_accelerator() if backend == OPENVINO else False

    def fits(name):
        """Whether the quantised model leaves room to breathe."""
        needed = MODEL_RAM_GB.get(name)
        if ram is None or needed is None:
            return True          # unknown memory: do not guess downwards
        return ram - RAM_HEADROOM_GB >= needed[0]

    if cuda:
        return next((m for m in MODELS_BY_QUALITY if fits(m)), "tiny")

    if accelerator:
        # OpenVINO on an iGPU/NPU: no int8, so judge against the full-precision
        # figure, and do not apply the CPU speed table at all.
        for name in MODELS_BY_QUALITY:
            needed = MODEL_RAM_GB.get(name)
            if ram is None or needed is None or ram - RAM_HEADROOM_GB >= needed[1]:
                return name
        return "tiny"

    for name in MODELS_BY_QUALITY:
        speed = CPU_SPEED_PER_CORE.get(name, 0) * max(1, cores)
        if speed >= TARGET_SPEED and fits(name):
            return name
    return "tiny"


def resolve_model(model_name, backend=None, device=None):
    """``(model, chosen_for_you)``: 'auto' becomes a real name here."""
    name = (model_name or AUTO).strip()
    if name.lower() in (AUTO, ""):
        return recommend_model(backend, device), True
    return name, False


def warn_if_tight(backend, model_name, compute_type):
    """Warn, without blocking, when the model does not fit the machine.

    Both checks are advisory on purpose: the estimates are approximate, and a
    user who knows their machine should not be stopped by a guess."""
    key = model_key(model_name)
    quantised = (backend == FASTER_WHISPER
                 and (compute_type or "int8").startswith("int8"))

    needed = MODEL_RAM_GB.get(key)
    free = available_ram_gb()
    if needed and free is not None:
        wanted = needed[0] if quantised else needed[1]
        if free < wanted:
            hint = "" if quantised else t("backend.low_ram_hint")
            print(t("backend.low_ram", model=model_name, needed=wanted,
                    free=free, hint=hint), file=sys.stderr)

    cores = cpu_count()
    on_cpu = backend == OPENVINO or (backend == FASTER_WHISPER and not has_cuda())
    if on_cpu and cores <= FEW_CORES and key in HEAVY_MODELS:
        print(t("backend.few_cores", cores=cores, model=model_name), file=sys.stderr)


def transcribe(audio, model_name, language, device, model_dir=None, prompt="",
               backend="auto", compute_type=None, threads=None, vad=True,
               progress=None, word_timestamps=False):
    """Transcribe ``audio`` and return ``(segments, raw_text, info)``.

    ``segments`` is a list of ``{"text", "start", "end"}``; ``info`` records
    which backend, device and model actually ran. ``progress``, if given, is
    called with a percentage: the CLI prints a line, the web interface moves a
    bar, and a backend that cannot report progress simply never calls it."""
    name = resolve_backend(backend, device)
    model_name, chosen = resolve_model(model_name, name, device)
    if chosen:
        ram = available_ram_gb()
        print(t("model.auto", model=model_name, cores=cpu_count(),
                ram=f"{ram:.1f}" if ram is not None else "?"))
    warn_if_tight(name, model_name, compute_type)

    directory = model_dir or paths.models_dir(name)
    segments, raw_text, used_device = load(name).transcribe(
        audio, model_name, language, device, directory, prompt,
        compute_type=compute_type, threads=threads, vad=vad, progress=progress,
        word_timestamps=word_timestamps,
    )
    return segments, raw_text, {
        "backend": name,
        "device": used_device,
        "model": model_name,
        "model_dir": directory,
    }
