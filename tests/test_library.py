"""The recordings library: entry creation, lookup, and the safety rules."""
import json
import os
from datetime import datetime
from pathlib import Path

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


def test_a_recording_filed_twice_is_found_by_its_digest(library, recording, tmp_path):
    """Renamed, it is still the same recording; a different file of the same
    name is not, and a recording filed once is not a copy of anything."""
    first = library.create(source=recording, title="Sync")
    renamed = tmp_path / "copia.wav"
    renamed.write_bytes(Path(recording).read_bytes())
    second = library.create(source=str(renamed), title="Sync")
    other = tmp_path / "Team Sync.mp3"
    other.write_bytes(b"another meeting")
    alone = library.create(source=str(other), title="Sync")
    library.create(title="No source at all")

    copies = library.copies()
    assert set(copies) == {first.id, second.id}
    assert [entry.id for entry in copies[first.id]] == [second.id, first.id]
    assert alone.id not in copies


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


# --- subtitles ------------------------------------------------------------

def test_an_entry_can_hold_its_subtitles(tmp_path):
    """A file rather than data in metadata.json, for the reason the transcript
    is a file: an .srt is something a player, an editor and a person all
    already know how to read."""
    library = Library(str(tmp_path / "library"))
    entry = library.create(title="Comitato")
    assert entry.subtitles() == []
    entry.write_subtitles("1\n00:00:00,000 --> 00:00:02,000\nCiao\n", "srt")
    assert entry.subtitles() == ["srt"]
    assert entry.subtitle_path("srt").endswith("subtitles.srt")
    with open(entry.subtitle_path("srt"), encoding="utf-8") as handle:
        assert "-->" in handle.read()


def test_an_unknown_subtitle_format_is_refused(tmp_path):
    library = Library(str(tmp_path / "library"))
    entry = library.create(title="Comitato")
    with pytest.raises(LibraryError):
        entry.subtitle_path("ass")


# --- who is speaking ------------------------------------------------------

#: A two-voice transcript as the pipeline files one: segments carrying the
#: labels pyannote hands out, and a transcript.txt written from them.
DIALOGUE = [
    {"text": "Buongiorno a tutti.", "start": 0.0, "end": 2.0,
     "speaker": "SPEAKER_00"},
    {"text": "Cominciamo dal bilancio.", "start": 2.0, "end": 4.0,
     "speaker": "SPEAKER_00"},
    {"text": "Ho i numeri qui.", "start": 4.0, "end": 6.0,
     "speaker": "SPEAKER_01"},
]


@pytest.fixture
def diarized(library, recording):
    from audio_transcriber.diarization import format_dialogue

    entry = library.create(source=recording)
    entry.write_transcript(format_dialogue(DIALOGUE) + "\n", DIALOGUE)
    return entry


def test_the_speakers_are_the_ones_in_the_segments_in_the_order_heard(diarized):
    assert diarized.speakers() == ["SPEAKER_00", "SPEAKER_01"]


def test_a_transcript_with_no_speakers_has_none(library, recording):
    entry = library.create(source=recording)
    entry.write_transcript("Buongiorno a tutti.\n",
                           [{"text": "Buongiorno a tutti.", "start": 0.0,
                             "end": 2.0}])
    assert entry.speakers() == []


def test_naming_them_rewrites_the_transcript_and_the_segments(diarized):
    assert diarized.name_speakers({"SPEAKER_00": "Anna",
                                   "SPEAKER_01": "Bruno"}) == ["Anna", "Bruno"]
    text = diarized.read_transcript()
    assert "[Anna] Buongiorno a tutti. Cominciamo dal bilancio." in text
    assert "[Bruno] Ho i numeri qui." in text
    assert "SPEAKER_" not in text
    assert [segment["speaker"] for segment in diarized.read_segments()] == [
        "Anna", "Anna", "Bruno"]


def test_a_name_nobody_gave_leaves_that_speaker_alone(diarized):
    """Naming one person is not a decision about the others."""
    assert diarized.name_speakers({"SPEAKER_01": "Bruno"}) == ["SPEAKER_00",
                                                               "Bruno"]
    assert "[SPEAKER_00] Buongiorno" in diarized.read_transcript()


