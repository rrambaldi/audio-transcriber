"""What to load on this machine, and whether to load anything at all.

The engines used to answer this with a table: three model names against three
numbers of free gigabytes, written by hand. It chose reasonably on a laptop
and badly everywhere else, because it left out the two things that decide
whether a model actually runs — the KV cache, which nobody counts until the
machine starts swapping, and the possibility that the answer is "no model".

This module is that policy, done as arithmetic:

*what the machine has*
    free memory, less a reserve for the operating system and for the rest of
    this program, which is also holding a transcript.
*what a model would take*
    its weights at the chosen quantisation, plus the KV cache it would hold at
    the chosen context, plus what the runtime costs on top. The cache is
    **calculated** from the model's own shape, and only from its attention
    layers: in a hybrid model most layers are Mamba or convolution and hold no
    cache at all, which is why the catalogue prefers them and why a table of
    round numbers could never have expressed the preference.
*what to give up first*
    context, then the precision of the cache, then the precision of the
    weights, then the whole tier. In that order, because that is the order of
    what it costs to lose.
*when to refuse*
    if the smallest model in the catalogue does not fit, this returns None and
    the caller loads nothing. On these machines the alternative to swapping is
    a page of quoted sentences, which is an acceptable outcome; an out-of-
    memory kill halfway through a queue of jobs is not.

Nothing here imports a runtime, downloads anything or looks at the network:
the catalogue is static data, verified by hand against the models' own
configuration files, and the whole module is covered by the test suite on a
machine that can run none of it.
"""
from collections import namedtuple

from ..hardware import available_ram_gb, cpu_count, physical_cores, total_ram_gb
from . import prompting

#: One model, as the arithmetic needs to see it. ``attn_layers`` is the count
#: of layers that actually hold a KV cache — in a hybrid model that is a
#: handful of the total — and ``weights`` maps a quantisation to the size of
#: the file, in GiB, as published.
Model = namedtuple("Model", "name hf_id gguf_repo gguf_file context "
                            "attn_layers kv_heads head_dim weights tier "
                            "floor note")
Model.__new__.__defaults__ = (None,)

#: The execution plan: everything the engines need that depends on this
#: machine rather than on this recording.
Plan = namedtuple("Plan", "model quant context_tokens kv_k kv_v chunk_tokens "
                          "chunk_overlap max_passes prereduce threads "
                          "est_ram_gb tier map_answer_tokens "
                          "reduce_answer_tokens")

#: Bytes per element of a quantised KV cache. ``q8_0`` and ``q4_0`` carry a
#: scale per block of 32, which is where the fractions come from.
KV_BYTES = {"f16": 2.0, "q8_0": 1.0625, "q4_0": 0.5625}

#: The KV cache is quantised **asymmetrically**, and the key never below
#: ``q8_0``. This is not a rounding preference. Measured on one model against
#: its own f16 output, a q8_0 cache holds about 82% similarity and a
#: symmetric q4_0 cache falls to about 8% — it is a cliff, not a slope —
#: while quantising only the values costs on the order of a percent. The
#: failure it causes is the worst kind available here: nothing crashes,
#: nothing appears in a log, and the page is a summary that reads like a
#: summary and is not faithful to the recording.
KV_LADDER = (("f16", "f16"), ("q8_0", "q8_0"), ("q8_0", "q4_0"))

#: Weight precisions, best first. A model is only offered the ones its
#: publisher actually built: degrading to a file that does not exist is not a
#: degradation.
QUANT_LADDER = ("Q8_0", "Q6_K", "Q5_K_M", "Q4_K_M", "Q3_K_M", "Q2_K")

#: What the runtime costs beyond the weights and the cache: scratch buffers,
#: the tokenizer, the graph. Observed rather than derived, and generous on
#: purpose — the estimate exists to prevent an overflow, so it should err
#: towards refusing.
RUNTIME_OVERHEAD_GB = 0.35

