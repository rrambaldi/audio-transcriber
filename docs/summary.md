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

Today one engine ships — the one that does the selection and stops there.

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
| `extractive` | nothing beyond numpy | the sentences that carry the transcript, as they were said |

`extractive` is honest about its limits, and the page says so under the title:
these are somebody's own words, selected. It cannot tell a decision from a
digression, and it will never write "the team agreed to ship on Friday" unless
somebody said roughly that. In exchange it is instant, needs nothing installed,
and runs on any machine — including in CI, which is why the whole surface
around the engines is testable without a model.

More engines are planned, and the shape of `summarizers/` is the promise that
adding one is a single file: a local model on an Intel iGPU for the summaries
that have to be good, a small quantised model in-process for a machine with no
GPU. **Nothing here will ever reach the network.** The transcript does not
leave the machine it was made on, and a summary is not a good enough reason to
change that.

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
# auto | extractive
engine = "auto"
# short | medium | long
length = "medium"
```

`--engine` and `--length` on the command line win over both.

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
- **Nothing automatic yet.** A summary is asked for. Summarising every
  transcription as it finishes is a setting worth having, but on a two-core
  server it would sit in the same queue as the transcriptions, and that is a
  decision to make deliberately rather than by default.
