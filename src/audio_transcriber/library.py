"""The recordings library: one self-contained folder per recording.

Layout of an entry::

    <library>/2026-09-04_1530_team-meeting/
        metadata.json     what it is, how it was transcribed, how long it took
        source.mp4        the original file (copied, moved, or only referenced)
        transcript.txt    the readable text, exactly what the CLI writes
        transcript.json   segments with timestamps and speakers, for tooling
        summary.md        the short version, when one was asked for
        waveform.json     how loud it was, moment by moment, for the row
        notes.md          yours to write

Entries can be kept in folders, as deep as anybody likes: a directory with a
``metadata.json`` in it is an entry, any other directory is a folder, and an
entry's id is its path from the top of the library - ``Clienti/ACME/
2026-09-04_1530_team-meeting``. One at the top keeps the id it always had.

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
SUMMARY_FILENAME = "summary.md"
WAVEFORM_FILENAME = "waveform.json"
SUBTITLE_FILENAMES = {"srt": "subtitles.srt", "vtt": "subtitles.vtt"}
SOURCE_STEM = "source"

#: Where the summaries a newer one replaced are kept, inside the entry.
SUMMARIES_DIRNAME = "summaries"

#: What a folder of the library may not be called. The characters Windows
#: refuses, since a library is as likely to be on a laptop as on a server.
FOLDER_FORBIDDEN = frozenset('<>:"|?*/\\')
MAX_FOLDER_NAME = 100

#: A Windows junction is how a folder of the library can live on another
#: disk; ``os.path`` only learnt to recognise one in Python 3.12.
_isjunction = getattr(os.path, "isjunction", lambda path: False)

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


def valid_folder_name(name):
    """True if ``name`` can be one folder of the library, on every platform.

    Anything a person would type - spaces, accents - as long as it is one
    name: no separators, nothing hidden, nothing Windows would refuse."""
    name = str(name or "")
    return (bool(name) and len(name) <= MAX_FOLDER_NAME
            and name not in (".", "..") and not name.startswith(".")
            and not name.endswith((".", " "))
            and not any(char in FOLDER_FORBIDDEN or ord(char) < 32
                        for char in name))


def normalise_folder(folder):
    """``"A/B"`` out of whatever a caller sent, or a :class:`LibraryError`.

    Either slash separates, empty steps are dropped, and ``""`` - or
    ``None`` - is the top of the library. Every step is checked, so what
    comes back can be joined onto the root without walking out of it."""
    parts = [part.strip() for part in re.split(r"[\\/]", str(folder or ""))]
    parts = [part for part in parts if part]
    for part in parts:
        if not valid_folder_name(part):
            raise LibraryError(f"not a usable folder name: {part!r}")
    return "/".join(parts)


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

    def __init__(self, path, root=None):
        self.path = os.path.abspath(path)
        self.root = os.path.abspath(root) if root else None

    # --- identity ---------------------------------------------------------
    @property
    def id(self):
        """Where it is in the library: ``Clienti/ACME/2026-09-04_1530_sync``.

        Only the folder's own name for an entry at the top, which is what
        every id was before there were folders - so none of those changed."""
        if not self.root:
            return self.name
        return os.path.relpath(self.path, self.root).replace(os.sep, "/")

    @property
    def name(self):
        """The entry's own folder name, wherever it has been put."""
        return os.path.basename(self.path)

    @property
    def folder(self):
        """The library folder it is in, ``""`` at the top."""
        return self.id.rpartition("/")[0]

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
    def waveform_path(self):
        return os.path.join(self.path, WAVEFORM_FILENAME)

    @property
    def notes_path(self):
        return os.path.join(self.path, NOTES_FILENAME)

    @property
    def summary_path(self):
        return os.path.join(self.path, SUMMARY_FILENAME)

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

    def write_summary(self, text):
        """Replace ``summary.md``.

        A file rather than a field in the metadata, like the transcript and
        the subtitles: it is a page someone reads, and often the only part of
        an hour-long recording anybody reads twice."""
        write_atomic(self.summary_path, text if text.endswith("\n") else text + "\n")
        return self

    def read_summary(self):
        try:
            with open(self.summary_path, encoding="utf-8") as handle:
                return handle.read()
        except OSError:
            return ""

    def has_summary(self):
        return os.path.exists(self.summary_path)

    @property
    def summaries_path(self):
        return os.path.join(self.path, SUMMARIES_DIRNAME)

    def archive_summary(self):
        """Put the current summary aside, before a new one takes its place.

        Asked for by whoever is about to write that new one, and only then:
        the file goes to ``summaries/<when>.md`` and what the metadata said
        about it goes with it, so the old page can still be read and still
        says which model wrote it. Returns the file it went to, relative to
        the entry, or ``None`` when there was nothing to put aside."""
        if not self.has_summary():
            return None
        data = dict(self.metadata)
        os.makedirs(self.summaries_path, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        name, counter = f"{stamp}.md", 2
        while os.path.exists(os.path.join(self.summaries_path, name)):
            name = f"{stamp}-{counter}.md"
            counter += 1
        os.replace(self.summary_path, os.path.join(self.summaries_path, name))
        relative = f"{SUMMARIES_DIRNAME}/{name}"
        block = dict(data.pop("summary", None) or {})
        block["file"] = relative
        data["summary_versions"] = list(data.get("summary_versions") or []) + [block]
        self.save_metadata(data)
        return relative

    def summary_versions(self):
        """The summaries put aside, newest first, as the metadata describes
        them. One whose file has gone is left out rather than offered."""
        try:
            versions = self.metadata.get("summary_versions") or []
        except LibraryError:
            return []
        return [dict(version) for version in reversed(versions)
                if isinstance(version, dict)
                and self._summary_version_path(version.get("file"))]

    def read_summary_version(self, file):
        """The text of a summary put aside, by the file the metadata names.

        The name arrives from an interface, so it is only ever looked for
        directly inside ``summaries/``: nothing else in the entry, and
        nothing outside it, can be read this way."""
        path = self._summary_version_path(file)
        if path is None:
            raise LibraryError(f"no earlier summary {file!r} in {self.id}")
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def _summary_version_path(self, file):
        if not isinstance(file, str) or not file:
            return None
        path = os.path.realpath(os.path.join(self.path, file))
        inside = os.path.dirname(path) == os.path.realpath(self.summaries_path)
        return path if inside and os.path.isfile(path) else None

    def write_waveform(self, loudness):
        """Store how loud the recording was, slice by slice.

        Derived, like the subtitles: it is measured from the recording and can
        be measured again, so deleting it loses nothing but the second or two
        it takes to read the file back."""
        from . import waveform

        write_atomic(self.waveform_path, waveform.as_document(loudness) + "\n")
        return self

    def read_waveform(self):
        """The stored loudness, or ``None`` when nobody has measured this yet.

        ``None`` rather than an empty list, because the two are different
        answers: nothing measured, against measured and silent throughout."""
        from . import waveform

        return waveform.read_file(self.waveform_path)

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

    # --- who is speaking --------------------------------------------------
    def speakers(self):
        """Who this transcript says is talking, in the order they first do.

        Empty for a run that was not diarized, which is what the interfaces
        use to decide whether there is anything to name."""
        from .diarization import speakers_in
        return speakers_in(self.read_segments())

    def name_speakers(self, names):
        """Call the speakers what ``names`` calls them, and rewrite the files.

        A diarized transcript comes out of the machine addressed to
        ``SPEAKER_00`` and ``SPEAKER_01``, which is the best anything can do
        from the audio alone: who those are is in the room, not in the sound.
        So it is a thing done afterwards, by somebody who has read a line of
        it and recognised a voice.

        Both files are rewritten rather than annotated, because of the rule
        at the top of this module: the folder has to stay as readable without
        this program as with it, and a transcript that says ``SPEAKER_01``
        beside a metadata file that says it means Anna is a puzzle, not a
        document. What the metadata keeps is the mapping from the labels the
        machine gave out to the names they were given - provenance, for
        somebody who opens the folder in a year and wonders where the names
        came from.

        Returns the names now in use. Raises :class:`LibraryError` when there
        are no segments to rewrite: without them the transcript is prose,
        and a search and replace on prose is somebody else's tool.
        """
        from .diarization import format_dialogue
        from .diarization import rename_speakers as apply_names

        segments = self.read_segments()
        if not any(segment.get("speaker") for segment in segments):
            raise LibraryError(f"no speakers recorded in {self.id}")
        renamed = apply_names(segments, names)
        text = format_dialogue(renamed) + "\n"
        self.write_transcript(text, renamed)

        # Composed onto what is already there, so that renaming Anna to Anna
        # Bianchi still records which label she started as rather than
        # inventing a speaker called Anna.
        record = dict(self.metadata.get("speaker_names") or {})
        first_called = {given: label for label, given in record.items()}
        for label, name in (names or {}).items():
            name = str(name).strip()
            if name:
                record[first_called.get(label, label)] = name
        self.update(speaker_names=record,
                    stats={"words": len(text.split())})
        return self.speakers()

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
               metadata=None, folder=""):
        """Create a new entry, optionally taking the source file with it.

        ``folder`` is where in the library it goes, made if it is not there
        yet; the top, by default."""
        if store not in STORE_MODES:
            raise LibraryError(f"unknown store mode: {store}")
        when = when or datetime.now()
        if title is None and source:
            title = os.path.splitext(os.path.basename(source))[0]

        folder, parent = self._folder_path(folder)
        self._refuse_inside_entry(folder)
        os.makedirs(parent, exist_ok=True)
        entry = Entry(os.path.join(parent, self._unique_id(title, when, parent)),
                      self.root)
        os.makedirs(entry.path)

        data = {
            "schema": SCHEMA_VERSION,
            # The folder's own name: the id also says where the entry is, and
            # that changes whenever it is moved.
            "id": entry.name,
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

    def _unique_id(self, title, when, parent=None):
        """Entry id, suffixed if a recording with the same name and minute exists."""
        return _free_name(make_entry_id(title, when), parent or self.root)

    # --- folders ----------------------------------------------------------
    def _folder_path(self, folder):
        """``(normalised folder, absolute path)``, or a LibraryError."""
        folder = normalise_folder(folder)
        path = os.path.join(self.root, *folder.split("/")) if folder else self.root
        return folder, path

    def _refuse_inside_entry(self, folder):
        """A recording's folder holds its files, never other recordings."""
        path = self.root
        for part in folder.split("/") if folder else []:
            path = os.path.join(path, part)
            if os.path.isfile(os.path.join(path, METADATA_FILENAME)):
                raise LibraryError(f"{os.path.relpath(path, self.root)} is an "
                                   "entry, not a folder")

    def _existing_folder(self, folder):
        """The absolute path of a folder that is there, or a LibraryError."""
        folder, path = self._folder_path(folder)
        self._refuse_inside_entry(folder)
        if not os.path.isdir(path):
            raise LibraryError(f"no folder '{folder}' in the library")
        return folder, path

    def folders(self):
        """Every folder of the library, at any depth, parents before children."""
        return sorted((relative for relative, is_entry in self._walk()
                       if not is_entry),
                      key=lambda relative: [part.lower()
                                            for part in relative.split("/")])

    def create_folder(self, path):
        """Make a folder, and its parents if they are missing; return its path."""
        folder, target = self._folder_path(path)
        if not folder:
            raise LibraryError("a folder needs a name")
        self._refuse_inside_entry(folder)
        if os.path.lexists(target):
            raise LibraryError(f"'{folder}' already exists")
        os.makedirs(target)
        return folder

    def link_folder(self, path, target):
        """Make a folder of the library that is a folder elsewhere on the disk.

        A symlink, or on Windows a junction, which needs no administrator the
        way a symlink does. What is filed in it lands in ``target``; removing
        it removes the link and never what it points at. ``target`` has to be
        an existing folder that neither holds the library nor sits inside it.
        Returns the new folder's path."""
        folder, link = self._folder_path(path)
        if not folder:
            raise LibraryError("a folder needs a name")
        self._refuse_inside_entry(folder)
        if os.path.lexists(link):
            raise LibraryError(f"'{folder}' already exists")
        target = os.path.abspath(os.path.expanduser(str(target or "")))
        if not os.path.isdir(target):
            raise LibraryError(f"no folder at {target}")
        if _nested(os.path.realpath(self.root), os.path.realpath(target)):
            raise LibraryError(f"{target} holds the library or is inside it")
        os.makedirs(os.path.dirname(link), exist_ok=True)
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(target, link)
        else:
            os.symlink(target, link, target_is_directory=True)
        return folder

    def folder_target(self, path):
        """Where a folder of the library really is, when that is somewhere
        else - it is a link - or ``None`` for a folder of the library's own.

        By comparing where it resolves with where it sits, not by asking
        whether it is a link: ``os.path`` only knows a junction from 3.12."""
        try:
            folder, target = self._folder_path(path)
        except LibraryError:
            return None
        if not folder or not os.path.isdir(target):
            return None
        real = os.path.realpath(target)
        sits = os.path.join(os.path.realpath(os.path.dirname(target)),
                            os.path.basename(target))
        return real if os.path.normcase(real) != os.path.normcase(sits) else None

    def rename_folder(self, path, new_name):
        """Call a folder something else, where it is; return its new path."""
        folder, source = self._existing_folder(path)
        new_name = str(new_name or "").strip()
        if not folder:
            raise LibraryError("the top of the library cannot be renamed")
        if not valid_folder_name(new_name):
            raise LibraryError(f"not a usable folder name: {new_name!r}")
        target = os.path.join(os.path.dirname(source), new_name)
        # Changing only the case of a name finds "itself" on Windows.
        if os.path.lexists(target) and not _same_file(source, target):
            raise LibraryError(f"'{new_name}' already exists there")
        os.rename(source, target)
        parent = folder.rpartition("/")[0]
        return f"{parent}/{new_name}" if parent else new_name

    def remove_folder(self, path):
        """Delete a folder, but only an empty one; return its path.

        A folder that is a link to somewhere else - a symlink, a Windows
        junction - loses the link and nothing else, full or not: what it
        pointed at is somebody's folder, not this library's to delete. One
        whose target has gone, a disk that is not plugged in, can always be
        let go of."""
        folder, target = self._folder_path(path)
        if not folder:
            raise LibraryError("the top of the library cannot be removed")
        self._refuse_inside_entry(folder)
        linked = os.path.islink(target) or _isjunction(target)
        if not linked and not os.path.isdir(target):
            raise LibraryError(f"no folder '{folder}' in the library")
        if not linked and os.path.isdir(target) and os.listdir(target):
            raise LibraryError(f"'{folder}' is not empty")
        if linked:
            try:
                os.unlink(target)
            except OSError:
                os.rmdir(target)        # a directory link on Windows
        else:
            os.rmdir(target)
        return folder

    def move(self, entry, folder):
        """Put an entry in another folder and return it, as it is there now.

        The folder has to exist already: moving is filing something somewhere,
        not inventing a place for it. Its own name clashing with one already
        there gets the same "-2" a recording filed twice in a minute gets."""
        entry = entry if isinstance(entry, Entry) else self.get(entry)
        self._refuse_outside(entry.path)
        folder, parent = self._existing_folder(folder)
        if os.path.normcase(os.path.dirname(entry.path)) == os.path.normcase(parent):
            return Entry(entry.path, self.root)
        name = _free_name(entry.name, parent)
        target = os.path.join(parent, name)
        shutil.move(entry.path, target)
        moved = Entry(target, self.root)
        if name != entry.name:
            try:
                moved.update(id=name)
            except LibraryError:
                pass        # moved all the same; its metadata was never readable
        return moved

    def _refuse_outside(self, path):
        path = os.path.abspath(path)
        root = os.path.abspath(self.root)
        if os.path.commonpath([root, path]) != root or path == root:
            raise LibraryError(f"refusing a path outside the library: {path}")

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
    def _walk(self):
        """Every directory below the root, as ``(relative path, is an entry)``.

        Depth first, in name order. An entry is a leaf - a recording's folder
        holds its files, never another recording - and hidden directories are
        skipped. Links are followed, which is what lets a folder of the
        library live on another disk; a directory already reached another way
        is not walked twice, or a link back up the tree would be walked for
        ever."""
        seen = {os.path.realpath(self.root)}

        def visit(path, relative):
            try:
                names = sorted(os.listdir(path))
            except OSError:
                return
            for name in names:
                child = os.path.join(path, name)
                if name.startswith(".") or not os.path.isdir(child):
                    continue
                real = os.path.realpath(child)
                if real in seen:
                    continue
                seen.add(real)
                inner = f"{relative}/{name}" if relative else name
                if os.path.exists(os.path.join(child, METADATA_FILENAME)):
                    yield inner, True
                else:
                    yield inner, False
                    yield from visit(child, inner)

        yield from visit(self.root, "")

    def entries(self, folder=None):
        """Entries, newest first; unreadable ones are left to the caller.

        ``folder`` narrows it: ``None`` is the whole library at any depth,
        ``""`` only the top of it, ``"A/B"`` what sits directly in that
        folder."""
        if folder is not None:
            folder = normalise_folder(folder)
        found = [Entry(os.path.join(self.root, *relative.split("/")), self.root)
                 for relative, is_entry in self._walk()
                 if is_entry and (folder is None
                                  or relative.rpartition("/")[0] == folder)]
        # By the folder's own name, which starts with the date it was filed.
        found.sort(key=lambda entry: entry.name, reverse=True)
        return found

    def copies(self):
        """The recordings filed more than once, by entry id.

        Transcribing one file twice to compare two models files it twice, and
        the two rows look alike. Each id of such a recording maps to all of its
        entries, newest first; a recording filed once is not in here at all.
        The digest is the one :meth:`create` records, so a renamed file is
        still the same recording and two files with one name are not."""
        groups = {}
        for entry in self.entries():
            try:
                digest = (entry.metadata.get("source") or {}).get("sha256")
            except LibraryError:
                continue
            if digest:
                groups.setdefault(digest, []).append(entry)
        return {entry.id: group for group in groups.values() if len(group) > 1
                for entry in group}

    def find(self, query):
        """Entries whose id starts with, or whose title contains, ``query``.

        An id that is exactly one entry's is that entry, even when another
        starts the same way. Ids are only ever matched against the ones the
        library lists, never joined onto a path: a query is text from a
        command line or a URL."""
        needle = (query or "").strip().replace("\\", "/")
        if not needle:
            return []
        entries = self.entries()
        exact = [e for e in entries if e.id == needle]
        if exact:
            return exact
        needle = needle.lower()
        by_id = [e for e in entries if e.id.lower().startswith(needle)
                 or e.name.lower().startswith(needle)]
        if by_id:
            return by_id
        matches = []
        for entry in entries:
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
        self._refuse_outside(path)
        shutil.rmtree(path)
        return path


def _nested(one, other):
    """Whether either folder is the other or holds it."""
    one, other = os.path.normcase(one), os.path.normcase(other)
    try:
        common = os.path.commonpath([one, other])
    except ValueError:      # two drives on Windows: neither holds the other
        return False
    return common in (one, other)


def _free_name(name, parent):
    """``name``, or ``name-2``, ``name-3``... whichever ``parent`` lacks."""
    candidate, counter = name, 2
    while os.path.lexists(os.path.join(parent, candidate)):
        candidate = f"{name}-{counter}"
        counter += 1
    return candidate


def _same_file(first, second):
    try:
        return os.path.samefile(first, second)
    except OSError:
        return False
