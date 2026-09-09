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

Two engines ship: one that does the selection and stops there, and one that
reads the whole thing and writes.

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
| `extractive` | nothing beyond numpy | the sentences that carry the transcript, as they were said |

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

`--model auto` picks the largest recommended model that fits in this machine's
free memory, because on an integrated GPU the model lives in system memory
whichever device runs it:

| free memory | model | size at int4 |
|---|---|---|
| 9 GB and up | `Qwen/Qwen3-8B` | ~5 GB |
| 5 GB and up | `Qwen/Qwen3-4B` | ~2.5 GB |
| below that | `Qwen/Qwen3-1.7B` | ~1.1 GB |

Any Hugging Face id works in place of those.

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

### How it reads a long transcript

A transcript that fits in `chunk_tokens` (6000 by default) goes to the model in
one prompt. A longer one is cut into chunks on sentence boundaries, each
summarised on its own, and the chunk summaries summarised together — map and
reduce, against one loaded model. Every line of transcript the model sees
carries the minute it was said at, so it can cite them, and the citations are
parsed back out into the same anchors the extractive engine produces.

Two habits of language models are handled rather than hoped away. A reasoning
model's `<think>` block never reaches the page. And a model too small for the
job answers by repeating the question: the transcript in the prompt is fenced
with a marker, so an answer that echoes it is recognised as an echo, and you
get "returned nothing usable — try another model, or `--engine extractive`"
instead of a page that looks like a summary and is the transcript again.

## How long

Three lengths, by name rather than by number, the way the subtitle presets
work:

| length | share of the sentences | fewest | most |
|---|---|---|---|
| `short` | 5% | 3 | 8 |
| `medium` | 10% | 5 | 15 |
| `long` | 18% | 8 | 30 |

The floor keeps a five-minute note from summarising to nothing; the ceiling
keeps an all-day recording from producing a second transcript.

## Configuration

```toml
[summary]
# auto | openvino | extractive
engine = "auto"
# short | medium | long  (the extractive engine)
length = "medium"
# auto, a Hugging Face id, or a converted directory
model = "auto"
# auto | CPU | GPU | NPU
device = "auto"
# tokens of transcript per pass; lower it for a small-context model
chunk_tokens = 6000
```

`--engine`, `--length`, `--model` and `--device` on the command line win over
all of it.

## The reduction stage

`summary.reduce(sentences, target_tokens)` is the part the future model engines
depend on: it ranks the transcript, keeps the best sentences until the token
budget runs out, and returns them in the order they were spoken. An engine with
room to spare skips it and reads everything.

The token count is four characters to the token — close enough for "does this
fit", wrong enough that nothing should be promised on it.

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
