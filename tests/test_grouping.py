"""Grouping notes into sections, with no model anywhere.

Arithmetic on the words the notes are made of, so all of it runs on a machine
with no accelerator, no network and nothing downloaded — which is the whole
argument for doing it this way rather than asking a model to merge summaries
of summaries.
"""
import pytest

from audio_transcriber.summarizers import grouping
from audio_transcriber.summarizers import notes as note_kinds


def note(text, kind="fact", start=0.0, index=0):
    return note_kinds.Note(id=note_kinds.note_id(index, start, text), type=kind,
                           text=text, ts_start=start, chunk_idx=index)


#: Three subjects, each written in its own words. Parallel sentences with the
#: subject swapped would make note three of one subject and note three of
#: another nearly the same note, which is the opposite of what a meeting's
#: notes look like and would test the opposite of what these tests are for.
SUBJECTS = {
    "dashboard": [
        "La dashboard deve mostrare a quali utenti e' partita la mail di invito.",
        "Sulla dashboard serve sapere chi ha fatto il primo accesso e chi no.",
        "La dashboard distingue chi ha ignorato l'invito da chi lo ha aperto.",
        "Dalla dashboard parte il sollecito verso gli utenti fermi.",
        "La dashboard mostra il momento dell'ultimo accesso di ogni utente.",
        "Sulla dashboard il filtro per campagna precede quello per utente.",
    ],
    "documentale": [
        "Il documentale conserva i report firmati insieme ai loro metadati.",
        "Nel documentale finiscono anche i piani di remediation approvati.",
        "Il documentale va appoggiato a uno storage compatibile con S3.",
        "Dal documentale si recupera la copia firmata di un report scaricato.",
        "Il documentale tiene lo storico degli export prodotti dal sistema.",
        "Nel documentale un interim resta privato finche' non viene pubblicato.",
    ],
    "fatturazione": [
        "La fatturazione emette una nota di credito quando l'ordine rientra.",
        "In fatturazione l'imponibile va separato dall'imposta sul documento.",
        "La fatturazione chiude il periodo il quinto giorno del mese.",
        "Dalla fatturazione esce un tracciato per il commercialista.",
        "La fatturazione rifiuta un cliente senza codice destinatario.",
        "In fatturazione lo scadenzario segue i termini del contratto.",
    ],
}


def about(subject, how_many, start=0.0, kind="fact"):
    """Notes about one subject, sharing it and sharing nothing else.

    What binds two notes of a real meeting is the thing they are about, not
    the way they are phrased; and notes that differ by a single word are the
    same note, which the grouping is right to say."""
    said = SUBJECTS.get(subject)
    if said is None:
        said = [f"Il {subject} passa la fase {subject}{mark} senza errori."
                for mark in ("alfa", "beta", "gamma", "delta", "epsilon", "zeta")]
    return [note(text, kind, start + step * 10.0)
            for step, text in enumerate(said[:how_many])]


# --- what happens to every note --------------------------------------------

def test_a_note_is_told_what_it_is_about_by_its_own_words():
    found = about("dashboard", 3) + about("fatturazione", 3, start=600)
    grouping.enrich(found, "it")
    assert "dashboard" in found[0].entities
    assert "fatturazione" in found[-1].entities


def test_dates_and_numbers_are_taken_out_of_the_text_not_asked_for():
    """A model asked for them would sometimes supply ones nobody said, and a
    date nobody mentioned is worse than no date."""
    found = [note("Il rilascio e' previsto per venerdi e costa 4 euro al mese."),
             note("La prova ha richiesto 22 minuti sulla vecchia interfaccia.")]
    grouping.enrich(found, "it")
    assert found[0].dates == ["venerdi"]
    assert "4 euro" in " ".join(found[0].numbers)
    assert "22 minuti" in " ".join(found[1].numbers)
    assert found[1].dates == []


def test_the_note_that_arrived_twice_is_dropped_and_the_fuller_one_kept():
    """Chunks overlap on purpose so nothing falls between them; the price is
    that whatever sits on a seam is read twice."""
    found = [note("Serve una dashboard per gli utenti invitati.", start=120.0),
             note("Serve una dashboard per gli utenti invitati e non entrati.",
                  start=125.0),
             note("Il documentale va su uno storage S3.", start=400.0)]
    grouping.enrich(found, "it")
    kept = grouping.dedupe(found, "it")
    assert len(kept) == 2
    assert "non entrati" in kept[0].text          # the fuller telling
    assert kept[0].ts_start == 120.0              # and the earlier minute


def test_two_notes_about_different_things_are_both_kept():
    found = about("dashboard", 2) + about("fatturazione", 2, start=600)
    grouping.enrich(found, "it")
    assert len(grouping.dedupe(found, "it")) == 4


# --- discovering the sections ----------------------------------------------

