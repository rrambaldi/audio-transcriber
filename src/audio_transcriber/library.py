"""The recordings library: one self-contained folder per recording.

Layout of an entry::

    <library>/2026-09-04_1530_team-meeting/
        metadata.json     what it is, how it was transcribed, how long it took
        source.mp4        the original file (copied, moved, or only referenced)
        transcript.txt    the readable text, exactly what the CLI writes
        transcript.json   segments with timestamps and speakers, for tooling
        notes.md          yours to write

Two rules make the format durable. Everything a human needs is plain text, so
an entry stays readable even without this program; and every write goes through
a temporary file and an atomic replace, so an interrupted run can never leave
half a metadata file behind.
"""
import errno
import hashlib
import json
import os
import re
import shutil
import unicodedata
from datetime import datetime

from .paths import library_dir

SCHEMA_VERSION = 1

METADATA_FILENAME = "metadata.json"
TRANSCRIPT_FILENAME = "transcript.txt"
SEGMENTS_FILENAME = "transcript.json"
NOTES_FILENAME = "notes.md"
SUBTITLE_FILENAMES = {"srt": "subtitles.srt", "vtt": "subtitles.vtt"}
SOURCE_STEM = "source"

#: Notes are a page of thoughts about a meeting, not a document store: the
#: interfaces refuse to save more than this in one ``notes.md``.
MAX_NOTES = 100_000

ID_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{4}(_[a-z0-9-]+)?$")

# How the original recording is kept: copied into the entry (self-contained),
# moved into it (self-contained, no duplication), or left where it is.
STORE_COPY = "copy"
STORE_MOVE = "move"
STORE_REFERENCE = "reference"
STORE_MODES = (STORE_COPY, STORE_MOVE, STORE_REFERENCE)


class LibraryError(Exception):
    """Any problem reading or writing the library."""


def slugify(text, max_length=40):
    """ASCII, lowercase, hyphen-separated: safe on every filesystem."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:max_length].strip("-")


def make_entry_id(title=None, when=None):
    """Sortable, human-readable entry id: ``YYYY-MM-DD_HHMM_slug``."""
    when = when or datetime.now()
    stamp = when.strftime("%Y-%m-%d_%H%M")
    slug = slugify(title)
    return f"{stamp}_{slug}" if slug else stamp


def file_digest(path, chunk_size=1024 * 1024):
    """SHA-256 of a file, read in chunks so a 2 GB video does not land in RAM."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_atomic(path, text):
    """Write text so that the destination is either the old file or the new one."""
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