#: Left for the operating system and for the rest of this program, which is
#: holding a transcript and possibly a job queue while the model runs.
#:
#: A share of the machine, and then a ceiling — the ceiling is the part that
#: was learned the hard way. What has to be kept free does not grow with how
#: much RAM was installed: a desktop with thirty-two gigabytes needs no more
#: elbow room than one with eight. Without the cap, a large machine that is
#: merely busy — seven gigabytes free of thirty-two, which is an ordinary
#: Tuesday — reserved six of the seven and concluded that no model fits.
RESERVE_GB = 0.75
RESERVE_SHARE = 0.20
RESERVE_CAP_GB = 2.0

#: How much of what fits in a pass a chunk actually uses. Faithfulness is
#: U-shaped — high at the start and the end of an input, measurably lower in
#: the middle — so a chunk that fills the window has a middle worth losing.
#: The window is not a target.
CHUNK_SHARE = 0.75

#: Repeated at the head of the next chunk, so a decision taken across a
#: boundary is not half in one pass and half in another.
CHUNK_OVERLAP = 0.1

#: The catalogue. Every number here was read from the model's own
#: ``config.json`` and from the published file sizes on 2026-09-10; none of it
#: is inferred from a parameter count. ``head_dim`` is ``hidden_size`` divided
#: by the head count where the configuration does not state it.
#:
#: The hybrids are here on purpose. Granite 4.0 H-Micro holds a cache in four
#: of its forty layers, which is around a tenth of what a dense model of the
#: same depth would hold, and that is the difference between reading a long
#: transcript and not.
CATALOGUE = (
    # First in its tier because it is the one that works. Asked in Italian to
    # summarise a news article in three sentences, MiniCPM5-1B at Q4_K_M
    # returns the article — not a bad summary, no summary: it copies the input
    # verbatim, on the simplest instruction that can be given. This one
    # answers with three sentences of its own. Measured 2026-09-10 on the
    # Evalita-LLM Fanpage task; the hybrid also holds a cache in six of its
    # sixteen layers against the other's twenty-four, so it is cheaper too.
    Model(name="LFM2.5-1.2B",
          hf_id="LiquidAI/LFM2.5-1.2B-Instruct",
          gguf_repo="LiquidAI/LFM2.5-1.2B-Instruct-GGUF",
          gguf_file="LFM2.5-1.2B-Instruct-{quant}.gguf",
          context=128000, attn_layers=6, kv_heads=8, head_dim=64,
          weights={"Q4_K_M": 0.68, "Q5_K_M": 0.79, "Q6_K": 0.90,
                   "Q8_0": 1.16},
          tier="xs", floor=1.0),
    # Kept, and not chosen: somebody who has already fetched it can still ask
    # for it by name, and at Q8_0 it may well behave. At Q4_K_M it does not.
    Model(name="MiniCPM5-1B",
          hf_id="openbmb/MiniCPM5-1B",
          gguf_repo="openbmb/MiniCPM5-1B-GGUF",
          gguf_file="MiniCPM5-1B-{quant}.gguf",
          context=131072, attn_layers=24, kv_heads=2, head_dim=128,
          weights={"Q4_K_M": 0.64, "Q8_0": 1.07, "F16": 2.02},
          tier="xs", floor=1.0,
          note="copies the article instead of summarising it at Q4_K_M"),
    Model(name="MiniCPM5-2B",
          hf_id="openbmb/MiniCPM5-2B",
          gguf_repo="openbmb/MiniCPM5-2B-GGUF",
          gguf_file="MiniCPM5-2B-{quant}.gguf",
          context=131072, attn_layers=42, kv_heads=2, head_dim=128,
          weights={"Q4_K_M": 1.45, "Q8_0": 2.50, "F16": 4.69},
          tier="s", floor=2.0),
    Model(name="Granite 4.0 H-Micro",
          hf_id="ibm-granite/granite-4.0-h-micro",
          gguf_repo="ibm-granite/granite-4.0-h-micro-GGUF",
          gguf_file="granite-4.0-h-micro-{quant}.gguf",
          context=131072, attn_layers=4, kv_heads=8, head_dim=64,
          weights={"Q2_K": 1.14, "Q3_K_M": 1.45, "Q4_K_M": 1.81,
                   "Q5_K_M": 2.12, "Q6_K": 2.44, "Q8_0": 3.16},
          tier="m", floor=3.5),
    Model(name="Granite 4.0 H-Tiny",
          hf_id="ibm-granite/granite-4.0-h-tiny",
          gguf_repo="ibm-granite/granite-4.0-h-tiny-GGUF",
          gguf_file="granite-4.0-h-tiny-{quant}.gguf",
          context=131072, attn_layers=4, kv_heads=4, head_dim=128,
          weights={"Q2_K": 2.41, "Q3_K_M": 3.12, "Q4_K_M": 3.94,
                   "Q5_K_M": 4.61, "Q6_K": 5.32, "Q8_0": 6.88},
          tier="l", floor=8.0),
    # No GGUF is published for this one and it is a multimodal checkpoint, so
    # only the OpenVINO path can reach it and the weight figure is an estimate
    # rather than a file size. Both facts are why it is last.
    Model(name="Qwen3.5-4B",
          hf_id="Qwen/Qwen3.5-4B",
          gguf_repo=None, gguf_file=None,
          context=262144, attn_layers=8, kv_heads=4, head_dim=256,
          weights={"Q4_K_M": 2.6},
          tier="l", floor=6.0,
          note="weights estimated; no GGUF published"),
)

