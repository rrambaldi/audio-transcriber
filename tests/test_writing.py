"""Writing the document: one question per section, and none that sees it all.

The model is a function here, so every one of these runs on a machine with no
accelerator. What is checked is the shape of the questions and the shape of
what comes back — which is the whole of what this stage is, the rest being
whichever model happens to be loaded.
"""
import pytest

from audio_transcriber import summary as summarising
from audio_transcriber.summarizers import grouping, prompting, writing
from audio_transcriber.summarizers import notes as note_kinds


def note(text, kind="fact", start=0.0):
    return note_kinds.Note(id=note_kinds.note_id(0, start, text), type=kind,
                           text=text, ts_start=start)


def cluster(texts, kind=None, keywords=()):
    return grouping.Cluster(
        notes=[note(text, start=at * 60.0) for at, text in enumerate(texts)],
        kind=kind, keywords=list(keywords))


class Asked:
    """A model that writes down what it was asked and answers to order."""

    def __init__(self, answer="Una risposta qualunque."):
        self.prompts = []
        self.answer = answer

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.answer(prompt) if callable(self.answer) else self.answer


DASHBOARD = ["La dashboard mostra a chi e' partita la mail di invito.",
             "La dashboard dice chi ha fatto il primo accesso.",
             "Dalla dashboard parte il sollecito a chi non e' entrato."]
DOCUMENTALE = ["Il documentale conserva i report firmati.",
               "Il documentale si appoggia a uno storage S3."]


# --- one section, and only its own notes -----------------------------------

def test_a_section_is_written_from_its_own_notes_and_no_others():
    """The difference between this and the fold it replaces: whatever the
    model does with them, it cannot lose a part of the recording it was never
    shown."""
    asked = Asked("Un paragrafo.\n\n- Un dettaglio.")
    writing.section(cluster(DASHBOARD), asked, "it")
    written = asked.prompts[0]
    assert "dashboard" in written
    assert "documentale" not in written


def test_a_section_that_comes_back_empty_keeps_its_notes():
    """An empty section is a piece of the recording gone. The notes are worse
    prose and better than nothing, and there is no third option that does not
    lie."""
    body = writing.section(cluster(DASHBOARD), Asked(""), "it")
    assert "primo accesso" in body


def test_a_section_too_big_to_write_is_split_and_not_thinned():
    """A document with one section more is a correct document; a section that
    quietly lost a third of its notes is the failure all of this exists to
    stop."""
    big = cluster([f"La dashboard fa la cosa numero {n} del modulo."
                   for n in range(60)])
    pieces = grouping.split_oversize([big], writing.NOTES_PER_SECTION, "it")
    assert len(pieces) > 1
    assert all(len(piece.notes) <= writing.NOTES_PER_SECTION for piece in pieces)
    assert sum(len(piece.notes) for piece in pieces) == 60      # nothing left


def test_a_section_small_enough_is_left_alone():
    small = cluster(DASHBOARD)
    assert grouping.split_oversize([small], writing.NOTES_PER_SECTION,
                                   "it") == [small]


# --- naming one ------------------------------------------------------------

def test_a_title_comes_back_as_a_title_however_it_was_dressed():
    """Models answer a request for a title with one in quotation marks, one
    with a full stop, and one with a number in front of it."""
    for dressed in ('"Dashboard di monitoraggio"',
                    "## Dashboard di monitoraggio",
                    "1. Dashboard di monitoraggio.",
                    "  Dashboard di monitoraggio  "):
        assert writing.label(cluster(DASHBOARD), Asked(dressed), "it") == (
            "Dashboard di monitoraggio")


def test_a_title_run_together_like_an_identifier_is_given_its_spaces():
    """Spark-X2.5-4B names sections the way a programmer names a class."""
    for written, title in (("MonitoraggioUtentiCampagna",
                            "Monitoraggio utenti campagna"),
                           ("ArgomentoInterim", "Argomento interim"),
                           ("GitHub", "GitHub"),
                           ("Costo Storage Aruba", "Costo Storage Aruba")):
        assert writing.label(cluster(DASHBOARD), Asked(written), "it") == title


