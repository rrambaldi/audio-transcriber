<p align="center">
  <img src="docs/assets/banner.png" srcset="docs/assets/banner@2x.png 2x"
       width="820" alt="audio-transcriber — local audio and video transcription, nothing leaves your machine">
</p>

# audio-transcriber

Turn audio and video recordings into readable text — **entirely on your
machine**. Whisper runs either on an **Intel iGPU via OpenVINO** or on a plain
**CPU-only server via faster-whisper**, with optional **speaker diarization**
("who said what") through pyannote. No cloud, no API keys for transcription,
your recordings never leave your computer.

Built for meeting recordings you want to summarize afterwards.

```bash
audio-transcriber meeting.mp4        # -> meeting.txt
```

## Features

- **One command.** Point it at a file; it works out the rest.
- **Runs anywhere.** A laptop with an Intel iGPU or NPU, a headless server with
  no GPU at all, or a CUDA machine — the backend and device are detected, and a
  device that is not there falls back instead of failing.
- **Anything ffmpeg reads** — wav, mp3, m4a, mp4, mkv, flac. ffmpeg is bundled,
  nothing to install.
- **The model fits the machine.** `--model auto`, the default, picks the
  largest Whisper that this computer can run at a sensible speed — `small` on a
  two-core server, `large-v3` on a workstation or a GPU. Name one yourself and
  it is used as asked.
- **Readable output.** Whisper's silence hallucinations ("Thanks for
  watching...") and chunk-overlap duplicates are removed, and the text is
  grouped into paragraphs on the pauses in speech.
- **One choice up front**: text, text with who said what, or subtitles.
  `--output` on the command line, three buttons in the window and in the
  browser; it settles the options that belong to the other two answers.
- **Optional diarization** with pyannote, including a fully **offline** mode.
- **A library**, if you want one: each transcription filed as a self-contained
  folder with the recording, the transcript, timestamps and your notes.
- **Subtitles**, if you want them: the transcript cut into cues by the numbers
  the trade uses — characters per line, reading speed, minimum and maximum
  duration — as `.srt` or `.vtt`, with named presets from Netflix's guide to
  vertical video. See [docs/subtitles.md](docs/subtitles.md).
- **Summaries**, if you want them, as a `summary.md` in the library entry.
  With a local model — on an Intel iGPU through OpenVINO, or on plain CPU
  cores through llama.cpp: an abstract, the decisions, and who agreed to do
  what, each carrying the minute it was said at. The model is chosen by what
  the machine can actually hold, counting the memory the attention cache will
  take, and on a machine that can hold none it says so and quotes the
  transcript instead. Nothing is sent anywhere — the model runs on your
  computer and there is no endpoint to configure. See
  [docs/summary.md](docs/summary.md).
- **Keyword sets** to stop it mangling your technical terms — named, listed,
  and selectable from the command line or the web page.
- **A local web interface**, optional: drop a file in the browser or record
  from it, watch the job, then read, search and annotate the library.
- **A desktop window**, optional, on Windows, Linux and macOS: the same thing
  in Qt, with a player that
  reads along with the transcript and a recorder that can capture the
  microphone, what the speakers are playing, or both mixed together — which is
  how you record a call.
- English and Italian interface.

## Install

Pick the engine that matches your machine. The core package is deliberately
light, so a server never pulls in OpenVINO and a laptop never pulls in
CTranslate2 unless you want both.

```bash
git clone https://github.com/rrambaldi/audio-transcriber
cd audio-transcriber

pip install -e ".[cpu]"        # server, or any machine without a GPU
pip install -e ".[openvino]"   # PC with an Intel iGPU or NPU
pip install -e ".[all]"        # everything: both engines, diarization, web,
                               # the window and its recorder
pip install -e ".[summarize-ov]"   # summaries written by a model, on an Intel device
pip install -e ".[summarize-cpp]"  # the same, on plain CPU cores (builds from source)
pip install -e ".[diarize]"    # diarization, on top of either
pip install -e ".[web]"        # the local web interface, on top of either
pip install -e ".[gui]"        # the desktop window (Qt), on top of either
pip install -e ".[record]"     # host-API choice, loopback and mixing for the window
pip install -e ".[cpu,gui,record,dev]"   # and everything a contributor needs
```

There is a script for all of this, run from the checkout: **`./install.sh`** on
Linux and macOS, **`install.cmd`** on Windows. Both pull, install into the
right environment, check what usually goes wrong on that platform, and print
what to run. Pass the extras if the default is not yours — `openvino,gui,record`
on Windows, `cpu,gui,record` on Linux and macOS:

```bash
./install.sh cpu,gui            # Linux, macOS
install.cmd openvino,gui        # Windows
```

`install.sh` uses the environment already active, or a `.venv` in the checkout
which it creates, and names the system libraries Qt and PortAudio need when
they turn out to be missing. `install.cmd` activates the conda environment it
wants (`srt-ov2` by default, `AT_ENV` to name another) and leaves the window in
it, and it checks the two things that go wrong on Windows: a Qt inherited from
conda shadowing the one pip installs, and a PySide6 without QtMultimedia. Both
refuse conda's own `base`.

