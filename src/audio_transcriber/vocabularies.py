"""Named sets of keywords ("vocabularies") that steer Whisper's transcription.

Whisper mangles recurring technical terms unless the initial prompt tells it
they exist. A vocabulary is that list of terms, saved under a name so it can be
picked with ``--vocab iso27001-it`` instead of a file path that has to be typed
right every time — and so the web UI can offer the same sets in a menu.

A vocabulary is a plain text file, ``<name>.txt``. Lines starting with ``#`` are
comments; two of them are read as metadata::

    # title: ISO 27001 and risk assessment (Italian)
    # language: it

Everything else is the vocabulary itself: whitespace is collapsed, so the file
can be laid out for a human while Whisper receives one compact line.

They are looked up in two places, the first match winning:

``<config>/vocabularies``
    written by whoever installs and configures the tool (``vocab new`` creates
    one); this is the "installation level" set of choices;
``audio_transcriber/data/vocabularies``
    shipped with the package, as examples worth starting from.

A set defined by hand in the config directory therefore shadows a bundled one
of the same name, which is how you replace an example with your own version.

Web callers pass a name that came from a browser, so :func:`get` resolves only
validated names inside the known directories: a name is a slug, never a path.
"""
import os
import re

from .paths import vocabularies_dir

SUFFIX = ".txt"
SOURCE_USER = "user"
SOURCE_BUNDLED = "bundled"

# Whisper's initial prompt is capped at about 224 tokens and silently truncated
# beyond that; a longer one also makes the model start repeating it back.
MAX_PROMPT_CHARS = 900

#: A vocabulary typed into an interface — the browser's local sets, the terms
#: box in the window — is a list of terms, not an essay. Unlike
#: :data:`MAX_PROMPT_CHARS` this is a refusal, not a warning: the text arrives
#: from outside and something has to bound it.
MAX_CUSTOM_VOCABULARY = 4000

# A name is a file name, and it arrives from an HTTP request: no dots leading
# anywhere, no separators, nothing to walk out of the directory with.
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

BUNDLED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "data", "vocabularies")

_METADATA_KEYS = ("title", "language")


class VocabularyError(Exception):
    """Unknown, unreadable or badly named vocabulary."""


def valid_name(name):
    """True if ``name`` is a usable vocabulary name."""
    return bool(NAME_PATTERN.match(str(name or "")))


def normalise_name(text):
    """Turn a human title into a valid name, or return '' if nothing is left."""
    slug = re.sub(r"[^a-z0-9]+", "-", str(text or "").strip().lower()).strip("-_")
    return slug[:64].strip("-_")


def parse(raw):
    """The prompt Whisper receives: comments dropped, whitespace collapsed."""
    lines = [line for line in str(raw or "").splitlines()
             if not line.lstrip().startswith("#")]
    return " ".join(" ".join(lines).split())


