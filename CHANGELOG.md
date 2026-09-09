# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`install.cmd`**, for Windows: pull, install into the active environment,
  and a report of what to run. It also checks the two things that actually go
  wrong there — a Qt inherited from conda shadowing the one pip installs, and a
  PySide6 without QtMultimedia — and names the cure for each instead of leaving
  a traceback to interpret. `install.cmd cpu,gui` for a machine with no Intel
  iGPU; the default is `openvino,gui,record`.
- **Recording knows about audio systems, loopback and mixing**, behind the new
  `[record]` extra (`sounddevice` + `soundcard`). Two menus, the ones Audacity
  shows: the audio system — MME, DirectSound, WASAPI, WDM-KS — and its
  sources, with every output device also offered under WASAPI as
  `[loopback] …`. Recording that records what the machine plays, which for a
  call is everyone except you; a third menu, "together with", mixes a second
  source into the same file, so a microphone and the speakers' loopback give
  both halves of a meeting held over Teams. Qt cannot do any of this — its API
  has only a flat list of inputs — so the engine is a new `recording.py`, with
  the two libraries handed to it as objects and no Qt in it at all. Without the
  extra the window records through QtMultimedia as before and says what the
  other engine would add.
- The mix states its limitation rather than hiding it: two sound cards keep
  independent clocks, so the first source sets the pace and the second is held
  alongside it — silence fills a gap, and audio more than half a second ahead
  is dropped instead of drifting further behind every minute.
- *Reload* next to the audio system, because PortAudio reads the device list
  once when it initialises: a headset connected after the window opened is
  invisible until PortAudio is restarted, which is what the button does.
- Recordings are mono 16-bit WAV at the device's own rate. Nothing resamples
  here on purpose: every recording passes through ffmpeg on its way to Whisper,
  which does it better than a few lines of numpy would.
- **A desktop window**, `audio-transcriber gui`, behind the new `[gui]` extra
  (PySide6/Qt 6): three tabs over the same core. *Transcribe* takes dropped
  files or a recording, offers the model, the language, the engine,
  diarization and the keyword sets, and follows the queue with a progress bar
  per job; *Library* searches the transcripts and notes, shows the transcript
  with a clickable timestamp per block, plays the recording while reading
  along, and edits `notes.md`, the title or nothing at all; *This machine*
  reports what `hardware` and `paths` report, and opens `config.toml`. See
  [docs/gui.md](docs/gui.md).
- **Recording from a microphone**, in the window, with QtMultimedia — mono, in
  the best container the Qt build can encode. This is the one thing a window
  does better than a browser, which needs a secure context before it may
  capture audio; pressing *Stop* queues the recording for transcription
  straight away. QtMultimedia lives in `PySide6-Addons`, so the `[gui]` extra
  names both halves of PySide6 — pip only checks the name "PySide6", and an
  environment that already has `PySide6-Essentials` (or a Qt from conda-forge)
  would otherwise satisfy it and never gain multimedia. Without that half the
  window still opens, and the recorder and the player say, on the page, what
  is missing.
- The window remembers, in a `gui.ini` next to `config.toml`, its size and the
  choices last used — including the terms typed in its own vocabulary box,
  which are the desktop counterpart of the browser's `localStorage` and never
  become configuration.
- `JobQueue.submit(..., store=...)` chooses what becomes of the source file:
  an upload or a recording the program made is *moved* into the library entry,
  a file the user picked from their own disk is *copied*. Until now the queue
  always moved, which is right for an upload and wrong for someone's
  Documents folder.
- `JobQueue.pending_count()`, so the window can ask before closing on a
  transcription that is still running.
- `Entry.read_segments()`, `Entry.has_written_notes()` and
  `Entry.stored_audio()` in `library.py`: three questions both interfaces ask
  of an entry, answered in one place instead of inside the web layer.
- **Keyword sets.** A domain vocabulary can now be saved under a name and
  selected with `--vocab NAME` (repeatable, or comma-separated) instead of a
  file path, or with `vocabulary = "..."` in `config.toml`. Sets are looked up
  in `<config>/vocabularies` and among the ones shipped with the package, the
  first winning, so a hand-written set shadows a bundled one of the same name.
  `audio-transcriber vocab list|show|new|path` manages them, and
  `[paths] vocabularies` (or `AUDIO_TRANSCRIBER_VOCABULARIES_DIR`) adds a third,
  shared directory. See [docs/vocabularies.md](docs/vocabularies.md).
- **A local web interface**, `audio-transcriber web`, behind the new `[web]`
  extra: drop a recording on the page, choose the model, the language and the
  keyword sets, and watch the job. Transcriptions run in the background, one at
  a time, and each finished one is filed in the library, which the page also
  lists. Installed keyword sets are offered as a menu; a visitor's own sets stay
  in their browser's `localStorage` and are sent, as text, only with the job
  that uses them. It binds to localhost and has no authentication — see
  [docs/web.md](docs/web.md).
