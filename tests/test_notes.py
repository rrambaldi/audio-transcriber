"""Notes: the atoms a reading pass produces, read back out of what it wrote.

Text in, dataclasses out — no model, no ffmpeg, no Qt. What is checked is the
contract the grouping will be given: a kind, a sentence, and a minute.
"""
import pytest

from audio_transcriber.summarizers import notes, prompting

ANSWER = """## Requisiti
- Serve poter monitorare gli utenti a cui e' stata inviata la mail. [0:27]
- Dopo l'avvio della campagna occorre sapere chi ha fatto il login. [0:35]

## Fatti
- Una prova ha richiesto 22 minuti con la vecchia interfaccia. [14:11]
"""


def read(answer, **options):
    found, _unknown = notes.read(answer, **options)
    return found


# --- the catalogue ---------------------------------------------------------

def test_every_kind_has_a_heading_and_a_line_in_both_languages():
    """The headings are the words on a page, so they follow the language
    spoken; the lines are what the model is told belongs under them."""
    for language in ("it", "en"):
        for kind in notes.TYPES:
            assert notes.HEADINGS[language][kind]
            assert notes.INSTRUCTIONS[language][kind]


def test_requirement_is_in_the_catalogue():
    """It was the one kind missing, and the recordings this is built for are
    mostly made of it: somebody saying what a thing must do is not a decision,
    nor a proposal, nor a fact."""
    assert "requirement" in notes.TYPES


def test_what_is_not_a_kind_of_note_is_not_in_the_catalogue():
    """A topic is a section, and sections come out of grouping the notes. A
    date and a number are attributes, found by looking rather than asked of a
    model that would invent them."""
    for name in ("topic", "date", "number", "keywords", "abstract"):
        assert name not in notes.TYPES


def test_a_heading_is_read_back_in_either_language():
    """Told to write "## Requisiti", a model writes "## Requirements" often
    enough that losing the kind to it would be a poor trade."""
    assert notes.type_of("Requisiti", "it") == "requirement"
    assert notes.type_of("Requirements", "it") == "requirement"
    assert notes.type_of("## Questioni aperte", "it") == "open_question"
    assert notes.type_of("Qualcos'altro", "it") is None


def test_a_heading_in_the_wrong_romance_language_is_still_read_back():
    """What a real run came back with. Asked for Italian headings, a small
    model answers in the nearest language it knows better, and every note
    under "Decisões" was being demoted to a fact."""
    for written, kind in (("Requisitos", "requirement"), ("Fatos", "fact"),
                          ("Decisões", "decision"), ("Propostas", "proposal"),
                          ("Ações", "action"), ("Problemas", "problem"),
                          ("Questões Abertas", "open_question"),
                          ("Opiniões", "opinion")):
        assert notes.type_of(written, "it") == kind


def test_a_heading_that_stops_half_way_is_still_that_heading():
    """"Questioni apert" - Italian with the end missing, which no catalogue
    of words would ever hold."""
    assert notes.type_of("Questioni apert", "it") == "open_question"
    assert notes.type_of("Opinões", "it") == "opinion"


def test_a_word_that_is_no_heading_matches_nothing():
    """The other half of being tolerant: a page that says "Riassunto" has not
    named a kind of note, and guessing one would file its bullets under a
    heading nobody wrote."""
    for written in ("Riassunto", "Sommario", "Note", "Altro",
                    "Punti chiave", "Partecipanti"):
        assert notes.type_of(written, "it") is None


def test_two_kinds_equally_close_is_no_match():
    """Near neither of them in particular."""
    assert notes.type_of("xxxxxx", "it") is None


# --- reading one pass ------------------------------------------------------

def test_a_pass_is_read_into_one_note_per_bullet():
    found = read(ANSWER, language="it", chunk_idx=2)
    assert [note.type for note in found] == ["requirement", "requirement", "fact"]
    assert [note.ts_start for note in found] == [27, 35, 851]
    assert found[0].text.startswith("Serve poter monitorare")
    assert all(note.chunk_idx == 2 for note in found)
    assert all(note.origin == "model" for note in found)


def test_the_minute_comes_off_the_text_wherever_it_was_put():
    """At the end as often as at the front, and either way it is not part of
    what the note says."""
    front = read("## Fatti\n- `[1:15]` Il documentale va su S3.\n", language="it")
    back = read("## Fatti\n- Il documentale va su S3. [1:15]\n", language="it")
    assert front[0].ts_start == back[0].ts_start == 75
    assert front[0].text == back[0].text == "Il documentale va su S3."


def test_who_said_it_comes_off_the_text_too():
    found = read("## Azioni\n- Prepara la tabella. [2:00] (SPEAKER_01)\n",
                 language="it")
    assert found[0].speaker == "SPEAKER_01"
    assert found[0].text == "Prepara la tabella."


def test_a_heading_nobody_recognises_keeps_its_notes_as_facts():
    """Throwing them away would be the same silence this package spent a week
    taking out. Fact is the kind that claims least."""
    found, unknown = notes.read(
        "## Avanzamenti\n- Il lavoro sugli attributi e' chiuso. [3:00]\n",
        "it")
    assert [note.type for note in found] == ["fact"]
    assert unknown == ["Avanzamenti"]