def metadata(raw):
    """``title`` and ``language`` read from the ``# key: value`` header."""
    found = {}
    for line in str(raw or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            if stripped:
                break        # the header stops at the first real line
            continue
        body = stripped.lstrip("#").strip()
        key, separator, value = body.partition(":")
        key = key.strip().lower()
        if separator and key in _METADATA_KEYS and key not in found:
            found[key] = value.strip()
    return found


def terms(text):
    """The individual entries of a vocabulary, for counting and display.

    Both styles are in use: terms separated by commas, wrapped freely across
    lines, or one term per line. Commas win when there are any, because a file
    written that way wraps mid-term and splitting on the break would cut terms
    in half."""
    prompt = parse(text)
    if "," in prompt:
        chunks = prompt.split(",")
    else:
        chunks = [" ".join(line.split()) for line in str(text or "").splitlines()
                  if not line.lstrip().startswith("#")]
    return [chunk.strip(" .;") for chunk in chunks if chunk.strip(" .;")]


class Vocabulary:
    """One named keyword set, read lazily from disk."""

    def __init__(self, name, path, source):
        self.name = name
        self.path = path
        self.source = source
        self._raw = None

    @property
    def raw(self):
        """The file as written, comments included."""
        if self._raw is None:
            try:
                with open(self.path, encoding="utf-8") as handle:
                    self._raw = handle.read()
            except OSError as exc:
                raise VocabularyError(f"{self.name}: {exc}") from exc
        return self._raw

    @property
    def text(self):
        """The prompt text, ready to hand to the transcription backend."""
        return parse(self.raw)

    @property
    def title(self):
        return metadata(self.raw).get("title") or self.name

    @property
    def language(self):
        return metadata(self.raw).get("language") or None

    def as_dict(self, include_text=False):
        """JSON-friendly description, which is what the web API returns."""
        text = self.text
        data = {"name": self.name, "source": self.source, "title": self.title,
                "language": self.language, "terms": len(terms(text)),
                "chars": len(text)}
        if include_text:
            data["text"] = text
            data["raw"] = self.raw
        return data

    def __repr__(self):
        return f"Vocabulary({self.name!r}, {self.source!r})"


def user_dir():
    """Where hand-written vocabularies go."""
    return vocabularies_dir()


def search_paths(extra=None):
    """``(directory, source)`` pairs, most significant first.

    ``extra`` is an additional directory (the ``[paths] vocabularies`` setting)
    that takes precedence over both managed locations."""
    pairs = []
    if extra:
        pairs.append((os.path.abspath(os.path.expanduser(extra)), SOURCE_USER))
    pairs.append((user_dir(), SOURCE_USER))
    pairs.append((BUNDLED_DIR, SOURCE_BUNDLED))
    return pairs


def available(extra=None):
    """Every vocabulary that can be selected, by name, shadowing included."""
    found = {}
    for directory, source in search_paths(extra):
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            continue
        for filename in names:
            if not filename.endswith(SUFFIX):
                continue
            name = filename[: -len(SUFFIX)]
            if not valid_name(name) or name in found:
                continue
            found[name] = Vocabulary(name, os.path.join(directory, filename), source)
    return [found[name] for name in sorted(found)]


def get(name, extra=None):
    """The vocabulary called ``name``, or raise :class:`VocabularyError`."""
    name = str(name or "").strip()
    if not valid_name(name):
        raise VocabularyError(f"invalid vocabulary name: {name!r}")
    for directory, source in search_paths(extra):
        candidate = os.path.join(directory, name + SUFFIX)
        if os.path.isfile(candidate):
            return Vocabulary(name, candidate, source)
    known = ", ".join(v.name for v in available(extra)) or "none"
    raise VocabularyError(f"unknown vocabulary '{name}' (available: {known})")


def split_names(value):
    """Accept a comma-separated string, a list, or a mix of both."""
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple)) else [value]
    names = []
    for item in items:
        for part in str(item).split(","):
            part = part.strip()
            if part and part not in names:
                names.append(part)
    return names


def load(names, extra=None):
    """The combined prompt text of ``names``, in the order they were given."""
    parts = [get(name, extra).text for name in split_names(names)]
    return " ".join(part for part in parts if part)


def create(name, text, directory=None, overwrite=False):
    """Write a new vocabulary in the user directory and return its path."""
    if not valid_name(name):
        raise VocabularyError(
            f"invalid vocabulary name: {name!r} "
            "(lowercase letters, digits, '-' and '_', starting with a letter or digit)")
    directory = directory or user_dir()
    path = os.path.join(directory, name + SUFFIX)
    if os.path.exists(path) and not overwrite:
        raise VocabularyError(f"{path} already exists")
    try:
        os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text if text.endswith("\n") else text + "\n")
    except OSError as exc:
        raise VocabularyError(f"{name}: {exc}") from exc
    return path


TEMPLATE = """\
# title: {title}
# language: {language}
# One vocabulary per subject: the terms Whisper keeps getting wrong.
# Lines starting with # are comments. Keep the list to a few dozen terms:
# a longer prompt is truncated and makes the model repeat it back.

"""


def template(name, title=None, language=""):
    """Starting point for a hand-written vocabulary."""
    return TEMPLATE.format(title=title or name.replace("-", " "), language=language)
