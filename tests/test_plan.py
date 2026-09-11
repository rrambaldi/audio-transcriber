"""The execution plan: what this machine can hold, and what it must refuse.

None of this needs a model, or a runtime, or a network. The catalogue is
static data and the arithmetic is arithmetic, which is the point: the policy
that decides whether a summary is written by a model or quoted from the
transcript is the part that most needs to be inspectable, and it is fully
covered on a machine that can run none of the models it chooses between.
"""
import pytest

from audio_transcriber.summarizers import plan


@pytest.fixture(autouse=True)
def forget():
    plan.forget()
    yield
    plan.forget()


def dense(layers=40, kv_heads=8, head_dim=64, weights=None):
    """A model shaped like the ones in the catalogue, with numbers we chose."""
    return plan.Model(name="fake", hf_id="fake/fake", gguf_repo="fake/fake-GGUF",
                      gguf_file="fake-{quant}.gguf", context=131072,
                      attn_layers=layers, kv_heads=kv_heads, head_dim=head_dim,
                      weights=weights or {"Q5_K_M": 2.0, "Q4_K_M": 1.5,
                                          "Q3_K_M": 1.2, "Q2_K": 1.0},
                      tier="m", floor=3.5)


# --- the arithmetic -------------------------------------------------------

def test_only_the_attention_layers_hold_a_cache():
    """The reason the catalogue prefers hybrids, in one assertion.

    Granite 4.0 H-Micro keeps a cache in four of its forty layers; a dense
    model of the same depth keeps one in all forty."""
    hybrid = plan.named("ibm-granite/granite-4.0-h-micro")
    same_but_dense = hybrid._replace(attn_layers=40)
    small = plan.kv_gb(hybrid, 8192)
    large = plan.kv_gb(same_but_dense, 8192)
    assert large / small == pytest.approx(10.0)


def test_the_key_and_the_value_are_counted_apart():
    model = dense()
    both = plan.kv_gb(model, 4096, "f16", "f16")
    halved = plan.kv_gb(model, 4096, "q8_0", "q4_0")
    assert halved < both / 2


def test_the_cache_grows_with_the_context_and_nothing_else():
    model = dense()
    assert plan.kv_gb(model, 8192) == pytest.approx(2 * plan.kv_gb(model, 4096))


def test_the_estimate_is_weights_plus_cache_plus_the_runtime():
    model = dense()
    assert plan.estimate_ram_gb(model, "Q4_K_M", 4096, "q8_0", "q8_0") == (
        pytest.approx(1.5 + plan.kv_gb(model, 4096, "q8_0", "q8_0")
                      + plan.RUNTIME_OVERHEAD_GB))


def test_the_reserve_scales_with_the_machine_but_stops():
    """A fifth of it, never below three quarters of a gig, never above two.

    The ceiling matters more than either: what has to stay free does not grow
    with how much was installed, and without it a large machine that is merely
    busy reserves nearly everything it has left."""
    assert plan.usable_ram_gb(2.0, 2.0) == pytest.approx(1.25)
    assert plan.usable_ram_gb(40.0, 64.0) == pytest.approx(38.0)
    assert plan.usable_ram_gb(0.2, 2.0) == 0.0
    assert plan.usable_ram_gb(None, 8.0) is None


def test_a_big_machine_that_is_busy_is_not_told_it_is_full():
    """Seven gigabytes free of thirty-two is an ordinary Tuesday.

    Reserving a fifth of what was installed left half a gigabyte of it and
    concluded that no model fits — on a desktop with an Intel GPU."""
    usable = plan.usable_ram_gb(6.8, 31.5)
    assert usable > 4.0
    chosen = plan.resolve_plan(plan.OPENVINO, ram=6.8, total=31.5, cores=8)
    assert chosen is not None and chosen.tier == "s"
    gguf = plan.resolve_plan(plan.LLAMACPP, ram=6.8, total=31.5, cores=8)
    assert gguf is not None and gguf.tier == "m"


# --- choosing a tier ------------------------------------------------------

@pytest.mark.parametrize("available,total,tier", [
    (32.0, 64.0, "l"),
    (12.0, 16.0, "l"),
    (7.0, 8.0, "m"),
    (3.0, 4.0, "s"),
    (2.2, 4.0, "xs"),
])
def test_each_size_of_machine_gets_the_tier_it_can_hold(available, total, tier):
    chosen = plan.resolve_plan(plan.LLAMACPP, ram=available, total=total, cores=4)
    assert chosen is not None
    assert chosen.tier == tier
    assert chosen.est_ram_gb <= plan.usable_ram_gb(available, total)