def test_a_minute_nobody_gave_the_model_does_not_reach_the_page():
    """The notes of a section carry no minutes, so "[12:34]" in its answer is
    the example in the system prompt, copied: Spark-X2.5-4B wrote it eleven
    times on one page, and Granite 4.0 H-Tiny once."""
    answer = ("[12:34]\n\nLa dashboard mostra gli inviti. [12:34]\n\n"
              "- Un punto [3:05].")
    written = writing.section(cluster(DASHBOARD), Asked(answer), "it")
    assert "[" not in written
    assert written.startswith("La dashboard mostra gli inviti.")
    assert "- Un punto." in written
    opening = writing.abstract(["Dashboard"], Asked("[12:34] Si parla di tutto."),
                               "it")
    assert opening == "Si parla di tutto."


def test_a_paragraph_where_a_title_was_asked_for_is_not_a_title():
    essay = ("Il titolo di questa sezione dovrebbe descrivere l'argomento "
             "trattato, che riguarda principalmente la dashboard e i suoi usi.")
    named = writing.label(cluster(DASHBOARD, keywords=["dashboard", "mail"]),
                          Asked(essay), "it")
    assert named == "Dashboard, mail"


def test_a_routed_section_is_named_by_the_catalogue_and_asks_nobody():
    asked = Asked("non mi deve chiamare nessuno")
    named = writing.label(cluster(DASHBOARD, kind="decision"), asked, "it")
    assert named == "Decisioni"
    assert asked.prompts == []


def test_the_leftovers_say_they_are_leftovers():
    assert writing.label(cluster(DASHBOARD, kind="other"), Asked(), "it") == (
        "Altri punti")


# --- the opening paragraph -------------------------------------------------

def test_the_opening_paragraph_never_sees_the_bullets():
    """The page this replaces had an opening identical, word for word, to the
    list of key points under it, because the one request that wrote both had
    both in front of it."""
    asked = Asked("Si e' parlato di due cose.")
    writing.abstract(["Dashboard di monitoraggio", "Evoluzione del documentale"],
                     asked, "it")
    written = asked.prompts[0]
    assert "Dashboard di monitoraggio" in written
    assert "primo accesso" not in written
    assert "storage S3" not in written


def test_no_sections_no_opening_paragraph():
    asked = Asked()
    assert writing.abstract([], asked, "it") == ""
    assert asked.prompts == []


# --- the title of the document ---------------------------------------------

def test_the_title_is_made_of_the_subjects_and_never_of_the_speech():
    """The bug it is written against: a summary came back called "Ne va a
    Napoli Tutta una cosa", which is a fragment of somebody talking."""
    named = writing.derive_title(
        ["Dashboard di monitoraggio", "Evoluzione del documentale",
         "Stato dello sviluppo"], language="it")
    assert named.startswith("Dashboard di monitoraggio")
    assert "altro" in named


def test_a_recording_whose_sections_have_no_names_is_still_titled():
    material = summarising.Material(title="", sentences=(), language="it")
    assert writing.derive_title([], material, "it") == (
        "Riassunto della registrazione")
    assert writing.derive_title(["Altri punti"], material, "it") == (
        "Riassunto della registrazione")


# --- the whole stage -------------------------------------------------------

def test_every_question_is_about_one_section():
    """The count of questions follows the number of sections, not the length
    of the recording, and not one of them carries the whole of it."""
    body = [cluster(DASHBOARD), cluster(DOCUMENTALE)]
    asked = Asked(lambda prompt: "Titolo breve" if "titolo" in prompt.lower()
                  else "Un paragrafo.\n\n- Un dettaglio.")
    writing.write(body, [], asked, language="it")
    assert len(asked.prompts) == len(body) * 2 + 1
    for prompt in asked.prompts:
        assert not ("dashboard" in prompt and "documentale" in prompt)


def test_the_document_carries_its_sections_in_order_with_the_tail():
    body = [cluster(DASHBOARD), cluster(DOCUMENTALE)]
    tail = [cluster(["Il documentale va su Aruba."], kind="decision"),
            cluster(["Chiedere ad Aruba il supporto S3."], kind="action")]
    document = writing.write(body, tail, Asked("Titolo"), language="it")
    assert isinstance(document, summarising.Document)
    assert len(document.sections) == 2
    assert [note.text for note in document.decisions] == [
        "Il documentale va su Aruba."]
    assert [note.text for note in document.actions] == [
        "Chiedere ad Aruba il supporto S3."]