def test_notes_about_one_thing_end_up_in_one_section():
    found = (about("dashboard", 4)
             + about("fatturazione", 4, start=600)
             + about("documentale", 4, start=1200))
    grouping.enrich(found, "it")
    body, tail = grouping.assign(found, grouping.DISCOVER, "it")
    assert tail == []
    assert len(body) == 3
    for section in body:
        subjects = {word for note in section.notes for word in note.entities}
        assert len(subjects & {"dashboard", "fatturazione", "documentale"}) == 1


def test_the_sections_follow_the_recording_not_the_scores():
    """A document is read as a narrative, and the meeting happened in order."""
    found = (about("documentale", 3, start=1200)
             + about("dashboard", 3, start=60))
    grouping.enrich(found, "it")
    body, _tail = grouping.assign(found, grouping.DISCOVER, "it")
    assert [section.ts_min for section in body] == sorted(
        section.ts_min for section in body)


def test_a_note_that_found_no_company_goes_at_the_end_and_says_so():
    found = about("dashboard", 4) + [note("Il gatto e' salito sul tavolo.",
                                          start=900.0)]
    grouping.enrich(found, "it")
    body, _tail = grouping.assign(found, grouping.DISCOVER, "it")
    assert body[-1].kind == "other"
    assert [n.text for n in body[-1].notes] == ["Il gatto e' salito sul tavolo."]


def test_more_sections_than_a_reader_will_hold_are_grouped_again():
    """Tightened and asked again, rather than cut off at twelve: a section
    dropped is notes dropped."""
    found = []
    for step in range(20):
        found += about(f"modulo{step}", 2, start=step * 60.0)
    grouping.enrich(found, "it")
    body, _tail = grouping.assign(found, grouping.DISCOVER, "it", most=6)
    discovered = [s for s in body if s.kind != "other"]
    assert len(discovered) <= 6
    assert sum(len(s.notes) for s in body) == len(found)     # nothing lost


def test_nothing_in_nothing_out():
    assert grouping.assign([], grouping.HYBRID, "it") == ([], [])


# --- the three ways --------------------------------------------------------

def test_fixed_does_not_measure_any_distance(monkeypatch):
    """Running a decision through a clustering and then mapping the cluster
    back onto a heading called Decisions is a lossy way of arriving where the
    note already was."""
    def refuse(*arguments, **options):
        raise AssertionError("fixed must not compute distances")

    monkeypatch.setattr(grouping, "similarity", refuse)
    found = [note("Il documentale va su S3.", "decision", 100.0),
             note("Paolo prepara la tabella.", "action", 200.0),
             note("Serve una dashboard.", "requirement", 50.0)]
    body, tail = grouping.assign(found, grouping.FIXED, "it")
    assert tail == []
    assert [section.kind for section in body] == ["requirement", "decision",
                                                  "action"]
    assert all(section.origin == "routed" for section in body)


def test_fixed_follows_the_catalogue_order_not_the_recording():
    found = [note("Paolo prepara la tabella.", "action", 10.0),
             note("Serve una dashboard.", "requirement", 900.0)]
    body, _tail = grouping.assign(found, grouping.FIXED, "it")
    assert [section.kind for section in body] == ["requirement", "action"]


def test_hybrid_puts_a_decision_in_its_section_and_in_the_list():
    """The duplication is the one thing a reader of minutes asks for twice:
    what was being discussed, and what has to be done about it."""
    found = about("dashboard", 4) + [
        note("La dashboard viene messa nel nuovo modulo dashboard.", "decision",
             300.0),
        note("Paolo prepara la dashboard di monitoraggio.", "action", 320.0)]
    grouping.enrich(found, "it")
    body, tail = grouping.assign(found, grouping.HYBRID, "it")
    assert [section.kind for section in tail] == ["decision", "action"]
    in_body = {n.id for section in body for n in section.notes}
    for section in tail:
        assert all(n.id in in_body for n in section.notes)


def test_a_way_of_making_sections_nobody_has_heard_of_is_refused():
    with pytest.raises(ValueError):
        grouping.assign([note("Qualcosa.")], "inventata", "it")


# --- naming one without a model --------------------------------------------

def test_a_section_says_what_it_is_about_without_being_asked():
    """The extractive engine has no model to name a section with, and a
    section called "Section 3" is not worth the heading."""
    found = about("dashboard", 4)
    grouping.enrich(found, "it")
    body, _tail = grouping.assign(found, grouping.DISCOVER, "it")
    assert "dashboard" in body[0].keywords


def test_two_notes_about_one_subject_are_not_one_note():
    """The threshold has to sit between "said twice" and "about the same
    thing", and on real notes those are 0.82 and 0.21 apart."""
    found = [note("La dashboard deve mostrare chi ha fatto il primo accesso."),
             note("La dashboard deve mandare un sollecito a chi non e' entrato."),
             note("Il documentale conserva i report firmati con i metadati."),
             note("I report del PTR finiscono nel documentale con la data.")]
    grouping.enrich(found, "it")
    assert len(grouping.dedupe(found, "it")) == 4
