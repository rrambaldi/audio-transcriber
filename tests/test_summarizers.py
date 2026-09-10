"""The model engines: the prompts, the parsing, and the choices around them.

None of this needs a model. The runtime is one call — a string in, a string
out — and everything on either side of it is here, which is what keeps a
feature that only works on a machine with an accelerator testable on one
without.
"""
import os

import pytest

from audio_transcriber import paths
from audio_transcriber.summarizers import openvino_genai as engine
from audio_transcriber.summarizers import plan, prompting
from audio_transcriber.summary import NotEnoughMemory, Sentence, SummaryError


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "home"))
    monkeypatch.delenv("AUDIO_TRANSCRIBER_LANG", raising=False)


SENTENCES = [
    Sentence("Parliamo del budget.", 0.0, 8.0, "SPEAKER_00"),
    Sentence("Sono quarantaduemila euro.", 8.0, 20.0, "SPEAKER_00"),
    Sentence("Decidiamo entro venerdi.", 75.0, 90.0, "SPEAKER_01"),
]


# --- the transcript the model reads ---------------------------------------

def test_every_line_carries_the_minute_it_was_said_at():
    lines = prompting.transcript_for(SENTENCES).splitlines()
    assert lines[0].startswith("[0:00] SPEAKER_00: ")
    assert lines[2].startswith("[1:15] SPEAKER_01: ")


def test_the_speaker_is_named_only_when_it_changes():
    """In a two-person meeting that is half the labels, and they cost tokens."""
    lines = prompting.transcript_for(SENTENCES).splitlines()
    assert "SPEAKER_00" not in lines[1]
    assert lines[1] == "[0:08] Sono quarantaduemila euro."


def test_a_transcript_without_timestamps_still_renders():
    lines = prompting.transcript_for([Sentence("Solo testo.")]).splitlines()
    assert lines == ["Solo testo."]


# --- cutting it into passes -----------------------------------------------

def test_a_transcript_that_fits_is_one_pass():
    assert len(prompting.chunks(SENTENCES, 6000)) == 1
    assert len(prompting.plan(SENTENCES, 6000)) == 1


def test_a_long_transcript_is_cut_on_sentence_boundaries():
    many = [Sentence(f"Frase numero {n} del verbale.", n * 10.0) for n in range(200)]
    parts = prompting.chunks(many, 200)
    assert len(parts) > 1
    assert sum(len(part) for part in parts) == len(many)
    # No sentence was split, and none was lost or reordered.
    assert [s.text for part in parts for s in part] == [s.text for s in many]


def test_a_sentence_longer_than_the_whole_budget_gets_its_own_pass():
    """Cutting it would hand the model half a thought to summarise."""
    long_one = Sentence("parola " * 500)
    parts = prompting.chunks([long_one, Sentence("Corta.")], 50)
    assert parts[0] == [long_one]


def test_nothing_to_cut_is_no_passes():
    assert prompting.chunks([], 100) == []
    assert prompting.plan([], 100) == []


def test_the_seam_is_repeated_when_an_overlap_is_asked_for():
    """A decision taken across a boundary is otherwise half in each pass."""
    many = [Sentence(f"Frase numero {n} del verbale.", n * 10.0) for n in range(60)]
    plain = prompting.chunks(many, 200)
    lapped = prompting.chunks(many, 200, overlap=0.2)
    assert len(lapped) >= len(plain)
    repeated = set(s.text for s in plain[0]) & set(s.text for s in lapped[1])
    assert repeated, "the second pass never saw the end of the first"


def test_an_overlap_never_repeats_a_whole_pass():
    """A chunk made only of repetitions would not advance the transcript."""
    many = [Sentence(f"Frase numero {n} del verbale.", n * 10.0) for n in range(40)]
    parts = prompting.chunks(many, 120, overlap=0.5)
    assert sum(len(part) for part in parts) < 4 * len(many)
    assert [s.text for s in parts[-1]][-1] == many[-1].text


# --- the reduce tree ------------------------------------------------------

