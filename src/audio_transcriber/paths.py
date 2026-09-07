"""Where the program keeps its files.

A command-line tool should not scatter caches and recordings across whatever
directory it happens to be run from. Everything therefore lives in the
platform's standard per-user locations:

===========  =========================================  ==============================
purpose      Linux / BSD                                Windows
===========  =========================================  ==============================
config       ``$XDG_CONFIG_HOME/audio-transcriber``     ``%APPDATA%\\audio-transcriber``
data         ``$XDG_DATA_HOME/audio-transcriber``       ``%LOCALAPPDATA%\\audio-transcriber``
cache        ``$XDG_CACHE_HOME/audio-transcriber``      ``%LOCALAPPDATA%\\audio-transcriber\\Cache``
===========  =========================================  ==============================

On macOS the data and config roots are ``~/Library/Application Support`` and
the cache root is ``~/Library/Caches``.

Three escape hatches, in order of precedence:

1. a per-purpose variable (``AUDIO_TRANSCRIBER_MODELS_DIR`` and friends);
2. ``AUDIO_TRANSCRIBER_HOME``, which puts config, data and cache under a single
   self-contained folder — the portable mode you want in a container or on a
   server with a mounted volume;
3. the platform defaults above.

For backwards compatibility, a ``whisper-ov-models`` or ``pyannote-diar``
folder in the current working directory still wins over the managed location:
existing installs keep using the models they already downloaded.
"""
import os
import sys

APP_NAME = "audio-transcriber"

ENV_HOME = "AUDIO_TRANSCRIBER_HOME"
ENV_CONFIG_DIR = "AUDIO_TRANSCRIBER_CONFIG_DIR"
ENV_DATA_DIR = "AUDIO_TRANSCRIBER_DATA_DIR"
ENV_CACHE_DIR = "AUDIO_TRANSCRIBER_CACHE_DIR"
ENV_MODELS_DIR = "AUDIO_TRANSCRIBER_MODELS_DIR"
ENV_LIBRARY_DIR = "AUDIO_TRANSCRIBER_LIBRARY_DIR"
ENV_VOCAB_DIR = "AUDIO_TRANSCRIBER_VOCABULARIES_DIR"

# Folders written by versions <= 0.2 in the working directory.
LEGACY_MODELS_DIRNAME = "whisper-ov-models"
LEGACY_DIARIZATION_DIRNAME = "pyannote-diar"

CONFIG_FILENAME = "config.toml"
DOTENV_FILENAME = ".env"


def _env_path(name):
    """Expanded absolute path from an environment variable, or None."""
    value = (os.environ.get(name) or "").strip()
    if not value:
        return None
    return os.path.abspath(os.path.expanduser(os.path.expandvars(value)))


def _home_root():
    """Root of the portable single-folder layout, if requested."""
    return _env_path(ENV_HOME)


def _platform_root(kind):
    """Platform-specific root for 'config', 'data' or 'cache'."""
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        roaming = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
        if kind == "config":
            return os.path.join(roaming, APP_NAME)
        if kind == "cache":
            return os.path.join(local, APP_NAME, "Cache")
        return os.path.join(local, APP_NAME)
    if sys.platform == "darwin":
        if kind == "cache":
            return os.path.join(home, "Library", "Caches", APP_NAME)
        return os.path.join(home, "Library", "Application Support", APP_NAME)
    xdg = {"config": ("XDG_CONFIG_HOME", os.path.join(home, ".config")),
           "data": ("XDG_DATA_HOME", os.path.join(home, ".local", "share")),
           "cache": ("XDG_CACHE_HOME", os.path.join(home, ".cache"))}[kind]
    base = (os.environ.get(xdg[0]) or "").strip() or xdg[1]
    return os.path.join(os.path.expanduser(base), APP_NAME)


def _root(kind, env_var):
    override = _env_path(env_var)
    if override:
        return override
    home = _home_root()
    if home:
        return os.path.join(home, kind)
    return _platform_root(kind)


def config_dir():
    """Directory holding config.toml and the .env with the Hugging Face token."""
    return _root("config", ENV_CONFIG_DIR)


def data_dir():
    """Directory holding everything worth keeping: models and the library."""
    return _root("data", ENV_DATA_DIR)


def cache_dir():
    """Directory for regenerable files; safe to delete at any time."""
    return _root("cache", ENV_CACHE_DIR)


def config_file():
    """Path of the optional configuration file."""
    return os.path.join(config_dir(), CONFIG_FILENAME)


def legacy_models_dir():
    """Pre-0.3 model folder in the working directory, if it exists."""
    candidate = os.path.join(os.getcwd(), LEGACY_MODELS_DIRNAME)
    return candidate if os.path.isdir(candidate) else None


def models_root():
    """Root of the model store, honouring the legacy working-directory folder."""
    override = _env_path(ENV_MODELS_DIR)
    if override:
        return override
    legacy = legacy_models_dir()
    if legacy:
        return legacy
    return os.path.join(data_dir(), "models")


def models_dir(backend=None):
    """Model directory, optionally namespaced per backend.

    Inside the legacy folder the OpenVINO models sit at the top level (that is
    how they were written), so only faster-whisper gets a subfolder there."""
    root = models_root()
    if backend is None:
        return root
    if legacy_models_dir() and not _env_path(ENV_MODELS_DIR):
        return root if backend == "openvino" else os.path.join(root, backend)
    return os.path.join(root, backend)


def library_dir():
    """Root of the recordings library."""
    override = _env_path(ENV_LIBRARY_DIR)
    if override:
        return override
    return os.path.join(data_dir(), "library")


def vocabularies_dir():
    """Directory holding the keyword sets added by whoever installs the tool.

    It sits next to config.toml because it is configuration, not data: the sets
    are written by hand and are worth backing up with the rest of the setup."""
    override = _env_path(ENV_VOCAB_DIR)
    if override:
        return override
    return os.path.join(config_dir(), "vocabularies")


def diarization_config():
    """Default pyannote config: the legacy working-directory folder if present,
    otherwise the managed one."""
    legacy = os.path.join(os.getcwd(), LEGACY_DIARIZATION_DIRNAME, "config.yaml")
    if os.path.exists(legacy):
        return legacy
    return os.path.join(data_dir(), "diarization", "config.yaml")


def dotenv_candidates():
    """.env files to read, least significant last (the first one wins per key).

    The working directory still comes first so a project-local .env keeps
    overriding the user-wide one."""
    return [os.path.join(os.getcwd(), DOTENV_FILENAME),
            os.path.join(config_dir(), DOTENV_FILENAME)]


def ensure(path):
    """Create a directory (and its parents) and return it."""
    os.makedirs(path, exist_ok=True)
    return path


def describe(settings=None):
    """``(label, path, exists, configured)`` for every location in use.

    ``settings`` are the resolved options: a ``[paths]`` entry in config.toml
    moves a directory, and this command exists to answer "where are my files",
    so it has to report where they actually are rather than where they would be
    by default."""
    settings = settings or {}

    def chosen(key, fallback):
        value = settings.get(key)
        if not value:
            return fallback, False
        return os.path.abspath(os.path.expanduser(str(value))), True

    rows = [
        ("config", (config_dir(), False)),
        ("config file", (config_file(), False)),
        ("vocabularies", chosen("vocab_dir", vocabularies_dir())),
        ("data", (data_dir(), False)),
        ("models", chosen("models_dir", models_root())),
        ("library", chosen("library_dir", library_dir())),
        ("cache", chosen("cache_dir", cache_dir())),
    ]
    return [(label, path, os.path.exists(path), configured)
            for label, (path, configured) in rows]
