# Summaries

An hour of meeting is fifteen thousand tokens of speech: repetitions, false
starts, three people agreeing in four different ways. A summary of it is two
separate jobs, and only the second one needs a language model.

**Selection** is deciding which sentences carry the meeting. That is arithmetic
on the words themselves — TextRank over a graph of sentence similarity — and it
runs in milliseconds on numpy, which this program already depends on.

**Writing** is turning what was selected into prose: an abstract, the decisions,
who agreed to do what. That is language work, and there is no way around a
model for it.

Splitting them is what makes summaries portable across very different machines.
Where there is an accelerator, a model reads the whole transcript and the
selection is a nicety. On a two-core server with no GPU, the same selection
cuts fifteen thousand tokens down to three thousand first, and a small model
that would have drowned in the raw stream produces something usable. Same
module, same page, different amount of help.

Three engines ship: one that does the selection and stops there, and two that
read what was selected and write about it — one on an Intel device, one on
plain CPU cores.

```bash
audio-transcriber summarize 2026-09-04_1530          # into the library entry
audio-transcriber summarize 2026-09-04 --length long
audio-transcriber summarize verbale.txt --print      # a bare transcript file
audio-transcriber summarize 2026-09-04 --out ~/riassunto.md
```

The first form writes `summary.md` into the entry, beside `transcript.txt`, and
records in `metadata.json` which engine wrote it and when. `--print` writes
nothing anywhere. A path instead of an entry id summarises a text file and
leaves `verbale.summary.md` beside it.

## From the window and the browser

Both put the summary in the entry it belongs to: a **Summary** tab beside the
transcript and the notes, with a button under it and, when this machine has
more than one engine, a menu saying which will write it. What comes back says
who wrote it and when, because a page that does not say is one somebody will
quote in a meeting without knowing whether a model or a sentence-picker
produced it.

The summary goes into **the same queue the transcriptions use**, and that is
deliberate rather than convenient: a model reading an hour of transcript is
minutes of the same cores a transcription needs, and running both at once
would make each slower without finishing either sooner. So a summary asked for
while a recording is being transcribed waits its turn, visible in Jobs like
everything else, and the panel says where it is instead of spinning. Closing
the browser does not stop it; the window keeps drawing while it happens.

In the browser the summary can also be downloaded as `.md` or thrown away —
the transcript is untouched either way, so another one can always be asked
for.

## What comes out

Markdown, for the same reason the transcript is a `.txt`: an entry has to stay
readable by a person with no program at all, and this is a page somebody pastes
into an email.

```markdown
# Riassunto: Riunione ISO

_extractive (TextRank), 2026-09-09 18:40 — da una registrazione di 62 minuti_

_Queste sono frasi prese dalla trascrizione, scelte per peso e lasciate come
sono state dette: non un testo scritto su di essa._

## In breve

Oggi parliamo del budget del progetto ISO. Sul budget dobbiamo decidere entro
venerdì.

## Punti chiave

- `[4:12]` **SPEAKER_01** La decisione sul budget spetta al comitato.
- `[18:30]` **SPEAKER_00** Vi mando il documento con il budget aggiornato.

## Termini ricorrenti

budget, progetto, comitato, documento, venerdì
```

The headings are in the language that was **spoken**, not the language of the
interface: somebody with an English desktop summarising an Italian meeting
wants an Italian page. They come from a table in `summary.py` rather than from
the message catalogue for exactly that reason.

Each point carries the minute it was said at, so it is a way back into the
recording rather than a claim to be believed on its own — the same anchor the
library page uses to jump the player to a segment.

## The engines

Chosen by name, the way transcription backends are, and `auto` picks the best
one this machine has:

```bash
audio-transcriber hardware        # says which engine 'auto' would pick here
audio-transcriber summarize 2026-09-04 --engine extractive
```

| engine | needs | what it produces |
|---|---|---|
| `openvino` | the `[summarize-ov]` extra, an Intel device, and a model | an abstract, key points, decisions and actions — prose about the recording |
| `llamacpp` | `llama-cpp-python`, or just the `llama-server` binary, and a GGUF | the same page, on a machine with no accelerator at all |
| `extractive` | nothing beyond numpy | the sentences that carry the transcript, as they were said |