def widest(levels):
    return max(len(group) for level in levels for group in level)


def test_what_fits_in_one_pass_is_still_one_pass():
    assert len(prompting.reduce_tree(range(1))) == 1
    assert len(prompting.reduce_tree(range(prompting.REDUCE_FANIN))) == 1


def test_more_partials_than_one_prompt_holds_are_folded_in_two_levels():
    for count in (7, 40):
        levels = prompting.reduce_tree(range(count))
        assert len(levels) == 2, count
        assert levels[-1] == [list(range(len(levels[-2])))]


def test_the_tree_widens_rather_than_growing_another_level():
    """A meeting does not deserve four levels of summary."""
    levels = prompting.reduce_tree(range(40))
    assert len(levels) == 2
    assert widest(levels) == 7          # wider than the default fan-in of six
    assert all(len(group) <= 7 for level in levels for group in level)


def test_nothing_to_reduce_is_no_passes():
    assert prompting.reduce_tree([]) == []


def test_a_context_too_small_to_widen_grows_a_level_instead():
    """On a model that cannot hold a wider prompt, depth is the lesser harm."""
    levels = prompting.reduce_tree(range(40), fanin=3, max_fanin=3)
    assert len(levels) > 2
    assert widest(levels) == 3


# The plan for the smallest tier, as step 4 will compute it. Written out here
# so this file keeps testing prompting on its own; test_plan.py owns the
# question of where the numbers come from.
XS_CONTEXT, XS_MAP, XS_REDUCE, XS_EVIDENCE, XS_OVERHEAD = 2048, 150, 500, 200, 300


def test_no_prompt_of_the_tree_overflows_the_smallest_tier():
    """The regression this whole tree exists for.

    A star reduce hands one prompt every partial there is, so forty of them
    is a prompt ten times the context of the model that was chosen precisely
    because the machine is small. Every prompt of the tree has to fit, at
    every level — including the ones that fold answers rather than chunks."""
    words = "riga di riassunto del verbale "
    partials = [(words * 68).strip() for _ in range(40)]        # ~500 tokens
    assert 450 <= prompting.estimate_tokens(partials[0]) <= 550

    fanin = prompting.fanin_for(len(partials), XS_CONTEXT,
                                prompting.estimate_tokens(partials[0]),
                                XS_REDUCE, XS_EVIDENCE, XS_OVERHEAD)
    levels = prompting.reduce_tree(partials, fanin=fanin, max_fanin=fanin)
    evidence = "[0:00] " + words * 20

    # Above the first level the model is folding its own answers, and those
    # are capped at the map budget rather than at the size of a chunk.
    answer = (words * int(XS_MAP / prompting.estimate_tokens(words))).strip()
    for depth, level in enumerate(levels):
        for group in level:
            texts = ([partials[index] for index in group] if depth == 0
                     else [answer] * len(group))
            root = depth == len(levels) - 1
            prompt = (prompting.reduce_prompt(texts, "it", evidence=evidence)
                      if root else
                      prompting.reduce_partial_prompt(texts, "it",
                                                      evidence=evidence))
            assert prompting.estimate_tokens(prompt) <= XS_CONTEXT, (depth, root)


def test_the_budget_leaves_room_for_the_answer_and_the_instructions():
    for context in (2048, 4096, 8192, 16384):
        room = prompting.budget_for(context)
        assert room + prompting.REDUCE_ANSWER_TOKENS + 400 <= context
    # A context smaller than the answer it has to hold is not negative room.
    assert prompting.budget_for(256) == 0


def test_the_fan_in_narrows_with_the_context():
    wide = prompting.fanin_for(40, 16384, 500)
    narrow = prompting.fanin_for(40, 2048, 500, 500, 200, 300)
    assert wide == prompting.REDUCE_FANIN
    assert 2 <= narrow < wide


# --- the prompts ----------------------------------------------------------

