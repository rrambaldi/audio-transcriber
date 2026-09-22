"""What each pass did, and the two numbers computed from the result.

All of this is arithmetic over text, so it runs with no model, no ffmpeg and
no Qt. The bug it exists for is a summary of a twenty-two minute meeting that
described the first seven and said nothing about the rest: the tests below are
what would have caught it.
"""
import json

from audio_transcriber.summarizers import trace as tracing


def some_trace():
    found = tracing.Trace()
    found.chunk(index=1, total=3, in_tokens=3180, out_tokens=412, notes=4)
    found.chunk(index=2, total=3, in_tokens=3402, out_tokens=0, notes=0,
                status=tracing.EMPTY_OUTPUT)
    found.chunk(index=3, total=3, in_tokens=3355, out_tokens=210, notes=2,
                status=tracing.ECHOED)
    found.fold(level=1, group=1, groups=2, partials_in=2, in_tokens=900,
               budget=500, out_tokens=487)
    found.fold(level=1, group=2, groups=2, partials_in=6, in_tokens=3110,
               budget=500, out_tokens=0, status=tracing.COLLAPSED, lost=5)
    return found


# --- coverage: the number that would have made P1 obvious -----------------

def test_a_page_about_the_first_third_scores_a_third():
    """The bug this was written for: the last timestamp on a page about a
    twenty-two minute meeting was 7:30."""
    starts = [30.0, 90.0, 200.0, 300.0, 400.0, 450.0, 450.1]
    # Minutes 0, 1, 3, 5, 6 and 7 of twenty-two.
    assert tracing.coverage(starts, 22 * 60) == 6 / 22


def test_a_page_that_mentions_every_minute_scores_one():
    starts = [minute * 60 + 5 for minute in range(22)]
    assert tracing.coverage(starts, 22 * 60) == 1.0


def test_several_points_in_one_minute_are_one_minute():
    assert tracing.coverage([10.0, 20.0, 30.0], 5 * 60) == 1 / 5


def test_a_page_with_no_minutes_at_all_covers_nothing():
    assert tracing.coverage([None, None], 600) == 0.0
    assert tracing.coverage([], 600) == 0.0


def test_a_recording_of_unknown_length_gets_no_number():
    """An invented denominator is worse than no number: the entries filed
    before this program measured them have no duration."""
    assert tracing.coverage([10.0], None) is None
    assert tracing.coverage([10.0], 0) is None


def test_a_timestamp_past_the_end_does_not_inflate_the_share():
    assert tracing.coverage([10.0, 99999.0], 120) == 0.5


# --- copy_rate: written, or selected? --------------------------------------

TRANSCRIPT = ("allora io vorrei monitorare tutti gli utenti a cui è stata "
              "inviata la mail e poi vedere se sono entrati in piattaforma")


def test_a_sentence_lifted_whole_is_all_copied():
    lifted = "io vorrei monitorare tutti gli utenti a cui è stata inviata la mail"
    assert tracing.copy_rate([lifted], TRANSCRIPT) == 1.0


def test_a_sentence_written_afresh_is_not_copied():
    written = ("Serve un modo per sapere quali destinatari hanno aperto "
               "l'invito e completato la registrazione al servizio.")
    assert tracing.copy_rate([written], TRANSCRIPT) == 0.0


def test_the_accents_whisper_writes_do_not_hide_a_copy():
    """Whisper writes them and a model rewriting the line may not. Compared
    letter for letter this would read as freshly written; it is not."""
    lifted = "io vorrei monitorare tutti gli utenti a cui e stata inviata la mail"
    assert tracing.copy_rate([lifted], TRANSCRIPT) == 1.0


def test_too_little_text_to_ask_the_question_gets_no_number():
    assert tracing.copy_rate(["due parole"], TRANSCRIPT) is None
    assert tracing.copy_rate(["qualunque cosa"], "corto") is None


# --- what the records say --------------------------------------------------

def test_a_collapsed_fold_says_how_many_partials_it_lost():
    """The number that closes the case: a fold that produced nothing kept the
    first of what it was given and dropped the rest in silence."""
    line = some_trace().folds[1].line()
    assert "COLLAPSED" in line
    assert "persi=5" in line


def test_a_chunk_that_produced_nothing_says_so():
    line = some_trace().chunks[1].line()
    assert "note=0" in line and tracing.EMPTY_OUTPUT in line


def test_the_counts_add_up():
    counts = some_trace().counts()
    assert counts["chunks"] == 3
    assert counts["empty_chunks"] == 1
    assert counts["echoed_chunks"] == 1
    assert counts["folds"] == 2
    assert counts["folds_collapsed"] == 1
    assert counts["partials_lost"] == 5


def test_a_cache_hit_is_not_a_failure():
    found = tracing.Trace()
    found.chunk(index=1, total=1, in_tokens=0, out_tokens=0, notes=6,
                status=tracing.REUSED)
    assert found.failures() == []


def test_a_cache_hit_that_carries_nothing_is_still_a_failure():
    """A pass filed under a key and holding no notes is a pass that failed
    once and has been coming back ever since."""
    found = tracing.Trace()
    found.chunk(index=1, total=1, in_tokens=0, out_tokens=0, notes=0,
                status=tracing.REUSED)
    assert len(found.failures()) == 1


def test_silence_is_the_one_legitimate_zero():
    found = tracing.Trace()
    found.chunk(index=1, total=1, in_tokens=800, out_tokens=0, notes=0,
                status=tracing.NO_CONTENT)
    assert found.failures() == []
    assert found.counts()["empty_chunks"] == 0


def test_everything_recorded_comes_back_as_json():
    payload = json.loads(some_trace().as_document({"metrics": {"coverage": 0.34}}))
    assert payload["schema"] == 1
    assert len(payload["chunks"]) == 3
    assert payload["folds"][1]["lost"] == 5
    assert payload["counts"]["partials_lost"] == 5
    assert payload["metrics"]["coverage"] == 0.34