def test_a_machine_too_small_for_the_smallest_model_is_told_no():
    """Refusing is a real answer: the caller quotes sentences instead.

    A page of somebody's own words is an acceptable outcome on this machine;
    an out-of-memory kill halfway through a queue of jobs is not."""
    assert plan.resolve_plan(plan.LLAMACPP, ram=0.8, total=2.0, cores=2) is None


def test_a_machine_that_will_not_say_is_treated_as_the_smallest_one(monkeypatch):
    monkeypatch.setattr(plan, "available_ram_gb", lambda: None)
    chosen = plan.resolve_plan(plan.LLAMACPP, ram=None, total=None, cores=2)
    assert chosen is None or chosen.tier == "xs"


def test_the_better_model_of_a_tier_needs_the_memory_to_be_worth_it():
    """Granite H-Tiny is the better model and wants eight gigabytes."""
    plenty = plan.resolve_plan(plan.LLAMACPP, ram=32.0, total=64.0, cores=8)
    just_over = plan.resolve_plan(plan.OPENVINO, ram=9.0, total=10.0, cores=8)
    assert plenty.model.name == "Granite 4.0 H-Tiny"
    assert just_over.tier == "l" and just_over.model.name == "Qwen3.5-4B"


def test_an_engine_is_never_offered_a_model_it_cannot_load():
    """No GGUF is published for Qwen3.5-4B, so llama.cpp never sees it.
    Hybrid Mamba architectures cannot run on OpenVINO GenAI, so OpenVINO never sees them."""
    for tier in plan.TIERS:
        for model in plan.candidates(tier, plan.LLAMACPP):
            assert model.gguf_repo and model.gguf_file
        for model in plan.candidates(tier, plan.OPENVINO):
            assert model.hf_id not in plan.OPENVINO_INCOMPATIBLE
    gguf = plan.resolve_plan(plan.LLAMACPP, ram=9.0, total=10.0, cores=8)
    assert gguf is None or gguf.model.name != "Qwen3.5-4B"
    intel = plan.resolve_plan(plan.OPENVINO, ram=32.0, total=64.0, cores=8)
    assert intel is not None and intel.model.hf_id not in plan.OPENVINO_INCOMPATIBLE


# --- giving things up, in order -------------------------------------------

def test_the_context_is_the_first_thing_given_up():
    model = plan.named("ibm-granite/granite-4.0-h-micro")
    tier = plan.tier_named("m")
    roomy = plan._fit(model, tier, 8.0)
    tight = plan._fit(model, tier, plan.estimate_ram_gb(
        model, "Q4_K_M", tier.context, *tier.kv) - 0.005)
    assert roomy[1] == tier.context
    assert tight[1] < roomy[1]              # the context came down
    assert tight[0] == roomy[0]             # the weights did not
    assert tight[2:4] == roomy[2:4]         # nor the cache


def test_the_cache_goes_before_the_weights_and_the_weights_before_the_tier():
    """The order matters more than the outcome: each step costs more."""
    # A model whose cache is worth giving up: dense, wide, and long-context.
    model = dense(layers=40, kv_heads=32, head_dim=128,
                  weights={"Q5_K_M": 2.0, "Q4_K_M": 1.5, "Q2_K": 1.0})
    tier = plan.tier_named("l")._replace(kv=("f16", "f16"))

    floor = plan.estimate_ram_gb(model, "Q5_K_M", 2048, "f16", "f16")
    # Short of what the smallest context at full precision would take, so the
    # cache has to give before the weights do.
    quant, context, kv_k, kv_v, _ = plan._fit(model, tier, floor - 0.2,
                                              quant="Q5_K_M")
    assert context == 2048
    assert (kv_k, kv_v) != ("f16", "f16")
    assert quant == "Q5_K_M"

    # Short of even that, and the weights are next.
    cheapest_cache = plan.estimate_ram_gb(model, "Q5_K_M", 2048, "q8_0", "q4_0")
    quant, _, kv_k, kv_v, _ = plan._fit(model, tier, cheapest_cache - 0.2,
                                        quant="Q5_K_M")
    assert (kv_k, kv_v) == ("q8_0", "q4_0")
    assert quant != "Q5_K_M"


def test_the_key_is_never_quantised_below_q8():
    """Not a rounding preference: a q4 key is a cliff, and a silent one.

    Nothing crashes and nothing reaches a log; the page is a summary that
    reads like a summary and is not faithful to the recording."""
    for available in (0.9, 1.2, 2.2, 3.0, 5.0, 9.0, 32.0):
        for engine in (plan.OPENVINO, plan.LLAMACPP):
            plan.forget()
            chosen = plan.resolve_plan(engine, ram=available,
                                       total=available * 2, cores=2)
            assert chosen is None or chosen.kv_k == "q8_0" \
                or chosen.kv_k == "f16"
    assert plan.kv_pair("q4_0/q4_0") == ("q8_0", "q4_0")
    assert plan.kv_pair("q4_0") == ("q8_0", "q4_0")


