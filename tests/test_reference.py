"""A text you already have, helping the transcription and correcting it.

The rule these tests exist to hold: **the audio decides what was said, the
text decides how it is written.** A speaker improvises, skips a paragraph,
adds a sentence nobody wrote down - and none of that may be overwritten by
what the script expected. What the text is allowed to fix is a word the engine
misheard or cut short.

No engine is involved: segments with words in them are all this ever sees.
"""
import pytest

from audio_transcriber import reference


def spoken(text, start=0.0):
    """A segment in the shape an engine returns, one word every 0.4s."""
    words = text.split()
    return {"start": start, "end": start + 0.4 * len(words), "text": text,
            "words": [{"word": word, "start": start + index * 0.4,
                       "end": start + index * 0.4 + 0.35}
                      for index, word in enumerate(words)]}


def spelling(segments):
    """Every word of a run, as written."""
    return [word["word"] for segment in segments for word in segment["words"]]


# --- what the text is allowed to fix --------------------------------------

def test_an_accent_the_engine_dropped_comes_back():
    heard = [spoken("perche il budget e approvato")]
    fixed, report = reference.correct(heard, "Perché il budget è approvato.")

    assert spelling(fixed) == ["perché", "il", "budget", "è", "approvato"]
    assert report["corrected"] == 2


def test_a_name_the_engine_got_wrong_is_respelled():
    """The reason most people have a text at hand: the names."""
    heard = [spoken("ne parla rambardi del comitato")]
    fixed, _report = reference.correct(heard, "Ne parla Rambaldi del comitato.")

    assert "Rambaldi" in spelling(fixed)
    assert "rambardi" not in spelling(fixed)


def test_a_word_cut_short_is_finished():
    """"trascriz" is not a word; the engine ran out of audio for it."""
    heard = [spoken("parliamo delle trascriz automatiche")]
    fixed, _report = reference.correct(heard, "Parliamo delle trascrizioni automatiche.")

    assert "trascrizioni" in spelling(fixed)


def test_a_capital_that_is_only_a_sentence_start_is_not_imposed():
    """The text capitalises "poi" because a sentence starts there. The engine's
    sentence runs straight through it, and its own case is the right one."""
    heard = [spoken("e poi parliamo del bilancio")]
    fixed, _report = reference.correct(heard, "E poi parliamo del bilancio.\n\n"
                                              "Poi si vota.")

    assert "poi" in spelling(fixed)
    assert "Poi" not in spelling(fixed)


# --- what it must leave alone ---------------------------------------------

def test_a_word_that_is_simply_another_word_stands():
    """"bilancio" for "budget" is not a spelling difference: the speaker said
    something else, and that is a fact about the recording."""
    heard = [spoken("il bilancio e approvato")]
    fixed, report = reference.correct(heard, "Il budget è approvato.")

    assert "bilancio" in spelling(fixed)
    assert "budget" not in spelling(fixed)
    assert report["corrected"] == 1          # the accent on "è", nothing more


def test_a_sentence_in_the_text_that_was_never_said_does_not_appear():
    """The whole difference from laying a text over the audio: the script
    expected a closing line, the speaker skipped it, and the transcript is of
    the recording."""
    heard = [spoken("buongiorno a tutti")]
    fixed, report = reference.correct(
        heard, "Buongiorno a tutti. Grazie per essere venuti, cominciamo.")

    assert spelling(fixed) == ["Buongiorno", "a", "tutti"]
    assert "grazie" not in " ".join(spelling(fixed)).lower()
    assert report["heard"] == 3


def test_a_sentence_said_but_not_in_the_text_survives_untouched():
    """The speaker improvised. Nothing in the text says otherwise, so nothing
    may touch it."""
    heard = [spoken("il budget e approvato e aggiungo una cosa a mano libera")]
    fixed, _report = reference.correct(heard, "Il budget è approvato.")
    written = " ".join(spelling(fixed))

    assert "aggiungo una cosa a mano libera" in written


def test_short_words_are_not_corrected_by_edit_distance():
    """"che" and "chi", "caso" and "corso", "anno" and "hanno" are one edit
    apart and all real: an engine gets them right from the audio, and a text
    has no business guessing. Below six letters the distance means nothing."""
    for heard_text, given_text, kept in (
            ("dice che serve", "Dice chi serve.", "che"),
            ("nel caso di ieri", "Nel corso di ieri.", "caso"),
            ("anno detto sì", "Hanno detto sì.", "anno"),
            ("i dati di ieri", "Le date di ieri.", "dati")):
        fixed, _report = reference.correct([spoken(heard_text)], given_text)
        assert kept in spelling(fixed), (heard_text, given_text)


def test_two_edits_apart_is_two_different_words():
    """"premesso" and "permesso" are 87% alike by any ratio and are not the
    same word. The distance is what says so: two edits, not one."""
    heard = [spoken("premesso questo si vota")]
    fixed, _report = reference.correct(heard, "Permesso questo si vota.")

    assert "premesso" in spelling(fixed)


def test_an_inflection_is_left_to_the_audio():
    """A plural, a tense, a gender: one edit, and at the end of the word. The
    speaker said one or the other and the engine heard which - a text written
    beforehand does not get to decide it."""
    for heard_text, given_text, kept in (
            ("le trascrizione del giorno", "Le trascrizioni del giorno.",
             "trascrizione"),
            ("il piano approvato ieri", "Il piano approvata ieri.", "approvato"),
            ("la comunicazione di ieri", "Le comunicazioni di ieri.",
             "comunicazione")):
        fixed, _report = reference.correct([spoken(heard_text)], given_text)
        assert kept in spelling(fixed), (heard_text, given_text)