def test_the_document_counts_as_a_page_for_whatever_measures_one():
    """Coverage does not have to learn about the new shape: the points of a
    document are its notes."""
    body = [cluster(DASHBOARD)]
    document = writing.write(body, [], Asked("Titolo"), language="it")
    assert len(document.points) == len(DASHBOARD)
    assert document.points[0].start == 0.0


def test_a_document_with_decisions_can_still_be_measured():
    """The crash this is written against: a run on a real recording read the
    transcript, grouped it, wrote every section, and then fell over counting
    how much of the recording it had covered - because the decisions at the
    foot of the page are notes, and a note says when it happened in a field
    of its own."""
    material = summarising.Material(title="riunione", sentences=(),
                                    language="it", duration=1320.0)
    document = writing.write(
        [cluster(DASHBOARD)],
        [cluster(["Il documentale va su Aruba."], kind="decision"),
         cluster(["Chiedere ad Aruba il supporto S3."], kind="action")],
        Asked("Titolo"), material, "it")
    measured = summarising.report_metrics(document, material, {})
    assert measured["coverage"] is not None
    starts = [point.start for point in summarising.points_of(document)]
    assert all(start is not None for start in starts)


def test_progress_is_reported_as_the_sections_are_written():
    seen = []
    writing.write([cluster(DASHBOARD), cluster(DOCUMENTALE)], [],
                  Asked("Titolo"), language="it",
                  progress=lambda done, total: seen.append((done, total)))
    assert seen
    assert seen[-1][0] == seen[-1][1]


# --- the page it makes ------------------------------------------------------

def test_the_page_has_a_heading_per_section_and_no_minutes_in_it():
    material = summarising.Material(title="riunione", sentences=(),
                                    language="it", duration=1320.0)
    document = summarising.Document(
        title="Dashboard e documentale",
        abstract="Si e' parlato di due cose.",
        sections=(("Dashboard di monitoraggio", "Un paragrafo.\n\n- Un punto."),
                  ("Evoluzione del documentale", "Un altro paragrafo.")),
        decisions=(note("Il documentale va su Aruba.", "decision", 450.0),),
        actions=(note("Chiedere il supporto S3.", "action", 470.0),))
    page = summarising.render(material, document, "un motore")

    assert "# Riassunto: Dashboard e documentale" in page
    assert "## 1. Dashboard di monitoraggio" in page
    assert "## 2. Evoluzione del documentale" in page
    assert "## Decisioni" in page and "## Azioni" in page
    assert "7:30" not in page and "[" not in page.split("## Decisioni")[1]


def test_the_minutes_come_back_when_they_are_asked_for():
    material = summarising.Material(title="riunione", sentences=(),
                                    language="it", duration=1320.0)
    document = summarising.Document(
        title="Qualcosa", abstract="",
        sections=(("Una sezione", "Un paragrafo."),),
        decisions=(note("Il documentale va su Aruba.", "decision", 450.0),))
    page = summarising.render(material, document, "un motore", timestamps=True)
    assert "[7:30]" in page


def test_a_list_with_nothing_in_it_is_not_a_heading():
    material = summarising.Material(title="riunione", sentences=(),
                                    language="it")
    document = summarising.Document(
        title="Qualcosa", abstract="Un paragrafo.",
        sections=(("Una sezione", "Del testo."),))
    page = summarising.render(material, document, "un motore")
    assert "## Decisioni" not in page
    assert "## Azioni" not in page


@pytest.mark.parametrize("language", ["it", "en"])
def test_both_languages_can_write_every_question(language):
    from audio_transcriber.summarizers import prompting

    for key in ("label", "section", "abstract_from"):
        assert prompting.prompts_for(language)[key]


def test_a_document_with_no_model_is_titled_after_the_recording():
    """Where nothing named the sections, they are named after the words their
    notes share, and three filler words that happened to repeat make a worse
    title than the recording's own name."""
    material = summarising.Material(title="riunione del 4", sentences=(),
                                    language="it")
    body = [cluster(DASHBOARD, keywords=["viene", "visto", "mandato"])]
    document = writing.write(body, [], Asked(""), material, "it")
    assert document.title == "riunione del 4"
    assert document.sections[0][0] == "Viene, visto, mandato"