def test_the_prompt_asks_for_the_headings_the_page_uses():
    prompt = prompting.single_prompt(SENTENCES, "it")
    for heading in ("## In breve", "## Punti chiave", "## Decisioni", "## Azioni"):
        assert heading in prompt
    assert "Parliamo del budget." in prompt


def test_the_prompt_is_written_in_the_language_that_was_spoken():
    assert "## In brief" in prompting.single_prompt(SENTENCES, "en")
    assert "italiano" in prompting.prompts_for("it")["system"]
    assert "English" in prompting.prompts_for("en")["system"]
    # A language with no prompts of its own is answered in English.
    assert prompting.prompts_for("sv") is prompting.PROMPTS["en"]


def test_the_map_prompt_says_which_part_of_how_many_it_is():
    prompt = prompting.map_prompt(SENTENCES, "it", 2, 5)
    assert "parte 2 di 5" in prompt


def test_the_reduce_prompt_carries_every_partial_summary():
    prompt = prompting.reduce_prompt(["primo pezzo", "secondo pezzo"], "it")
    assert "primo pezzo" in prompt and "secondo pezzo" in prompt
    assert "--- 1 ---" in prompt and "--- 2 ---" in prompt


def test_an_intermediate_reduce_does_not_write_the_final_document():
    """Its answer is material for the level above, not a page."""
    middle = prompting.reduce_partial_prompt(["primo", "secondo"], "it")
    for heading in ("## In breve", "## Punti chiave", "## Decisioni"):
        assert heading not in middle
    assert "elenco puntato" in middle
    assert "## In breve" in prompting.reduce_prompt(["primo"], "it")


def test_a_reduce_pass_is_given_the_transcript_to_check_itself_against():
    """From the second level on the model is reading its own writing."""
    plain = prompting.reduce_prompt(["primo"], "it")
    checked = prompting.reduce_prompt(["primo"], "it",
                                      evidence="[0:08] Sono quarantaduemila euro.")
    assert "quarantaduemila" not in plain
    assert "quarantaduemila" in checked
    assert prompting.FENCE_START in checked
    assert "primo" in checked


def test_the_evidence_is_the_transcript_selected_not_summarised():
    many = [Sentence(f"Il budget del progetto vale {n} euro.", n * 10.0)
            for n in range(40)]
    extract = prompting.evidence_for(many, budget=120, language="it")
    lines = extract.splitlines()
    assert 0 < len(lines) < len(many)
    assert all(line in prompting.transcript_for(many) for line in lines)
    assert lines[0].startswith("[")


def test_no_evidence_is_no_block_at_all():
    assert prompting.evidence_for([], 100, "it") == ""
    assert prompting.evidence_for(SENTENCES, 0, "it") == ""


# --- reading the answer back ----------------------------------------------

ANSWER = """## In breve

La riunione ha approvato il budget della certificazione.

## Punti chiave

- `[4:12]` **SPEAKER_01** Le offerte confrontabili sono due.
- [18:30] Il perimetro resta la sede di Bologna.

## Decisioni

- Budget approvato a sessantaseimila euro.

## Azioni

- [1:02:03] **Rossi** Prepara il documento di scopo entro venerdi.
"""


def test_the_answer_becomes_the_same_sections_the_other_engine_produces():
    sections = prompting.parse(ANSWER, "it")
    assert sections.abstract == "La riunione ha approvato il budget della certificazione."
    assert len(sections.points) == 2
    assert len(sections.decisions) == 1
    assert len(sections.actions) == 1


def test_a_bullet_gives_back_its_minute_and_its_speaker():
    points = prompting.parse(ANSWER, "it").points
    assert points[0].start == 4 * 60 + 12
    assert points[0].speaker == "SPEAKER_01"
    assert points[0].text == "Le offerte confrontabili sono due."
    # Without the backticks, and without a speaker.
    assert points[1].start == 18 * 60 + 30
    assert points[1].speaker is None


def test_an_hour_long_position_is_read_back_correctly():
    action = prompting.parse(ANSWER, "it").actions[0]
    assert action.start == 3723
    assert action.speaker == "Rossi"