`auto` takes them in that order, and the order is the argument: where there is
an Intel device OpenVINO uses the iGPU and wins; where there is not, a GGUF on
the CPU still writes real prose; the extractive engine is last because it is
the one that never fails.

`extractive` is honest about its limits, and the page says so under the title:
these are somebody's own words, selected. It cannot tell a decision from a
digression, and it will never write "the team agreed to ship on Friday" unless
somebody said roughly that. In exchange it is instant, needs nothing installed,
and runs on any machine — including in CI, which is why the whole surface
around the engines is testable without a model.

**Nothing here reaches the network.** The model runs on this machine, there is
no endpoint to configure, and the transcript does not leave the computer it was
made on. A summary is not a good enough reason to change that.

## The model engine

```bash
pip install "audio-transcriber-ov[summarize-ov]"
audio-transcriber summarize 2026-09-04                      # auto everything
audio-transcriber summarize 2026-09-04 --model Qwen/Qwen3-4B
audio-transcriber summarize 2026-09-04 --model ~/models/mine-ov --device GPU
```

The first run converts the model to OpenVINO IR at int4 and keeps it under the
managed model directory; every run after that loads it. It downloads several
gigabytes, once, and says so before starting. A directory that is already
OpenVINO IR is used as it is — and then only `openvino-genai` is needed, not
the conversion half of the extra.

`--model auto` asks the plan, which is described below. Any Hugging Face id
works in place of it, and so does the path of a directory already converted to
OpenVINO IR.

### Why not the NPU

It is there, it sips power, and OpenVINO can see it — and `auto` still will not
choose it. The NPU's LLM pipeline runs on static shapes with the prompt capped
at 1024 tokens by default and 8K at the very best; an hour of transcript is
nearer fifteen thousand, and on Qwen3 the model does not even compile above 8K.
In generation an 8B on the NPU runs at around ten tokens a second, which is
slower than the same machine's iGPU. It is the right accelerator for small
constant work and the wrong one for reading a meeting.

`--device NPU` is still honoured — somebody summarising a five-minute note on
battery has a case — with a warning that says the above in three lines.

### What the page is made of

The page is **sections the recording produced**, one heading per subject, and
under each of them prose written from that subject's own notes. A reading pass
does not write prose at all: it writes notes, one thing said each, typed and
dated. The notes are grouped afterwards, on the whole recording at once, and
then every section is written from its own group — nothing is ever asked to
hold the whole meeting in one answer.

That last sentence is the whole point, and it has a number. The shape before
this one read the transcript in parts and folded the parts together, and the
fold is where a recording goes missing: on the same twenty-two minute meeting,
with the same model and the same reading passes, the old shape **read 41% of
the minutes and printed 14%**. The new one read 36% and printed 36% — the same
measurement, taken twice on two different engines, and nothing lost in
between. What reaches the page is what was read.

`shape = "headings"` brings the old one back: an abstract, key points,
decisions, actions, recurring terms, and the fold described below that makes
them.

**How much a pass is given to read** decides how much of the recording ends up
on the page, and it is not the number the window allows. A pass does not read
proportionally to what it is handed: given eleven minutes of meeting it writes
down twelve things and stops. The same recording, the same model, one number
changed:

| tokens per pass | passes | notes | minutes on the page | time |
| ---: | ---: | ---: | ---: | ---: |
| 4500 | 2 | 21 | 8 of 22 | 83 s |
| 2000 | 4 | 58 | 15 of 22 | 152 s |
| **1200** | 7 | 82 | **21 of 22** | 187 s |
| 700 | 12 | 141 | 21 of 22 | 326 s |

So a reading pass gets 1200 tokens, whatever the window would hold. Below that
the extra passes buy time and repetition rather than recording — a quarter of
the notes at 700 were things already written down. `chunk_tokens` in
`[summary]` overrides it, which is how the table was made.

