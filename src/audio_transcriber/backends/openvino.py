"""OpenVINO backend: Whisper on Intel devices (iGPU, NPU, CPU).

On a machine with no GPU this still works on the CPU, but it is noticeably
slower than :mod:`audio_transcriber.backends.faster_whisper`, which quantises
to int8.

A recording longer than Whisper's thirty-second window has to be broken up,
and *how* is the whole quality of the result. Two ways exist. The pipeline's
``chunk_length_s`` cuts the audio into fixed windows with an overlap and
stitches the text back together afterwards, by matching the words the two
windows have in common — and when that match fails, which over a silence or a
crosstalk it does, the overlap is transcribed twice and both copies are kept.
The other way is Whisper's own: decode a window, read the timestamp of the
last thing it understood, and start the next window there. No overlap to
stitch, so nothing to double, and the model's own safeguards against inventing
text — retry at a higher temperature, reject a window whose output is too
repetitive or too unlikely, skip one that is probably silence — apply, because
they are part of that loop and not of the fixed-window one.

The second way is what this backend asks for. It needs ``generate`` to
implement Whisper's long-form loop, which the model class here only does in
recent enough versions, so a failure falls back to fixed windows and says so
rather than stopping.
"""
import os
import re
import sys

from ..cleaning import segments_from_words
from ..hardware import openvino_devices
from ..i18n import t