def test_a_document_a_model_named_is_titled_after_its_sections():
    material = summarising.Material(title="riunione", sentences=(),
                                    language="it")
    body = [cluster(DASHBOARD), cluster(DOCUMENTALE)]
    asked = Asked(lambda prompt: ("Dashboard di monitoraggio"
                                  if "dashboard" in prompt else
                                  "Evoluzione del documentale")
                  if "titolo" in prompt else "Del testo.")
    document = writing.write(body, [], asked, material, "it")
    assert document.title.startswith("Dashboard di monitoraggio")


def test_the_passes_can_be_reported_on_a_document_with_decisions():
    """The same crash as above, one function earlier and in the other copy of
    it: the run that measures what the passes did counts minutes too, and it
    was reading them off the notes at the foot of the page."""
    from audio_transcriber.summarizers import reading, trace as tracing

    material = summarising.Material(title="riunione", sentences=(),
                                    language="it", duration=1320.0)
    document = writing.write(
        [cluster(DASHBOARD)],
        [cluster(["Il documentale va su Aruba."], kind="decision")],
        Asked("Titolo"), material, "it")
    found = tracing.Trace()
    found.chunk(index=1, total=1, in_tokens=3180, out_tokens=412, notes=4)
    counts = reading.report_trace(found, document, material)
    assert counts["chunks"] == 1


# --- how much of it is written down ----------------------------------------

def test_the_three_lengths_are_the_same_three_everywhere():
    """One list of names, kept in three places because each holds a different
    kind of thing: the extractive engine's ratios, the numbers a written page
    moves, and the wording it is asked with. A name in one and not the others
    is a length that silently does nothing."""
    assert set(writing.PAGES) == set(summarising.LENGTHS)
    for language in ("it", "en"):
        assert set(prompting.PAGE_DETAIL[language]) == set(summarising.LENGTHS)


def test_a_short_section_is_asked_for_as_a_paragraph_without_a_list():
    asked = Asked("Un paragrafo.")
    writing.section(cluster(DASHBOARD), asked, "it",
                    prompting.detail_for("it", "short"))
    assert "niente elenchi" in asked.prompts[0]


def test_a_long_section_is_asked_for_a_bullet_per_note():
    asked = Asked("Un paragrafo.\n\n- Un dettaglio.")
    writing.section(cluster(DASHBOARD), asked, "it",
                    prompting.detail_for("it", "long"))
    assert "un punto per ogni appunto" in asked.prompts[0]


def test_the_opening_paragraph_is_asked_for_at_the_asked_length():
    short, long = Asked("In breve."), Asked("Piu' a lungo.")
    writing.abstract(["Dashboard"], short, "it",
                     prompting.detail_for("it", "short"))
    writing.abstract(["Dashboard"], long, "it",
                     prompting.detail_for("it", "long"))
    assert "una o due frasi" in short.prompts[0]
    assert "da quattro a sei frasi" in long.prompts[0]


def test_every_section_of_one_page_is_asked_for_at_the_same_length():
    """The length is resolved once. Two sections of the same page asked for
    at two different lengths is a page that reads as if two people wrote it."""
    asked = Asked("Un paragrafo.")
    writing.write([cluster(DASHBOARD), cluster(DOCUMENTALE)], [], asked,
                  language="it", length="short")
    sections = [prompt for prompt in asked.prompts if "Struttura:" in prompt]
    assert len(sections) == 2
    assert all("niente elenchi" in prompt for prompt in sections)


def test_nothing_says_which_length_and_the_page_is_the_measured_one():
    """Medium is the default and the default is what was measured, so the
    page written when nobody asked has to be the page written for medium."""
    quiet, named = Asked("Un paragrafo."), Asked("Un paragrafo.")
    writing.write([cluster(DASHBOARD)], [], quiet, language="it")
    writing.write([cluster(DASHBOARD)], [], named, language="it",
                  length="medium")
    assert quiet.prompts == named.prompts


# --- a line said twice, and a page read back ---------------------------------

