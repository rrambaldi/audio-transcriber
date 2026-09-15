"""Backend, device and precision selection: pure logic, no engine installed."""
import os

import pytest

from audio_transcriber import backends, transcription
from audio_transcriber.backends import faster_whisper as fw
from audio_transcriber.backends import openvino as ov


def fake_environment(monkeypatch, *, faster=False, openvino=False, accelerator=False):
    available = {"faster_whisper": faster, "optimum": openvino, "openvino": openvino}
    monkeypatch.setattr(backends, "module_available", lambda name: available.get(name, False))
    monkeypatch.setattr(backends, "has_openvino_accelerator", lambda: accelerator)


# --- backend selection ----------------------------------------------------

def test_auto_prefers_faster_whisper_without_an_accelerator(monkeypatch):
    fake_environment(monkeypatch, faster=True, openvino=True, accelerator=False)
    assert backends.resolve_backend("auto", "auto") == backends.FASTER_WHISPER


def test_auto_prefers_openvino_with_an_intel_accelerator(monkeypatch):
    fake_environment(monkeypatch, faster=True, openvino=True, accelerator=True)
    assert backends.resolve_backend("auto", "auto") == backends.OPENVINO


def test_auto_uses_whichever_engine_is_installed(monkeypatch):
    fake_environment(monkeypatch, faster=False, openvino=True, accelerator=False)
    assert backends.resolve_backend("auto", "auto") == backends.OPENVINO
    fake_environment(monkeypatch, faster=True, openvino=False)
    assert backends.resolve_backend("auto", "auto") == backends.FASTER_WHISPER


def test_auto_honours_an_explicitly_requested_intel_device(monkeypatch):
    fake_environment(monkeypatch, faster=True, openvino=True, accelerator=False)
    assert backends.resolve_backend("auto", "NPU") == backends.OPENVINO


def test_auto_honours_an_explicitly_requested_cuda_device(monkeypatch):
    fake_environment(monkeypatch, faster=True, openvino=True, accelerator=True)
    assert backends.resolve_backend("auto", "CUDA") == backends.FASTER_WHISPER


def test_no_backend_installed_exits_with_installation_hint(monkeypatch):
    fake_environment(monkeypatch, faster=False, openvino=False)
    with pytest.raises(SystemExit) as exit_info:
        backends.resolve_backend("auto", "auto")
    assert "pip install" in str(exit_info.value)


def test_explicit_backend_wins_over_hardware(monkeypatch):
    fake_environment(monkeypatch, faster=True, openvino=True, accelerator=True)
    assert backends.resolve_backend("faster-whisper", "GPU") == backends.FASTER_WHISPER
    assert backends.resolve_backend("openvino", "CPU") == backends.OPENVINO


def test_backend_aliases_are_accepted(monkeypatch):
    monkeypatch.setattr(backends, "is_installed", lambda name: True)
    for alias in ("ct2", "faster_whisper", "CTranslate2"):
        assert backends.resolve_backend(alias, "auto") == backends.FASTER_WHISPER
    assert backends.resolve_backend("OV", "auto") == backends.OPENVINO


def test_an_engine_asked_for_by_name_has_to_be_here(monkeypatch):
    """It used to be taken at its word and found missing deep inside the run,
    after the audio had been decoded: a queued job that had been "running" for
    a while, and the reason in a log."""
    monkeypatch.setattr(backends, "is_installed",
                        lambda name: name == backends.OPENVINO)

    with pytest.raises(SystemExit) as stopped:
        backends.resolve_backend("faster-whisper", "auto")

    message = str(stopped.value)
    assert "faster-whisper" in message
    assert "openvino" in message          # and what this machine does have
    assert backends.resolve_backend("openvino", "auto") == backends.OPENVINO


def test_the_engines_this_machine_has_are_listed_in_menu_order(monkeypatch):
    monkeypatch.setattr(backends, "is_installed", lambda name: True)
    assert backends.installed() == [backends.FASTER_WHISPER, backends.OPENVINO]
    monkeypatch.setattr(backends, "is_installed", lambda name: False)
    assert backends.installed() == []