def test_english_headings_are_accepted_even_when_italian_was_asked_for():
    """Models do this, and losing a section to it would be a poor trade."""
    sections = prompting.parse(
        "## In brief\nTesto.\n\n## Decisions\n- Approvato.\n", "it")
    assert sections.abstract == "Testo."
    assert len(sections.decisions) == 1


def test_a_reasoning_model_does_not_get_its_thinking_onto_the_page():
    sections = prompting.parse(
        "<think>Devo elencare i punti...</think>\n## In breve\nTesto.", "it")
    assert sections.abstract == "Testo."
    assert "think" not in sections.abstract


def test_an_answer_in_the_wrong_shape_is_kept_rather_than_thrown_away():
    sections = prompting.parse("Il budget e' stato approvato.", "it")
    assert sections.abstract == "Il budget e' stato approvato."
    assert not sections.points


def test_a_model_that_echoes_its_input_does_not_produce_a_summary():
    """A 135M model does exactly this, and the page must not accept it."""
    prompt = prompting.single_prompt(SENTENCES, "it")
    echoed = ("Questa e' la trascrizione di una registrazione.\n\n"
              + prompting.FENCE_START
              + "\nBuongiorno a tutti. Parliamo del budget.\n"
              + prompting.FENCE_END)
    assert prompting.parse(echoed, "it", prompt).abstract == ""


def test_a_summary_is_not_mistaken_for_an_echo():
    prompt = prompting.single_prompt(SENTENCES, "it")
    real = "La riunione ha approvato il budget e fissato il perimetro."
    assert prompting.parse(real, "it", prompt).abstract == real


def test_a_real_answer_that_happens_to_quote_the_fence_keeps_its_head():
    answer = ("Il budget e' stato approvato e il perimetro resta Bologna.\n"
              + prompting.FENCE_START + "\nrumore\n")
    assert prompting.parse(answer, "it").abstract.startswith("Il budget")


def test_an_empty_answer_is_empty_sections():
    assert prompting.parse("", "it").abstract == ""
    assert prompting.parse(None, "it").points == ()


def test_numbered_and_starred_bullets_are_bullets_too():
    sections = prompting.parse(
        "## Punti chiave\n1. Primo punto.\n* Secondo punto.\n", "it")
    assert [point.text for point in sections.points] == ["Primo punto.",
                                                         "Secondo punto."]


# --- choosing the device --------------------------------------------------

def devices(monkeypatch, found):
    monkeypatch.setattr(engine, "openvino_devices", lambda: found)


def test_auto_prefers_the_igpu(monkeypatch):
    devices(monkeypatch, ["CPU", "GPU.0", "NPU"])
    assert engine.resolve_device("auto") == "GPU.0"


def test_auto_never_picks_the_npu_on_its_own(monkeypatch):
    """8K of context against fifteen thousand tokens of transcript."""
    devices(monkeypatch, ["CPU", "NPU"])
    assert engine.resolve_device("auto") == "CPU"
    assert engine.resolve_device(None) == "CPU"


def test_the_npu_asked_for_by_name_is_honoured_with_a_warning(monkeypatch, capsys):
    devices(monkeypatch, ["CPU", "NPU"])
    assert engine.resolve_device("NPU") == "NPU"
    assert "8K" in capsys.readouterr().err


def test_a_device_that_is_not_there_falls_back_to_the_cpu(monkeypatch, capsys):
    devices(monkeypatch, ["CPU"])
    assert engine.resolve_device("GPU") == "CPU"
    assert "GPU" in capsys.readouterr().err


def test_with_openvino_unavailable_the_request_is_passed_through(monkeypatch):
    devices(monkeypatch, [])
    assert engine.resolve_device("GPU") == "GPU"
    assert engine.resolve_device("auto") == "CPU"


# --- choosing the model ---------------------------------------------------

def test_the_model_is_whatever_the_plan_worked_out(monkeypatch, roomy):
    """The engine no longer has an opinion; it asks."""
    assert engine.resolve_model("auto") == roomy.model.hf_id


