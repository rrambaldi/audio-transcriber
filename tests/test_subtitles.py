"""Cutting a transcript into subtitles, against the numbers the trade uses.

Every rule here is checkable without a model, an engine or a video: given
segments with timings, either the cues respect the preset or they do not.
That is the whole reason this lives in a module of its own."""
import pytest

from audio_transcriber import subtitles


def segment(text, start, end, words=None):
    body = {"text": text, "start": start, "end": end}
    if words:
        body["words"] = words
    return body


def timed(text, start, per_word=0.4):
    """One segment whose words are timed evenly, as an engine would report."""
    pieces = text.split()
    words = [{"word": piece, "start": start + index * per_word,
              "end": start + (index + 1) * per_word}
             for index, piece in enumerate(pieces)]
    return segment(text, start, start + len(pieces) * per_word, words)


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch, tmp_path):
    from audio_transcriber import paths

    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "home"))


@pytest.fixture
def netflix():
    return subtitles.preset("netflix")


# --- the presets ----------------------------------------------------------

def test_the_bundled_presets_are_all_there():
    available = subtitles.presets()
    assert set(available) >= {"netflix", "bbc", "ebu_broadcast", "fcc_verbatim",
                              "social_vertical", "social_karaoke",
                              "kids_accessible"}


def test_a_preset_carries_the_shared_defaults(netflix):
    """The lead-in, the tail and the forbidden breaks are written once."""
    assert netflix["max_chars_per_line"] == 42
    assert netflix["max_lines"] == 2
    assert netflix["max_chars_per_second"] == 17
    assert netflix["sync_lead_in_ms"] == 100          # from defaults
    assert netflix["tail_ms"] == {"min": 200, "max": 500}
    assert "article+noun" in netflix["forbidden_line_breaks"]


def test_a_house_style_can_replace_a_bundled_one(tmp_path, monkeypatch):
    """The same two places the keyword sets use, the user's winning."""
    import json

    from audio_transcriber import paths

    directory = paths.ensure(paths.config_dir())
    with open(subtitles.user_file(), "w", encoding="utf-8") as handle:
        json.dump({"presets": {"netflix": {"max_chars_per_line": 30},
                               "house": {"max_chars_per_line": 28,
                                          "max_lines": 1}}}, handle)
    assert directory
    assert subtitles.preset("netflix")["max_chars_per_line"] == 30
    assert subtitles.preset("netflix")["max_chars_per_second"] == 17   # kept
    assert subtitles.preset("house")["max_lines"] == 1


def test_an_unknown_preset_says_which_ones_exist():
    with pytest.raises(subtitles.SubtitleError) as raised:
        subtitles.preset("bbc-1974")
    assert "netflix" in str(raised.value)


def test_the_knobs_an_interface_offers_win_over_the_preset():
    spec = subtitles.preset("netflix", {"max_chars_per_line": 20,
                                        "max_chars_per_second": None})
    assert spec["max_chars_per_line"] == 20
    assert spec["max_chars_per_second"] == 17          # None means "not chosen"


# --- words ----------------------------------------------------------------

def test_word_timings_are_used_when_the_engine_reports_them():
    """Then the cuts fall where the speaker actually paused."""
    words = subtitles.words_of([timed("uno due tre", 10.0)])
    assert [word.text for word in words] == ["uno", "due", "tre"]
    assert words[0].start == 10.0
    assert words[2].end == pytest.approx(11.2)


def test_without_word_timings_the_times_are_interpolated():
    """Good to a few tenths of a second, which is why the real thing is worth
    asking the engine for."""
    words = subtitles.words_of([segment("uno due tre", 0.0, 3.0)])
    assert [word.text for word in words] == ["uno", "due", "tre"]
    assert words[0].start == 0.0
    assert words[-1].end == pytest.approx(3.0)
    assert words[1].start == pytest.approx(1.0, abs=0.2)