def test_unknown_backend_exits():
    with pytest.raises(SystemExit):
        backends.resolve_backend("nonsense", "auto")


# --- OpenVINO devices -----------------------------------------------------

def test_openvino_auto_picks_the_gpu_when_present(monkeypatch):
    monkeypatch.setattr(ov, "openvino_devices", lambda: ["CPU", "GPU.0"])
    assert ov.resolve_device("auto") == "GPU.0"


def test_openvino_auto_picks_the_cpu_on_a_headless_server(monkeypatch):
    monkeypatch.setattr(ov, "openvino_devices", lambda: ["CPU"])
    assert ov.resolve_device("auto") == "CPU"


def test_openvino_missing_gpu_falls_back_to_the_cpu(monkeypatch):
    """The server case: --device GPU must not make the command fail."""
    monkeypatch.setattr(ov, "openvino_devices", lambda: ["CPU"])
    assert ov.resolve_device("GPU") == "CPU"


def test_openvino_matches_an_enumerated_device(monkeypatch):
    monkeypatch.setattr(ov, "openvino_devices", lambda: ["CPU", "GPU.1"])
    assert ov.resolve_device("GPU") == "GPU.1"


def test_openvino_passes_the_request_through_when_it_cannot_enumerate(monkeypatch):
    monkeypatch.setattr(ov, "openvino_devices", lambda: [])
    assert ov.resolve_device("auto") == "CPU"
    assert ov.resolve_device("GPU") == "GPU"


# --- cutting the silence out before the model sees it ---------------------

def test_the_silences_are_taken_out_in_one_run(monkeypatch):
    """Whisper invents phrases over silence, and silence it never sees costs
    nothing to transcribe."""
    import numpy as np

    audio = np.arange(16000 * 10, dtype=np.float32)      # ten seconds
    speech = [{"start": 0, "end": 16000}, {"start": 16000 * 8, "end": 16000 * 10}]

    kept = ov.keep_speech(audio, speech)

    assert len(kept) == 16000 * 3                        # one second plus two
    assert kept[0] == 0 and kept[16000] == 16000 * 8     # and in order


def test_a_timestamp_comes_back_to_the_clock_of_the_recording():
    """The model is handed speech with the gaps closed up, so everything it
    reports is early by whatever silence came before it. A subtitle on the
    wrong second is the whole recording out of step."""
    # Speech at 0-1 s and at 8-10 s: the second run starts seven seconds
    # later on the real clock than it does on the trimmed one.
    original = ov.original_clock([{"start": 0, "end": 16000},
                                  {"start": 16000 * 8, "end": 16000 * 10}])

    assert original(0.0) == 0.0
    assert original(0.5) == 0.5
    assert original(1.0) == 1.0          # the end of a run stays in that run
    assert original(1.5) == 8.5          # the next word, after the silence
    assert original(3.0) == 10.0


def test_the_words_and_the_segments_are_moved_together():
    """Restoring the chunks rather than the segments built from them is what
    keeps the words inside a segment on the same clock as the segment."""
    speech = [{"start": 0, "end": 16000}, {"start": 16000 * 8, "end": 16000 * 10}]
    chunks = [{"text": "one", "timestamp": (0.0, 1.0)},
              {"text": "two", "timestamp": (1.2, 2.0)},
              {"text": "cut off", "timestamp": (2.5, None)}]

    restored = ov.restore_times(chunks, speech)

    assert restored[0]["timestamp"] == (0.0, 1.0)
    assert restored[1]["timestamp"] == (8.2, 9.0)
    # An open end is left open: it is closed later, with the length of the
    # recording, and that length is the real one.
    assert restored[2]["timestamp"] == (9.5, None)


