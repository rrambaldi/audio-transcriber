"""Where files go: platform defaults, overrides, and legacy folders."""
import os

import pytest

from audio_transcriber import paths

ENV_VARS = (paths.ENV_HOME, paths.ENV_CONFIG_DIR, paths.ENV_DATA_DIR,
            paths.ENV_CACHE_DIR, paths.ENV_MODELS_DIR, paths.ENV_LIBRARY_DIR,
            "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """Start every test from a machine with nothing configured."""
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_xdg_variables_are_honoured(monkeypatch, tmp_path):
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    assert paths.data_dir() == str(tmp_path / "data" / paths.APP_NAME)
    assert paths.config_dir() == str(tmp_path / "config" / paths.APP_NAME)
    assert paths.cache_dir() == str(tmp_path / "cache" / paths.APP_NAME)


def test_home_override_puts_everything_in_one_folder(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
    assert paths.config_dir() == str(tmp_path / "config")
    assert paths.data_dir() == str(tmp_path / "data")
    assert paths.cache_dir() == str(tmp_path / "cache")
    assert paths.library_dir() == str(tmp_path / "data" / "library")


def test_per_purpose_override_beats_the_home_override(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "home"))
    monkeypatch.setenv(paths.ENV_LIBRARY_DIR, str(tmp_path / "elsewhere"))
    assert paths.library_dir() == str(tmp_path / "elsewhere")
    assert paths.data_dir() == str(tmp_path / "home" / "data")


def test_overrides_expand_user_and_variables(monkeypatch, tmp_path):
    monkeypatch.setenv("SOME_ROOT", str(tmp_path))
    monkeypatch.setenv(paths.ENV_LIBRARY_DIR, "$SOME_ROOT/recordings")
    assert paths.library_dir() == str(tmp_path / "recordings")


def test_models_are_namespaced_per_backend(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
    assert paths.models_dir("openvino").endswith(os.path.join("models", "openvino"))
    assert paths.models_dir("faster-whisper").endswith(
        os.path.join("models", "faster-whisper"))


def test_a_legacy_model_folder_in_the_working_directory_still_wins(monkeypatch, tmp_path):
    """Existing installs must keep using the models they already downloaded."""
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "managed"))
    workdir = tmp_path / "project"
    (workdir / paths.LEGACY_MODELS_DIRNAME).mkdir(parents=True)
    monkeypatch.chdir(workdir)
    legacy = str(workdir / paths.LEGACY_MODELS_DIRNAME)
    assert paths.models_root() == legacy
    # OpenVINO models sat at the top level of that folder, so they stay there.
    assert paths.models_dir("openvino") == legacy
    assert paths.models_dir("faster-whisper") == os.path.join(legacy, "faster-whisper")


def test_an_explicit_models_override_beats_the_legacy_folder(monkeypatch, tmp_path):
    workdir = tmp_path / "project"
    (workdir / paths.LEGACY_MODELS_DIRNAME).mkdir(parents=True)
    monkeypatch.chdir(workdir)
    monkeypatch.setenv(paths.ENV_MODELS_DIR, str(tmp_path / "chosen"))
    assert paths.models_dir("openvino") == str(tmp_path / "chosen" / "openvino")


def test_dotenv_prefers_the_working_directory(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "managed"))
    monkeypatch.chdir(tmp_path)
    candidates = paths.dotenv_candidates()
    assert candidates[0] == str(tmp_path / ".env")
    assert candidates[1].startswith(str(tmp_path / "managed"))


def test_legacy_diarization_config_is_found_in_the_working_directory(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "managed"))
    monkeypatch.chdir(tmp_path)
    legacy = tmp_path / paths.LEGACY_DIARIZATION_DIRNAME
    legacy.mkdir()
    (legacy / "config.yaml").write_text("x")
    assert paths.diarization_config() == str(legacy / "config.yaml")


def test_windows_layout(monkeypatch, tmp_path):
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert paths.config_dir() == str(tmp_path / "Roaming" / paths.APP_NAME)
    assert paths.data_dir() == str(tmp_path / "Local" / paths.APP_NAME)
    assert paths.cache_dir() == str(tmp_path / "Local" / paths.APP_NAME / "Cache")


def test_describe_lists_every_managed_location(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path))
    labels = [label for label, _, _, _ in paths.describe()]
    assert {"config", "data", "models", "library", "cache"} <= set(labels)


def test_describe_reports_where_the_files_actually_are(monkeypatch, tmp_path):
    """A [paths] entry in config.toml moves a directory; the command that
    answers "where are my files" has to follow it, or it answers wrongly."""
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "home"))
    volume = tmp_path / "volume"
    rows = {label: (path, configured)
            for label, path, _, configured in paths.describe(
                {"library_dir": str(volume / "library"),
                 "cache_dir": str(volume / "cache")})}
    assert rows["library"] == (str(volume / "library"), True)
    assert rows["cache"] == (str(volume / "cache"), True)
    assert rows["models"][1] is False          # not overridden: still managed
    assert rows["models"][0].startswith(str(tmp_path / "home"))