def test_a_segment_with_no_timings_at_all_is_skipped():
    assert subtitles.words_of([{"text": "uno due"}]) == []


# --- cutting --------------------------------------------------------------

def test_a_short_sentence_is_one_cue(netflix):
    built = subtitles.cues([timed("Il budget e' approvato.", 0.0)], netflix)
    assert len(built) == 1
    assert built[0].text == "Il budget e' approvato."
    assert built[0].index == 1


def test_a_long_paragraph_is_cut_into_readable_cues(netflix):
    """The engine's thirty-second segment is what makes subtitles impossible;
    this is the whole point of the module."""
    text = ("Il primo punto all'ordine del giorno riguarda il budget del "
            "prossimo trimestre e le assunzioni previste per la sede di "
            "Bologna, che vanno approvate entro la fine del mese.")
    built = subtitles.cues([timed(text, 0.0, per_word=0.35)], netflix)
    assert len(built) >= 3
    for cue in built:
        assert cue.chars <= netflix["max_chars_per_line"]
        assert len(cue.lines) <= netflix["max_lines"]
        assert cue.duration <= netflix["max_duration_ms"] / 1000 + 0.001


def test_every_word_survives_the_cutting(netflix):
    """Cut, not condensed: this program does not rewrite what was said."""
    text = ("Abbiamo deciso di rinviare la decisione sul contratto perche' "
            "mancano i numeri definitivi del controllo di gestione.")
    built = subtitles.cues([timed(text, 0.0)], netflix)
    rebuilt = " ".join(cue.text.replace("\n", " ") for cue in built)
    assert rebuilt.split() == text.split()


def test_a_sentence_boundary_is_preferred_to_a_word_boundary(netflix):
    text = "Approvato. Passiamo al punto successivo dell'ordine del giorno."
    built = subtitles.cues([timed(text, 0.0)], netflix)
    assert built[0].text == "Approvato."


def test_a_cue_can_be_capped_by_words_as_well_as_by_characters():
    """Not one of the trade's numbers, but the one people reach for first: a
    new subtitle every so many words."""
    spec = subtitles.preset("netflix", {"max_words_per_cue": 3})
    built = subtitles.cues([timed("uno due tre quattro cinque sei sette otto", 0.0)],
                           spec)
    assert len(built) >= 3
    for cue in built:
        assert len(cue.text.split()) <= 3


# --- lines ----------------------------------------------------------------

def test_a_line_never_ends_on_an_article():
    """"il" alone at the end of a line reads as a stumble - it is the first
    of the forbidden breaks."""
    spec = subtitles.preset("netflix", {"max_chars_per_line": 20})
    built = subtitles.cues([timed("Approviamo il bilancio consolidato adesso", 0.0)],
                           spec, language="it")
    for cue in built:
        for line in cue.lines[:-1]:
            assert line.split()[-1].lower() not in subtitles.NO_BREAK_AFTER["it"]


def test_a_line_never_ends_on_a_preposition_or_a_negation():
    spec = subtitles.preset("netflix", {"max_chars_per_line": 18})
    text = "Non possiamo procedere con la fornitura di materiale"
    built = subtitles.cues([timed(text, 0.0)], spec, language="it")
    for cue in built:
        for line in cue.lines[:-1]:
            last = line.split()[-1].lower()
            assert last not in {"non", "con", "di", "la"}


def test_a_clitic_is_not_left_at_the_start_of_a_line():
    spec = subtitles.preset("netflix", {"max_chars_per_line": 16})
    built = subtitles.cues([timed("Possiamo mandarlo lo stesso domani", 0.0)],
                           spec, language="it")
    for cue in built:
        for line in cue.lines[1:]:
            assert line.split()[0].lower() not in subtitles.NO_BREAK_BEFORE["it"]


