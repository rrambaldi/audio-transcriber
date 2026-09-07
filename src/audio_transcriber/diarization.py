"""Speaker diarization with pyannote, and mapping speakers onto segments.

pyannote runs on the CPU here. It can work fully offline from a local
``config.yaml``, or online from the Hugging Face repository with a token.
"""
import os
import re
import sys

from .audio import SAMPLE_RATE
from .cleaning import clean_text
from .hardware import module_available
from .i18n import t

DEFAULT_PIPELINE = "pyannote/speaker-diarization-3.1"

#: Extensions that mark a config entry as a path rather than a repo id.
_WEIGHT_SUFFIXES = (".bin", ".pt", ".ckpt", ".onnx", ".safetensors")
_CONFIG_SUFFIXES = (".yaml", ".yml")


def looks_like_path(value):
    """Whether a config value names a file rather than a Hugging Face repo."""
    return (os.sep in value or "/" in value
            or value.lower().endswith(_WEIGHT_SUFFIXES + _CONFIG_SUFFIXES))


#: Why diarization cannot run here, if it cannot.
NOT_INSTALLED = "not_installed"
NO_MODEL = "no_model"
READY = "ready"


def availability(model=None, token=None):
    """``(state, detail)``: can this machine work out who said what?

    Asked before anything is offered rather than after an upload, so a front
    end can grey the option out and say why instead of accepting a job that is
    going to fail. Imports nothing heavy: pyannote pulls in PyTorch."""
    if not module_available("pyannote.audio"):
        return NOT_INSTALLED, "pyannote.audio"
    token = token or os.environ.get("HUGGINGFACE_TOKEN") or os.environ.get("HF_TOKEN")
    if token:
        return READY, "token"
    from . import paths

    config = model or paths.diarization_config()
    if os.path.exists(config):
        return READY, config
    return NO_MODEL, config


def check_diar_assets(model, token):
    """Pre-flight check, run before the long transcription starts.

    Exits with a clear message if something is missing, so nobody waits an hour
    for a transcript only to find the diarization cannot run. Downloads
    nothing and loads nothing heavy."""
    try:
        import pyannote.audio  # noqa: F401
    except ImportError:
        sys.exit(t("diarize.missing"))

    if not os.path.exists(model):
        if looks_like_path(model):
            print(t("diarize.local_config_missing", path=model))
        if not token:
            sys.exit(t("diarize.no_config_no_token"))
        print(t("diarize.online_ok"))
        return

    try:
        with open(model, encoding="utf-8") as handle:
            content = handle.read()
    except OSError as exc:
        sys.exit(t("diarize.config_unreadable", path=model, error=exc))

    references = re.findall(r"^\s*(embedding|segmentation)\s*:\s*(.+?)\s*$",
                            content, re.M)
    base = os.path.dirname(os.path.abspath(model))
    missing, relative = [], []
    for key, value in references:
        value = value.strip().strip('"').strip("'")
        if not looks_like_path(value):
            continue  # a repo id: pyannote will fetch it, token already checked
        if os.path.exists(value):
            continue
        if os.path.exists(os.path.join(base, value)):
            relative.append((key, value))
            continue
        missing.append((key, value))

    if missing:
        listed = "\n".join(f"    - {key}: {value}" for key, value in missing)
        sys.exit(t("diarize.missing_files", files=listed, path=model))
    for key, value in relative:
        print(t("diarize.relative_path_warning", key=key, value=value))
    print(t("diarize.preflight_ok", path=model))


def diarize(audio, token, num_speakers, model=DEFAULT_PIPELINE,
            sample_rate=SAMPLE_RATE):
    """Return speech turns as a list of ``(start, end, speaker_label)``.

    ``model`` is either a Hugging Face id (downloaded, needs a token) or the
    path of a local ``config.yaml`` (offline, no token)."""
    try:
        import torch
        from pyannote.audio import Pipeline
    except ImportError:
        sys.exit(t("diarize.missing"))

    is_local = os.path.exists(model)
    if not is_local and looks_like_path(model):
        print(t("diarize.config_fallback", path=model, fallback=DEFAULT_PIPELINE))
        model = DEFAULT_PIPELINE
    if not is_local and not token:
        sys.exit(t("diarize.token_required"))

    print(t("diarize.loading", model=model))
    if is_local:
        pipeline = Pipeline.from_pretrained(model)  # local config: no token
    else:
        try:
            pipeline = Pipeline.from_pretrained(model, use_auth_token=token)
        except TypeError:  # newer pyannote renamed the argument
            pipeline = Pipeline.from_pretrained(model, token=token)
    if pipeline is None:
        sys.exit(t("diarize.not_initialised"))

    pipeline.to(torch.device("cpu"))
    waveform = torch.from_numpy(audio).unsqueeze(0)  # (1, samples)
    options = {"num_speakers": num_speakers} if num_speakers else {}

    print(t("diarize.running"))
    annotation = pipeline({"waveform": waveform, "sample_rate": sample_rate}, **options)
    turns = [(segment.start, segment.end, label)
             for segment, _, label in annotation.itertracks(yield_label=True)]
    print(t("diarize.result", turns=len(turns),
            speakers=len({label for _, _, label in turns})))
    return turns


def assign_speakers(segments, turns):
    """Give each segment the speaker it overlaps with most.

    A segment without timestamps inherits the previous speaker, which is the
    least surprising guess in a conversation."""
    assigned = []
    last = turns[0][2] if turns else "SPEAKER_00"
    for segment in segments:
        start, end = segment.get("start"), segment.get("end")
        speaker = None
        if start is not None and end is not None and turns:
            best = 0.0
            for turn_start, turn_end, label in turns:
                overlap = min(end, turn_end) - max(start, turn_start)
                if overlap > best:
                    best, speaker = overlap, label
        if speaker is None:
            speaker = last
        last = speaker
        assigned.append({**segment, "speaker": speaker})
    return assigned


def format_dialogue(segments):
    """Merge consecutive segments from the same speaker into readable turns."""
    blocks, current_speaker, buffer = [], None, []
    for segment in segments:
        if segment["speaker"] != current_speaker:
            if buffer:
                blocks.append((current_speaker, clean_text(" ".join(buffer))))
            current_speaker, buffer = segment["speaker"], [segment["text"]]
        else:
            buffer.append(segment["text"])
    if buffer:
        blocks.append((current_speaker, clean_text(" ".join(buffer))))
    return "\n\n".join(f"[{speaker}] {text}" for speaker, text in blocks if text)