def test_a_kind_that_never_appears_is_not_an_error():
    found = read(ANSWER, language="it")
    assert not [note for note in found if note.type == "decision"]


def test_a_bullet_with_no_minute_inherits_the_one_above_it():
    found = read("## Fatti\n- Prima cosa. [5:00]\n- Seconda cosa.\n",
                 language="it")
    assert [note.ts_start for note in found] == [300, 300]


def test_the_first_bullet_with_no_minute_falls_back_to_the_chunk():
    found = read("## Fatti\n- Una cosa senza minuto.\n", language="it",
                 span=(420.0, 800.0))
    assert found[0].ts_start == 420.0


def test_prose_with_no_bullets_produces_no_notes():
    assert read("Questa registrazione parla di varie cose.", language="it") == []


def test_a_note_keeps_its_name_across_runs():
    """Two reports of the same recording have to be comparable note by note."""
    first = read(ANSWER, language="it", chunk_idx=1)
    again = read(ANSWER, language="it", chunk_idx=1)
    assert [note.id for note in first] == [note.id for note in again]
    assert len({note.id for note in first}) == len(first)


def test_how_many_notes_say_when_they_happened():
    found = read(ANSWER, language="it")
    assert notes.placed(found) == 3


# --- the bridge to the rest of the pipeline --------------------------------

def test_the_notes_go_back_out_as_the_flat_list_the_rest_expects():
    found = read(ANSWER, language="it")
    written = notes.as_bullets(found, "it")
    assert written.splitlines()[0].startswith("- `[0:27]`")
    # And it reads back into the same notes, which is what makes the bridge
    # safe to walk in both directions until it is torn down.
    assert [note.text for note in read(written, language="it")] == [
        note.text for note in found]


# --- the prompt ------------------------------------------------------------

def test_the_reading_prompt_carries_a_worked_example():
    """Told to put the minute on every row, the first reading pass of every
    measured run put it on none. A small model copies the shape of an example
    far more reliably than it obeys a sentence describing one."""
    prompt = prompting.map_prompt([], "it", 1, 2)
    assert "## Requisiti" in prompt
    assert "[0:27]" in prompt
    assert "[14:11]" in prompt


def test_the_prompt_asks_for_a_speaker_only_when_there_is_one():
    """The transcripts this was built on carry no speaker labels, and an
    example that shows one teaches a model to invent them."""
    from audio_transcriber.summary import Sentence

    without = prompting.map_prompt([Sentence("Ciao.", 0.0)], "it", 1, 1)
    with_them = prompting.map_prompt(
        [Sentence("Ciao.", 0.0, speaker="SPEAKER_01")], "it", 1, 1)
    assert "parentesi tonde" not in without
    assert "parentesi tonde" in with_them


def test_the_scaffold_knows_the_headings_and_the_example():
    """Neither is in a template — one is generated, the other is a model
    answer — and both are exactly what a model that understood nothing hands
    back."""
    lines = prompting.scaffold("it")
    assert any("Requisiti" in line for line in lines)
    assert any("pasti buttati sono scesi" in line for line in lines)


EXAMPLE_WRITTEN_BACK = """## Requisiti
- I genitori chiedono il pane integrale almeno due giorni alla settimana. [3:27]
## Fatti
- A ottobre i pasti buttati erano 140, a novembre 62. [3:40]
"""

COPIED_LINE = "I genitori chiedono il pane integrale almeno due giorni alla settimana."


def read_by(answer, tmp_path, said="Il server arriva a marzo."):
    """One reading pass over a chunk that says ``said``, by a model that
    answers ``answer``."""
    from audio_transcriber.summarizers import plan, reading
    from audio_transcriber.summarizers import trace as tracing
    from audio_transcriber.summary import Sentence

    class Pipeline:
        def ask(self, system, prompt, max_new_tokens=0, think=False):
            return answer

    found = tracing.Trace()
    chosen = plan.resolve_plan(plan.LLAMACPP, ram=32.0, total=64.0, cores=4)
    passed = reading._map(Pipeline(), "sys", [[Sentence(said, 200.0)]],
                          "it", chosen, lambda *a: None, (0, 100),
                          str(tmp_path), trace=found)
    return found, passed[0][0]


def test_the_worked_example_written_back_is_not_a_note_of_the_chunk(tmp_path):
    """Over five meetings the example's notes reached every page, as facts of
    meetings that never mentioned them, under the chunk's own minute."""
    found, _ = read_by(EXAMPLE_WRITTEN_BACK
                       + "- Il fornitore consegna il nuovo server a marzo. [3:20]\n",
                       tmp_path)
    assert [note.text for note in found.notes] == [
        "Il fornitore consegna il nuovo server a marzo."]
    assert found.counts()["notes_copied"] == 2