- **Recording in the browser.** The web interface can capture audio from the
  microphone with `MediaRecorder` and send it as the job's file. Browsers only
  allow this in a secure context (localhost or HTTPS), which the page explains
  when it applies.
- **The library, from the browser.** Search across transcripts and notes, open
  an entry, play the recording with seeking (range requests), jump to a moment
  from its timestamp, edit `notes.md`, rename and delete. New endpoints:
  `GET /api/library?q=`, `PATCH` and `DELETE /api/library/{id}`,
  `PUT /api/library/{id}/notes`, `GET /api/library/{id}/transcript.json` and
  `GET /api/library/{id}/audio`. Only a recording stored inside the entry is
  served, never one it merely references.
- `Entry.write_notes()` in `library.py`, so notes have one writer.
- **The web interface can live under a prefix.** Every URL the page builds is
  relative to itself, so a reverse proxy can serve it at, say,
  `https://example.org/transcriber/` with TLS and a password in front, while
  the app itself listens on localhost. `web --root-path /transcriber` tells
  FastAPI where it really is, which only the generated API docs need. A worked
  nginx configuration is in [docs/web.md](docs/web.md).
- **Eighteen more bundled keyword sets**, in Italian, one per kind of meeting:
  general meetings, project management, software development, cloud
  infrastructure, data and BI, AI and LLMs, cybersecurity operations, privacy
  and GDPR, IT service desk, marketing, digital marketing and SEO, sales and
  CRM, finance and controlling, Italian accounting and tax, HR, procurement,
  legal, and board and strategy. Each is a couple of dozen terms — acronyms and
  anglicisms, the words Whisper actually gets wrong — short enough that
  `riunione-generale-it` can be combined with any of them inside Whisper's
  prompt budget, which a test enforces.
- A library entry now records which keyword sets shaped it, under
  `transcription.vocabulary` in `metadata.json`.
- A transcription warns when the resulting prompt is longer than Whisper
  reliably accepts (about 900 characters), instead of letting it be truncated
  in silence.

### Changed

- **The default model is now `auto`**, worked out from the machine instead of
  being `large-v3` everywhere: the best model that runs at about half realtime
  given the cores and fits in the free memory, with a GPU short-circuiting the
  question. A 2-core server gets `small`, a workstation `large-v3`. The choice
  is printed when it happens, `audio-transcriber hardware` shows it in advance,
  the web page labels the menu entry "automatic (small)", and naming a model
  still overrides everything. See [docs/backends.md](docs/backends.md).
- **`[paths] cache` in `config.toml`.** Uploads from the web interface are
  written to the cache directory before being filed, so on a server it has to
  be movable to the volume with the room — and until now only an environment
  variable could move it.
- **The page only offers what the machine can do.** `/api/status` now reports
  whether diarization can run — pyannote installed, and a token or a local
  model configured — and the "who said what" checkbox is disabled, with the
  reason next to it, when it cannot. Before, ticking it on a machine without
  pyannote produced a job that failed straight after the upload.
  `audio-transcriber hardware` reports the same three states.
- **The keyword sets are laid out in columns with a search box** instead of
  nineteen rows stacked in one column. It matches names, titles and the terms
  themselves, and a ticked set stays visible however you filter, so the search
  cannot hide a vocabulary you are about to transcribe with.
- **Selects and autofilled fields are painted explicitly.** They are drawn by
  the browser rather than by the stylesheet, and a transparent background left
  the dropdown in the theme's colours against ours — ivory text on white, or on
  Chrome's autofill yellow. Both now carry an explicit background and ink,
  checked for contrast by a test.
- **The web interface was redesigned**: an editorial two-column sheet — the
  explanation in a narrow column, the controls in a wide one — on an ivory and
  forest palette, with fields drawn as a single rule and typographic buttons.
  Two self-hosted typefaces (Fraunces and Karla, OFL, in `web/static/fonts/`):
  no CDN, so the page still calls nobody.
- **Nothing is deleted without asking.** Removing a job from the list, deleting
  a library entry and deleting a personal keyword set all go through one
  in-page dialog that names the consequence. The job action was labelled
  "forget", which read as if it deleted the recording; it is now "remove from
  the list" and the dialog says the transcription stays in the library.
- **Accessibility**: every field has a bound `<label>`, tabs report the
  selected one, focus is always visible, and both palettes meet WCAG AA — all
  three checked by `tests/test_web_page.py`.

- **The job queue moved out of the web layer** into `jobs.py`, next to
  `pipeline.py`: a window on a laptop and a page in a browser need exactly the
  same queue, and it depends on neither FastAPI nor Qt. Its tests moved with it
  into `tests/test_jobs.py`, where they no longer need the `[web]` extra to
  run. `audio_transcriber.web.jobs` is now `audio_transcriber.jobs`.