def test_an_edit_inside_a_long_word_is_a_misspelling():
    """The other side of the same rule: inside the word it is spelling, and
    that is exactly what the text is for."""
    for heard_text, given_text, wanted in (
            ("parliamo di kubernets", "Parliamo di Kubernetes.", "Kubernetes"),
            ("con openvimo va meglio", "Con OpenVINO va meglio.", "OpenVINO"),
            ("i sottotitolli sono pronti", "I sottotitoli sono pronti.",
             "sottotitoli")):
        fixed, _report = reference.correct([spoken(heard_text)], given_text)
        assert wanted in spelling(fixed), (heard_text, given_text)


def test_the_distance_is_the_textbook_one():
    """One edit is one insertion, one deletion or one substitution - so that
    the constant in the module means what it says."""
    assert reference.levenshtein("rambardi", "rambaldi") == 1     # substitute
    assert reference.levenshtein("kubernets", "kubernetes") == 1  # insert
    assert reference.levenshtein("kubernetees", "kubernetes") == 1  # delete
    assert reference.levenshtein("premesso", "permesso") == 2
    assert reference.levenshtein("", "abc") == 3
    assert reference.levenshtein("uguale", "uguale") == 0


def test_nothing_is_added_removed_or_re_timed():
    """The output is the engine's own run with some words respelled. Anything
    else would make the subtitles, the transcript and the audio disagree."""
    heard = [spoken("perche il budget e approvato"), spoken("poi si vota", 3.0)]
    fixed, _report = reference.correct(
        heard, "Perché il budget è approvato.\n\nPoi si vota, se c'è tempo.")

    assert [len(segment["words"]) for segment in fixed] == [5, 3]
    assert [word["start"] for segment in fixed for word in segment["words"]] == \
           [word["start"] for segment in heard for word in segment["words"]]
    assert [segment["end"] for segment in fixed] == \
           [segment["end"] for segment in heard]


def test_the_segment_text_is_rebuilt_from_its_own_words():
    """The transcript and the word list must not be able to disagree: one is
    written into the entry and the other is what the subtitles are cut from."""
    heard = [spoken("perche il budget e approvato")]
    fixed, _report = reference.correct(heard, "Perché il budget è approvato.")

    assert fixed[0]["text"] == " ".join(spelling(fixed))


def test_a_backend_that_reports_no_word_times_is_still_corrected():
    """faster-whisper is asked for word timings only when subtitles are
    wanted; the proof-reading has to work either way."""
    heard = [{"start": 0.0, "end": 2.0, "text": "perche il budget e approvato"}]
    fixed, report = reference.correct(heard, "Perché il budget è approvato.")

    assert fixed[0]["text"] == "perché il budget è approvato"
    assert report["corrected"] == 2


def test_no_text_or_no_words_changes_nothing():
    heard = [spoken("buongiorno a tutti")]
    same, report = reference.correct(heard, "   ")
    assert same is heard and report is None
    same, report = reference.correct([], "Buongiorno.")
    assert same == [] and report is None


# --- what it says about itself --------------------------------------------

def test_a_text_of_another_recording_corrects_nothing_and_says_so():
    """It cannot do damage - there is nothing close enough to respell - but
    "corrected 0 words" alone would not explain why."""
    heard = [spoken("il budget e approvato dal comitato")]
    _fixed, report = reference.correct(
        heard, "Ricetta della carbonara: guanciale, uova, pecorino.")

    assert report["corrected"] == 0
    assert report["coverage"] < reference.POOR_MATCH


def test_the_report_counts_both_sides():
    heard = [spoken("perche il budget e approvato")]
    _fixed, report = reference.correct(heard, "Perché il budget è approvato.")

    assert report["heard"] == 5
    assert report["given"] == 5
    assert report["matched"] == 5
    assert report["coverage"] == 1.0


# --- and what it hands the engine before it starts ------------------------

def test_the_prompt_is_the_words_an_engine_cannot_guess():
    """Names, acronyms, numbers, compounds and long rare words - not the
    prose. A prompt is a few hundred characters and "and then we agreed" buys
    nothing."""
    prompt = reference.prompt_from(
        "Il comitato ISO ha approvato il piano di Rambaldi per l'H.264 "
        "e per le trascrizioni automatiche di quest'anno.")

    assert "ISO" in prompt and "Rambaldi" in prompt and "H.264" in prompt
    assert "trascrizioni" in prompt
    for ordinary in (" il ", " ha ", " per ", " e "):
        assert ordinary not in f" {prompt} "


def test_the_prompt_repeats_nothing_and_respects_its_limit():
    text = "Rambaldi Rambaldi Rambaldi " + " ".join(
        f"parolalunga{index}" for index in range(200))
    prompt = reference.prompt_from(text, limit=120)

    assert prompt.count("Rambaldi") == 1
    assert len(prompt) <= 120


def test_a_capitalised_sentence_start_is_not_mistaken_for_a_name():
    """"Poi" is not a name, and prompt characters spent on it are wasted."""
    prompt = reference.prompt_from("Poi il comitato vota. Quando si decide?")

    assert "Poi" not in prompt
    assert "Quando" not in prompt


@pytest.mark.parametrize("first,second", [
    ("Perché,", "perche"), ("«Sì!»", "si"), ("PERCHÉ", "perche"),
])
def test_folding_ignores_case_accents_and_punctuation(first, second):
    assert reference.fold(first) == reference.fold(second)