**A finer copy of the same model is not a better reader of it**, which is
worth knowing before spending seven gigabytes finding out. The same recording
again, only the precision of the weights changed — and, in the last row, the
allowance a pass may answer in:

| weights | minutes on the page | distinct notes | repeated | passes cut off | time |
| :--- | ---: | ---: | ---: | ---: | ---: |
| **Q4_K_M** | **21 of 22** | 82 | 6 | 0 | 182 s |
| Q6_K | 17 of 22 | 87 | 22 | 2 | — |
| Q8_0 | 19 of 22 | 77 | 16 | 1 | 184 s |
| Q8_0, 900-token answers | 20 of 22 | 83 | 22 | 0 | 178 s |

Two things that table is careful about. **The finer file is not slower**: the
first measurement said it was seven times slower and that was a five gigabyte
download inside the clock — read to the end of this section before believing
a number of this kind. And **minutes are a coarse ruler**: coverage counts
minute-long buckets, so on a twenty-two minute recording it moves in steps of
4.5 points and one bucket is not a finding.

What is left is the repetition, which is not quantised and does not move: the
coarse file wrote 82 notes of which 6 repeated something, the fine one 83 of
which 22 did. The mechanism is visible in the passes — the finer files write
*longer* notes, spend the pass's allowance sooner and get cut off mid-list,
and where the allowance was raised to stop that, they filled it with the same
things said again. The coarse file is terser, and terser is the job.

`quant` exists for a machine where that goes the other way. It is a thing to
measure on your own recordings, not to assume.

On a machine small enough to have a limit on how many passes it will spend,
that limit is scaled by the same factor. What a tier decides is how much
transcript this machine should read, not how finely; without the scaling,
reading in smaller pieces would hit the cap and the transcript would be cut to
fit, spending the coverage the smaller chunk just bought.

### How it reads a long transcript

A transcript that fits in one pass goes to the model in one prompt. A longer
one is cut into chunks on sentence boundaries, each summarised on its own, and
the chunk summaries folded together — map and reduce, against one loaded
model. Every line of transcript the model sees carries the minute it was said
at, so it can cite them, and the citations are parsed back out into the same
anchors the extractive engine produces.

The folding is **a tree, not a star**, and that is the difference between
working and not on a small machine. A single reduce prompt holding every
partial summary grows with the length of the recording: fifteen chunks of a
ninety-thousand-token meeting is a twenty-one-thousand-token prompt, handed to
the model that was chosen precisely because the machine is small. So the
partials are folded in groups, the groups folded again, and the fan-in is
whatever that model's context can actually hold.

Each level answers under its own budget. A chunk summary is a bulleted list;
only the last pass writes the page. And reasoning is switched off while
reading a chunk — the token budget is the whole budget, so a model that
narrates for all of it is cut off before the answer starts, which arrives as
"returned nothing usable" several minutes later.

**Every folding pass is handed a piece of the transcript**, not only the
partials it is merging. From the second level up, the model is summarising its
own writing and has no way back to what was said; recursive merging amplifies
whatever it invented one level down. The fix is the selection this program
already has: a few hundred tokens of the highest-weighted original sentences,
with the instruction to correct the partials against them.

Chunks are also deliberately smaller than the window allows, and they overlap
by a tenth. Faithfulness is highest at the start and the end of an input and
measurably lower in the middle, so filling the context is a temptation rather
than an optimisation; and a decision taken across a chunk boundary would
otherwise be half in one pass and half in another.

Map passes are cached under the cache directory, keyed by the chunk, the
model, its precision and a version of the prompts. Asking for the same
recording at a different length re-reads nothing, and a job interrupted
halfway resumes where it stopped. Changing a prompt bumps the version, because
a cache that survives the change is not a saving but a bug that accumulates.

Several habits of language models are handled rather than hoped away, and
every one of them was found by running a small model rather than by reasoning
about it.

A reasoning model's `<think>` block never reaches the page — including one
with no end, which is not a preamble to an answer but the whole of what there
was room for. If the model was still thinking when its allowance ran out, it
is asked again with room, once: that is a different failure from a model too
small for the job, and from the outside they look identical.