def test_the_two_lines_of_a_cue_are_never_wildly_different(netflix):
    """The guidance asks for balance *after* a good break, not instead of one:
    a break before a conjunction beats a balanced break mid-phrase. What is
    ruled out is a lopsided split - more than half the longer line."""
    text = "Il consiglio ha approvato il bilancio e la nota integrativa oggi"
    lines = subtitles.wrap(subtitles.words_of([timed(text, 0.0)]), netflix)
    assert len(lines) == 2
    assert lines[1].startswith("e ")             # broken before the conjunction
    assert abs(len(lines[0]) - len(lines[1])) <= 0.5 * max(len(lines[0]),
                                                           len(lines[1]))


def test_the_pyramid_is_preferred_among_equally_good_breaks(netflix):
    """With nothing to choose between the break points, the shorter line goes
    first: it is what the guidance asks for and it reads more easily."""
    words = subtitles.words_of([timed("alfa bravo charlie delta echo foxtrot", 0.0)])
    spec = subtitles.preset("netflix", {"max_chars_per_line": 22})
    lines = subtitles.wrap(words, spec)
    assert len(lines) == 2
    assert len(lines[0]) <= len(lines[1])


def test_one_line_presets_never_produce_two():
    spec = subtitles.preset("social_karaoke")
    built = subtitles.cues([timed("una frase piuttosto lunga da spezzare", 0.0)], spec)
    assert built
    for cue in built:
        assert len(cue.lines) == 1
        assert cue.chars <= spec["max_chars_per_line"]


def test_the_karaoke_preset_cuts_by_words_not_by_sentences():
    spec = subtitles.preset("social_karaoke")
    built = subtitles.cues([timed("uno due tre quattro cinque sei sette otto", 0.0)],
                           spec)
    assert len(built) >= 2
    for cue in built:
        assert len(cue.text.split()) <= spec["segment_by_words"]["max"]


# --- who is speaking ------------------------------------------------------

def spoken(text, start, speaker, per_word=0.4):
    body = timed(text, start, per_word)
    body["speaker"] = speaker
    for word in body["words"]:
        word["speaker"] = speaker
    return body


def test_a_cue_never_holds_two_voices(netflix):
    """Two people sharing a cue would have to share its two lines; splitting
    at the change is cleaner and always possible."""
    built = subtitles.cues([spoken("Approvato, direi.", 0.0, "SPEAKER_00"),
                            spoken("Non sono d'accordo.", 2.0, "SPEAKER_01")],
                           netflix, mark_speakers=True)
    assert len(built) == 2
    assert "Approvato" in built[0].text and "d'accordo" in built[1].text


def test_a_change_of_voice_is_marked_with_a_hyphen(netflix):
    built = subtitles.cues([spoken("Approvato, direi.", 0.0, "SPEAKER_00"),
                            spoken("Non sono d'accordo.", 2.0, "SPEAKER_01")],
                           netflix, mark_speakers=True)
    assert built[0].lines[0].startswith(subtitles.SPEAKER_MARK)
    assert built[1].lines[0].startswith(subtitles.SPEAKER_MARK)


def test_a_monologue_is_not_marked_at_all(netflix):
    """A hyphen in front of every cue of one voice says nothing."""
    built = subtitles.cues([spoken("Il primo punto. Il secondo punto.", 0.0,
                                   "SPEAKER_00")],
                           netflix, mark_speakers=True)
    assert built
    assert not any(cue.lines[0].startswith(subtitles.SPEAKER_MARK) for cue in built)


def test_consecutive_cues_of_the_same_voice_are_marked_once(netflix):
    built = subtitles.cues([spoken("Primo punto. Secondo punto.", 0.0, "SPEAKER_00"),
                            spoken("Terzo punto.", 4.0, "SPEAKER_01")],
                           netflix, mark_speakers=True)
    marked = [cue.lines[0].startswith(subtitles.SPEAKER_MARK) for cue in built]
    assert marked[0] is True            # there is more than one voice here
    assert marked[1] is False           # still the first speaker
    assert marked[-1] is True           # and now it changed