Python 3.11 or newer. Conda users: `envs/environment-cpu.yml` for a GPU-less
server, `envs/environment-intel.yml` for an Intel machine. Let conda provide
the interpreter and pip provide the rest — a Qt installed with
`conda install pyside6` cannot be completed or replaced by pip afterwards, see
[docs/gui.md](docs/gui.md).

Afterwards, **`./run.sh`** and **`run.cmd`** are the same idea for running it:
they get into the environment first — the conda one (`srt-ov2`, or `AT_ENV`),
else on Linux and macOS whatever virtualenv the checkout has — and then hand
everything they were given to the program, so `run.cmd hardware` and
`./run.sh meeting.mp4 --summary` work from a shell that knows nothing about it. With no arguments they open the
window, which is what a double-click on `run.cmd` does.

Not sure what your machine can do?

```bash
$ audio-transcriber hardware
CPU: 8 cores | free RAM: 21.4 GiB | OpenVINO: CPU, GPU.0 | CUDA: no
backend that '--backend auto' would pick: openvino
model that '--model auto' would pick: large-v3
```

## Usage

```bash
# plain transcription; Italian by default, backend and device auto-detected
audio-transcriber meeting.wav

# say what the run is for, and it settles the rest:
#   text (just the words) | speakers (who said what) | subtitles (cues, .srt)
audio-transcriber meeting.wav --output speakers --speakers 3
audio-transcriber talk.mp4 --output subtitles --subtitle-preset netflix

# or set the flags yourself: who said what, with 3 known speakers
audio-transcriber meeting.wav --diarize --speakers 3

# GPU-less server: CPU engine, lighter model
audio-transcriber meeting.wav --backend faster-whisper --model small

# force the Intel iGPU
audio-transcriber meeting.wav --backend openvino --device GPU

# another language, a specific output file
audio-transcriber talk.mp4 --language en --out talk.txt

# with a keyword set, so the technical terms survive
audio-transcriber meeting.wav --vocab iso27001-it

# in Italian, if you prefer
audio-transcriber riunione.wav --lang it
```

`audio-transcriber --help` lists everything. The other commands:

```bash
audio-transcriber hardware      # what this machine can do
audio-transcriber paths         # where models, config and recordings are kept
audio-transcriber config init   # write a commented config.toml
audio-transcriber summarize 2026-09-04    # the short version of one of them
audio-transcriber library list  # browse what you have transcribed
audio-transcriber vocab list    # the keyword sets you can select
audio-transcriber web           # the same things, from a browser
```

## The library

By default the transcript is written next to the input file. With `--library`
it is instead filed as a self-contained folder:

```bash
$ audio-transcriber meeting.mp4 --library --title "Weekly sync"
$ audio-transcriber library list
ID                          DATE        LENGTH  WORDS  TITLE
--------------------------  ----------  ------  -----  -----------
2026-09-04_1530_weekly-syn  2026-09-04  52m 10s  7841  Weekly sync
```

Each entry holds the original recording, `transcript.txt`, `transcript.json`
(segments with timestamps and speakers), `notes.md` for you to write in,
`summary.md` if you asked for one, and `metadata.json` recording how it was
transcribed and how long it took.
Everything is plain text or JSON, readable without this program.

```bash
audio-transcriber library show 2026-09-04
audio-transcriber library search "risk assessment"
```

See [docs/data-layout.md](docs/data-layout.md) for the format and for how to
put the library somewhere else.

## Configuration

Nothing needs configuring, but if you get tired of repeating options:

```bash
audio-transcriber config init     # writes a commented config.toml
audio-transcriber config show     # the settings currently in effect
```

Command-line options always win over the file. Models, configuration and the
library live in your platform's standard per-user locations; run
`audio-transcriber paths` to see where, and set `AUDIO_TRANSCRIBER_HOME` to put
all of it under one folder — handy in a container or on a server volume.

## Keyword sets

Whisper mangles recurring technical terms unless you tell it they exist. Give it
a list of the words you know will come up, saved under a name:

```bash
$ audio-transcriber vocab list
NAME                     SOURCE   LANG  TERMS  TITLE
-----------------------  -------  ----  -----  ------------------------------
cybersecurity-it         bundled  it    29     Cybersecurity operativa
finance-controllo-it     bundled  it    27     Finance e controllo di gestione
riunione-generale-it     bundled  it    24     Riunioni di lavoro (generico)
sviluppo-software-it     bundled  it    31     Sviluppo software
...

$ audio-transcriber meeting.wav --vocab riunione-generale-it,sviluppo-software-it
```

Nineteen Italian sets ship with the package — one per kind of meeting, from IT
and security to marketing, sales, finance, HR and legal — short on purpose so
that the general one can be combined with the subject at hand. Write your own
with `audio-transcriber vocab new my-terms`: it lands in your config directory
as a text file to edit. `vocabulary = "..."` in `config.toml` applies a set to
every run, and `--prompt` / `--prompt-file` still work for a one-off list.