#: Still accepted by name, no longer chosen by ``auto``. Somebody who
#: converted one of these into their model directory should not find it gone.
LEGACY_MODELS = ("Qwen/Qwen3-8B", "Qwen/Qwen3-4B", "Qwen/Qwen3-1.7B")

#: One tier: how much usable memory it wants, and how a model runs there. The
#: answer budgets shrink with the tier because they are what the level above
#: has to carry: a map answer of 500 tokens is nothing to a model with 16k of
#: context and is a quarter of the window of one with 2k.
#:
#: They do not shrink as far as the arithmetic alone would allow, and that is
#: a lesson from running one. A small model spends the first thirty or forty
#: tokens of an answer restating the question, so a budget tight enough to
#: look elegant is a budget that truncates the list halfway through its second
#: item. The floor here is what a bulleted summary of a chunk actually needs.
Tier = namedtuple("Tier", "name floor context kv max_passes prereduce "
                          "map_answer reduce_answer")

TIERS = (
    Tier("l",  6.0, 16384, ("f16", "f16"),   None, False, 500, 1400),
    Tier("m",  3.5,  8192, ("q8_0", "q8_0"),    8, True,  500, 1200),
    Tier("s",  2.0,  4096, ("q8_0", "q8_0"),    4, True,  400,  900),
    Tier("xs", 1.0,  2048, ("q8_0", "q4_0"),    3, True,  350,  650),
)

#: The engines this policy chooses for. Spelled out here rather than imported
#: from the registry because the plan has to be able to answer for an engine
#: that is not installed on this machine, which is most of them most of the
#: time — and because asking the registry would make a pure module depend on
#: what happens to be importable.
OPENVINO, LLAMACPP = "openvino", "llamacpp"

#: Cleared by the tests, and by nothing else: the answer depends on hardware,
#: which does not change while the program runs.
_CACHE = {}


def tier_named(name):
    """The tier called ``name``, or None."""
    wanted = str(name or "").strip().lower()
    for tier in TIERS:
        if tier.name == wanted:
            return tier
    return None


