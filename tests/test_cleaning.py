"""Text-cleaning tests. No models, no accelerators, no network."""
from audio_transcriber.cleaning import (
    HALLUCINATION_PHRASES,
    clean_segments,
    clean_text,
    normalise,
    paragraphs_from_blob,
    segments_from_words,
    to_paragraphs,
)


def test_clean_text_collapses_spaces_and_punctuation():
    assert clean_text("ciao   mondo , come  va ?") == "ciao mondo, come va?"


def test_normalise_strips_punctuation_and_case():
    assert normalise("Grazie, a tutti!") == "grazie a tutti"


def test_drops_italian_hallucinations():
    segments = [
        {"text": "Grazie a tutti", "start": 0.0, "end": 1.0},
        {"text": "Parliamo del progetto", "start": 1.0, "end": 3.0},
    ]
    kept = clean_segments(segments)
    assert [s["text"] for s in kept] == ["Parliamo del progetto"]


def test_drops_english_hallucinations():
    segments = [
        {"text": "Thanks for watching", "start": 0.0, "end": 1.0},
        {"text": "Let us look at the numbers", "start": 1.0, "end": 3.0},
    ]
    kept = clean_segments(segments)
    assert [s["text"] for s in kept] == ["Let us look at the numbers"]


def test_keep_fillers_keeps_everything():
    segments = [{"text": "Grazie a tutti", "start": 0.0, "end": 1.0}]
    assert len(clean_segments(segments, drop_fillers=False)) == 1


def test_collapses_identical_consecutive_segments():
    segments = [
        {"text": "stessa frase", "start": 0.0, "end": 1.0},
        {"text": "stessa frase", "start": 1.0, "end": 2.0},
    ]
    assert len(clean_segments(segments)) == 1


def test_a_segment_that_re_says_the_one_before_it_keeps_only_its_own_tail():
    """The engine transcribed the same span twice, the second time with more
    on the end. Both halves are kept - the first with its own start, the
    second reduced to what it adds - rather than dropping the first and
    losing the seconds it covered."""
    long_text = "una frase abbastanza lunga da superare la soglia di contenimento"
    segments = [
        {"text": long_text, "start": 0.0, "end": 2.0},
        {"text": long_text + " e con una coda in piu", "start": 1.5, "end": 3.0},
    ]
    kept = clean_segments(segments)
    assert [s["text"] for s in kept] == [long_text, "e con una coda in piu"]
    assert kept[0]["start"] == 0.0
    # No word timings, so the start of what is left is worked out from the
    # share of the characters that were cut.
    assert kept[1]["start"] > 1.5


def test_short_similar_segments_are_not_collapsed():
    segments = [
        {"text": "va bene", "start": 0.0, "end": 1.0},
        {"text": "va bene cosi", "start": 1.0, "end": 2.0},
    ]
    assert len(clean_segments(segments)) == 2


def test_paragraph_breaks_on_a_long_pause():
    segments = [
        {"text": "Prima frase.", "start": 0.0, "end": 1.0},
        {"text": "Seconda frase.", "start": 5.0, "end": 6.0},
    ]
    assert to_paragraphs(segments, gap_break=1.2, max_chars=600) == [
        "Prima frase.", "Seconda frase."]


def test_paragraph_keeps_segments_separated_by_a_short_pause_together():
    segments = [
        {"text": "Prima frase.", "start": 0.0, "end": 1.0},
        {"text": "Seconda frase.", "start": 1.1, "end": 2.0},
    ]
    assert to_paragraphs(segments, gap_break=1.2, max_chars=600) == [
        "Prima frase. Seconda frase."]


def test_paragraph_breaks_on_max_chars():
    segments = [{"text": "x" * 30, "start": i, "end": i + 0.5} for i in range(4)]
    assert len(to_paragraphs(segments, gap_break=10, max_chars=50)) == 2


def test_paragraph_breaks_when_timestamps_are_missing():
    segments = [
        {"text": "Prima.", "start": None, "end": None},
        {"text": "Seconda.", "start": None, "end": None},
    ]
    assert to_paragraphs(segments, gap_break=1.2, max_chars=600) == ["Prima.", "Seconda."]


def test_paragraphs_from_blob_groups_sentences():
    blob = "Una. Due. Tre. Quattro. Cinque. Sei."
    assert len(paragraphs_from_blob(blob, sentences_per_para=5)) == 2


def test_hallucination_catalogues_are_lowercase_and_unpunctuated():
    for phrases in HALLUCINATION_PHRASES.values():
        for phrase in phrases:
            assert phrase == phrase.lower()


# --------------------------------------------------------------------------
# the doubling a chunked engine leaves behind
# --------------------------------------------------------------------------

def test_trims_an_overlap_the_engine_failed_to_stitch():
    """The tail of one segment, said again at the head of the next.

    The two copies are not word-identical - "solo questo. quindi campo" comes
    back as "in solo questo campo" - which is why they are aligned rather than
    compared."""
    segments = [
        {"text": "faremo un caricamento massivo, solo questo. "
                 "quindi campo e tabellini quindi la configurazione",
         "start": 0.0, "end": 68.0},
        {"text": "in solo questo campo e tabellini quindi la configurazione "
                 "si risolve tutto in aggiungere campo all'asset",
         "start": 68.0, "end": 147.0},
    ]
    kept = clean_segments(segments)
    assert kept[1]["text"] == "si risolve tutto in aggiungere campo all'asset"


