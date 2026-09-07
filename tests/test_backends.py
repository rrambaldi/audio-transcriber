"""Backend, device and precision selection: pure logic, no engine installed."""
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


def test_backend_aliases_are_accepted():
    for alias in ("ct2", "faster_whisper", "CTranslate2"):
        assert backends.resolve_backend(alias, "auto") == backends.FASTER_WHISPER
    assert backends.resolve_backend("OV", "auto") == backends.OPENVINO


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