A model too small answers by repeating the question. The transcript is fenced
with a marker, so an answer that gives it back is recognised — even when the
model has reflowed it onto one line, which is what they do. A chunk whose pass
came back as the question still contributes: it contributes its own
highest-weighted sentences, arithmetic instead of a model.

A model that copies the instructions is recognised too. The scaffold is this
program's own text, so a line of it coming back is not something the model
wrote about the recording; "one paragraph of three or four lines" printed as
the summary is a page that looks finished and says nothing.

And a heading written as `**Punti chiave**` rather than `## Punti chiave` is
still a heading. Left unrecognised, every section the model wrote lands in the
abstract.

So is a heading in the wrong language, or one that stops half way. A small
model asked for Italian headings answers in the nearest language it knows
better: a real run came back with `Decisões`, `Ações`, `Requisitos` —
Portuguese, every one of them — and another with `Questioni apert`, which is
Italian with the end missing and which no catalogue of words would ever hold.
A heading close enough to one that was asked for counts as that one; a word
that is close to nothing, `Riassunto` or `Altro`, still counts as nothing,
because guessing there would file bullets under a heading nobody wrote.

When nothing survives all of that, you get "returned nothing usable — try
another model, or `--engine extractive`" instead of a page that looks like a
summary and is the transcript again.

## Choosing a model, and refusing to

`auto` is not a table of names against numbers of free gigabytes. It is an
estimate, and the part everybody leaves out is the KV cache: the memory the
model needs to hold the attention keys and values for the prompt it is
reading. It grows with the context, and on a small machine it is the
difference between a model that runs and one that swaps.

The estimate is weights plus cache plus what the runtime costs, and the cache
is counted only over the **attention** layers. That is why the catalogue
prefers hybrid models: Granite 4.0 H-Micro keeps a cache in four of its forty
layers, a tenth of what a dense model of the same depth would keep.

| size class | usable memory | model | context | cache (key/value) | pre-reduction |
|---|---|---|---|---|---|
| `xs` | 1.0–2.0 GB | LFM2.5-1.2B Q4_K_M | 2048 | q8_0 / q4_0 | always |
| `s` | 2.0–3.5 GB | MiniCPM5-2B Q4_K_M | 4096 | q8_0 / q8_0 | above 4 passes |
| `m` | 3.5–6.0 GB | Granite 4.0 H-Micro Q4_K_M | 8192 | q8_0 / q8_0 | above 8 passes |
| `l` | above 6.0 GB | Qwen3.5-4B, or Granite 4.0 H-Tiny above 8 GB | 16384 | f16 / f16 | no |

"Usable" is the free memory less a reserve for the operating system and for
the rest of this program, which is holding a transcript while the model runs.

The smallest class is LFM2.5-1.2B and not MiniCPM5-1B, and the reason is worth
recording: asked in Italian to summarise a news article in three sentences,
MiniCPM5-1B at Q4_K_M returns the article. Not a poor summary — no summary: it
copies the input, on the simplest instruction that can be given. Both are in
the catalogue and either can be asked for by name; only one of them is chosen.
That is what the Italian screening in
[summary-lowram-plan.md](summary-lowram-plan.md) is for, and it is why a
catalogue picked on English benchmarks is not enough.

When a class does not quite fit, things are given up in the order they cost
least: the context first, then the precision of the cache, then the precision
of the weights, then the class below. **The key is never quantised below
`q8_0`.** A symmetric four-bit cache is a cliff rather than a slope — against
the same model's own full-precision output, an eight-bit cache holds around
82% similarity and a four-bit one falls to about 8%, while quantising only the
values costs on the order of a percent. It is the worst failure available
here: nothing crashes, nothing reaches a log, and the page is a summary that
reads like a summary and is not faithful to the recording.

And when nothing fits at all, **nothing is loaded**. The page is written by
the extractive engine and says why, with both figures:

```
_Nessun modello entra nella memoria di questa macchina (1.0 GB richiesti,
0.9 GB liberi): questa pagina non l'ha scritta nessuno._
```