def kv_pair(value, fallback=("q8_0", "q8_0")):
    """``"q8_0"`` or ``"q8_0/q4_0"`` read into ``(key, value)`` types.

    A key below ``q8_0`` is refused however it was asked for — see
    :data:`KV_LADDER`. It is the one place this module overrules the person
    who typed the setting, and the reason is that the damage it does is
    invisible."""
    text = str(value or "").strip().lower()
    if not text:
        return fallback
    key, _, val = text.partition("/")
    key, val = key.strip() or fallback[0], val.strip() or key.strip()
    if key not in KV_BYTES or val not in KV_BYTES:
        return fallback
    if KV_BYTES[key] < KV_BYTES["q8_0"]:
        key = "q8_0"
    return key, val


def kv_gb(model, context_tokens, kv_k="q8_0", kv_v="q8_0"):
    """The KV cache this model would hold at this context, in GiB.

    Keys and values are counted apart because they are quantised apart, and
    only the attention layers are counted at all: a Mamba or convolution layer
    keeps a fixed-size state, not a cache that grows with the transcript."""
    slots = model.attn_layers * model.kv_heads * model.head_dim * int(context_tokens)
    bytes_used = slots * (KV_BYTES.get(kv_k, 2.0) + KV_BYTES.get(kv_v, 2.0))
    return bytes_used / (1024.0 ** 3)


def estimate_ram_gb(model, quant, context_tokens, kv_k="q8_0", kv_v="q8_0"):
    """Weights, plus cache, plus what the runtime costs on top.

    None for a model that is not in the catalogue: its shape is unknown, and a
    number invented for it would be worse than the absence of one — it would
    be believed."""
    if not model.weights:
        return None
    weights = model.weights.get(quant, max(model.weights.values()))
    return (weights + kv_gb(model, context_tokens, kv_k, kv_v)
            + RUNTIME_OVERHEAD_GB)


def usable_ram_gb(available, total):
    """What a model may take, once the machine has been left room to run."""
    if available is None:
        return None
    reserve = RESERVE_GB if not total else max(RESERVE_GB, total * RESERVE_SHARE)
    return max(0.0, available - min(reserve, RESERVE_CAP_GB))


def quants_for(model):
    """The weight precisions this model is published in, best first."""
    have = {name.upper() for name in model.weights}
    return tuple(name for name in QUANT_LADDER if name.upper() in have)


#: Hybrid architectures (Mamba/SSM layers) whose OpenVINO export unrolls into
#: tens of thousands of elementary nodes, which openvino_genai's CausalLM
#: pipeline cannot load or execute cleanly.
OPENVINO_INCOMPATIBLE = {
    "ibm-granite/granite-4.0-h-micro",
    "ibm-granite/granite-4.0-h-tiny",
    "LiquidAI/LFM2.5-1.2B-Instruct",
}


def runnable(model, engine):
    """Whether this engine could load this model at all.

    The GGUF engine needs a GGUF, and not every model has one published; the
    OpenVINO path converts from the Hugging Face checkpoint and needs that,
    excluding hybrid architectures that OpenVINO GenAI cannot load."""
    name = str(engine or "").strip().lower()
    if name == LLAMACPP:
        return bool(model.gguf_repo and model.gguf_file)
    if name == OPENVINO:
        return bool(model.hf_id) and model.hf_id not in OPENVINO_INCOMPATIBLE
    return True


def candidates(tier, engine, usable=None):
    """The models this tier would choose between, best first.

    A tier can hold more than one, and then the floor decides: Granite H-Tiny
    is the better model of the two in the largest tier and wants eight
    gigabytes to be worth loading, so a machine with seven gets the other
    one rather than a squeezed version of the bigger."""
    found = [(index, model) for index, model in enumerate(CATALOGUE)
             if model.tier == tier.name and runnable(model, engine)
             and (usable is None or usable >= model.floor)]
    # The floor first, then the order they are listed in: two models in one
    # tier that want the same memory are ranked by the catalogue, which is
    # where a measurement can be recorded and a preference explained.
    found.sort(key=lambda pair: (-pair[1].floor, pair[0]))
    return tuple(model for _, model in found)