def test_a_cache_setting_is_read_as_one_type_or_as_a_pair():
    assert plan.kv_pair("q8_0") == ("q8_0", "q8_0")
    assert plan.kv_pair("f16/q8_0") == ("f16", "q8_0")
    assert plan.kv_pair("") == ("q8_0", "q8_0")
    assert plan.kv_pair("nonsense", ("f16", "f16")) == ("f16", "f16")


def test_a_model_only_degrades_to_a_file_that_exists():
    """MiniCPM5 is published at three precisions, and Q3_K_M is not one."""
    model = plan.named("openbmb/MiniCPM5-1B")
    assert plan.quants_for(model) == ("Q8_0", "Q4_K_M")
    fitted = plan._fit(model, plan.tier_named("xs"), 1.05, quant="Q8_0")
    assert fitted[0] in plan.quants_for(model)


# --- what the caller asked for --------------------------------------------

def test_a_model_named_by_hand_wins_even_when_it_does_not_fit():
    """Somebody who typed a model name may be wrong about their machine.

    The default may not."""
    chosen = plan.resolve_plan(plan.OPENVINO, {"summary_model": "Qwen3.5-4B"},
                               ram=2.0, total=4.0, cores=2)
    assert chosen is not None
    assert chosen.model.name == "Qwen3.5-4B"
    assert chosen.est_ram_gb > plan.usable_ram_gb(2.0, 4.0)


def test_a_tier_asked_for_by_name_is_the_only_one_considered():
    chosen = plan.resolve_plan(plan.LLAMACPP, {"summary_tier": "xs"},
                               ram=32.0, total=64.0, cores=8)
    assert chosen.tier == "xs"


def test_a_context_asked_for_by_hand_is_not_exceeded():
    chosen = plan.resolve_plan(plan.LLAMACPP, {"summary_context_tokens": 4096},
                               ram=32.0, total=64.0, cores=8)
    assert chosen.context_tokens <= 4096


# --- the shape of the passes ----------------------------------------------

def test_a_chunk_never_fills_the_window():
    """Faithfulness sags in the middle of an input, so chunks stay small."""
    for available in (2.2, 5.0, 32.0):
        plan.forget()
        chosen = plan.resolve_plan(plan.LLAMACPP, ram=available,
                                   total=available * 2, cores=4)
        assert chosen.chunk_tokens < chosen.context_tokens
        assert chosen.chunk_tokens <= 6000
        assert 0 < chosen.chunk_overlap < 0.5


def test_the_smallest_tier_always_pre_reduces_and_the_largest_never_does():
    small = plan.resolve_plan(plan.LLAMACPP, ram=2.2, total=4.0, cores=2)
    plan.forget()
    large = plan.resolve_plan(plan.LLAMACPP, ram=32.0, total=64.0, cores=8)
    assert small.prereduce and small.max_passes
    assert not large.prereduce


def test_the_answer_budgets_shrink_with_the_window():
    small = plan.resolve_plan(plan.LLAMACPP, ram=2.2, total=4.0, cores=2)
    plan.forget()
    large = plan.resolve_plan(plan.LLAMACPP, ram=32.0, total=64.0, cores=8)
    assert small.map_answer_tokens < large.map_answer_tokens
    assert small.reduce_answer_tokens < large.reduce_answer_tokens


# --- reading the machine once ---------------------------------------------

def test_the_same_machine_is_measured_once_and_answered_the_same(monkeypatch):
    reads = []

    def counted():
        reads.append(1)
        return 5.0

    monkeypatch.setattr(plan, "available_ram_gb", counted)
    monkeypatch.setattr(plan, "total_ram_gb", lambda: 8.0)
    monkeypatch.setattr(plan, "physical_cores", lambda: 4)

    first = plan.resolve_plan(plan.LLAMACPP)
    again = plan.resolve_plan(plan.LLAMACPP)
    assert first == again
    assert len(reads) == 1


def test_two_engines_do_not_share_one_answer(monkeypatch):
    monkeypatch.setattr(plan, "available_ram_gb", lambda: 9.0)
    monkeypatch.setattr(plan, "total_ram_gb", lambda: 10.0)
    monkeypatch.setattr(plan, "physical_cores", lambda: 4)
    intel = plan.resolve_plan(plan.OPENVINO)
    gguf = plan.resolve_plan(plan.LLAMACPP)
    assert intel.model.name == "Qwen3.5-4B"
    assert gguf.model.name != "Qwen3.5-4B"


def test_the_legacy_models_are_no_longer_chosen_by_anything():
    names = {model.hf_id for model in plan.CATALOGUE}
    assert not names & set(plan.LEGACY_MODELS)
    assert "Qwen/Qwen3-8B" in plan.LEGACY_MODELS
