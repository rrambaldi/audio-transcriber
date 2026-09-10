# Summarising long transcripts on a machine with little RAM — the plan

This is the low-RAM summary specification mapped onto the files that exist,
with the exact signatures each step introduces. It was written before any code
was, so that it could be disagreed with first: four of the steps touch modules
that are pure and testable without a model, and that property is easier to keep
than to recover. It is kept current as the steps land.

The spec's own diagnosis is accepted as written: the architecture is right —
selection separated from writing, engines behind a registry, map/reduce — and
what follows closes four holes in it rather than rearranging it. A later
revision of the spec added a section of research findings which **corrects**
its own model policy in three places; those corrections are folded in below
rather than kept apart, because a plan with two answers in it is not a plan.

Where this document departs from the spec, or found the spec under-determined,
it says so in [Open questions](#open-questions) rather than choosing quietly.
Those are the points worth reading first.

## The four holes, in one line each

| # | Hole | Where it bites | Closed by |
|---|---|---|---|
| 2.1 | the reduce is a star, and its prompt has no ceiling | `openvino_genai.summarize()` builds one `reduce_prompt(partials)` over every chunk: 15 chunks of a 90k-token recording is a ~21k-token prompt handed to a model chosen because the machine is small | step 2 |
| 2.2 | `summary.reduce()` and `prompting.plan()` are dead | both are called only from tests; the docstrings of `summarizers/__init__.py` and `summary.reduce()` claim otherwise | step 6 |
| 2.3 | `recommend_model()` is a table, not a policy | no KV-cache arithmetic, no degradation, no refusal, and a catalogue from spring 2025 | step 4 |
| 2.4 | the CPU env cannot write prose at all | `environment-cpu.yml` has no OpenVINO, so `available()` returns `extractive` only — the machine class this spec is about is the one class that never gets a document | step 8 |

## The map: spec → files

### `summarizers/prompting.py` — pure, stays pure

Today: `CHUNK_TOKENS = 6000` (line 33), `ANSWER_TOKENS = 1200` (line 36, **no
callers**), `chunks()` (178), `parse()` (241), `plan()` (317, no production
callers), `single_prompt()` (323), `map_prompt()` (333), `reduce_prompt()`
(340), and the `PROMPTS` catalogue (71) keyed by spoken language.

Added:

```python
REDUCE_FANIN = 6
MAX_REDUCE_DEPTH = 3      # the map counts as the first level: two reduces
MAP_ANSWER_TOKENS = 500   # an intermediate answer is capped here too
REDUCE_ANSWER_TOKENS = 1400
EVIDENCE_TOKENS = 400
PROMPT_VERSION = 1

def reduce_tree(partials, fanin=REDUCE_FANIN, max_depth=MAX_REDUCE_DEPTH,
                max_fanin=None):
    """-> list[list[list[int]]]: one entry per level, each a list of groups,
    each group the indices one prompt folds together — indices into the
    partials at the first level, into the previous level's results above it,
    because the answers a higher level folds do not exist when the shape is
    decided."""

def fanin_for(count, context_tokens, partial_tokens,
              answer_tokens=REDUCE_ANSWER_TOKENS,
              evidence_tokens=EVIDENCE_TOKENS, overhead=400): ...
def budget_for(context_tokens, answer_tokens=REDUCE_ANSWER_TOKENS, overhead=400): ...
def evidence_for(sentences, budget=EVIDENCE_TOKENS, language="it"): ...
def chunks(sentences, budget=CHUNK_TOKENS, overlap=0.0): ...
def reduce_partial_prompt(partials, language, evidence=None): ...
def reduce_prompt(partials, language, evidence=None): ...   # the root only
```

`max_fanin` is the one part not in the specification, and it settles a
conflict inside it. The rule "widen the fan-in rather than add a level" and
the rule "no prompt exceeds the context" cannot both hold on a small model:
widening is exactly what makes a prompt bigger. So widening stops at
`max_fanin` when the caller passes one, and the tree grows a level instead —
on a model that cannot hold a wider prompt, depth is the lesser harm. Without
it the defaults behave as the specification describes, which is what
acceptance criterion 1 pins down.

`reduce_prompt()` keeps its signature and becomes the **root level only**.
`CHUNK_TOKENS` stays as the default for a caller that does not know the
model's context. `ANSWER_TOKENS` is superseded by the two named budgets and is
removed with a note in the changelog — it has no callers to break.

New `PROMPTS` entries `reduce_partial` and `evidence` in **both** `it` and
`en`; the prompt catalogue is keyed by the language that was *spoken*, not by
the interface language, and that does not change.

**Every reduce pass reads a piece of the transcript, not only the partials.**
Recursive merging amplifies whatever the model invented one level down, because
from the second level on it is summarising its own writing with no way back to
the source (arXiv:2502.00977). The measured cure is the cheap one: hand each
group a small extract — `EVIDENCE_TOKENS`, the same TextRank selection the
extractive engine makes — and ask it to correct the partials against that
rather than only to merge them. `evidence_for()` is
`transcript_for(summary.reduce(...))`: no new algorithm, and `summary.reduce()`
gains its second production caller.

**Chunks stay smaller than the context allows.** Faithfulness is U-shaped —
high at the start and the end of an input, measurably lower in the middle
(NAACL 2025) — so filling the window is a temptation to resist for a reason
that is not memory. `chunks()` also grows an `overlap`, which the spec assumed
existed and which did not: a decision taken across a boundary is otherwise half
in one pass and half in another. It defaults to `0.0`, so nothing changes for a
caller without a plan, and the plan sets it to 0.1.

### `summary.py` — the pre-reduction gets called

`estimate_tokens()` (231) goes from `// 4` to `/ 3.6`, with the docstring
saying the new number and staying honest that it is a heuristic. The direction
matters: underestimating produces chunks *larger* than the declared budget,
which is the failure this whole spec is about.

```python
def estimate_tokens(text):
    """Roughly how many tokens a piece of text is worth."""
    # 3.6 characters to the token: measured against the tokenizers of the
    # models in the catalogue on Italian prose, where 4 was optimistic.
```

`reduce()` (404) is not touched — it is correct, it is tested, and step 6 is
about *calling* it. The call site is in the model engines, before
`prompting.chunks()`, and the quota it discarded is reported as a **note**,
which `render()` (442) already prints under the title. No new field on
`Summary`, no new `Material`: pre-reduction returns a list of `Sentence`,
which is what engines already consume.

### `hardware.py` — two more facts about the machine

```python
def total_ram_gb():
    """Installed RAM in GiB, or None."""

def physical_cores():
    """Cores rather than threads, or None when they cannot be told apart."""
```

Same discipline as the rest of the module: nothing raises, nothing heavy is
imported, `None` means "could not tell". `summary()` (101) grows the total
beside the available figure — the ratio between them is what separates a small
machine from a busy one, and those are different diagnoses. The
`hardware.summary` message gains a placeholder in both catalogues.

### `summarizers/plan.py` — new, pure

```python
Plan = namedtuple("Plan", "model quant context_tokens kv_k kv_v chunk_tokens "
                          "chunk_overlap max_passes prereduce threads "
                          "est_ram_gb tier map_answer_tokens reduce_answer_tokens")

CATALOGUE = (...)   # one entry per model: ids, params, native context,
                    # weight bytes per quantisation, attention layers,
                    # KV heads, head dim, minimum tier
LEGACY_MODELS = ("Qwen/Qwen3-8B", "Qwen/Qwen3-4B", "Qwen/Qwen3-1.7B")

def kv_gb(entry, context_tokens, kv_k, kv_v):
    """The KV cache this model would hold at this context, in GiB."""

def kv_pair(value):
    """``"q8_0"`` or ``"q8_0/q4_0"`` -> ``(kv_k, kv_v)``."""

def estimate_ram_gb(entry, quant, context_tokens, kv_k, kv_v):
    """Weights plus KV cache plus the runtime's own overhead."""

def resolve_plan(engine, settings=None, ram=None, total=None, cores=None):
    """The plan to run, or None when this machine cannot hold the smallest
    model in the catalogue."""
```

The two lines that make this different from `recommend_model()`:

* the KV cache is **calculated** — `2 * n_attention_layers * n_kv_heads *
  head_dim * context_tokens * bytes_per_element`, with `f16 = 2`, `q8_0 ≈
  1.06`, `q4_0 ≈ 0.56`. `n_attention_layers`, not the layer count: in the
  hybrid models the catalogue prefers, only the attention layers hold a cache,
  and that is why they are in the catalogue;
* there is a **refusal**. `resolve_plan()` returning `None` means the caller
  loads nothing and falls back to the extractive engine with a note saying how
  much RAM was wanted and how much there was. On these machines the
  alternative to swap is a page of quoted sentences, which is an acceptable
  outcome; an OOM halfway through a job queue is not.

Degradation order, which the tests check as an *order* and not only as an
outcome: context to the next lower power of two (floor 2048) → the KV cache
`f16/f16` → `q8_0/q8_0` → `q8_0/q4_0` → weights `Q5_K_M` → `Q4_K_M` →
`Q3_K_M` → `Q2_K` → the tier below.

**The key is never quantised below `q8_0`.** Symmetric `q4_0` is not a gentle
degradation but a cliff — in a direct comparison on one model, `q8_0` held
81.6% similarity with the `f16` output and `q4_0` fell to 8.3%, while
`q8_0/q4_0` costs about 1.3%. The failure it causes is the one this program
can least afford: nothing crashes, nothing appears in a log, and the page is a
summary that reads like a summary and is not faithful to the recording. A
`kv_k` below `q8_0` asked for by hand is refused rather than honoured — the
single place where the plan does not let the person who typed it be wrong.

An explicit `summary_model` always wins over the plan, with a warning when it
exceeds the estimate. Somebody who typed a model name has the right to be
wrong; the default does not.

Memoised on `(round(total_ram_gb), physical_cores, device)` so a summary of
sixty chunks reads `/proc/meminfo` once.

### `summarizers/openvino_genai.py` — consumes the plan

* `MODELS` (63) and `recommend_model()` (115) go; the three Qwen3 ids move to
  `plan.LEGACY_MODELS`, still accepted by name so that a model already
  converted in somebody's model directory does not vanish, no longer chosen by
  `auto`. `tests/test_summarizers.py:245-258` is rewritten against
  `resolve_plan`.
* `summarize()` (243) takes its budget from `plan.chunk_tokens`, pre-reduces
  when `plan.prereduce` and the chunk count exceeds `plan.max_passes`, and
  runs the tree from step 2.
* `Pipeline.ask(self, system, user, max_new_tokens=None, think=False)` (226):
  a per-stage answer budget, and reasoning switched off during the map stage,
  where it buys nothing and can spend the entire budget before the answer
  starts. Off via the chat template's own parameter where the runtime exposes
  it, otherwise via the model's textual convention; where neither exists,
  leave the behaviour as it is and say so in a comment rather than pretending.
* `READING_BAND` (83) is split across the levels of the tree, not across the
  first level's chunks.
* `resolve_device()` (86) and the NPU skip are **untouched**. The reasoning in
  the docstring is right and the edge case already warns.

### `summarizers/llamacpp.py` — new engine

`ENGINES = (OPENVINO, LLAMACPP, EXTRACTIVE)` in `summarizers/__init__.py:39`,
with `_ALIASES` (46), `is_installed()` (59) and `load()` (95) extended. The
order is the argument: where there is an Intel device OpenVINO uses the iGPU
and wins; where there is not, `llama.cpp` on a GGUF beats the extractive
engine because it actually writes; extractive stays last, the one that always
works.

`is_installed(LLAMACPP)` is true for **either** path — `module_available
("llama_cpp")`, or a `llama-server` binary on `PATH` or at the configured
location. The binary is the zero-dependency route on a server; the binding is
the comfortable one on a desktop.

The engine is the model's life cycle and nothing else: prompts, chunking, the
reduce tree and parsing all come from `prompting`, exactly as the module's own
docstring promises. GGUF files are downloaded once into the managed model
directory under the existing `NAMESPACE = "summary"`, with the expected size
checked afterwards; there is **no conversion step**, which is half the reason
this engine exists. One process for the whole run. With `llama-server`: bound
to `127.0.0.1` only, an ephemeral port, a health check with backoff, a clean
shutdown in `finally`, and nothing on the network beyond loopback — the same
promise the rest of the program makes.

`environment-cpu.yml` gains a **commented** line saying what it costs. It is
the only way to get prose on that env, and it is offered rather than imposed.

### Partial cache

Map passes are deterministic (`do_sample = False`) and independent, so they
are cached under `cache_dir` on
`hash(chunk_text + PROMPT_VERSION + model_id + quant + stage)`. Two concrete
payoffs: re-running at a different length does not re-read the transcript with
the model, and an interrupted job resumes where it stopped.

### Surfaces

* **`config.py`**: `summary_context_tokens`, `summary_kv_type`,
  `summary_reduce_fanin`, `summary_tier` — all `None` by default, all in
  `SCHEMA` under `[summary]`. (See the open question about
  `summary_llama_server`.)
* **`cli.py`**: `--context-tokens`, `--kv-type`, `--tier` on `summarize`, and
  the new keys added to the `collect_cli_settings()` names tuple at lines
  867-868. `--hardware` (`command_hardware`, 719) prints the plan it would
  choose — tier, model, context, KV type, estimated RAM. That is the
  diagnostic that makes the policy inspectable without reading the code, and
  it is worth more than the documentation of it.
* **GUI and web**: no new control. The tier is the machine's decision, not the
  user's. It is shown: `gui/options.py:summary_state()` (478) composes the
  caption, and `cli.py:542` and `jobs.py:472` write the metadata it reads —
  both gain the tier and the pre-reduction share. Somebody reading a summary
  has the right to know it was written by a 1B model from 40% of the speech.
* **README** and **`docs/summary.md`**: three engines and the tier table.
  `docs/summary.md` currently documents `MODELS` as the `auto` policy (the
  "free memory / model / size at int4" table) and describes the reduce as a
  single second stage; both become wrong at steps 4 and 2 respectively.

## The commits

One commit per step, suite green at each.

| # | Commit | Files | Closes |
|---|---|---|---|
| 1 | this document | `docs/summary-lowram-plan.md` | — |
| 2 | the reduce tree and the per-stage budgets | `prompting.py`, `i18n.py`, `tests/test_summarizers.py` | 2.1 |
| 3 | total RAM and physical cores | `hardware.py`, `i18n.py`, tests | — |
| 4 | the execution plan | `summarizers/plan.py`, `tests/test_plan.py` | 2.3 |
| 5 | OpenVINO consumes the plan | `openvino_genai.py`, tests | — |
| 6 | pre-reduction, declared in a note | `openvino_genai.py`, `summary.py`, `summarizers/__init__.py` docstring, tests | 2.2 |
| 7 | `estimate_tokens` at 3.6 | `summary.py`, tests | 2.5 |
| 8 | the `llama.cpp` engine | `summarizers/llamacpp.py`, `__init__.py`, `i18n.py`, `envs/environment-cpu.yml`, tests | 2.4 |
| 9 | the partial cache | `openvino_genai.py`, `llamacpp.py`, a shared helper | — |
| 10 | config, CLI, metadata, docs | `config.py`, `cli.py`, `jobs.py`, `gui/options.py`, `README.md`, `docs/summary.md` | — |
| 11-bis | the catalogue validated in Italian | `summarizers/plan.py` (numbers only), this document | — |

Steps 2-4 are entirely pure code and close the worst defect without touching a
model. They are the best ratio of value to risk in the list, and they go
first.

Step 11-bis is the one the spec asks for last and argues for hardest: the
models in the catalogue are graded on English benchmarks, and Italian is where
small multilingual models fail first. Evalita-LLM's summarization task
(`evalitahf/summarization-fp`, Fanpage news, ROUGE) is the nearest thing to the
real job, and it reports that the correlation between size and performance in
Italian is only moderate — Pearson 0.48 in few-shot — so architecture and
training count as much as parameters. That is precisely the claim the catalogue
rests on when it prefers a 1-3 B hybrid to a dense model that does not fit, and
it is worth checking rather than assuming. It runs after step 8, because on
this machine only the GGUF path can run at all; it changes numbers in the
catalogue, not code.

## Open questions

These are the places where the spec and the code, or the spec and itself, do
not yet agree. Each needs a decision before the step that depends on it.
Questions 2 and 3 were settled when step 2 landed, and are kept here with their
answers because the reasoning is what a reader will want when the constants
look arbitrary.

**1. The page note is not an i18n string.** §3.4 asks for "una nuova voce
i18n" for the refusal note. But a note printed on the page belongs to the
language that was *spoken*, not to the interface: `extractive_note` lives in
`summary.HEADINGS`, deliberately, for the same reason the prompts do. An
Italian meeting summarised on an English desktop must not get an English
caveat under an Italian summary. **Proposal:** page notes (refusal,
pre-reduction quota) go into `HEADINGS` in both languages; the stderr warning
that a model was loaded against the estimate goes into `i18n`. This is the one
place where following the spec literally would break an existing invariant.

**2. `MAX_REDUCE_DEPTH = 3` and acceptance criterion 1 disagree unless depth
counts the map pass.** Criterion 1 wants 40 partials to produce **2** reduce
levels. With `fanin = 6`, 40 partials give 7 groups, then a root over 7 —
which is 2 levels but with one group above the fan-in; widening to 7 gives 6
groups then a root over 6, which is 2 levels with no group over the effective
fan-in, and matches the criterion's second half exactly. Reading
`MAX_REDUCE_DEPTH` as reduce levels only would permit 3 levels here and fail
the criterion. **Proposal:** `MAX_REDUCE_DEPTH` counts the map pass as the
first level, so it caps reduce levels at two; the constant keeps the spec's
name and the docstring says which it means. 7 partials then give 2 levels
(criterion 1), and 1 and 6 give one, as asked.

**3. Fixed answer budgets do not fit the `xs` tier, and criterion 2 cannot
pass with them.** At tier `xs`, `context_tokens = 2048`. With
`REDUCE_ANSWER_TOKENS = 1400` and `overhead = 400`, `budget_for(2048)` is 248
tokens — under one map answer of 500, so the root reduce prompt of criterion 2
cannot fit however the tree is shaped. **Proposal:** the answer budgets become
plan fields (`map_answer_tokens`, `reduce_answer_tokens` in the `Plan`
namedtuple above), with the module constants as the defaults for a caller with
room; at `xs` they are roughly 200 and 600. Then the fan-in follows from
arithmetic — `fanin_for(count, context_tokens, partial_tokens, answer_tokens)`
— with `REDUCE_FANIN` as its ceiling rather than its value. Without this,
criterion 2 is unsatisfiable and the tree only moves the overflow one level up.

**4. The `llama-server` path needs a configuration key.** §3.6 says "il
`PATH` o nel percorso configurato" but §3.8 lists no key for it. **Proposal:**
`("summary", "llama_server") -> summary_llama_server`, `None` by default, in
the same batch as the other four.

**5. Acceptance criterion 19 already exists.**
`tests/test_i18n.py::test_every_catalogue_defines_the_same_keys` compares the
key sets of both catalogues, and `test_placeholders_match_across_catalogues`
checks the placeholders too. Nothing to add; new keys are covered the moment
they are written.

**6. Where the partial cache lives.** Both model engines need it, and neither
is the right home. **Proposal:** `summarizers/partials.py`, pure except for
the file I/O, so the key derivation is testable without a model — same shape
as `prompting`. Decide at step 9, not before.

## What does not change

Named here so that no step quietly does it:

* the context is never widened to fit a transcript. The KV cache is the cost
  and it grows with the context; the whole transcript never enters a prompt on
  these machines;
* the NPU skip stays, with its reasoning;
* TextRank stays. It is numpy, it is instant, it has no model and no download,
  and it is not the bottleneck;
* no parallel map passes at tiers `xs` and `s`: the constraint is RAM, not
  time, and two prompts in flight are two KV caches;
* `llama_cpp` never becomes a hard dependency, and `environment-cpu.yml` stays
  light;
* nothing contacts the network during a summary. Downloading a model is a
  separate, announced step; inference does not leave the machine, and that is
  why the program exists;
* `summary.py` and `summarizers/prompting.py` import no runtime and no network
  client. Acceptance criterion 18 makes that a test rather than a habit;
* the extractive pre-filter is not replaced by prompt compression. LLMLingua
  and its relatives measure end-to-end gains of up to 18%, and only when prompt
  length, compression ratio and hardware line up — in exchange for a second
  model resident in RAM on a machine picked because it has little. TextRank on
  numpy costs nothing and loads nothing;
* no dependency on a llama.cpp fork for a KV cache type that is not upstream.
  TurboQuant would be the right lever and `llama-server` does not accept it;
  `kv_k` and `kv_v` are strings handed to the runtime, so the day a `tq*` type
  is accepted it is a catalogue entry and a re-estimate, and nothing else.