A page of somebody's own words is an acceptable outcome on such a machine. An
out-of-memory kill halfway through a queue of jobs is not.

`audio-transcriber hardware` prints the plan it would choose here — the class,
the model, the context, the cache and the estimate — which is the only way to
inspect this policy without reading the code:

```
engine that '--engine auto' would pick: llamacpp
  plan for this machine: tier s, MiniCPM5-2B Q4_K_M, context 4096,
  cache q8_0/q8_0, about 1.9 GB
```

A model named by hand always wins over the plan, with a warning when it
exceeds the estimate. Somebody who typed a model name has the right to be
wrong about their own machine; the default does not.

### When the transcript is longer than the passes allowed

On the smaller classes, reading everything would take more passes than the
machine should spend — and each pass is minutes without an accelerator. So the
transcript is selected down first, by the same TextRank the extractive engine
uses, to what the allowed passes can hold. The page says what share arrived:

```
_Riassunto da una selezione del 38% della trascrizione, scelta per peso:
l'intera trascrizione non entra nel modello di questa macchina._
```

A summary written from two fifths of what was said is still a summary, and a
good one, because the selection is by weight rather than by truncation. But
silence about it would be the one dishonest thing on the page.

## The engine without an accelerator

```bash
pip install llama-cpp-python          # or: put 'llama-server' on the PATH
audio-transcriber summarize 2026-09-04 --engine llamacpp
```

For the machine this whole design is about: a server with two cores, no GPU
and a few gigabytes of memory. Nothing is converted — a GGUF is downloaded
already quantised and loaded as it arrives, so there is no `transformers`, no
`optimum`, and no conversion step that needs more memory than the model. The
weights are mapped from disk rather than read into memory, so a model larger
than the free memory is slow rather than fatal.

Either way in will do. The Python binding is one `pip install` on a desktop;
the `llama-server` binary is a single file with no Python at all, which is
what somebody administering a server would rather deploy — name it in
`config.toml` if it is not on the `PATH`. When the binary is used it is bound
to `127.0.0.1` on a port the kernel picked, it lives for exactly one summary,
and it is stopped in a `finally`. This must not become a way to serve a model
to a network.

The model is downloaded once, into the managed model directory, and the
download says so before it starts. It is the only moment this engine uses the
network.

### It is also the engine *with* an accelerator

llama.cpp is built against a backend — Vulkan, SYCL, OpenVINO, CUDA — and a
build that has one runs a GGUF on that device without converting anything.
This matters more than it sounds: the OpenVINO engine above needs the model
turned into IR first, and it is that conversion, not the hardware, that the
larger models fail. So on an Intel laptop a Vulkan build of `llama-server`
reaches models the other engine cannot open at all.

Which device is a question put to the binary, not guessed here, because two
builds on one machine answer differently:

```
> llama-server --list-devices
Available devices:
  Vulkan0: Intel(R) Arc(TM) 140V GPU (16GB) (18413 MiB, 17645 MiB free)
```

Whatever it lists, the first thing that is not a processor is used, and every
layer goes on it — half a model on an integrated GPU is slower than all of it
on the cores, because each token then crosses the bus twice. `device` in the
configuration overrides that: `cpu` to stay on the processor, or a name from
that list (`vulkan` will do for `Vulkan0`). A build too old for the flag, or
one with no backend, answers nothing and runs where it always did.

One warning about the memory those lines report. An integrated GPU has no
memory of its own: the 17 GB Vulkan offers above is a budget against the same
RAM everything else is using, of which that machine had 8 GB free. The plan
sizes the model against *free system memory* for exactly this reason, and
will not pick a bigger one because a driver was optimistic.

## How long

Three lengths, by name rather than by number, the way the subtitle presets
work. What the name does depends on which engine is writing, because the two
have nothing in common but the name.

**The extractive engine** keeps a share of the transcript's own sentences:

| length | share of the sentences | fewest | most |
|---|---|---|---|
| `short` | 5% | 3 | 8 |
| `medium` | 10% | 5 | 15 |
| `long` | 18% | 8 | 30 |