def _lower(context):
    """The next context down, by halves, never below the floor of 2048."""
    return max(2048, int(context) // 2)


def _fit(model, tier, usable, quant=None, context=None, kv=None):
    """Squeeze one model into ``usable``, or return None.

    Concessions are made in the order they cost least: the context first,
    then the precision of the cache, then the precision of the weights. The
    context goes first deliberately — a smaller window is a smaller prompt,
    which this program wants anyway, while a coarser cache is a quieter
    kind of wrong."""
    quants = quants_for(model)
    if not quants:
        return None
    quant = quant if quant in quants else (
        "Q4_K_M" if "Q4_K_M" in quants else quants[-1])
    context = min(int(context or tier.context), model.context)
    kv_k, kv_v = kv or tier.kv
    if KV_BYTES.get(kv_k, 2.0) < KV_BYTES["q8_0"]:
        kv_k = "q8_0"

    def estimate():
        return estimate_ram_gb(model, quant, context, kv_k, kv_v)

    while estimate() > usable and context > 2048:
        context = _lower(context)

    start = KV_LADDER.index((kv_k, kv_v)) if (kv_k, kv_v) in KV_LADDER else 0
    for step in KV_LADDER[start + 1:]:
        if estimate() <= usable:
            break
        kv_k, kv_v = step

    for step in quants[quants.index(quant) + 1:]:
        if estimate() <= usable:
            break
        quant = step

    if estimate() > usable:
        return None
    return quant, context, kv_k, kv_v, estimate()


def evidence_for(context_tokens):
    """How much original transcript a fold may be shown, at this context.

    A share rather than a constant: four hundred tokens of evidence is nothing
    in a sixteen-thousand-token window and a fifth of a two-thousand-token
    one, where it would be taken out of the material the fold is there to
    merge."""
    return max(120, min(prompting.EVIDENCE_TOKENS, int(context_tokens) // 8))


def tier_for(usable):
    """The largest tier this much memory can hold, or the smallest one."""
    for tier in TIERS:
        if usable is not None and usable >= tier.floor:
            return tier
    return TIERS[-1]


def unknown(name, tier, context):
    """A catalogue entry for a model nobody catalogued.

    Somebody may name any Hugging Face id, or a directory they converted by
    hand. Nothing is known about its shape, so nothing is estimated for it:
    the plan carries the name and admits the rest."""
    return Model(name=name, hf_id=name, gguf_repo=None, gguf_file=None,
                 context=int(context), attn_layers=0, kv_heads=0, head_dim=0,
                 weights={}, tier=tier.name, floor=0.0,
                 note="not in the catalogue: nothing estimated")


def _plan_of(model, tier, quant, context, kv_k, kv_v, estimate, threads):
    """Assemble the plan around a model that has been made to fit."""
    # Never the whole window, and never more than the figure this program
    # used before it could measure anything: a chunk with a real middle has a
    # middle the model reads least faithfully, and that is a reason to keep
    # chunks small that has nothing to do with memory.
    room = min(prompting.budget_for(context, tier.map_answer),
               prompting.CHUNK_TOKENS)
    return Plan(model=model, quant=quant, context_tokens=context,
                kv_k=kv_k, kv_v=kv_v,
                chunk_tokens=max(256, int(room * CHUNK_SHARE)),
                chunk_overlap=CHUNK_OVERLAP,
                max_passes=tier.max_passes, prereduce=tier.prereduce,
                threads=threads,
                est_ram_gb=None if estimate is None else round(estimate, 2),
                tier=tier.name, map_answer_tokens=tier.map_answer,
                reduce_answer_tokens=tier.reduce_answer)


def named(name):
    """The catalogue entry a name refers to, or None for anything else."""
    wanted = str(name or "").strip().lower()
    for model in CATALOGUE:
        if wanted in (model.name.lower(), (model.hf_id or "").lower()):
            return model
    return None


def resolve_plan(engine, settings=None, ram=None, total=None, cores=None):
    """The plan for this machine, or None when it should not load a model.

    ``None`` is a real answer and not a failure: the caller falls back to the
    extractive engine and says on the page that it did, which is a better
    outcome than a model that swaps.

    A ``summary_model`` given by name always wins, even when the estimate says
    it will not fit. Somebody who typed a model name has the right to be
    wrong about their own machine; the default does not.

    Memoised on the shape of the machine rather than on the moment: reading
    ``/proc/meminfo`` once per summary is right, once per chunk is not."""
    settings = settings or {}
    overrides = (settings.get("summary_model"), settings.get("summary_tier"),
                 settings.get("summary_context_tokens"),
                 settings.get("summary_kv_type"),
                 settings.get("summary_device"))
    if total is None:
        total = total_ram_gb()
    if cores is None:
        cores = physical_cores() or cpu_count()
    key = (engine, None if total is None else round(total), cores, overrides)
    if key in _CACHE and ram is None:
        return _CACHE[key]

    available = available_ram_gb() if ram is None else ram
    plan = _resolve(engine, settings, available, total, cores)
    if ram is None:
        _CACHE[key] = plan
    return plan


def _resolve(engine, settings, available, total, cores):
    """:func:`resolve_plan` with the machine already measured."""
    threads = int(settings.get("threads") or cores or 1)
    usable = usable_ram_gb(available, total)
    if usable is None:
        # A machine that will not say how much memory it has is treated as the
        # smallest one that exists rather than as an unlimited one.
        usable = TIERS[-1].floor

    asked_tier = tier_named(settings.get("summary_tier"))
    asked_context = settings.get("summary_context_tokens")
    asked_kv = settings.get("summary_kv_type")

    asked_model = str(settings.get("summary_model") or "").strip()
    if asked_model and asked_model.lower() != "auto":
        wanted = named(asked_model)
        tier = (asked_tier or tier_named(wanted.tier if wanted else None)
                or tier_for(usable))
        kv = kv_pair(asked_kv, tier.kv)
        if wanted is None:
            model = unknown(asked_model, tier, asked_context or tier.context)
            return _plan_of(model, tier, None, model.context, kv[0], kv[1],
                            None, threads)
        context = min(int(asked_context or tier.context), wanted.context)
        quant = quants_for(wanted)
        quant = "Q4_K_M" if "Q4_K_M" in quant else (quant[-1] if quant else None)
        estimate = estimate_ram_gb(wanted, quant, context, *kv)
        return _plan_of(wanted, tier, quant, context, kv[0], kv[1],
                        estimate, threads)

    for tier in TIERS:
        if asked_tier is not None and tier.name != asked_tier.name:
            continue
        if asked_tier is None and usable < tier.floor:
            continue
        for model in candidates(tier, engine, usable):
            fitted = _fit(model, tier, usable,
                          context=asked_context,
                          kv=kv_pair(asked_kv, tier.kv) if asked_kv else None)
            if fitted:
                return _plan_of(model, tier, *fitted, threads=threads)
    return None


def cheapest(engine):
    """The least this engine could possibly need, in GiB, or None.

    What the smallest model in the catalogue costs at the smallest context and
    the coarsest cache it is allowed. It is the number a machine is compared
    against before being told no, and the number the page prints when it
    is."""
    tier = TIERS[-1]
    best = None
    for model in candidates(tier, engine):
        quants = quants_for(model)
        if not quants:
            continue
        estimate = estimate_ram_gb(model, quants[-1], 2048, *KV_LADDER[-1])
        if estimate is not None and (best is None or estimate < best):
            best = estimate
    return best


def forget():
    """Drop the memoised plans. For the tests, and for nothing else."""
    _CACHE.clear()