def test_a_pass_that_wrote_nothing_but_the_example_hands_nothing_up(tmp_path):
    """Not the answer as it came, which is what goes up when no note could be
    read out of it: here notes were read, and they were the example."""
    found, handed_up = read_by(EXAMPLE_WRITTEN_BACK, tmp_path)
    assert found.notes == []
    assert handed_up == ""
    # And the console tells it from a pass that wrote nothing, read from the
    # cache as much as asked for.
    assert "copied=2" in found.chunks[0].line()
    again, _ = read_by(EXAMPLE_WRITTEN_BACK, tmp_path)
    assert "cache-hit" in again.chunks[0].line()
    assert "copied=2" in again.chunks[0].line()


def test_an_answer_with_no_notes_goes_up_without_the_example(tmp_path):
    """Without bullets nothing is read out of an answer and it goes up as it
    came, to be merged with the others; the example's lines must not."""
    found, handed_up = read_by(
        "Il fornitore consegna il nuovo server a marzo.\n"
        + COPIED_LINE + "\n"
        "Il collaudo e' fissato per aprile.\n", tmp_path)
    assert handed_up == ("Il fornitore consegna il nuovo server a marzo.\n"
                         "Il collaudo e' fissato per aprile.")
    assert found.counts()["notes_copied"] == 1


def test_what_was_said_stands_in_for_an_echo_whatever_its_words(tmp_path):
    """A model that hands back the question is replaced by the chunk's own
    sentences, and those were said: none of them is the example."""
    found, handed_up = read_by("", tmp_path, said=COPIED_LINE)
    assert COPIED_LINE in handed_up
    assert found.counts()["notes_copied"] == 0


def test_a_pass_that_filed_an_answer_tidies_the_cache_up(tmp_path):
    """Whatever the answer held: deciding on the notes of the last chunk
    skipped the tidying whenever that chunk had none."""
    import os
    import time

    from audio_transcriber.summarizers import partials

    stale = partials._path("ff" + "0" * 62, str(tmp_path))
    os.makedirs(os.path.dirname(stale), exist_ok=True)
    with open(stale, "w", encoding="utf-8") as handle:
        handle.write("an answer from last month")
    old = time.time() - (partials.KEEP_DAYS + 1) * 86400
    os.utime(stale, (old, old))

    read_by("Nessun appunto: in questa parte non si dice niente di utile.",
            tmp_path)
    assert not os.path.exists(stale)


def test_a_copy_is_told_by_its_content_words_in_either_language():
    # Reworded: a word added, an elision typeset with a curly apostrophe, a
    # line of the extract rather than of the notes.
    assert prompting.copies_the_example(
        "La cuoca deve sapere ogni mattina, appena arriva, quali bambini sono "
        "allergici al latte.", "it")
    assert prompting.copies_the_example(
        "Nel conto dell’ottobre i pasti buttati erano centoquaranta.", "it")
    assert prompting.copies_the_example(
        "Dicevo ho rifatto il conto dei pasti buttati: a ottobre erano "
        "centoquaranta.", "it")
    assert prompting.copies_the_example(
        "Meals thrown away fell from 140 to 62.", "en")
    # The copies that got through a measured round: an aside of the model's
    # own, another ending, another form of the same verb.
    assert prompting.copies_the_example(
        "I pasti buttati sono scesi da 140 a ottobre a 62 a novembre (nota: "
        "questo viene dall'estratto precedente, non da questa parte).", "it")
    assert prompting.copies_the_example(
        "Le paste buttate sono scese da 140 a ottobre a 62 a novembre.", "it")
    assert prompting.copies_the_example(
        "Il numero di pasti buttati è sceso da 140 a ottobre a 62 a novembre.",
        "it")
    assert prompting.copies_the_example(
        "Rifare il conto dei pasti buttati.", "it")
    assert not prompting.copies_the_example(
        "La cuoca ha chiesto un forno nuovo per la mensa di via Roma.", "it")
    # Real notes, nearly all words of the example once "i", "sono", "da",
    # "from", "to" and "in" are counted.
    assert not prompting.copies_the_example(
        "I costi sono scesi da 140 a 62 a novembre.", "it")
    assert not prompting.copies_the_example(
        "Costs fell from 140 to 62 in November.", "en")
    # Too short to be judged, though every word of it is the example's.
    assert not prompting.copies_the_example("Due giorni alla settimana.", "it")


def test_two_sets_of_kinds_do_not_share_a_scaffold():
    """Memoised on the language alone, two runs in one process with different
    kinds would filter each other's lines."""
    # On a heading the worked example does not itself contain: that one is
    # fixed text and is in the scaffold whatever is asked for.
    few = prompting.scaffold("it", ("decision",))
    every = prompting.scaffold("it")
    assert any("Questioni aperte" in line for line in every)
    assert not any("Questioni aperte" in line for line in few)


def test_the_overhead_of_a_reading_prompt_is_measured_not_guessed():
    """A chunk sized against the old guess of four hundred overflows the
    window by the difference, and what falls off is the end of the
    transcript."""
    assert prompting.map_overhead("it") > 500
    assert prompting.map_overhead("it") == pytest.approx(
        prompting.estimate_tokens(prompting.map_prompt([], "it", 1, 1), "it"))