The floor keeps a five-minute note from summarising to nothing; the ceiling
keeps an all-day recording from producing a second transcript.

**A model engine** changes the question it asks, and never the answer it
got. A page is not made short by cutting its prose off at a word count —
that produces a broken section rather than a brief one — so:

| length | a section is asked for as | sections at most | opening paragraph |
|---|---|---|---|
| `short` | one paragraph of one or two sentences, no list | 5 | one or two sentences |
| `medium` | a paragraph and a list of the detail | 12 | two to four sentences |
| `long` | a paragraph and a bullet per note | 18 | four to six sentences |

Three things this deliberately does not do. It does not read less: every
length reads the whole recording in the same passes, which is why asking
again for a longer page costs the writing only and not the reading — the
pass cache is keyed without the length on purpose. It does not keep fewer
notes: a short page has the same notes grouped into fewer, coarser sections,
and none of them are thrown away. And it does not shorten the decisions or
the actions: there were as many of them as there were, and a short page that
leaves two of them out is not shorter, it is wrong.

On the old `headings` shape the same names move the opening paragraph and
the key points, and leave decisions and actions alone for the same reason.

## Configuration

```toml
[summary]
# auto | openvino | llamacpp | extractive
engine = "auto"
# short | medium | long   (see "How long": it works on every engine)
length = "medium"
# auto, a Hugging Face id, a GGUF file, or a converted directory
model = "auto"
# auto | CPU | GPU | NPU        (the OpenVINO engine)
# auto | cpu | Vulkan0 | SYCL0  (llama.cpp: what --list-devices printed)
device = "auto"
# tokens of transcript per pass; unset, the plan works it out
chunk_tokens = 6000
# sections | headings   (sections: the page the recording produced)
shape = "sections"
# Q8_0 | Q6_K | Q5_K_M | Q4_K_M; unset, the best one that fits
quant = "Q8_0"

# Everything below is worked out from this machine and is here for a
# controlled deployment, or to reproduce somebody else's result.
tier = "s"                 # force a size class: xs | s | m | l
context_tokens = 4096      # bigger is not better: the cache grows with it
kv_type = "q8_0/q4_0"      # key/value, or one type for both
reduce_fanin = 6           # partials merged by one folding pass
llama_server = "/opt/llama.cpp/llama-server"   # or C:\\llama\\vulkan-x64\\llama-server.exe
```

`--engine`, `--length`, `--model`, `--device`, `--context-tokens`, `--kv-type`,
`--quant` and `--tier` on the command line win over all of it.

## The reduction stage

`summary.reduce(sentences, target_tokens)` ranks the transcript, keeps the best
sentences until the token budget runs out, and returns them in the order they
were spoken. It is the arithmetic the model engines lean on, three times over:
to cut a transcript down before reading it, to build the extract every folding
pass checks itself against, and — through the extractive engine — to write the
page when no model fits at all. An engine with room to spare skips the first
of those and reads everything.

The token count is a heuristic, but a measured one. Counted with the
tokenizers of the models above, over spoken Italian of the shape this program
produces, the rate is between 2.8 and 3.2 characters per token; the code uses
the worst of them. English really is around 4.6. The four-characters-to-the-
token figure everybody quotes is wrong here by a third, and wrong in the
direction that produces chunks larger than the budget claims — which is the
overflow this whole design exists to avoid. A language nobody named is charged
the careful rate.

## What is deliberately missing

- **No cloud, and no endpoint.** See above; this is a property of the program,
  not a default.
- **No editing of anybody's words.** The extractive engine quotes; it does not
  paraphrase. When a model engine arrives it will write prose, and the page
  will say which engine wrote it — that line is not decoration.
- **No summary of a summary.** The model is asked to leave a section out
  rather than fill it, and an empty section is left off the page instead of
  printing a heading over nothing.
- **Nothing automatic yet.** A summary is asked for. Summarising every
  transcription as it finishes is a setting worth having, but on a two-core
  server it would sit in the same queue as the transcriptions, and that is a
  decision to make deliberately rather than by default.
