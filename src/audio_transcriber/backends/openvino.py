"""OpenVINO backend: Whisper on Intel devices (iGPU, NPU, CPU).

On a machine with no GPU this still works on the CPU, but it is noticeably
slower than :mod:`audio_transcriber.backends.faster_whisper`, which quantises
to int8.
"""
import os
import re
import sys

from ..hardware import openvino_devices
from ..i18n import t

#: Short model names mapped to Hugging Face ids.
MODEL_MAP = {
    "tiny": "openai/whisper-tiny",
    "base": "openai/whisper-base",
    "small": "openai/whisper-small",
    "medium": "openai/whisper-medium",
    "large-v2": "openai/whisper-large-v2",
    "large-v3": "openai/whisper-large-v3",
    "large-v3-turbo": "openai/whisper-large-v3-turbo",
}


def resolve_device(device):
    """Map the requested device onto one OpenVINO can actually see.

    ``auto`` prefers a GPU, then an NPU, then the CPU. A device asked for
    explicitly but absent is not fatal: it warns and falls back to the CPU, so
    the same command line works on a laptop and on a headless server."""
    devices = openvino_devices()
    requested = (device or "auto").strip().upper()

    def find(prefix):
        # Real names may be enumerated: 'GPU.0', 'GPU.1', ...
        for name in devices:
            if name.upper() == prefix or name.upper().startswith(prefix + "."):
                return name
        return None

    if requested in ("", "AUTO"):
        if not devices:
            return "CPU"
        for preference in ("GPU", "NPU", "CPU"):
            found = find(preference)
            if found:
                return found
        return devices[0]

    if not devices:
        # OpenVINO could not be queried: pass the request through and let the
        # runtime complain with its own, more precise, error.
        return requested

    found = requested if requested in devices else find(requested.split(".")[0])
    if found:
        return found

    fallback = find("CPU") or "CPU"
    print(t("openvino.device_unavailable", requested=requested,
            found=", ".join(devices) or "-", fallback=fallback), file=sys.stderr)
    return fallback


def transcribe(audio, model_name, language, device, model_dir, prompt, **_unused):
    """Transcribe and return ``(segments, raw_text, device_used)``."""
    try:
        from optimum.intel import OVModelForSpeechSeq2Seq
        from transformers import AutoProcessor, pipeline
    except ImportError:
        sys.exit(t("openvino.missing"))

    device = resolve_device(device)
    hf_id = MODEL_MAP.get(model_name, model_name)
    os.makedirs(model_dir, exist_ok=True)
    converted = os.path.join(model_dir, re.sub(r"[^\w.-]", "_", hf_id) + "-ov")

    if os.path.isdir(converted) and os.listdir(converted):
        print(t("openvino.reusing_model", path=converted))
        model = OVModelForSpeechSeq2Seq.from_pretrained(converted, device=device)
        processor = AutoProcessor.from_pretrained(converted)
    else:
        print(t("openvino.converting", model=hf_id))
        model = OVModelForSpeechSeq2Seq.from_pretrained(hf_id, export=True, device=device)
        processor = AutoProcessor.from_pretrained(hf_id)
        model.save_pretrained(converted)
        processor.save_pretrained(converted)
        print(t("openvino.model_saved", path=converted))

    print(t("openvino.compiling", device=device))
    try:
        model.to(device)
        model.compile()
    except Exception as exc:
        print(t("openvino.compile_warning", error=exc))

    pipe = pipeline(
        "automatic-speech-recognition",
        model=model,
        tokenizer=processor.tokenizer,
        feature_extractor=processor.feature_extractor,
        chunk_length_s=30,
        stride_length_s=5,
    )

    base_kwargs = {"task": "transcribe"}
    if language:
        base_kwargs["language"] = language
    prompt_ids = None
    if prompt:
        try:
            # A torch tensor: Whisper calls torch.cat() on prompt_ids, so numpy
            # will not do.
            prompt_ids = processor.get_prompt_ids(prompt, return_tensors="pt")
        except Exception:
            prompt_ids = None

    def run(with_prompt):
        generate_kwargs = dict(base_kwargs)
        if with_prompt and prompt_ids is not None:
            generate_kwargs["prompt_ids"] = prompt_ids
        # The audio is already decoded at 16 kHz, so it goes in as
        # {"raw", "sampling_rate"} and the pipeline attempts no decoding of its
        # own (no torchcodec). The pipeline pops the dict's keys, hence a fresh
        # dict on every call.
        return pipe({"raw": audio, "sampling_rate": 16000},
                    return_timestamps=True, generate_kwargs=generate_kwargs)

    print(t("transcribe.running"))
    try:
        result = run(with_prompt=True)
    except Exception as exc:
        print(t("openvino.prompt_failed", error=exc))
        result = run(with_prompt=False)

    segments = []
    for chunk in result.get("chunks", []):
        text = (chunk.get("text") or "").strip()
        start, end = chunk.get("timestamp") or (None, None)
        if text:
            segments.append({"text": text, "start": start, "end": end})
    return segments, (result.get("text") or ""), device
