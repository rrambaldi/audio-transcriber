"""The recordings library: entry creation, lookup, and the safety rules."""
import json
import os
from datetime import datetime

import pytest

from audio_transcriber.library import (
    STORE_COPY,
    STORE_MOVE,
    STORE_REFERENCE,
    Library,
    LibraryError,
    make_entry_id,
    slugify,
    write_atomic,
)


@pytest.fixture
def library(tmp_path):
    return Library(str(tmp_path / "library"))


@pytest.fixture
def recording(tmp_path):
    path = tmp_path / "Team Sync.wav"
    path.write_bytes(b"not really audio, but a real file")
    return str(path)


# --- naming ---------------------------------------------------------------

def test_slugify_is_ascii_lowercase_and_hyphenated():
    assert slugify("Riunione Progetto ACM — 3° incontro") == "riunione-progetto-acm-3-incontro"


def test_slugify_handles_input_with_nothing_usable():
    assert slugify("///") == ""
    assert slugify(None) == ""


def test_entry_ids_sort_chronologically():
    early = make_entry_id("a", datetime(2026, 1, 2, 9, 5))
    late = make_entry_id("a", datetime(2026, 1, 2, 14, 30))
    assert early < late
    assert early == "2026-01-02_0905_a"


# --- creation -------------------------------------------------------------

def test_create_lays_out_the_entry(library, recording):
    entry = library.create(source=recording, title="Team Sync")
    assert os.path.isdir(entry.path)
    assert os.path.exists(entry.metadata_path)
    assert os.path.exists(entry.notes_path)
    assert entry.metadata["title"] == "Team Sync"
    assert entry.metadata["schema"] == 1


def test_the_title_defaults_to_the_file_name(library, recording):
    assert library.create(source=recording).metadata["title"] == "Team Sync"


def test_copy_keeps_the_original_where_it_was(library, recording):
    entry = library.create(source=recording, store=STORE_COPY)
    assert os.path.exists(recording)
    assert os.path.exists(entry.source_path())
    assert entry.metadata["source"]["stored"] == "source.wav"


def test_move_takes_the_original_with_it(library, recording):
    entry = library.create(source=recording, store=STORE_MOVE)
    assert not os.path.exists(recording)
    assert os.path.exists(entry.source_path())


def test_reference_leaves_the_original_in_place(library, recording):
    entry = library.create(source=recording, store=STORE_REFERENCE)
    assert os.path.exists(recording)
    assert entry.source_path() == recording
    assert "stored" not in entry.metadata["source"]


def test_the_source_digest_is_recorded(library, recording):
    source = library.create(source=recording).metadata["source"]
    assert len(source["sha256"]) == 64
    assert source["bytes"] == os.path.getsize(recording)


def test_a_missing_source_is_reported(library):
    with pytest.raises(LibraryError):
        library.create(source="/nonexistent/recording.wav")


def test_an_unknown_store_mode_is_rejected(library, recording):
    with pytest.raises(LibraryError):
        library.create(source=recording, store="teleport")


def test_two_recordings_in_the_same_minute_get_distinct_folders(library, recording):
    when = datetime(2026, 3, 1, 10, 0)
    first = library.create(source=recording, title="Sync", when=when)
    second = library.create(source=recording, title="Sync", when=when)
    assert first.id != second.id
    assert second.id.startswith(first.id)


# --- content --------------------------------------------------------------

def test_transcript_and_segments_round_trip(library, recording):
    entry = library.create(source=recording)
    segments = [{"text": "hello", "start": 0.0, "end": 1.0}]
    entry.write_transcript("hello\n", segments)
    assert entry.read_transcript() == "hello\n"
    with open(entry.segments_path, encoding="utf-8") as handle:
        assert json.load(handle)["segments"] == segments


def test_update_merges_nested_metadata(library, recording):
    entry = library.create(source=recording)
    entry.update(transcription={"model": "small"})
    entry.update(transcription={"backend": "faster-whisper"})
    saved = entry.read_metadata()["transcription"]
    assert saved == {"model": "small", "backend": "faster-whisper"}


def test_metadata_is_written_atomically(tmp_path):
    target = tmp_path / "metadata.json"
    write_atomic(str(target), '{"a": 1}')
    assert target.read_text() == '{"a": 1}'
    assert list(tmp_path.glob("*.tmp")) == []


# --- lookup ---------------------------------------------------------------

def test_entries_come_back_newest_first(library, recording):
    library.create(source=recording, title="First", when=datetime(2026, 1, 1, 9, 0))
    library.create(source=recording, title="Second", when=datetime(2026, 6, 1, 9, 0))
    assert [e.metadata["title"] for e in library.entries()] == ["Second", "First"]


def test_an_empty_library_lists_nothing(library):
    assert library.entries() == []


def test_folders_without_metadata_are_ignored(library, recording):
    library.create(source=recording, title="Real")
    os.makedirs(os.path.join(library.root, "not-an-entry"))
    assert len(library.entries()) == 1


def test_lookup_by_id_prefix(library, recording):
    entry = library.create(source=recording, title="Weekly",
                           when=datetime(2026, 4, 5, 11, 30))
    assert library.get("2026-04-05").id == entry.id


def test_lookup_by_part_of_the_title(library, recording):
    entry = library.create(source=recording, title="Quarterly review")
    assert library.get("quarterly").id == entry.id


def test_an_ambiguous_query_is_refused(library, recording):
    library.create(source=recording, title="Review one", when=datetime(2026, 1, 1, 9, 0))
    library.create(source=recording, title="Review two", when=datetime(2026, 2, 1, 9, 0))
    with pytest.raises(LibraryError) as error:
        library.get("review")
    assert "several" in str(error.value)


def test_a_query_matching_nothing_is_refused(library):
    with pytest.raises(LibraryError):
        library.get("nothing at all")


def test_search_looks_inside_transcripts_and_notes(library, recording):
    first = library.create(source=recording, title="One",
                           when=datetime(2026, 1, 1, 9, 0))
    first.write_transcript("we discussed the risk assessment\n")
    second = library.create(source=recording, title="Two",
                            when=datetime(2026, 2, 1, 9, 0))
    second.write_transcript("nothing relevant here\n")
    write_atomic(second.notes_path, "follow up on the risk assessment\n")

    assert {e.id for e in library.search("RISK assessment")} == {first.id, second.id}
    assert [e.id for e in library.search("discussed")] == [first.id]
    assert library.search("") == []


# --- removal --------------------------------------------------------------

def test_remove_deletes_the_entry(library, recording):
    entry = library.create(source=recording)
    library.remove(entry)
    assert not os.path.exists(entry.path)


def test_remove_refuses_a_path_outside_the_library(library, tmp_path):
    outside = tmp_path / "precious"
    outside.mkdir()
    with pytest.raises(LibraryError):
        library.remove(str(outside))
    assert outside.exists()


def test_remove_refuses_the_library_root_itself(library, recording):
    library.create(source=recording)
    with pytest.raises(LibraryError):
        library.remove(library.root)
    assert os.path.exists(library.root)


def test_unreadable_metadata_is_reported_clearly(library, recording):
    entry = library.create(source=recording)
    with open(entry.metadata_path, "w", encoding="utf-8") as handle:
        handle.write("{ not json")
    with pytest.raises(LibraryError):
        entry.read_metadata()
