"""Templates: the sections somebody decided they wanted.

Nothing here loads a model. What a template is, is a set of headings and what
goes under each — reading one, refusing a broken one, and the two places that
matter downstream: the question the reading pass is given, and the page the
notes are laid out on.
"""
import pytest

from audio_transcriber.summarizers import grouping, prompting, templates
from audio_transcriber.summarizers import notes as note_kinds

OPERATIVE = """\
# title: Verbale operativo
# language: it
# layout: fixed

Decisioni:
Azioni:
Questioni aperte:
"""

OWN = """\
# title: Privacy e costi
# language: it
# layout: hybrid
# lists: Rischi privacy

Rischi privacy: un trattamento di dati personali che potrebbe non essere lecito
Costi: una cifra, un canone o una stima detta ad alta voce
Tempi: una data o una durata su cui ci si e' impegnati
"""


# --- reading one ------------------------------------------------------------

def test_a_heading_the_program_knows_keeps_its_own_name_and_words():
    """Which is what lets a bundled template be three words a line, and what
    keeps a decision called a decision however somebody asked for it."""
    page = templates.parse(OPERATIVE, "minutes")
    assert page.types == ("decision", "action", "open_question")
    assert page.catalogue.instruction("decision")
    assert page.headings == ("Decisioni", "Azioni", "Questioni aperte")


def test_a_heading_nobody_knows_gets_a_name_and_the_words_it_was_given():
    page = templates.parse(OWN, "privacy")
    assert page.types == ("rischi-privacy", "costi", "tempi")
    assert page.catalogue.instruction("costi").startswith("una cifra")


def test_the_headings_are_what_a_reading_pass_is_asked_for():
    """The one thing a template has to change, or it changes nothing."""
    block = prompting.note_headings("it", templates.parse(OWN).catalogue)
    assert "## Rischi privacy" in block
    assert "## Decisioni" not in block


def test_the_worked_example_is_headed_with_the_template_s_own_sections():
    """An example headed with a word the rules forbid is the one thing in
    that prompt a small model copies more reliably than the rules."""
    prompt = prompting.map_prompt([], "it", 1, 1,
                                  templates.parse(OWN).catalogue)
    assert "## Rischi privacy" in prompt
    assert "## Requisiti" not in prompt


def test_the_layout_decides_how_the_notes_are_laid_out():
    assert templates.parse(OPERATIVE).mode == grouping.FIXED
    assert templates.parse(OWN).mode == grouping.HYBRID
    assert templates.parse(OWN).tail == ("rischi-privacy",)


def test_a_hybrid_template_that_says_nothing_repeats_what_it_has():
    """The page this program shipped before templates existed."""
    page = templates.parse("# layout: hybrid\nDecisioni:\nAzioni:\nFatti:\n")
    assert page.tail == ("decision", "action")
    plain = templates.parse("# layout: hybrid\nFatti:\nOpinioni:\n")
    assert plain.tail == ()


def test_only_a_hybrid_page_has_a_foot():
    page = templates.parse("# layout: fixed\n# lists: Decisioni\n"
                           "Decisioni:\nAzioni:\n")
    assert page.tail == ()


# --- refusing a broken one --------------------------------------------------

def test_a_template_with_one_section_is_refused():
    """Two at least, because the reading prompt's worked example has two
    headings in it and they have to be the template's own."""
    with pytest.raises(templates.TemplateError):
        templates.parse("Decisioni:\n", "thin")


def test_a_template_with_too_many_sections_is_refused():
    many = "\n".join(f"Sezione numero {n}:" for n in range(20))
    with pytest.raises(templates.TemplateError):
        templates.parse(many, "fat")


def test_an_unknown_layout_is_refused_by_name():
    with pytest.raises(templates.TemplateError, match="sideways"):
        templates.parse("# layout: sideways\nDecisioni:\nAzioni:\n", "odd")


def test_a_name_that_is_a_path_is_refused_before_anything_is_opened():
    """It arrives from an HTTP request."""
    with pytest.raises(templates.TemplateError):
        templates.get("../../etc/passwd")


def test_a_template_typed_in_has_a_bound_on_it():
    with pytest.raises(templates.TemplateError):
        templates.resolve({"summary_template_text":
                           "Decisioni:\nAzioni:\n" + "x" * 5000})


# --- the ones that ship -----------------------------------------------------

def test_every_bundled_template_reads():
    found = {item.name for item in templates.available()}
    assert {"meeting-it", "minutes-it", "requirements-it", "interview-it",
            "narrative-it"} <= found
    assert {"meeting-en", "minutes-en", "requirements-en", "interview-en",
            "narrative-en"} <= found


def test_a_bundled_template_is_offered_in_the_language_it_is_written_in():
    """Offering an Italian one for an English recording would put Italian
    headings on an English page."""
    italian = {item.name for item in templates.available(language="it")}
    assert "meeting-it" in italian
    assert "meeting-en" not in italian


def test_the_name_to_type_is_the_same_whoever_is_talking():
    assert templates.get("minutes", language="it").name == "minutes-it"
    assert templates.get("minutes", language="en").name == "minutes-en"


def test_the_bundled_meeting_template_is_the_page_made_without_one():
    """It is the default written down, and if the two ever part company the
    file is a lie about what the program does."""
    page = templates.get("meeting", language="it")
    assert page.types == note_kinds.TYPES
    assert page.mode == grouping.HYBRID
    assert page.tail == grouping.TAIL_TYPES


def test_every_bundled_template_uses_the_headings_of_its_own_language():
    for item in templates.available():
        catalogue = note_kinds.catalogue_for(item.language)
        for kind in item.catalogue.kinds:
            assert kind.heading == catalogue.heading(kind.name), item.name


# --- how a run asks for one -------------------------------------------------

def test_no_template_asked_for_is_no_template():
    """Not the bundled default: a run that asks for nothing is the run this
    program was measured on, and it stays that run rather than becoming a
    file somebody could edit."""
    assert templates.resolve({}) is None
    assert templates.resolve({"summary_template": "auto"}) is None


def test_a_template_typed_in_wins_over_a_named_one():
    page = templates.resolve({"summary_template": "minutes",
                              "summary_template_text": OWN})
    assert page.name == "custom"
    assert page.types == ("rischi-privacy", "costi", "tempi")


def test_an_unknown_name_says_which_ones_there_are():
    with pytest.raises(templates.TemplateError, match="minutes"):
        templates.resolve({"summary_template": "verbale"})


# --- nothing is dropped on the way to the page ------------------------------

def note(text, kind, start=0.0):
    return note_kinds.Note(id=note_kinds.note_id(0, start, text), type=kind,
                           text=text, ts_start=start)


def test_a_fixed_page_keeps_the_notes_its_headings_did_not_claim():
    """A model invents a heading, the note under it is filed under the kind
    that claims least, and that kind is not one of the three this template
    asked for. Dropping it here would be the silence this package exists to
    take out; it goes under "other" instead."""
    found = [note("Si e' deciso di rifare la dashboard.", "decision"),
             note("Marco prepara il preventivo.", "action"),
             note("Il sistema oggi non regge il carico.", "fact", 60.0)]
    page = templates.parse(OPERATIVE)
    body, tail = grouping.assign(found, page.mode, "it", kinds=page.types,
                                 tail_kinds=page.tail)
    assert tail == []
    assert sum(len(section.notes) for section in body) == len(found)
    assert "other" in [section.kind for section in body]
