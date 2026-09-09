"""Configuration: a ``.env`` for secrets and a ``config.toml`` for defaults.

Precedence, strongest first: command-line option, environment variable,
``config.toml``, built-in default. Nothing here is required — the tool works
with no configuration at all.

The secrets (currently only the Hugging Face token) stay in a ``.env`` rather
than in ``config.toml``, so the file that may be worth sharing and the file
that must never be shared are different files.
"""
import os
import tomllib

from .paths import config_file, dotenv_candidates

# Built-in defaults. The CLI reads them from here so that "no option given"
# means the same thing whether or not a config file exists.
DEFAULTS = {
    "interface_language": None,   # None: environment, then system locale
    "language": "it",
    "backend": "auto",
    "device": "auto",
    "model": "auto",           # "auto": worked out from the machine
    "compute_type": None,         # None: int8 on CPU, float16 on CUDA
    "threads": None,              # None: every available core
    "vad": True,
    "prompt": "",
    "prompt_file": None,
    "vocabulary": None,           # names of the keyword sets to prepend
    "para_gap": 1.2,
    "para_max_chars": 600,
    "keep_fillers": False,
    "diarize": False,
    "subtitles": None,            # formats to save: "srt", "vtt", "srt,vtt"
    "subtitle_preset": None,      # None: the module's default (netflix)
    "subtitle_chars": None,       # characters per line
    "subtitle_lines": None,       # lines per cue
    "subtitle_words": None,       # words per cue, if you would rather cap that
    "speakers": None,
    "diar_model": None,
    "models_dir": None,
    "library_dir": None,
    "vocab_dir": None,
    "cache_dir": None,
}

# (section, key) in config.toml -> internal name and expected Python type.
SCHEMA = {
    ("general", "interface_language"): ("interface_language", str),
    ("general", "language"): ("language", str),
    ("transcription", "backend"): ("backend", str),
    ("transcription", "device"): ("device", str),
    ("transcription", "model"): ("model", str),
    ("transcription", "compute_type"): ("compute_type", str),
    ("transcription", "threads"): ("threads", int),
    ("transcription", "vad"): ("vad", bool),
    ("transcription", "prompt"): ("prompt", str),
    ("transcription", "prompt_file"): ("prompt_file", str),
    ("transcription", "vocabulary"): ("vocabulary", str),
    ("output", "paragraph_gap"): ("para_gap", float),
    ("output", "paragraph_max_chars"): ("para_max_chars", int),
    ("output", "keep_fillers"): ("keep_fillers", bool),
    ("subtitles", "save"): ("subtitles", str),
    ("subtitles", "preset"): ("subtitle_preset", str),
    ("subtitles", "max_chars_per_line"): ("subtitle_chars", int),
    ("subtitles", "max_lines"): ("subtitle_lines", int),
    ("subtitles", "max_words_per_cue"): ("subtitle_words", int),
    ("diarization", "enabled"): ("diarize", bool),
    ("diarization", "speakers"): ("speakers", int),
    ("diarization", "model"): ("diar_model", str),
    ("paths", "models"): ("models_dir", str),
    ("paths", "library"): ("library_dir", str),
    ("paths", "vocabularies"): ("vocab_dir", str),
    ("paths", "cache"): ("cache_dir", str),
}


class ConfigError(Exception):
    """Raised when config.toml exists but cannot be used."""


def load_dotenv(paths=None):
    """Load ``KEY=VALUE`` files into the environment.

    Real environment variables always win, and among the files the first one
    that defines a key wins (working directory before the user config)."""
    for path in (paths if paths is not None else dotenv_candidates()):
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(),
                                          value.strip().strip('"').strip("'"))
        except OSError:
            continue


def _coerce(value, expected, where):
    """Check a TOML value against the schema, allowing int where float is due."""
    if expected is float and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    if expected is bool and not isinstance(value, bool):
        raise ConfigError(f"{where}: expected true/false, got {value!r}")
    if not isinstance(value, expected):
        raise ConfigError(f"{where}: expected {expected.__name__}, got {value!r}")
    return value


def load_config(path=None):
    """Read config.toml and return ``(settings, path_or_None, warnings)``.

    A missing file is not an error: it yields empty settings. A malformed one
    is, because silently ignoring a config the user wrote is worse than
    stopping."""
    path = path or config_file()
    if not os.path.exists(path):
        return {}, None, []
    try:
        with open(path, "rb") as handle:
            raw = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(str(exc)) from exc

    settings, warnings = {}, []
    for section, values in raw.items():
        if not isinstance(values, dict):
            warnings.append(f"[{section}]: expected a section, ignored")
            continue
        for key, value in values.items():
            entry = SCHEMA.get((section, key))
            if entry is None:
                warnings.append(f"{section}.{key}: unknown option, ignored")
                continue
            name, expected = entry
            settings[name] = _coerce(value, expected, f"{section}.{key}")
    return settings, path, warnings


def read_prompt(prompt, prompt_file, vocabulary=None, vocab_dir=None):
    """Resolve the domain prompt handed to the transcription backend.

    Three sources, concatenated in this order: the named keyword sets
    (``--vocab``), then either a prompt file or an inline prompt — an explicit
    file wins over an inline string, as it always has.

    In a prompt file, ``#`` lines are comments and whitespace is collapsed, so
    a vocabulary can be kept readable without bloating the prompt Whisper
    actually receives."""
    from .vocabularies import VocabularyError
    from .vocabularies import load as load_vocabularies

    parts = []
    if vocabulary:
        try:
            parts.append(load_vocabularies(vocabulary, vocab_dir))
        except VocabularyError as exc:
            raise ConfigError(str(exc)) from exc
    if prompt_file:
        expanded = os.path.abspath(os.path.expanduser(prompt_file))
        try:
            with open(expanded, encoding="utf-8") as handle:
                lines = [line for line in handle
                         if not line.lstrip().startswith("#")]
        except OSError as exc:
            raise ConfigError(f"prompt_file: {exc}") from exc
        parts.append(" ".join(" ".join(lines).split()))
    elif prompt:
        parts.append(prompt)
    return " ".join(part for part in parts if part)


def resolve(cli_values, file_settings):
    """Merge command-line values over file settings over built-in defaults.

    A CLI value of ``None`` means "not given"; store_true flags are passed as
    ``True`` only when set, so they never silently override the file."""
    merged = dict(DEFAULTS)
    merged.update({k: v for k, v in file_settings.items() if v is not None})
    merged.update({k: v for k, v in cli_values.items() if v is not None})
    return merged