def test_a_model_asked_for_by_name_is_used_as_asked():
    assert engine.resolve_model("Qwen/Qwen3-4B") == "Qwen/Qwen3-4B"
    assert engine.resolve_model("/models/mine-ov") == "/models/mine-ov"


def test_a_model_already_converted_is_still_accepted_by_name():
    """Nobody's model directory should quietly stop being usable."""
    for name in plan.LEGACY_MODELS:
        assert engine.resolve_model(name) == name
    assert not {model.hf_id for model in plan.CATALOGUE} & set(plan.LEGACY_MODELS)


def test_the_converted_model_is_named_after_what_it_came_from(tmp_path):
    where = engine.converted_dir("Qwen/Qwen3-8B", str(tmp_path))
    assert where.startswith(os.path.join(str(tmp_path), "summary"))
    assert os.path.basename(where) == "Qwen_Qwen3-8B-ov-int4"


def test_a_directory_that_is_already_converted_is_not_converted_again(tmp_path):
    ready = tmp_path / "mine-ov"
    ready.mkdir()
    (ready / "openvino_model.xml").write_text("<net/>", encoding="utf-8")
    assert engine.prepare(str(ready)) == str(ready)


def test_converting_without_the_extra_says_what_to_install(tmp_path, monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "optimum.intel", None)
    with pytest.raises(SummaryError) as raised:
        engine.prepare("Qwen/Qwen3-8B", str(tmp_path))
    assert "summarize-ov" in str(raised.value)


def test_the_page_is_told_which_model_wrote_it():
    assert "Qwen/Qwen3-4B" in engine.label({"summary_model": "Qwen/Qwen3-4B"})
    assert engine.LABEL in engine.label({"summary_model": "Qwen/Qwen3-4B"})


# --- the orchestration, without a model -----------------------------------

class FakePipeline:
    """Records what it was asked, answers with a well-formed summary."""

    asked = []

    def __init__(self, model_path, device):
        FakePipeline.asked = []
        self.model_path, self.device = model_path, device

    def ask(self, system, user, max_new_tokens=None, think=False):
        FakePipeline.asked.append({"prompt": user, "tokens": max_new_tokens,
                                   "think": think})
        return "## In breve\nUn riassunto vero.\n\n## Punti chiave\n- [0:08] Budget."


@pytest.fixture
def roomy(monkeypatch):
    """A machine with room, so the plan does not refuse before we get there."""
    plan.forget()
    monkeypatch.setattr(plan, "available_ram_gb", lambda: 32.0)
    monkeypatch.setattr(plan, "total_ram_gb", lambda: 64.0)
    monkeypatch.setattr(plan, "physical_cores", lambda: 8)
    monkeypatch.setattr(engine, "available_ram_gb", lambda: 32.0)
    monkeypatch.setattr(engine, "total_ram_gb", lambda: 64.0)
    yield plan.resolve_plan(plan.OPENVINO, {})
    plan.forget()


@pytest.fixture
def stubbed(monkeypatch, tmp_path, roomy):
    monkeypatch.setattr(engine, "prepare", lambda hf_id, models_dir=None: str(tmp_path))
    monkeypatch.setattr(engine, "Pipeline", FakePipeline)
    monkeypatch.setattr(engine, "openvino_devices", lambda: ["CPU"])
    return FakePipeline


def prompts(stub):
    return [call["prompt"] for call in stub.asked]


def material(sentences, language="it"):
    from audio_transcriber.summary import Material
    return Material(title="Riunione", sentences=sentences, language=language)


def test_a_transcript_that_fits_is_summarised_in_one_prompt(stubbed):
    sections, note = engine.summarize(material(SENTENCES), {})
    assert len(stubbed.asked) == 1
    assert "Parliamo del budget." in prompts(stubbed)[0]
    assert sections.abstract == "Un riassunto vero."
    assert note is None