def test_an_empty_name_is_not_a_name(diarized):
    diarized.name_speakers({"SPEAKER_00": "   ", "SPEAKER_01": "Bruno"})
    assert diarized.speakers() == ["SPEAKER_00", "Bruno"]


def test_two_labels_with_one_name_become_one_person(diarized):
    """The machine heard two voices where there was one. Saying so should
    join their turns, not leave the same person answering themselves."""
    diarized.name_speakers({"SPEAKER_00": "Anna", "SPEAKER_01": "Anna"})
    assert diarized.speakers() == ["Anna"]
    assert diarized.read_transcript().strip() == (
        "[Anna] Buongiorno a tutti. Cominciamo dal bilancio. Ho i numeri qui.")


def test_the_metadata_remembers_which_label_a_name_started_as(diarized):
    """Provenance, for somebody who opens the folder in a year: the files
    themselves say Anna, and this is where it says Anna was SPEAKER_00."""
    diarized.name_speakers({"SPEAKER_00": "Anna"})
    assert diarized.read_metadata()["speaker_names"] == {"SPEAKER_00": "Anna"}

    diarized.name_speakers({"Anna": "Anna Bianchi"})
    assert diarized.read_metadata()["speaker_names"] == {
        "SPEAKER_00": "Anna Bianchi"}


def test_the_word_count_follows_the_rewrite(diarized):
    diarized.update(stats={"words": 999})
    diarized.name_speakers({"SPEAKER_00": "Anna", "SPEAKER_01": "Anna"})
    assert diarized.read_metadata()["stats"]["words"] == len(
        diarized.read_transcript().split())


def test_naming_speakers_in_a_transcript_that_has_none_is_refused(library,
                                                                  recording):
    """Without segments the transcript is prose, and a search and replace on
    prose is somebody else's tool."""
    entry = library.create(source=recording)
    entry.write_transcript("Buongiorno a tutti.\n", [])
    with pytest.raises(LibraryError):
        entry.name_speakers({"SPEAKER_00": "Anna"})


# --- what the recording looks like ----------------------------------------

def test_a_waveform_is_written_and_read_back(library, recording):
    """A file beside the transcript, like the subtitles: derived from the
    recording, and losing it costs only the second it takes to measure it
    again."""
    entry = library.create(source=recording)
    assert entry.read_waveform() is None            # nobody has measured it
    entry.write_waveform([0, 500, 1000])
    assert entry.read_waveform() == [0, 500, 1000]
    assert os.path.basename(entry.waveform_path) == "waveform.json"


def test_a_measured_silence_is_not_the_same_as_an_unmeasured_recording(
        library, recording):
    entry = library.create(source=recording)
    entry.write_waveform([0, 0, 0])
    assert entry.read_waveform() == [0, 0, 0]


def test_deleting_an_entry_takes_its_waveform_with_it(library, recording):
    entry = library.create(source=recording)
    entry.write_waveform([1, 2, 3])
    library.remove(entry)
    assert not os.path.exists(entry.waveform_path)


# --- folders --------------------------------------------------------------

def test_entries_can_live_in_folders_at_any_depth(library, recording):
    top = library.create(source=recording, title="Top", when=datetime(2026, 1, 1, 9, 0))
    deep = library.create(source=recording, title="Deep", folder="Clienti/ACME",
                          when=datetime(2026, 2, 1, 9, 0))
    os.makedirs(os.path.join(library.root, ".nascosta", "dentro"))
    os.makedirs(os.path.join(library.root, "Vuota"))

    assert (top.id, top.folder) == (top.name, "")
    assert (deep.id, deep.folder) == (f"Clienti/ACME/{deep.name}", "Clienti/ACME")
    assert [e.id for e in library.entries()] == [deep.id, top.id]
    assert [e.id for e in library.entries("")] == [top.id]
    assert [e.id for e in library.entries("Clienti/ACME")] == [deep.id]
    assert library.entries("Clienti") == []
    assert library.folders() == ["Clienti", "Clienti/ACME", "Vuota"]
    assert library.get(deep.id).id == deep.id
    assert library.get(deep.name).id == deep.id