def test_a_bullet_the_page_says_twice_is_kept_once():
    """Two notes that said it two ways, or two sections that each got a
    telling of it: the page keeps the first and says how many went."""
    written = [(cluster(DASHBOARD), "Dashboard",
                "Un paragrafo.\n\n- Ha fatto tutti i test da meta' settimana.\n"
                "- Ha fatto tutti i test da meta' settimana.\n"
                "- La dashboard mostra gli inviti."),
               (cluster(DOCUMENTALE), "Documentale",
                "Un altro paragrafo.\n\n- Ha fatto tutti i test da meta' settimana.\n"
                "- Il documentale va su Aruba.")]
    kept, dropped = writing.without_repeats(written, "it")
    assert dropped == 2
    first, second = kept[0][2], kept[1][2]
    assert first.count("tutti i test") == 1 and "Un paragrafo." in first
    assert "tutti i test" not in second and "Aruba" in second
    assert writing.without_repeats(kept, "it")[1] == 0


def test_a_document_says_nothing_twice_and_keeps_its_foot():
    """The decisions and actions at the foot repeat the body on purpose."""
    document = writing.write(
        [cluster(DASHBOARD), cluster(DOCUMENTALE)],
        [cluster(["Il documentale va su Aruba."], kind="decision")],
        Asked("- Il documentale va su Aruba."), language="it")
    bodies = [text for _title, text in document.sections]
    assert sum(text.count("Aruba") for text in bodies) == 1
    assert document.repeats == 1
    assert [note.text for note in document.decisions] == ["Il documentale va su Aruba."]


def test_a_reviewer_is_believed_only_about_lines_that_are_on_the_page():
    """It lists; it does not rewrite. A finding that quotes a line the page
    does not have is the reviewer's own invention and is dropped."""
    text = ("Si e' parlato della dashboard.\n\n"
            "- La dashboard mostra a chi e' partita la mail.\n"
            "- La dashboard mostra chi e' partita la mail di invito.\n"
            "- Il 20% degli utenti e' stressato.\n"
            "- Sollecito parte da chi non entrato dashboard.")
    answer = ("DOPPIA: La dashboard mostra chi e' partita la mail di invito.\n"
              "- INVENTATA: \"Il 20% degli utenti e' stressato.\" (non c'e')\n"
              "SCORRETTA: Sollecito parte da chi non entrato dashboard\n"
              "INVENTATA: Il budget e' di diecimila euro.\n"
              "INVENTATA: la riga")
    asked = Asked(answer)
    found = writing.review([(cluster(DASHBOARD), "Dashboard", text)], asked, "it")
    assert [kind for *_, kind in found] == ["repeated", "unsupported", "garbled"]
    assert all(line in text for _title, line, _kind in found)
    assert found[0][0] == "Dashboard"
    assert DASHBOARD[0] in asked.prompts[0] and text in asked.prompts[0]
    assert writing.review([(cluster(DASHBOARD), "D", text)], Asked("NESSUNO"), "it") == ()


def test_the_review_is_asked_only_when_wanted_and_lands_at_the_foot():
    material = summarising.Material(title="riunione", sentences=(),
                                    language="it", duration=1320.0)
    body = [cluster(DASHBOARD)]
    plain = writing.write(body, [], Asked("- La dashboard mostra gli inviti."),
                          material, "it")
    assert plain.review == ()

    reviews = Asked("SCORRETTA: La dashboard mostra gli inviti.")
    document = writing.write([cluster(DASHBOARD)], [],
                             Asked("- La dashboard mostra gli inviti."),
                             material, "it", review_ask=reviews)
    assert len(reviews.prompts) == 1
    assert document.review == (
        (document.sections[0][0], "La dashboard mostra gli inviti.", "garbled"),)
    page = summarising.render(material, document, "un motore")
    foot = page.split("## Da ricontrollare")[1]
    assert "_La dashboard mostra gli inviti._" in foot
    assert "non si legge come una frase" in foot and "(1. " in foot


@pytest.mark.parametrize("language", ["it", "en"])
def test_both_languages_can_ask_for_a_review(language):
    prompt = prompting.prompts_for(language)["review"].format(notes="- a", text="b")
    assert "- a" in prompt and "b" in prompt
    assert summarising.HEADINGS[language]["review"]