def test_nothing_is_marked_when_it_was_not_asked_for(netflix):
    built = subtitles.cues([spoken("Approvato.", 0.0, "SPEAKER_00"),
                            spoken("No.", 2.0, "SPEAKER_01")], netflix)
    assert not any(cue.text.startswith(subtitles.SPEAKER_MARK) for cue in built)


# --- timing ---------------------------------------------------------------

def test_a_cue_may_appear_early_but_never_late(netflix):
    built = subtitles.cues([timed("Buonasera.", 5.0)], netflix)
    lead_in = netflix["sync_lead_in_ms"] / 1000
    assert built[0].start == pytest.approx(5.0 - lead_in)


def test_a_cue_is_never_shorter_than_the_minimum(netflix):
    """Below it, a subtitle blinks rather than reads."""
    built = subtitles.cues([timed("Sì.", 1.0, per_word=0.1)], netflix)
    assert built[0].duration >= netflix["min_duration_ms"] / 1000 - 0.001


def test_a_cue_is_never_longer_than_the_maximum(netflix):
    """Even when the speaker leaves a long silence after it."""
    built = subtitles.cues([segment("Una frase breve.", 0.0, 30.0)], netflix)
    assert built[0].duration <= netflix["max_duration_ms"] / 1000 + 0.001


def test_cues_never_overlap_and_keep_the_minimum_gap(netflix):
    text = ("Primo punto. Secondo punto. Terzo punto. Quarto punto. "
            "Quinto punto. Sesto punto.")
    built = subtitles.cues([timed(text, 0.0, per_word=0.5)], netflix)
    gap = netflix["min_gap_ms"] / 1000
    for first, second in zip(built, built[1:], strict=False):
        assert second.start >= first.end + gap - 0.001


def test_a_near_zero_gap_is_snapped_open(netflix):
    """A hole of thirty milliseconds does not read as two subtitles, it reads
    as one that blinked; chaining pulls it out to the minimum."""
    first = subtitles.Cue(1, 0.0, 2.0, ["uno"])
    second = subtitles.Cue(2, 2.02, 4.0, ["due"])
    subtitles._chain([first, second], netflix)
    snap = netflix["gap_chaining"]["snap_to_ms"] / 1000
    assert second.start - first.end == pytest.approx(snap, abs=0.002)


def test_speech_too_fast_to_subtitle_is_split_and_then_reported(netflix):
    """There is a point past which the numbers cannot be met without cutting
    words out, and cutting words out is not this program's decision. It splits
    as far as splitting helps, emits the cues, and says what is wrong with
    them - which is a warning a person can act on rather than a sentence a
    program invented."""
    text = ("Questa frase viene detta molto velocemente e contiene parecchie "
            "parole in pochissimo tempo davvero")
    built = subtitles.cues([timed(text, 0.0, per_word=0.12)], netflix)
    assert len(built) > 1
    keys = {key for key, _where, _value in subtitles.validate(built, netflix)}
    assert "subtitles.too_fast" in keys


# --- the files ------------------------------------------------------------

def test_a_timestamp_is_written_the_way_srt_wants_it():
    assert subtitles.timestamp(0) == "00:00:00,000"
    assert subtitles.timestamp(3661.5) == "01:01:01,500"
    assert subtitles.timestamp(1.9999) == "00:00:02,000"     # never ,1000
    assert subtitles.timestamp(59.9999) == "00:01:00,000"


def test_webvtt_uses_a_dot_instead():
    assert subtitles.timestamp(1.25, ".") == "00:00:01.250"


def test_the_srt_file_has_the_shape_players_expect(netflix):
    built = subtitles.cues([timed("Primo punto. Secondo punto.", 0.0)], netflix)
    text = subtitles.to_srt(built)
    blocks = text.strip().split("\n\n")
    assert len(blocks) == len(built)
    first = blocks[0].splitlines()
    assert first[0] == "1"
    assert " --> " in first[1] and "," in first[1]
    assert first[2]
    assert text.endswith("\n")