class Entry:
    """One recording: a folder plus the metadata that describes it."""

    def __init__(self, path):
        self.path = os.path.abspath(path)

    # --- identity ---------------------------------------------------------
    @property
    def id(self):
        return os.path.basename(self.path)

    @property
    def metadata_path(self):
        return os.path.join(self.path, METADATA_FILENAME)

    @property
    def transcript_path(self):
        return os.path.join(self.path, TRANSCRIPT_FILENAME)

    @property
    def segments_path(self):
        return os.path.join(self.path, SEGMENTS_FILENAME)

    @property
    def notes_path(self):
        return os.path.join(self.path, NOTES_FILENAME)

    def source_path(self):
        """Absolute path of the recording, wherever it actually lives."""
        source = self.metadata.get("source") or {}
        stored = source.get("stored")
        if stored:
            return os.path.join(self.path, stored)
        return source.get("path")

    # --- metadata ---------------------------------------------------------
    @property
    def metadata(self):
        if getattr(self, "_metadata", None) is None:
            self._metadata = self.read_metadata()
        return self._metadata

    def read_metadata(self):
        try:
            with open(self.metadata_path, encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError as exc:
            raise LibraryError(f"missing {METADATA_FILENAME} in {self.path}") from exc
        except (OSError, ValueError) as exc:
            raise LibraryError(
                f"unreadable {METADATA_FILENAME} in {self.path}: {exc}") from exc
        if not isinstance(data, dict):
            raise LibraryError(f"malformed {METADATA_FILENAME} in {self.path}")
        return data

    def save_metadata(self, metadata=None):
        if metadata is not None:
            self._metadata = metadata
        write_atomic(self.metadata_path,
                     json.dumps(self.metadata, ensure_ascii=False, indent=2,
                                sort_keys=False) + "\n")

    def update(self, **fields):
        """Shallow-merge fields into the metadata and persist them."""
        data = dict(self.metadata)
        for key, value in fields.items():
            if isinstance(value, dict) and isinstance(data.get(key), dict):
                merged = dict(data[key])
                merged.update(value)
                data[key] = merged
            else:
                data[key] = value
        self.save_metadata(data)
        return self

    # --- content ----------------------------------------------------------
    def write_transcript(self, text, segments=None):
        """Store the readable transcript and, when available, the segments."""
        write_atomic(self.transcript_path, text)
        if segments is not None:
            payload = {"schema": SCHEMA_VERSION, "segments": segments}
            write_atomic(self.segments_path,
                         json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return self

    def read_transcript(self):
        try:
            with open(self.transcript_path, encoding="utf-8") as handle:
                return handle.read()
        except OSError:
            return ""

    def write_notes(self, text):
        """Replace ``notes.md``. Yours to write, from an editor or the page."""
        write_atomic(self.notes_path, text if text.endswith("\n") else text + "\n")
        return self

    def read_notes(self):
        try:
            with open(self.notes_path, encoding="utf-8") as handle:
                return handle.read()
        except OSError:
            return ""

    def subtitle_path(self, kind="srt"):
        """Where the subtitles of this entry live, whether or not they exist."""
        name = SUBTITLE_FILENAMES.get(kind)
        if name is None:
            raise LibraryError(f"unknown subtitle format: {kind}")
        return os.path.join(self.path, name)

    def write_subtitles(self, text, kind="srt"):
        """Store a subtitle file beside the transcript.

        Kept as a file rather than as data in ``metadata.json`` for the same
        reason the transcript is: an .srt is what a player, an editor and a
        person all already know how to read."""
        write_atomic(self.subtitle_path(kind), text)
        return self

    def subtitles(self):
        """Which subtitle formats this entry actually holds."""
        return [kind for kind, name in SUBTITLE_FILENAMES.items()
                if os.path.exists(os.path.join(self.path, name))]

    def read_segments(self):
        """The timestamped segments, or an empty list: they are optional."""
        try:
            with open(self.segments_path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            return []
        segments = payload.get("segments") if isinstance(payload, dict) else payload
        return segments if isinstance(segments, list) else []

    def has_written_notes(self):
        """True when someone actually wrote something.

        A new entry starts with ``notes.md`` holding only its title as a
        heading, so "not empty" would mark every entry as annotated."""
        return any(line.strip() and not line.lstrip().startswith("#")
                   for line in self.read_notes().splitlines())

    def stored_audio(self):
        """Path of the recording, but only when the entry really holds it.

        An entry created with ``--library-store reference`` points at a file
        somewhere else on disk, which may have moved or been deleted; and an
        interface should not become a way to read arbitrary files, so only what
        lives inside the entry counts as playable."""
        try:
            source = self.source_path()
        except LibraryError:
            return None
        if not source:
            return None
        source = os.path.abspath(source)
        inside = source.startswith(os.path.abspath(self.path) + os.sep)
        return source if inside and os.path.isfile(source) else None

    def __repr__(self):
        return f"<Entry {self.id}>"


class Library:
    """A directory of :class:`Entry` folders."""

    def __init__(self, root=None):
        self.root = os.path.abspath(os.path.expanduser(root or library_dir()))

    # --- creation ---------------------------------------------------------
    def create(self, source=None, title=None, when=None, store=STORE_COPY,
               metadata=None):
        """Create a new entry, optionally taking the source file with it."""
        if store not in STORE_MODES:
            raise LibraryError(f"unknown store mode: {store}")
        when = when or datetime.now()
        if title is None and source:
            title = os.path.splitext(os.path.basename(source))[0]

        os.makedirs(self.root, exist_ok=True)
        entry = Entry(os.path.join(self.root, self._unique_id(title, when)))
        os.makedirs(entry.path)

        data = {
            "schema": SCHEMA_VERSION,
            "id": entry.id,
            "title": title or entry.id,
            "created_at": when.astimezone().isoformat(timespec="seconds"),
            "source": self._store_source(entry, source, store) if source else None,
            "audio": {},
            "transcription": {},
            "stats": {},
            "tags": [],
        }
        if metadata:
            data.update(metadata)
        entry.save_metadata(data)

        if not os.path.exists(entry.notes_path):
            write_atomic(entry.notes_path, f"# {data['title']}\n\n")
        return entry

    def _unique_id(self, title, when):
        """Entry id, suffixed if a recording with the same name and minute exists."""
        base = make_entry_id(title, when)
        candidate, counter = base, 2
        while os.path.exists(os.path.join(self.root, candidate)):
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

    def _store_source(self, entry, source, store):
        """Copy, move or reference the original recording; record what we did."""
        source = os.path.abspath(os.path.expanduser(source))
        if not os.path.exists(source):
            raise LibraryError(f"source file not found: {source}")
        info = {
            "filename": os.path.basename(source),
            "bytes": os.path.getsize(source),
            "sha256": file_digest(source),
            "mode": store,
        }
        if store == STORE_REFERENCE:
            info["path"] = source
            return info
        target_name = SOURCE_STEM + os.path.splitext(source)[1].lower()
        target = os.path.join(entry.path, target_name)
        try:
            if store == STORE_MOVE:
                shutil.move(source, target)
            else:
                shutil.copy2(source, target)
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                raise LibraryError(
                    f"not enough space to store {info['filename']} "
                    f"in the library") from exc
            raise LibraryError(f"cannot store {info['filename']}: {exc}") from exc
        info["stored"] = target_name
        return info

    # --- lookup -----------------------------------------------------------
    def entries(self):
        """Every readable entry, newest first. Unreadable folders are skipped."""
        try:
            names = os.listdir(self.root)
        except OSError:
            return []
        found = []
        for name in sorted(names, reverse=True):
            path = os.path.join(self.root, name)
            if not os.path.isdir(path):
                continue
            if not os.path.exists(os.path.join(path, METADATA_FILENAME)):
                continue
            found.append(Entry(path))
        return found

    def find(self, query):
        """Entries whose id starts with, or whose title contains, ``query``."""
        needle = (query or "").strip().lower()
        if not needle:
            return []
        by_id = [e for e in self.entries() if e.id.lower().startswith(needle)]
        if by_id:
            return by_id
        matches = []
        for entry in self.entries():
            try:
                title = str(entry.metadata.get("title", ""))
            except LibraryError:
                continue
            if needle in title.lower():
                matches.append(entry)
        return matches

    def get(self, query):
        """Exactly one entry, or a :class:`LibraryError` explaining why not."""
        matches = self.find(query)
        if not matches:
            raise LibraryError(f"no entry matches '{query}'")
        if len(matches) > 1:
            names = ", ".join(e.id for e in matches[:5])
            raise LibraryError(f"'{query}' matches several entries: {names}")
        return matches[0]

    def search(self, text):
        """Entries whose transcript or notes contain ``text`` (case-insensitive)."""
        needle = (text or "").strip().lower()
        if not needle:
            return []
        return [e for e in self.entries()
                if needle in e.read_transcript().lower()
                or needle in e.read_notes().lower()]

    def remove(self, entry):
        """Delete an entry, refusing anything that is not inside this library."""
        path = os.path.abspath(entry.path if isinstance(entry, Entry) else entry)
        root = os.path.abspath(self.root)
        if os.path.commonpath([root, path]) != root or path == root:
            raise LibraryError(f"refusing to remove a path outside the library: {path}")
        shutil.rmtree(path)
        return path