def test_a_long_transcript_is_read_in_parts_and_then_folded(stubbed):
    many = [Sentence(f"Frase numero {n} del verbale.", n * 10.0) for n in range(60)]
    engine.summarize(material(many), {"summary_chunk_tokens": 120})

    asked = prompts(stubbed)
    assert "parte 1 di" in asked[0]
    assert "riassunti parziali" in asked[-1]
    assert "Un riassunto vero." in asked[-1]


def test_the_passes_are_exactly_the_ones_the_tree_calls_for(stubbed):
    """Not one per chunk plus one: the folding levels are passes too."""
    many = [Sentence(f"Frase numero {n} del verbale.", n * 10.0) for n in range(400)]
    engine.summarize(material(many), {"summary_chunk_tokens": 120})

    chunks = prompting.chunks(many, 120, stubbed_overlap := 0.1)
    fanin = prompting.fanin_for(len(chunks), 16384, 500, 1400,
                                prompting.EVIDENCE_TOKENS)
    levels = prompting.reduce_tree(range(len(chunks)), fanin=fanin,
                                   max_fanin=fanin)
    expected = len(chunks) + sum(len(level) for level in levels)
    assert len(stubbed.asked) == expected
    assert sum(1 for call in stubbed.asked
               if "parte 1 di" in call["prompt"]) == 1


def test_the_map_answers_under_a_tighter_budget_than_the_page(stubbed, roomy):
    many = [Sentence(f"Frase numero {n} del verbale.", n * 10.0) for n in range(60)]
    engine.summarize(material(many), {"summary_chunk_tokens": 120})

    mapping = [call for call in stubbed.asked if "parte 1 di" in call["prompt"]]
    root = stubbed.asked[-1]
    assert mapping[0]["tokens"] == roomy.map_answer_tokens
    assert root["tokens"] == roomy.reduce_answer_tokens
    assert root["tokens"] > mapping[0]["tokens"]


def test_the_model_is_told_not_to_think_while_reading_a_chunk(stubbed):
    """Its whole budget spent narrating is a truncated answer and no page."""
    many = [Sentence(f"Frase numero {n} del verbale.", n * 10.0) for n in range(60)]
    engine.summarize(material(many), {"summary_chunk_tokens": 120})
    mapping = [call for call in stubbed.asked if "parte 1 di" in call["prompt"]]
    assert mapping and all(call["think"] is False for call in mapping)


def test_every_fold_is_given_the_transcript_to_check_itself_against(stubbed):
    many = [Sentence(f"Il budget vale {n} mila euro.", n * 10.0) for n in range(60)]
    engine.summarize(material(many), {"summary_chunk_tokens": 120})
    folds = [call["prompt"] for call in stubbed.asked
             if "parte 1 di" not in call["prompt"]]
    assert folds
    assert all(prompting.FENCE_START in prompt for prompt in folds)


def test_a_machine_with_no_room_loads_nothing_at_all(monkeypatch, tmp_path):
    plan.forget()
    monkeypatch.setattr(plan, "available_ram_gb", lambda: 0.8)
    monkeypatch.setattr(plan, "total_ram_gb", lambda: 2.0)
    monkeypatch.setattr(plan, "physical_cores", lambda: 2)
    loaded = []
    monkeypatch.setattr(engine, "prepare",
                        lambda hf_id, models_dir=None: loaded.append(hf_id))

    with pytest.raises(NotEnoughMemory) as refused:
        engine.summarize(material(SENTENCES), {})
    assert loaded == []
    assert refused.value.needed and refused.value.free is not None
    plan.forget()


def test_the_model_saying_nothing_usable_is_an_error_not_an_empty_page(stubbed,
                                                                      monkeypatch):
    monkeypatch.setattr(FakePipeline, "ask",
                        lambda self, system, user, max_new_tokens=None,
                        think=False: "   ")
    with pytest.raises(SummaryError) as raised:
        engine.summarize(material(SENTENCES), {})
    assert "extractive" in str(raised.value)


def test_summarising_nothing_never_reaches_the_model(stubbed):
    with pytest.raises(SummaryError):
        engine.summarize(material([]), {})
    assert stubbed.asked == []