def test_a_folder_can_be_a_link_elsewhere_and_a_loop_is_walked_once(library, recording,
                                                                    tmp_path):
    elsewhere = tmp_path / "other-disk" / "ACME"
    elsewhere.mkdir(parents=True)
    os.makedirs(library.root)
    try:
        os.symlink(elsewhere, os.path.join(library.root, "ACME"), target_is_directory=True)
        os.symlink(library.root, elsewhere / "loop", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this system will not make symlinks")
    entry = library.create(source=recording, title="Sync", folder="ACME")
    assert (elsewhere / entry.name / "metadata.json").is_file()
    assert [e.id for e in library.entries()] == [entry.id]
    assert library.folders() == ["ACME"]


def test_folders_are_made_renamed_and_removed_only_when_empty(library, recording):
    assert library.create_folder("Clienti/ACME") == "Clienti/ACME"
    with pytest.raises(LibraryError):
        library.create_folder("Clienti/ACME")
    for bad in ("..", ".nascosta", "a:b", "fine.", "Clienti/ACME/../x"):
        with pytest.raises(LibraryError):
            library.create_folder(bad)
    assert library.rename_folder("Clienti/ACME", "Acme Srl") == "Clienti/Acme Srl"
    entry = library.create(source=recording, folder="Clienti/Acme Srl")
    with pytest.raises(LibraryError):
        library.create_folder(f"{entry.id}/dentro")     # not inside a recording
    with pytest.raises(LibraryError, match="not empty"):
        library.remove_folder("Clienti")
    library.remove(entry)
    assert library.remove_folder("Clienti/Acme Srl") == "Clienti/Acme Srl"
    assert library.folders() == ["Clienti"]


def test_removing_a_linked_folder_removes_the_link_not_what_it_points_at(library, tmp_path):
    target = tmp_path / "elsewhere"
    target.mkdir()
    os.makedirs(library.root)
    link = os.path.join(library.root, "Esterna")
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this system will not make symlinks")
    library.remove_folder("Esterna")
    assert not os.path.lexists(link) and target.is_dir()


def test_an_entry_moves_between_folders_and_keeps_its_name_unless_taken(library,
                                                                        recording):
    when = datetime(2026, 3, 1, 10, 0)
    first = library.create(source=recording, title="Sync", when=when)
    library.create_folder("Archivio")
    moved = library.move(first, "Archivio")
    assert moved.id == f"Archivio/{first.name}" and not os.path.exists(first.path)

    second = library.move(library.create(source=recording, title="Sync", when=when),
                          "Archivio")
    assert second.name == first.name + "-2"
    assert second.metadata["id"] == second.name
    assert library.move(moved, "").id == first.name
    with pytest.raises(LibraryError):
        library.move(second, "Nessuna")


def test_an_exact_id_wins_over_another_that_starts_the_same(library, recording):
    when = datetime(2026, 3, 1, 10, 0)
    first = library.create(source=recording, title="Sync", when=when)
    library.create(source=recording, title="Sync", when=when)
    assert library.get(first.id).id == first.id


# --- summaries put aside --------------------------------------------------

def test_a_summary_put_aside_can_be_listed_and_read_back(library, recording):
    entry = library.create(source=recording)
    assert entry.archive_summary() is None
    entry.write_summary("prima versione")
    entry.update(summary={"engine": "llamacpp"})

    archived = entry.archive_summary()
    assert archived.startswith("summaries/") and not entry.has_summary()
    assert entry.summary_versions() == [{"engine": "llamacpp", "file": archived}]
    assert "summary" not in entry.metadata
    assert entry.read_summary_version(archived) == "prima versione\n"
    for sneaky in ("metadata.json", "../metadata.json", "summaries/../notes.md",
                   "/etc/passwd"):
        with pytest.raises(LibraryError):
            entry.read_summary_version(sneaky)
