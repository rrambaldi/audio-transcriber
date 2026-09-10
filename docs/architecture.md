# Architecture

The program is a pipeline with four stages and a few services around it. Every
module is small enough to read in one sitting, which is the main design
constraint.

```
             cli.py        web/ (a browser)     gui/ (a window)
                │                    \                /
                │                     jobs.py   one job at a time, in a thread
input file      │                          \      /
    │           └──────────────────────── pipeline.py   one run, shared by all three
    ├─ audio.py           decode to 16 kHz mono float32, via bundled ffmpeg
    │
    ├─ vocabularies.py    named keyword sets -> the initial prompt
    │
    ├─ transcription.py   pick a backend, warn about bad fits
    │      └─ backends/   openvino.py | faster_whisper.py  -> segments
    │
    ├─ diarization.py     optional: pyannote turns, mapped onto the segments
    │
    ├─ cleaning.py        drop hallucinations, collapse duplicates, paragraphs
    │
    └─ output             a .txt beside the input, or a library entry

summary.py               a library entry or a text file, summarised
    └─ summarizers/       openvino_genai.py (a local model, Intel devices)
                          extractive.py     (TextRank, no model)  -> summary.md
                          prompting.py      map/reduce, prompts, parsing
```

## The modules

| module | responsibility |
|---|---|
| `cli.py` | argument parsing, command dispatch, and nothing else that matters |
| `pipeline.py` | one transcription end to end, with no argparse and no HTTP in it |
| `vocabularies.py` | named keyword sets: discovery, shadowing, the prompt they build |
| `jobs.py` | the queue both interfaces submit to: one transcription at a time, in a worker thread |
| `web/` | the optional local interface: a JSON API and one static page |
| `gui/` | the optional desktop window; `gui/options.py` holds its decisions and imports no Qt |
| `recording.py` | recording from this machine's devices: audio systems, loopback, mixing — no Qt |
| `formatting.py` | durations, clock positions and file sizes, worded the same way everywhere |
| `audio.py` | one job: any container in, a numpy array out |
| `transcription.py` | orchestration — chooses an engine, checks it fits, returns a uniform result |
| `backends/` | the engine-specific code, and the rules for choosing between engines |
| `cleaning.py` | pure text functions; no I/O, no state, trivially testable |
| `diarization.py` | pyannote, plus mapping speakers onto transcribed segments |
| `summary.py` | sentences, ranking, selection and the page a summary is written on |
| `summarizers/` | the summary engines, and the rules for choosing between them |
| `library.py` | the on-disk format of a recording entry |
| `paths.py` | every filesystem location the program uses |
| `config.py` | `.env`, `config.toml`, and the precedence rules |
| `hardware.py` | what this machine can do |
| `i18n.py` | the message catalogue |
| `branding.py` | where the icon files are, so the browser and the window take theirs from one place |

## Decisions worth knowing about

**The core has two dependencies.** `numpy` and `imageio-ffmpeg`. Everything
heavy — CTranslate2, OpenVINO, PyTorch, pyannote — sits behind an extra and is
imported inside the function that needs it. That is why a GPU-less server can
install this in seconds, and why `audio-transcriber hardware` answers instantly.
It also means every such import needs a clear message for when the package is
absent.

**One run, three front ends.** `pipeline.py` holds the sequence — decode,
pre-flight, transcribe, clean, lay out, file — and the CLI, the web interface
and the desktop window all call it. None can drift from the others, and neither
interface layer contains any transcription logic: they queue, poll and display.

**What a run is for is decided in one place.** All three front ends ask the
same three-way question — text, who said what, subtitles — and none of them
works out what it implies: `config.resolve_output()` does, and it is called
from `config.resolve()` (the CLI's settings) and from `JobQueue.submit()`
(after the per-job overrides are merged). The alternative was three copies of
"text means no diarization and no subtitle files", which is three chances to
disagree. `config.output_of()` is the reverse reading, for a `config.toml`
written before the choice existed: the flags are read back into the answer they
describe.

**The queue belongs to neither interface.** `jobs.py` sits next to
`pipeline.py` rather than inside `web/`, because a window on a laptop and a
page in a browser need exactly the same thing: submit a file, run one job at a
time in a worker thread, report progress, file the result. The only difference
is what becomes of the source file — an upload or a recording the program made
is *moved* into the library entry, a file the user picked is *copied* — which
is why `submit()` takes a store mode.

**Recording is an engine, not a widget.** `recording.py` holds the device
enumeration, the WAV writing and the mixing of two sources, and it is handed
the two audio libraries as objects. That is what makes it testable on a machine
with no microphone, no PortAudio and no sound server: the tests pass fakes and
assert on the samples that reach the file. The Qt recorder stays as a fallback
for installations without the `[record]` extra, and the widget picks between
them.

**The window's decisions are not in the widgets.** Everything the desktop
interface actually decides — which menus to offer, what a table row says, how a
transcript is laid out in blocks — lives in `gui/options.py`, which imports no
Qt. That is what lets the test suite check the interface on a machine with no
display and no PySide6, and it keeps the widget modules to wiring.

**Nothing the browser sends becomes server configuration.** The web interface
selects installed keyword sets by name and validates the name against a slug
pattern; a visitor's own sets stay in their browser and travel as text with the
job. There is deliberately no endpoint that writes to the config directory.

**A worker thread must survive a `sys.exit`.** The modules underneath were
written for a command line and report a missing model or an undecodable file by
exiting. In the web queue that would kill the worker and leave a job stuck at
"running", so `SystemExit` is caught there like any other failure — a good
error message on a failed job.

**Detection never imports what it is detecting.** `hardware.py` uses
`importlib.util.find_spec` to ask whether a package exists, because importing
`openvino` or `torch` costs seconds. Only `openvino_devices()` and `has_cuda()`
actually import, and only when the answer requires it.

**Failing over beats failing.** A device that was requested but is absent
produces a warning and a CPU fallback, not an error. The whole point is that one
command line works on every machine.

**Warn, do not block.** The memory and core checks are advisory: the estimates
are approximate, and someone who knows their machine should not be stopped by a
guess.

**Timestamps are optional throughout.** Some models and settings return no
timestamps. Paragraph splitting, speaker assignment and the library format all
degrade to something sensible rather than crashing.

**One dict shape for segments.** `{"text", "start", "end"}`, plus `"speaker"`
after diarization. Both backends produce it; everything downstream consumes it.
That is the seam that makes the test suite need no models.

## Testing

`pytest` runs in about a second and needs no models, no GPU and no network.
Anything that would need an engine is tested through the pure function that
decides — `resolve_backend`, `resolve_device`, `resolve_compute_type`,
`warn_if_tight` — with the engine itself replaced. Keeping that seam intact is
the single most useful thing a contributor can do.

Two structural tests are worth pointing out, because they catch a class of bug
that review does not: one asserts that every message catalogue defines the same
keys, and another that a translation never renames a placeholder.