#: Whisper's own guards against inventing text over silence, and against
#: getting stuck repeating itself. Only the long-form loop applies them, which
#: is the main reason to prefer it. The numbers are the reference
#: implementation's: retry a window at each temperature in turn until its
#: output stops looking degenerate, judge it too repetitive above a
#: compression ratio of 1.35, too unlikely below an average log-probability of
#: -1, and probably silence above a no-speech probability of 0.6.
DECODING_GUARDS = {
    "temperature": (0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
    "compression_ratio_threshold": 1.35,
    "logprob_threshold": -1.0,
    "no_speech_threshold": 0.6,
    # Each window starting fresh: carrying the previous window's text in as
    # context is what makes Whisper fall into a loop and repeat a phrase for
    # a minute. faster-whisper's backend does the same, for the same reason.
    "condition_on_prev_tokens": False,
}

#: Whisper's window, and the length above which a recording has to be broken
#: up at all. At or below it there is one window, no loop, and none of this
#: matters.
WINDOW_S = 30

#: The fixed-window fallback: one window at a time with five seconds of
#: overlap, which is what the pipeline needs to stitch two windows together.
FALLBACK_WINDOW_S = WINDOW_S
FALLBACK_OVERLAP_S = 5

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


def segments_of(chunks, audio_seconds=None):
    """The pipeline's timestamped chunks as this program's segments.

    An end of ``None`` is what a window that ran to the end of the audio
    reports; the next chunk's start, or the length of the recording, is the
    honest reading of it. A chunk with neither time is dropped, because a
    segment with no clock cannot be laid out or cut into a subtitle."""
    built = []
    for position, chunk in enumerate(chunks or []):
        text = (chunk.get("text") or "").strip()
        if not text:
            continue
        start, end = chunk.get("timestamp") or (None, None)
        if start is None:
            continue
        if end is None:
            following = chunks[position + 1] if position + 1 < len(chunks) else None
            after = (following.get("timestamp") or (None, None))[0] if following else None
            end = after if after is not None else audio_seconds
            if end is None:
                continue
        built.append({"text": text, "start": float(start), "end": float(end)})
    return built


def words_of(chunks):
    """The pipeline's word-level chunks as timed words.

    Asked for word timestamps, the pipeline reports one chunk per word and no
    segments at all, so the segments are built back up from the words —
    keeping the timings underneath them, which is the point of having asked."""
    words = []
    for chunk in chunks or []:
        body = (chunk.get("text") or "").strip()
        start, end = chunk.get("timestamp") or (None, None)
        if body and start is not None:
            words.append({"word": body, "start": float(start),
                          "end": float(end) if end is not None else float(start)})
    return words


def warn_about_vad(vad):
    """Say, once, that this backend has no voice-activity filter.

    faster-whisper has one and uses it to cut the silences out before the
    model ever sees them, which is the surest way not to have a phrase
    invented over one. There is no equivalent here, and silently accepting
    ``vad=True`` would be a promise this backend cannot keep — so it says so,
    and points at the backend that can."""
    if vad:
        print(t("openvino.no_vad"), file=sys.stderr)


def transcribe(audio, model_name, language, device, model_dir, prompt,
               progress=None, vad=True, word_timestamps=False, **_unused):
    """Transcribe and return ``(segments, raw_text, device_used)``.

    ``word_timestamps`` asks for a time per word, which is what makes a
    subtitle cut fall where the speaker paused instead of being interpolated
    across a segment. It is worked out from the model's cross-attention, which
    an exported model does not always expose, so a refusal is not fatal: it
    warns and settles for segment timings.

    ``vad`` cannot be honoured here — see :func:`warn_about_vad`.

    ``progress`` is reported for the setup only. The transcription itself is a
    single call into the pipeline over the whole recording, which hands nothing
    back until it is done — so the bar shows the model being converted, loaded
    and compiled, and then stands still."""
    def report(percent, stage):
        if progress:
            progress(percent, stage)

    try:
        from optimum.intel import OVModelForSpeechSeq2Seq
        from transformers import AutoProcessor, pipeline
    except ImportError:
        sys.exit(t("openvino.missing"))

    device = resolve_device(device)
    hf_id = MODEL_MAP.get(model_name, model_name)
    os.makedirs(model_dir, exist_ok=True)
    converted = os.path.join(model_dir, re.sub(r"[^\w.-]", "_", hf_id) + "-ov")

    report(2, "stage.loading_model")
    if os.path.isdir(converted) and os.listdir(converted):
        print(t("openvino.reusing_model", path=converted))
        model = OVModelForSpeechSeq2Seq.from_pretrained(converted, device=device)
        processor = AutoProcessor.from_pretrained(converted)
    else:
        report(4, "stage.converting_model")
        print(t("openvino.converting", model=hf_id))
        model = OVModelForSpeechSeq2Seq.from_pretrained(hf_id, export=True, device=device)
        processor = AutoProcessor.from_pretrained(hf_id)
        model.save_pretrained(converted)
        processor.save_pretrained(converted)
        print(t("openvino.model_saved", path=converted))

    report(20, "stage.compiling_model")
    print(t("openvino.compiling", device=device))
    try:
        model.to(device)
        model.compile()
    except Exception as exc:
        print(t("openvino.compile_warning", error=exc))

    warn_about_vad(vad)

    prompt_ids = None
    if prompt:
        try:
            # A torch tensor: Whisper calls torch.cat() on prompt_ids, so numpy
            # will not do.
            prompt_ids = processor.get_prompt_ids(prompt, return_tensors="pt")
        except Exception:
            prompt_ids = None

    def attempt(plan):
        """Run one plan and return what the pipeline gave back."""
        windowed = plan["windowed"]
        pipe = pipeline("automatic-speech-recognition", model=model,
                        tokenizer=processor.tokenizer,
                        feature_extractor=processor.feature_extractor,
                        **({"chunk_length_s": FALLBACK_WINDOW_S,
                            "stride_length_s": FALLBACK_OVERLAP_S}
                           if windowed else {}))
        generate_kwargs = {"task": "transcribe"}
        if language:
            generate_kwargs["language"] = language
        if not windowed and long_form:
            # The guards belong to the long-form loop. The fixed-window path
            # does not run it, and neither does a recording that fits in one
            # window - and a list of temperatures handed to a decode that
            # cannot retry is not something to send.
            generate_kwargs.update(DECODING_GUARDS)
        if plan["prompt"] and prompt_ids is not None:
            generate_kwargs["prompt_ids"] = prompt_ids
        # The audio is already decoded at 16 kHz, so it goes in as
        # {"raw", "sampling_rate"} and the pipeline attempts no decoding of its
        # own (no torchcodec). The pipeline pops the dict's keys, hence a fresh
        # dict on every call.
        return pipe({"raw": audio, "sampling_rate": 16000},
                    return_timestamps=plan["timestamps"],
                    generate_kwargs=generate_kwargs)

    # Best first, and each fallback says what it gave up. The prompt is
    # dropped along with the long-form loop: prompt tokens are precisely what
    # makes the pipeline mis-stitch two overlapping windows, and a transcript
    # with a passage in it twice is worse than one that did not get the
    # keywords.
    plans = []
    if word_timestamps:
        plans.append({"name": "long_form_words", "windowed": False,
                      "timestamps": "word", "prompt": True})
    plans.append({"name": "long_form", "windowed": False,
                  "timestamps": True, "prompt": True})
    plans.append({"name": "windowed", "windowed": True,
                  "timestamps": True, "prompt": False})

    report(30, "stage.transcribing")
    print(t("transcribe.running"))
    audio_seconds = len(audio) / 16000.0 if len(audio) else 0.0
    long_form = audio_seconds > WINDOW_S
    result, ran, failure = None, None, None
    for plan in plans:
        if failure is not None:
            print(t("openvino.falling_back_to_" + plan["name"], error=failure),
                  file=sys.stderr)
        try:
            result, ran = attempt(plan), plan["name"]
            break
        except Exception as exc:
            failure = exc
    if result is None:
        sys.exit(t("openvino.transcription_failed", error=failure))

    report(100, "stage.laying_out")
    chunks = result.get("chunks") or []
    segments = (segments_from_words(words_of(chunks)) if ran == "long_form_words"
                else segments_of(chunks, audio_seconds or None))
    return segments, (result.get("text") or ""), device