In the web interface the installed sets appear as a menu, and you can keep your
own private sets in the browser. Details, and the reasoning, in
[docs/vocabularies.md](docs/vocabularies.md).

## The web interface

```bash
pip install -e ".[web]"
audio-transcriber web
# Web interface: http://127.0.0.1:8765  (Ctrl-C to stop)
```

Drop a recording on the page — or record one straight from the browser — pick
the model and the keyword sets, and watch the job: transcriptions run in the
background, one at a time, and each finished one is filed in the library. The
library is browsable from the same page: search the transcripts, play the
recording while reading along, jump to a moment from its timestamp, and keep
your notes with it.

It listens on localhost only and has **no authentication** — see
[docs/web.md](docs/web.md) before exposing it.

## The desktop window

```bash
pip install -e ".[gui]"
audio-transcriber gui
```

Three tabs over the same core: **Transcribe** (drop files in or record a
meeting, pick the model and the keyword sets, watch the queue), **Library**
(search, read with a clickable timestamp per block, play the recording while
reading along, write notes, rename, export, delete) and **This machine** (what
was detected, and where the files are).

Recording is the thing a window does better than a browser: a page needs
`https://` or `localhost` before it may touch a microphone, this does not.
Press *Record*, press *Stop*, and the recording queues itself for
transcription.

With the `[record]` extra it also offers what Audacity does — the audio system
(MME, DirectSound, WASAPI, WDM-KS) and its sources, **including the loopback of
an output device**, so a call can be recorded from the speakers. And a second
source mixed into the same file: a microphone plus that loopback are the two
halves of a meeting held over Teams, your voice and everyone else's.

The window needs a graphical session, so on a headless server use
`audio-transcriber web` instead. See [docs/gui.md](docs/gui.md).

## Choosing a backend

| | `faster-whisper` | `openvino` |
|---|---|---|
| Install | `".[cpu]"` | `".[openvino]"` |
| Best on | CPU-only servers, CUDA GPUs | Intel iGPU and NPU |
| Precision | int8 by default on CPU (half the memory) | fp32 |
| Devices | `CPU`, `CUDA` | `CPU`, `GPU`, `NPU` |

`--backend auto` uses OpenVINO when it sees an Intel iGPU or NPU, and
faster-whisper otherwise.

### What to expect on a small server

Measured on a 2 vCPU Xeon (Skylake, KVM) with 3.7 GB RAM, faster-whisper int8:

| model | speed | 1 hour of audio takes about |
|---|---|---|
| `tiny` | 2.0x realtime | 30 min |
| `base` | 1.0x realtime | 1 h |
| `small` | 0.6x realtime | 1 h 40 |
| `large-v3` | — | does not fit comfortably in 3.7 GB |

More cores scale this close to linearly, which is what `--model auto` uses to
choose: it takes the best model that still runs at about half realtime and fits
in the free memory, so the same command gives `small` here and `large-v3` on a
workstation. Ask for a model by name and you get it — with a warning first if
it is likely to swap, be killed for memory, or take far longer than the
recording itself.

More detail in [docs/backends.md](docs/backends.md).

## Diarization setup

Two options:

1. **Online** — set `HUGGINGFACE_TOKEN` (in a `.env`, or as an environment
   variable) with *Read access to public gated repos*, and accept the terms of
   `pyannote/speaker-diarization-3.1`, `pyannote/segmentation-3.0` and
   `pyannote/wespeaker-voxceleb-resnet34-LM` on huggingface.co.
2. **Offline** — put the pyannote models locally and point a `config.yaml` at
   them. No token needed at runtime. `audio-transcriber paths` shows where they
   are expected.

Either way the assets are checked *before* the long transcription starts, so a
missing file does not cost you an hour.

Diarization pulls in PyTorch (~2 GB) and wants a fair amount of RAM, so on a
small server you may prefer to leave it off.

## Roadmap

- [x] Local web UI: drag and drop files, transcription as a background job
- [x] Record straight from the browser
- [x] Browsing, searching and annotating the library from that UI
- [x] Desktop window in Qt, recording from a microphone included
- [x] Recording what the speakers play (WASAPI loopback), and mixing it with
      the microphone
- [x] Subtitles: cues by the trade's numbers, .srt and .vtt, named presets
- [x] Summaries of a transcript: the module, the command, and the engine that
      needs no model
- [x] Summaries written by a local model, on an Intel iGPU through OpenVINO.
      Never a cloud API.
- [x] A summary engine for a machine with no Intel device either: a GGUF on
      the CPU, through llama.cpp
- [x] Choosing the model by what the machine can hold, cache included, and
      refusing to load one when it cannot

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The test suite runs in a second and
needs no models, no GPU and no network — please keep it that way.

## License

The Gratitude & Random Kindness License — see [LICENSE](LICENSE). It is the
MIT license, word for word, with a wish in front of it: nothing in the wish is
a condition, so if you are here to use, copy, modify or sell this, the terms
you are looking for are MIT and you already know them. The wish is worth
reading anyway.