def test_an_overlap_is_looked_for_two_segments_back():
    """An engine that doubles one window often doubles the next as well."""
    segments = [
        {"text": "mi devi per forza legare il documento", "start": 0.0, "end": 6.0},
        {"text": "o comunque l'altro sara' piu' in un concetto l'ho fatto "
                 "non l'ho fatto smarcato non smarcato", "start": 6.0, "end": 14.0},
        {"text": "altro mi devi per forza legare il documento o comunque l'altro "
                 "sara' piu' in un concetto l'ho fatto o non l'ho fatto smarcato "
                 "o non smarcato ci stavo gia' ragionando", "start": 14.0, "end": 40.0},
    ]
    kept = clean_segments(segments)
    assert kept[-1]["text"] == "ci stavo gia' ragionando"


def test_collapses_a_run_repeated_inside_one_segment():
    """The same overlap, when the engine glued both windows into one segment."""
    segments = [{"text": "gli daranno un profilo di rischio quindi la matrice "
                         "gli daranno un profilo di rischio quindi la matrice "
                         "abbinamento di default", "start": 0.0, "end": 20.0}]
    kept = clean_segments(segments)
    assert kept[0]["text"] == ("gli daranno un profilo di rischio quindi la matrice "
                               "abbinamento di default")


def test_a_short_phrase_said_twice_is_the_record_not_an_artefact():
    """Six words echoed by the next speaker stay: that is the conversation."""
    segments = [
        {"text": "questo era gia' cosi', ogni asset ha i suoi impatti",
         "start": 0.0, "end": 5.0},
        {"text": "ogni asset ha i suoi impatti, sono uguali? cioe' quello che "
                 "tu hai preparato", "start": 5.0, "end": 11.0},
    ]
    kept = clean_segments(segments)
    assert kept[1]["text"].startswith("ogni asset ha i suoi impatti")


def test_unrelated_neighbours_are_left_alone():
    """Two passages of the same language always share small words."""
    segments = [
        {"text": "ok pero' questa gestione la facciamo dopo, non ci serve adesso, "
                 "dobbiamo solo creare le tabelle", "start": 0.0, "end": 7.0},
        {"text": "ma no, neanche, non importa creare quelle tabelle ora perche' noi "
                 "andiamo direttamente da quel punto", "start": 7.0, "end": 14.0},
    ]
    kept = clean_segments(segments)
    assert [s["text"] for s in kept] == [s["text"] for s in segments]


def test_a_hallucination_glued_to_a_real_segment_is_cut_off_it():
    """Not the whole segment, so dropping the segment would lose the speech."""
    segments = [{"text": "Grazie a tutti. dobbiamo tirar fuori qualcosa. Grazie",
                 "start": 0.0, "end": 8.0}]
    assert clean_segments(segments)[0]["text"] == "dobbiamo tirar fuori qualcosa."


def test_keep_fillers_keeps_a_hallucination_at_the_edge_too():
    segments = [{"text": "Grazie a tutti. dobbiamo tirar fuori qualcosa",
                 "start": 0.0, "end": 8.0}]
    kept = clean_segments(segments, drop_fillers=False)
    assert kept[0]["text"].startswith("Grazie a tutti")


def test_the_doubling_goes_even_when_fillers_are_kept():
    """Verbatim means faithful to the speech, not to the engine's stitching."""
    segments = [
        {"text": "solo questo quindi campo e tabellini quindi la configurazione",
         "start": 0.0, "end": 6.0},
        {"text": "solo questo quindi campo e tabellini quindi la configurazione "
                 "si risolve tutto", "start": 6.0, "end": 12.0},
    ]
    kept = clean_segments(segments, drop_fillers=False)
    assert kept[1]["text"] == "si risolve tutto"


def test_word_timings_are_trimmed_with_the_text():
    """Text and timings must not drift apart, or subtitles are cut on words
    that are no longer there."""
    def timed(text, start, step=0.4):
        return [{"word": word, "start": start + index * step,
                 "end": start + (index + 1) * step}
                for index, word in enumerate(text.split())]

    first = "solo questo quindi campo e tabellini quindi la configurazione"
    second = "in solo questo campo e tabellini quindi la configurazione si risolve tutto"
    segments = [
        {"text": first, "start": 0.0, "end": 4.0, "words": timed(first, 0.0)},
        {"text": second, "start": 4.0, "end": 10.0, "words": timed(second, 4.0)},
    ]
    kept = clean_segments(segments)
    assert kept[1]["text"] == "si risolve tutto"
    assert [word["word"] for word in kept[1]["words"]] == ["si", "risolve", "tutto"]
    # The segment now starts at its first surviving word, not where the
    # doubling did.
    assert kept[1]["start"] == kept[1]["words"][0]["start"] > 4.0


def test_words_become_segments_at_a_pause_and_at_a_full_stop():
    """What the OpenVINO backend needs: it reports words and no segments."""
    words = [{"word": "questo", "start": 0.0, "end": 0.4},
             {"word": "e'", "start": 0.4, "end": 0.8},
             {"word": "un", "start": 0.8, "end": 1.2},
             {"word": "test.", "start": 1.2, "end": 1.6},
             {"word": "poi", "start": 5.0, "end": 5.4},
             {"word": "dopo", "start": 5.4, "end": 5.8}]
    built = segments_from_words(words)
    assert [segment["text"] for segment in built] == ["questo e' un test.", "poi dopo"]
    assert built[1]["start"] == 5.0
    assert [word["word"] for word in built[0]["words"]] == ["questo", "e'", "un", "test."]