def test_an_installation_without_the_filter_transcribes_the_whole_recording(monkeypatch):
    """The Silero model arrives with faster-whisper, which is only one of the
    two backends. Not having it is not an error."""
    import builtins

    real_import = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name.startswith("faster_whisper"):
            raise ImportError("no faster-whisper here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)
    assert ov.speech_in([0.0, 0.0, 0.0]) is None


def fake_vad(monkeypatch, answer):
    """Stand in for faster-whisper's Silero module, which is not installed
    wherever the tests run."""
    import sys
    import types

    package = types.ModuleType("faster_whisper")
    module = types.ModuleType("faster_whisper.vad")
    module.get_speech_timestamps = answer
    package.vad = module
    monkeypatch.setitem(sys.modules, "faster_whisper", package)
    monkeypatch.setitem(sys.modules, "faster_whisper.vad", module)


def test_a_recording_the_filter_hears_no_speech_in_is_left_alone(monkeypatch):
    """An empty answer must not become an empty recording: nothing is cut and
    the model gets what it was given, silences and all."""
    fake_vad(monkeypatch, lambda audio: [])
    assert ov.speech_in([1.0, 2.0]) is None


def test_a_filter_that_throws_does_not_take_the_transcription_with_it(monkeypatch):
    """It is a saving, not a requirement: a recording transcribed whole is a
    worse transcription, not a failed one."""
    def explode(audio):
        raise RuntimeError("onnxruntime is not installed")

    fake_vad(monkeypatch, explode)
    assert ov.speech_in([1.0, 2.0]) is None


def test_the_speech_the_filter_found_is_what_comes_back(monkeypatch):
    found = [{"start": 0, "end": 16000}]
    fake_vad(monkeypatch, lambda audio: found)
    assert ov.speech_in([1.0, 2.0]) == found


# --- the fixed-window fallback --------------------------------------------

def test_the_fallback_does_not_make_transformers_lecture_the_user(monkeypatch):
    """Fixed windows are experimental on a seq2seq model and transformers
    says so at length. The fallback has already said it in its own words, and
    the paragraph reads like a fault in a transcription that is running."""
    monkeypatch.setattr(ov, "takes_ignore_warning", lambda: True)
    settings = ov.windowing()

    assert settings["chunk_length_s"] == ov.FALLBACK_WINDOW_S
    assert settings["stride_length_s"] == ov.FALLBACK_OVERLAP_S
    assert settings["ignore_warning"] is True


def test_a_keyword_this_installation_does_not_know_is_not_sent(monkeypatch):
    """An unrecognised keyword is not ignored: the pipeline hands it to
    generate(), which refuses it and takes the fallback down with it."""
    monkeypatch.setattr(ov, "takes_ignore_warning", lambda: False)
    assert "ignore_warning" not in ov.windowing()


def test_the_keyword_is_looked_for_in_the_pipeline_that_is_installed():
    """Answered from the signature, not from a version number - and False,
    not an exception, when transformers is not installed at all."""
    assert ov.takes_ignore_warning() in (True, False)


# --- faster-whisper devices and precision ---------------------------------

def test_faster_whisper_auto_is_cpu_without_cuda(monkeypatch):
    monkeypatch.setattr(fw, "has_cuda", lambda: False)
    assert fw.resolve_device("auto") == "cpu"


def test_faster_whisper_gpu_request_falls_back_to_the_cpu(monkeypatch):
    monkeypatch.setattr(fw, "has_cuda", lambda: False)
    assert fw.resolve_device("GPU") == "cpu"


def test_faster_whisper_uses_cuda_when_available(monkeypatch):
    monkeypatch.setattr(fw, "has_cuda", lambda: True)
    assert fw.resolve_device("auto") == "cuda"
    assert fw.resolve_device("GPU") == "cuda"


def test_compute_type_defaults_to_int8_on_cpu_and_float16_on_cuda():
    assert fw.resolve_compute_type(None, "cpu") == "int8"
    assert fw.resolve_compute_type(None, "cuda") == "float16"
    assert fw.resolve_compute_type("float32", "cpu") == "float32"


def test_model_names_are_normalised():
    assert fw.resolve_model("openai/whisper-large-v3") == "large-v3"
    assert fw.resolve_model("small") == "small"
    assert fw.resolve_model(None) == "large-v3"


# --- fit warnings ---------------------------------------------------------

def test_warns_when_the_model_does_not_fit_in_memory(monkeypatch, capsys):
    monkeypatch.setattr(transcription, "available_ram_gb", lambda: 1.0)
    monkeypatch.setattr(transcription, "cpu_count", lambda: 16)
    transcription.warn_if_tight(backends.FASTER_WHISPER, "large-v3", "int8")
    assert "large-v3" in capsys.readouterr().err


def test_no_memory_warning_when_the_model_fits(monkeypatch, capsys):
    monkeypatch.setattr(transcription, "available_ram_gb", lambda: 32.0)
    monkeypatch.setattr(transcription, "cpu_count", lambda: 16)
    transcription.warn_if_tight(backends.FASTER_WHISPER, "large-v3", "int8")
    assert capsys.readouterr().err == ""


def test_warns_when_a_heavy_model_meets_very_few_cores(monkeypatch, capsys):
    monkeypatch.setattr(transcription, "available_ram_gb", lambda: 64.0)
    monkeypatch.setattr(transcription, "cpu_count", lambda: 2)
    monkeypatch.setattr(transcription, "has_cuda", lambda: False)
    transcription.warn_if_tight(backends.FASTER_WHISPER, "large-v3", "int8")
    assert "2" in capsys.readouterr().err


def test_small_model_on_few_cores_is_not_flagged(monkeypatch, capsys):
    monkeypatch.setattr(transcription, "available_ram_gb", lambda: 64.0)
    monkeypatch.setattr(transcription, "cpu_count", lambda: 2)
    monkeypatch.setattr(transcription, "has_cuda", lambda: False)
    transcription.warn_if_tight(backends.FASTER_WHISPER, "small", "int8")
    assert capsys.readouterr().err == ""


def test_model_key_accepts_both_spellings():
    assert transcription.model_key("openai/whisper-medium") == "medium"
    assert transcription.model_key("small.en") == "small"


# --- choosing a model for the machine -------------------------------------

@pytest.mark.parametrize("machine,expected", [
    # (cores, free GiB) -> the model someone should be given by default
    ((2, 2.8), "small"),            # the 2 vCPU server this was measured on
    ((1, 1.5), "base"),             # one core: anything larger is a whole day
    ((2, 1.0), "tiny"),             # memory decides before speed does
    ((4, 8.0), "large-v3-turbo"),
    ((8, 16.0), "large-v3-turbo"),
    ((16, 32.0), "large-v3"),       # enough cores to run the big one honestly
])
def test_the_default_model_follows_the_cpu(machine, expected):
    cores, ram = machine
    assert transcription.recommend_model(cores=cores, ram=ram) == expected


def test_a_cuda_gpu_takes_the_best_model():
    assert transcription.recommend_model(cores=4, ram=16, cuda=True) == "large-v3"


def test_an_intel_accelerator_is_limited_by_memory_not_by_patience():
    """OpenVINO on an iGPU runs at full precision but is not a CPU: the speed
    table does not apply, the memory figure does."""
    assert transcription.recommend_model(backends.OPENVINO, cores=8, ram=21.0,
                                         accelerator=True) == "large-v3"
    assert transcription.recommend_model(backends.OPENVINO, cores=4, ram=5.0,
                                         accelerator=True) == "large-v3-turbo"


def test_unknown_memory_does_not_push_the_choice_downwards():
    """available_ram_gb() returns None on an unusual platform; that is not a
    reason to hand someone 'tiny'. Note ram=None, not the DETECT sentinel:
    'we could not measure it' and 'go and measure it' are different answers,
    and if they were the same value this test would quietly grade the machine
    it happens to run on."""
    assert transcription.recommend_model(cores=8, ram=None) == "large-v3-turbo"
    assert transcription.recommend_model(cores=1, ram=None) == "base"


def test_a_recommendation_is_always_a_model_that_exists():
    for cores in (1, 2, 4, 8, 32):
        for ram in (0.2, 1.0, 4.0, 64.0, None, transcription.DETECT):
            model = transcription.recommend_model(cores=cores, ram=ram)
            assert model in transcription.MODEL_RAM_GB


def test_auto_becomes_a_real_name_and_says_so():
    model, chosen = transcription.resolve_model("auto")
    assert chosen and model in transcription.MODEL_RAM_GB
    assert transcription.resolve_model("") == transcription.resolve_model("auto")


def test_an_explicit_model_is_left_alone():
    assert transcription.resolve_model("medium") == ("medium", False)
    assert transcription.resolve_model("openai/whisper-large-v3")[1] is False


# --- what the OpenVINO pipeline hands back --------------------------------

def test_chunks_become_segments():
    chunks = [{"text": " prima parte", "timestamp": (0.0, 4.5)},
              {"text": "seconda parte", "timestamp": (4.5, 9.0)}]
    assert ov.segments_of(chunks) == [
        {"text": "prima parte", "start": 0.0, "end": 4.5},
        {"text": "seconda parte", "start": 4.5, "end": 9.0}]


def test_a_chunk_with_no_end_takes_the_next_ones_start():
    """What a window that ran to the end of the audio reports."""
    chunks = [{"text": "prima", "timestamp": (0.0, None)},
              {"text": "seconda", "timestamp": (6.0, 9.0)}]
    assert ov.segments_of(chunks)[0]["end"] == 6.0


def test_the_last_chunk_with_no_end_takes_the_length_of_the_recording():
    chunks = [{"text": "ultima", "timestamp": (12.0, None)}]
    assert ov.segments_of(chunks, audio_seconds=20.0)[0]["end"] == 20.0
    # Nothing to fall back on: a segment with no clock cannot be laid out.
    assert ov.segments_of(chunks) == []


def test_a_chunk_with_no_start_is_dropped():
    assert ov.segments_of([{"text": "senza tempo", "timestamp": (None, None)}]) == []


def test_word_chunks_become_timed_words():
    chunks = [{"text": " ogni", "timestamp": (1.0, 1.4)},
              {"text": "asset", "timestamp": (1.4, 1.9)},
              {"text": "", "timestamp": (1.9, 2.0)}]
    assert ov.words_of(chunks) == [{"word": "ogni", "start": 1.0, "end": 1.4},
                                   {"word": "asset", "start": 1.4, "end": 1.9}]


def test_the_vad_it_cannot_honour_is_said_out_loud(capsys):
    """Accepting vad=True in silence would be a promise this backend cannot
    keep, and a hallucination over a silence is what comes of it."""
    ov.warn_about_vad(True)
    assert "faster-whisper" in capsys.readouterr().err
    ov.warn_about_vad(False)
    assert capsys.readouterr().err == ""


def test_the_long_form_guards_are_off_by_default_nowhere():
    """Whisper's own anti-hallucination guards, which only the long-form loop
    applies: this is the reason to prefer it over fixed windows."""
    assert ov.DECODING_GUARDS["condition_on_prev_tokens"] is False
    assert ov.DECODING_GUARDS["temperature"][0] == 0.0
    assert len(ov.DECODING_GUARDS["temperature"]) > 1


# --- installed, and yet not there -----------------------------------------

def test_a_package_that_is_there_but_will_not_load_says_so(monkeypatch):
    """The Windows classic: ctranslate2 without its runtime, or an OpenVINO
    whose DLLs lost their place in the search path. "The package is not
    installed" sends somebody to install what they have just installed."""
    monkeypatch.setattr(backends, "module_available", lambda name: name == "ctranslate2")
    broken = ImportError("DLL load failed while importing translator")
    broken.name = "ctranslate2"

    message = backends.import_failure("faster_whisper.missing", broken)
    assert "ctranslate2" in message
    assert "DLL load failed" in message          # the real reason, not ours
    assert "pip install" not in message          # it is installed already


def test_a_package_that_really_is_missing_says_how_to_install_it(monkeypatch):
    monkeypatch.setattr(backends, "module_available", lambda name: False)
    absent = ImportError("No module named 'faster_whisper'")
    absent.name = "faster_whisper"

    message = backends.import_failure("faster_whisper.missing", absent)
    assert "pip install" in message


def test_an_error_that_names_nothing_falls_back_to_the_install_message():
    assert "pip install" in backends.import_failure("openvino.missing",
                                                    ImportError("something"))


# --- the whole OpenVINO path, with no OpenVINO -----------------------------

def fake_intel_stack(monkeypatch, chunks):
    """optimum-intel and transformers, as far as this backend touches them.

    Neither is installed wherever the tests run, and neither can be: they
    bring a runtime and a converted model with them. What is being checked
    here is this module's own wiring — what it hands the pipeline, and what it
    makes of what comes back."""
    import sys
    import types

    seen = {}

    class Model:
        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            return cls()

        def to(self, device):
            return self

        def compile(self):
            pass

        def save_pretrained(self, path):
            os.makedirs(path, exist_ok=True)

    class Processor:
        tokenizer = object()
        feature_extractor = object()

        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            return cls()

        def save_pretrained(self, path):
            os.makedirs(path, exist_ok=True)

    def pipeline(task, **kwargs):
        seen["built"] = kwargs

        def run(inputs, **call_kwargs):
            seen["samples"] = len(inputs["raw"])
            return {"text": "one two", "chunks": chunks}

        return run

    optimum = types.ModuleType("optimum")
    intel = types.ModuleType("optimum.intel")
    intel.OVModelForSpeechSeq2Seq = Model
    optimum.intel = intel
    transformers = types.ModuleType("transformers")
    transformers.AutoProcessor = Processor
    transformers.pipeline = pipeline
    for name, module in (("optimum", optimum), ("optimum.intel", intel),
                         ("transformers", transformers)):
        monkeypatch.setitem(sys.modules, name, module)
    return seen


def test_the_model_never_sees_the_silence_and_the_subtitles_never_know(tmp_path,
                                                                       monkeypatch):
    """End to end: the silence is cut before the pipeline is called, and the
    segments that come back are on the recording's clock, not the trimmed one.

    This is the pair that has to hold together. Cutting without restoring
    would put every subtitle of a long interview seconds early."""
    import numpy as np

    monkeypatch.setattr(ov, "openvino_devices", lambda: ["CPU"])
    # Ten seconds: a second of speech, seven of silence, two more of speech.
    fake_vad(monkeypatch, lambda audio: [{"start": 0, "end": 16000},
                                         {"start": 16000 * 8, "end": 16000 * 10}])
    seen = fake_intel_stack(monkeypatch, [
        {"text": "one", "timestamp": (0.0, 1.0)},
        {"text": "two", "timestamp": (1.2, 3.0)},
    ])

    segments, text, device = ov.transcribe(
        np.zeros(16000 * 10, dtype=np.float32), "small", "it", "auto",
        str(tmp_path / "models"), "")

    # Three seconds went to the model, not ten.
    assert seen["samples"] == 16000 * 3
    assert text == "one two" and device == "CPU"
    # And the second segment is back where it was said, after the silence.
    assert segments[0]["start"] == 0.0 and segments[0]["end"] == 1.0
    assert segments[1]["start"] == 8.2 and segments[1]["end"] == 10.0


def test_the_long_form_loop_is_asked_for_before_fixed_windows(tmp_path, monkeypatch):
    """Fixed windows are the fallback, and the fallback stitches overlapping
    text back together - which is where a phrase comes out twice."""
    import numpy as np

    monkeypatch.setattr(ov, "openvino_devices", lambda: ["CPU"])
    fake_vad(monkeypatch, lambda audio: None)
    seen = fake_intel_stack(monkeypatch, [{"text": "one", "timestamp": (0.0, 1.0)}])

    ov.transcribe(np.zeros(16000 * 120, dtype=np.float32), "small", "it", "auto",
                  str(tmp_path / "models"), "")

    # No windowing on the first attempt: the model does its own.
    assert "chunk_length_s" not in seen["built"]
    assert seen["samples"] == 16000 * 120