- **The option lists the interfaces offer are shared.** `MODEL_CHOICES` and
  `LANGUAGE_CHOICES` live in `transcription.py`, the limits on what a visitor
  may type (`MAX_CUSTOM_VOCABULARY`, `MAX_NOTES`) with the vocabulary and
  library modules that own them, and durations, clock positions and file sizes
  are formatted by the new `formatting.py`. Two front ends were about to hold
  two copies of each.
- **`pipeline.py`** holds one transcription end to end; the CLI, the web
  interface and the desktop window all call it, so they cannot drift apart.
- The bundled example vocabulary moved from `examples/prompts/iso27001-it.txt`
  into the package, where it is the `iso27001-it` keyword set. Set
  `--vocab iso27001-it` in place of the old `--prompt-file` path; a
  `prompt_file` pointing at your own file keeps working unchanged.
- `audio-transcriber paths` also lists the keyword-set directory.

### Fixed

- **`audio-transcriber hardware` no longer stops on a machine with no
  transcription engine installed.** Working out which backend `auto` would pick
  ends in "none is installed", which was reported by exiting — swallowing the
  hardware summary and the diarization state on precisely the installation
  someone runs that command to inspect. The message is now part of the report,
  and the command returns 1 so a script can still tell.

## [0.3.0] — 2026-09-04

The release that makes the project publishable: managed data locations, a
recordings library, a configuration file, and an English codebase.

### Added

- **Recordings library.** `--library` files a transcription as a self-contained
  folder holding the original recording, `transcript.txt`, `transcript.json`
  (segments with timestamps and speakers), `notes.md` and `metadata.json`.
  Browse it with `audio-transcriber library list|show|search|remove|path`.
- **Managed directories.** Models, configuration and the library now live in the
  platform's standard per-user locations instead of the working directory. See
  `audio-transcriber paths` and [docs/data-layout.md](docs/data-layout.md).
  `AUDIO_TRANSCRIBER_HOME` puts everything under one folder, which is what you
  want in a container or on a server volume.
- **Configuration file.** `audio-transcriber config init` writes a commented
  `config.toml`; `config show` prints the settings in effect. Command-line
  options still win over the file.
- **Subcommands**: `transcribe`, `library`, `hardware`, `paths`, `config`.
  `audio-transcriber FILE` keeps working and is treated as `transcribe FILE`.
- **Localised interface.** Messages and help are available in English and
  Italian, selected with `--lang`, `AUDIO_TRANSCRIBER_LANG`, or the system
  locale.
- `--prompt-file` reads the domain vocabulary from a file (`#` lines are
  comments), with an example under `examples/prompts/`.
- `--json` writes the segments, with timestamps, next to the transcript.
- English hallucination phrases are now filtered as well as Italian ones.
- The run report includes elapsed time and speed relative to realtime.

### Changed

- **The codebase, its comments and its docstrings are English.** Only the text
  users read is translated.
- **The default domain prompt is now empty.** Version 0.2 shipped a hardcoded
  Italian ISO 27001 vocabulary; it moved to
  `examples/prompts/iso27001-it.txt`. To keep using it, set `prompt_file` in
  `config.toml` or pass `--prompt-file`.
- Backends moved into `audio_transcriber.backends`.
- The environment files moved to `envs/`.
- **Python 3.11 or newer is required** (3.10 previously), for `tomllib`.

### Fixed

- A malformed `config.toml` no longer blocks `config init`, the one command
  that can repair it.
- Progress output no longer appears out of order when stdout is redirected.

### Compatibility

A `whisper-ov-models/` or `pyannote-diar/` folder in the working directory
still takes precedence over the managed locations, so an existing install keeps
using the models it has already downloaded.

## [0.2.0] — 2026-09-04

### Added

- **faster-whisper backend** (CTranslate2, int8): Whisper on machines with no
  GPU, several times faster than the OpenVINO CPU path and half the memory.
  CUDA is supported too.
- `--backend auto` picks OpenVINO when an Intel iGPU or NPU is present and
  faster-whisper otherwise; `--hardware` reports what was detected.
- `--compute-type`, `--threads` and `--no-vad` for the new backend. The VAD
  filter is on by default and cuts silence hallucinations considerably.
- Warnings before a run when the chosen model will not fit in memory or is
  disproportionate to the available cores.

### Changed

- `--device` defaults to `auto`. A device that was asked for but is absent is
  no longer fatal: it warns and falls back to the CPU.
- The heavy dependencies became extras: `[cpu]`, `[openvino]`, `[diarize]`,
  `[all]`. The core is `numpy` and `imageio-ffmpeg`.

## [0.1.0] — 2026-09-03

- First release: the personal script restructured as a Python package with a
  `src` layout, an `audio-transcriber` entry point, Whisper on OpenVINO, and
  optional pyannote diarization.
