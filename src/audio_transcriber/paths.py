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
ENV_TEMPLATES_DIR = "AUDIO_TRANSCRIBER_SUMMARY_TEMPLATES_DIR"
ENV_LOG_DIR = "AUDIO_TRANSCRIBER_LOG_DIR"

# Folders written by versions <= 0.2 in the working directory.
LEGACY_MODELS_DIRNAME = "whisper-ov-models"
LEGACY_DIARIZATION_DIRNAME = "pyannote-diar"

CONFIG_FILENAME = "config.toml"
DOTENV_FILENAME = ".env"
LOG_FILENAME = "audio-transcriber.log"


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


def summary_templates_dir():
    """Directory holding the summary templates added by hand.

    Beside the keyword sets, and for the same reason: a template is a page
    somebody decided they wanted, written once and used for years. It is
    configuration, not data."""
    override = _env_path(ENV_TEMPLATES_DIR)
    if override:
        return override
    return os.path.join(config_dir(), "summary-templates")


def log_dir():
    """Directory holding what the window and the server print.

    Under the *cache* root rather than the data one, and the distinction is
    the promise this program makes about each: data is what you would be
    upset to lose, cache is what can be deleted at any time without losing
    anything. A log is the second. It is worth reading after a crash and
    worth nothing a week later."""
    override = _env_path(ENV_LOG_DIR)
    if override:
        return override
    return os.path.join(cache_dir(), "logs")


def log_file():
    """Path of the log, whether or not anything has been written to it."""
    return os.path.join(log_dir(), LOG_FILENAME)


def diarization_candidates():
    """Where a pyannote config is looked for, in the order it is looked for.

    More than one place because there is more than one way people end up with
    these files, and none of them involves reading this docstring. The folder
    beside the command is the pre-0.3 habit; the managed directory is where
    the tool would put them; ``pyannote-diar`` inside it is the same folder
    downloaded by hand and dropped in whole — which keeps the paths written
    inside its config working, since they tend to start with the folder's own
    name."""
    return [
        os.path.join(os.getcwd(), LEGACY_DIARIZATION_DIRNAME, "config.yaml"),
        os.path.join(data_dir(), "diarization", "config.yaml"),
        os.path.join(data_dir(), LEGACY_DIARIZATION_DIRNAME, "config.yaml"),
    ]


def diarization_config():
    """The pyannote config in use: the first candidate that is there.

    With none of them there, the managed location is the answer, because that
    is where the file is missing *from* — an error message naming it is how
    somebody finds out where to put one."""
    for candidate in diarization_candidates():
        if os.path.exists(candidate):
            return candidate
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
        # Written by hand like the keyword sets, and asked about for the same
        # reason: it is one of the two files here worth backing up.
        ("srt presets", (os.path.join(config_dir(), "srt-presets.json"), False)),
        ("data", (data_dir(), False)),
        ("models", chosen("models_dir", models_root())),
        ("library", chosen("library_dir", library_dir())),
        # Asked about as often as the library: "I downloaded the models, where
        # do they go?" - so the answer is one of the lines this prints.
        ("diarization", (diarization_config(), False)),
        ("cache", chosen("cache_dir", cache_dir())),
        # Where the window and the server put what they would otherwise have
        # printed into a terminal nobody is reading. Asked about in exactly
        # one situation, and it is the situation where nothing else worked.
        ("log", (log_file(), False)),
    ]
    return [(label, path, os.path.exists(path), configured)
            for label, (path, configured) in rows]