def test_the_srt_file_can_be_written_with_windows_line_endings(netflix):
    built = subtitles.cues([timed("Primo punto.", 0.0)], netflix)
    assert "\r\n" in subtitles.to_srt(built, line_ending="\r\n")


def test_the_vtt_file_starts_with_its_header(netflix):
    built = subtitles.cues([timed("Primo punto.", 0.0)], netflix)
    text = subtitles.to_vtt(built)
    assert text.startswith("WEBVTT")
    assert " --> " in text
    assert ",000" not in text          # WebVTT wants dots, not commas


# --- validation -----------------------------------------------------------

def test_a_clean_set_of_cues_reports_nothing(netflix):
    built = subtitles.cues([timed("Il budget e' approvato.", 0.0)], netflix)
    assert subtitles.validate(built, netflix) == []


def test_validation_names_what_a_subtitler_would_object_to(netflix):
    problems = subtitles.validate([
        subtitles.Cue(1, 0.0, 0.2, ["x" * 60]),        # too short, too wide
        subtitles.Cue(2, 0.1, 9.0, ["ok"]),            # overlaps, too long
        subtitles.Cue(3, 9.0, 8.0, ["backwards"]),
        subtitles.Cue(4, 20.0, 21.0, [""]),
    ], netflix)
    keys = {key for key, _where, _value in problems}
    assert {"subtitles.too_short", "subtitles.too_wide", "subtitles.too_long",
            "subtitles.backwards", "subtitles.empty"} <= keys


def test_validation_counts_words_per_minute_when_the_preset_does():
    bbc = subtitles.preset("bbc")
    fast = subtitles.Cue(1, 0.0, 1.0, ["una due tre quattro cinque sei sette"])
    keys = {key for key, _where, _value in subtitles.validate([fast], bbc)}
    assert "subtitles.too_many_words" in keys


def test_nothing_is_reported_for_an_empty_transcript(netflix):
    assert subtitles.cues([], netflix) == []
    assert subtitles.validate([], netflix) == []


# --- telling one kind of remark from another ------------------------------

def test_the_remark_groups_cover_everything_validate_can_report():
    """A remark in no group would be printed without its heading."""
    grouped = set()
    for _heading, keys in subtitles.PROBLEM_GROUPS:
        grouped |= keys
    spec = subtitles.preset("bbc")
    reported = set()
    # Every branch of validate(), on cues built to break each rule.
    cues = [subtitles.Cue(1, 0.0, 0.05, [""]),
            subtitles.Cue(2, 5.0, 4.0, ["indietro"]),
            subtitles.Cue(3, 10.0, 10.4, ["x" * 80]),
            subtitles.Cue(4, 20.0, 40.0, ["a", "b", "c", "d"]),
            subtitles.Cue(5, 41.0, 41.2, ["troppo veloce da leggere davvero"]),
            subtitles.Cue(6, 41.1, 48.0, ["si sovrappone"])]
    for key, _where, _value in subtitles.validate(cues, spec):
        reported.add(key)
    assert reported, "no rule was exercised"
    assert reported <= grouped


def test_word_timings_are_what_makes_a_clock_measured():
    assert not subtitles.timings_measured([{"text": "ciao", "start": 0.0, "end": 1.0}])
    assert subtitles.timings_measured(
        [{"text": "ciao", "start": 0.0, "end": 1.0,
          "words": [{"word": "ciao", "start": 0.0, "end": 1.0}]}])
    assert not subtitles.timings_measured([])


def test_remarks_are_counted_by_kind():
    problems = [("subtitles.too_fast", 1, 20.0), ("subtitles.too_fast", 2, 19.0),
                ("subtitles.too_short", 3, 0.4)]
    assert subtitles.tally(problems) == {"subtitles.too_fast": 2,
                                         "subtitles.too_short": 1}
