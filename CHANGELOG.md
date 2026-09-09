# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **Half the Italian stopwords never matched anything.** They were typed
  without accents — `perche`, `cosi`, `pero`, `piu` — and Whisper writes
  Italian as it is spelled, so `perché`, `così`, `però` and `più` sailed
  through the filter and into the ranking. Found by summarising a real
  nineteen-minute recording, whose "recurring terms" came back as *esatto,
  framework, perché, roba, così, eccetera*. Comparison is now made on the
  accent-folded form while the word itself is kept as it was said, and the
  list has gained the glue of actual speech: the fillers two people talking
  say more often than they say their subject, plus the modals and the three
  light verbs in the present. The same nineteen minutes now come back as
  *framework, configurazione, controlli, catalogo*. The list stops at the
  modals on purpose — chasing every conjugation would be a lemmatiser, and
  that is not a dependency this program will take for a keyword list.

### Added

- **Summaries from the browser and the window**, not just the command line. A
  *Summary* tab sits beside the transcript and the notes in both, with the
  button that writes one under it and — where this machine has more than one
  engine — a menu saying which will. What comes back says who wrote it and
  when, because a page that does not say is one somebody will quote in a
  meeting without knowing whether a model or a sentence-picker produced it.

  A summary goes into **the same queue as the transcriptions**, which is the
  decision worth recording: a model reading an hour of transcript is minutes
  of the same two cores a transcription needs, so running both at once would
  make each slower without finishing either sooner. `JobQueue` therefore
  carries two kinds of job rather than gaining a second queue — one worker,
  one thing at a time — and a summary asked for mid-transcription waits its
  turn where everything else is visible. The window watches its job instead of
  doing the work on the thread that draws it, and a summary that lands while
  somebody has moved on to another entry does not change the pane under them.

  New endpoints: `POST`/`DELETE /api/library/{id}/summary`,
  `GET /api/library/{id}/summary.md`, `GET /api/summary/engines`, and the
  entry payload now carries its summary. `summary.summarize()` takes a
  `progress` callback, so a long map/reduce reports which pass it is on rather
  than standing still.
- **Summaries written by a local model**, behind the new `[summarize-ov]`
  extra: the `openvino` engine runs a language model on an Intel device
  through OpenVINO GenAI, and the page stops being a list of quoted sentences
  and becomes an abstract, the decisions, and who agreed to do what — each
  carrying the minute it was said at. `--model auto` picks the largest
  recommended model that fits in this machine's free memory (an 8B at int4 is
  about 5 GB, and on an integrated GPU the model lives in system memory
  whichever device runs it); any Hugging Face id or an already-converted
  directory works instead. The first run converts to int4 and keeps the
  result, which is also where the one non-obvious step lives:
  `save_pretrained` writes the Hugging Face tokenizer, which the GenAI runtime
  cannot read, so `openvino_tokenizer.xml` and its detokenizer are converted
  explicitly — without that the model loads and then fails at the first
  prompt.

  **`auto` does not choose the NPU**, deliberately. Its LLM pipeline runs on
  static shapes with the prompt capped at 1024 tokens by default and 8K at
  best, an hour of transcript is nearer fifteen thousand, on Qwen3 it does not
  compile above 8K, and an 8B generates slower there than on the same
  machine's iGPU. `--device NPU` is still honoured, with a warning.

  A transcript that fits goes to the model in one prompt; a longer one is read
  in chunks and the chunk summaries summarised together, against one loaded
  model. The prompts, the chunking and the parsing live in
  `summarizers/prompting.py` rather than in the engine, so the next runtime
  inherits all of it: an engine is now the one call that turns a string into a
  string. Two habits of language models are handled rather than hoped away —
  a reasoning model's `<think>` block never reaches the page, and a model too
  small for the job answers by repeating the question, which is caught by
  fencing the transcript inside the prompt and recognising the echo. That
  earns "returned nothing usable, try another model or `--engine extractive`"
  instead of a page that looks like a summary and is the transcript again.

  Still no network, and no endpoint to configure: the model runs on the
  machine that made the transcript.
- **Summaries of a transcript**, in a `summary.py` of their own with the
  engines in `summarizers/`, chosen by name the way the transcription backends
  are. A summary is two jobs and only the second needs a model: *selection* —
  which sentences carry the meeting, which is TextRank over a graph of sentence
  similarity and runs in milliseconds on the numpy the core already has — and
  *writing*, which is language work. Splitting them is what makes the feature
  portable: where there is an accelerator a model will read everything, and on
  a two-core server the same selection cuts fifteen thousand tokens to three
  thousand first. One engine ships now, `extractive`, which does the selection
  and stops there; the page says so under the title, because sentences quoted
  from a transcript must not be mistaken for prose somebody wrote about it.
  `audio-transcriber summarize ENTRY|FILE`, with `--engine`, `--length`
  (`short`/`medium`/`long`), `--out` and `--print`; a `[summary]` section in
  `config.toml`; `summary.md` in the library entry beside `transcript.txt`,
  with the engine and the date recorded in `metadata.json`; and
  `audio-transcriber hardware` now also says which engine `auto` would pick
  here. The headings of the page are in the language that was *spoken*, not the
  language of the interface — a summary is a document, not a message from the
  program. Nothing in this feature reaches the network, now or later: see
  [docs/summary.md](docs/summary.md).
- **One choice up front: what the run is for.** *Just the text*, *the text with
  who said what*, or *subtitles* — three radio buttons in the window, the same
  three in the browser, `--output text|speakers|subtitles` on the command line,
  `[general] output` in `config.toml`. Until now the window asked it in five
  scattered controls and never in so many words: a diarization checkbox next to
  a subtitle preset next to a "save as .srt", with no way to say "I only want
  the text". The answer settles what it implies (`config.resolve_output`, in
  one place because the three front ends must agree): plain text refuses
  diarization and subtitles even if the configuration file asks for them, "who
  said what" turns diarization on, and subtitles assume `.srt` when no format
  is named, since subtitles saved nowhere are not an output. The controls
  belonging to the other two answers are put away rather than left doing
  nothing, one note says what the chosen answer produces, and the answer is
  remembered. "Who said what" is refused outright — with the reason on it —
  when the machine cannot diarize, instead of by a job that fails after forty
  minutes. With subtitles it stays optional: marking the speakers in the cues
  is a separate decision, and then two voices never share a cue and a change of
  voice is marked with a leading hyphen.

- **`install.cmd`**, for Windows: it puts itself in the right conda environment
  (`srt-ov2`, or whatever `AT_ENV` says) and leaves the window in it, pulls,
  installs, and prints what to run. It refuses conda's own `base` — where
  Anaconda's Qt shadows the one pip installs and the window cannot load QtCore
  — unless told `--base` explicitly, and it checks afterwards that PySide6
  loads, that QtMultimedia is there, and how many audio sources the recorder
  can see, naming the cure for each failure instead of leaving a traceback to
  interpret. `install.cmd cpu,gui` for a machine with no Intel iGPU; the
  default extras are `openvino,gui,record`.
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
- **Subtitles**, in a `subtitles.py` of their own, and reachable from all three
  interfaces. A transcript and a subtitle track are not the same thing:
  Whisper's segments run twenty or thirty seconds and hundreds of characters,
  so they are cut again against the numbers subtitling uses — characters per
  line, lines, reading speed, minimum and maximum duration, minimum gap — held
  in named presets (`netflix`, `bbc`, `ebu_broadcast`, `fcc_verbatim`,
  `social_vertical`, `social_karaoke`, `kids_accessible`) shipped as data and
  overridable by name from `<config>/srt-presets.json`, like the keyword sets.
  `--srt`, `--vtt`, `--subtitle-preset`, `--subtitle-chars`,
  `--subtitle-lines`, `--subtitle-words` and a `[subtitles]` section in
  `config.toml`; the same four choices next to the model in the window and in
  the browser; `GET /api/library/{id}/subtitles.srt` and `.vtt`, and *Export
  the subtitles* in the window, both cutting an entry from its segments so one
  transcribed months ago can be cut with today's numbers.
  Line breaking follows the forbidden-break rules — never between an article
  and its noun, an auxiliary and its participle, a verb and its clitic, or
  between two capitalised words, which is usually a name and a surname — and
  the word timings are asked of the engine only when subtitles are wanted,
  because they cost time and buy a cut that falls where the speaker paused.
  What it will not do is rewrite anybody's words: speech too fast to read is
  reported, not condensed. See [docs/subtitles.md](docs/subtitles.md) for that
  list and its reasons.
- **The desktop window is not a Windows program.** Qt was always portable, but
  the recording engine was not: the loopback engine was called `WasapiEngine`
  and filed its sources under a host API named "Windows WASAPI", which on a
  Linux box is a group that does not exist. It is now `SystemEngine` — the
  platform's own audio API — and the group is named after the platform:
  WASAPI on Windows (where the name matches PortAudio's, so the loopbacks join
  that group instead of forming one of their own), PulseAudio on Linux, Core
  Audio on macOS. It also enumerates loopbacks by asking `soundcard` for them
  rather than by turning every speaker into one, which is what makes the
  Linux monitor sources appear.
  On macOS no loopback is offered at all: Core Audio cannot record what it is
  playing, and an entry that fails when it is used is worse than no entry. A
  virtual device such as BlackHole appears as an ordinary input and can be
  recorded and mixed like any other.
- **`install.sh`**, the Unix twin of `install.cmd`: it uses the environment
  already active or a `.venv` it creates, pulls, installs, and checks what
  actually goes wrong on these platforms — the system libraries the PySide6
  wheel does not carry, and PortAudio for the recorder — naming the packages
  for Debian, Ubuntu and Fedora. It refuses conda's `base` for the same reason
  the Windows one does.
- **The web interface gained what the window gained, where a browser can have
  it.** A job's status shows the stage it is in, not only its percentage;
  *stop* interrupts the transcription that is running, after asking, and *take
  out of the queue* drops one that has not started (`POST
  /api/jobs/{id}/cancel`); finished rows can be cleared in one go. Recording in
  the browser shows an input level meter next to the timer — Web Audio, the
  same decibel scale as the window, floored at -60 dBFS — and says so when a
  recording never rose above silence.
  Deliberately not ported, because a page cannot have them: the audio-system
  menu, the loopback of an output device, mixing two sources, and the "test
  audio" button. A browser gets one microphone through `getUserMedia` and
  nothing else. The explicit *Transcribe* button was not ported either — in the
  browser the upload already is that decision.
- **A run says what it is doing, not only how far it has got.** The stages —
  starting, audio decoded, loading the model, converting it, compiling for the
  device, transcribing, who said what, laying out the text — are reported as
  they are reached, and the desktop window shows them in the status column
  next to the state. The engine's own progress is now mapped into the slice of
  the bar that belongs to transcribing instead of being passed straight
  through, so a model coming up can no longer send the bar back to zero, and
  diarization gets a slice of its own because it takes about as long again as
  the transcription.
  This matters most where the bar cannot move: faster-whisper reports every
  segment, while the OpenVINO backend hands nothing back until it has finished
  the whole file, and "transcribing" next to a motionless bar is the difference
  between waiting and wondering. Both backends now report their setup, which is
  where the first minutes of a run actually go.
- `pipeline.run` takes a progress callback of one *or* two arguments — the
  percentage, and the message key of the stage — and works out which by
  looking at the signature once, rather than by calling it and catching
  TypeError.
- **One list in the desktop window, and one button that runs it.** A file
  added — dropped anywhere on the tab, chosen with *Add files…*, or just
  recorded — lands in the queue itself, marked *not started*, and *Transcribe*
  runs everything waiting. The separate list of chosen files is gone: nobody
  could tell how to begin from it. Starting each file the moment it was added
  was tried in between and was worse in the other direction — it left no room
  to change the model or tick a keyword set once the files were in.
- **The queue is a box with a title on it, and things can be taken out of it.**
  *Take out of the queue* drops a job that has not started; *Stop* interrupts
  the one running, after asking, since it may be forty minutes in; *Clear the
  finished* empties the rest. The buttons offer only what applies to the
  selected job, and the selection updates them immediately rather than on the
  next refresh.
- `JobQueue.submit(start=False)`, a `held` state and `JobQueue.start()`: the
  window fills the queue and runs it on request, while the web interface
  uploads and starts in one motion as it always did.
- `JobQueue.cancel()`, and a `cancelled` state that is not a failure. A job
  that never started is dropped without leaving a row — nothing happened to
  it, and "cancelled" is for a transcription that really was under way; a
  running one is asked, and stops at the
  engine's next progress report — which is why faster-whisper now calls that
  callback on every segment instead of every five per cent. The OpenVINO
  backend reports no progress until it has finished the file, so there a stop
  means "run to the end and discard the result": the confirmation dialog says
  so rather than promising otherwise. Nothing cancelled reaches the library,
  and the source file is deliberately left alone — a recording nobody has
  transcribed yet may be the only copy of that meeting.
- **A "test audio" button**: it opens the chosen source without recording
  anything, so the meters move, and after a second and a half it says whether
  what is arriving behaves like somebody talking — silence, sound that is not a
  voice (a fan, a tone, music), or speech — with the three numbers behind the
  guess: the level, the decibels between the quiet and the loud moments, and
  how much of the energy sits between 100 Hz and 4 kHz. It is a heuristic and
  says so; recognition is Whisper's job and needs a model and a file. It stops
  itself after thirty seconds, since it holds the microphone open, and pressing
  *Record* takes the device back from it. The thresholds were calibrated on
  synthetic signals — a tone, mains hum, white noise, constant noise inside the
  speech band, and speech loud, quiet, hurried and over a noisy room — which
  are now the tests.
- `recording.py` grew a `Monitor` alongside `Recording`, both on a shared base:
  holding devices open and reading them in step is what they have in common,
  and what each does with the audio — a WAV file, or a verdict — is one hook.
- **Level meters while recording**, one per source, on the row of the source
  they measure. The question they answer is "is anything arriving at all",
  which is the one worth asking before a meeting rather than after: a wrong
  device, a muted microphone or a Windows privacy setting all produce a
  recording that is an hour of digital silence. Two bars rather than one for a
  mix, so a loopback that delivers nothing is visible next to a microphone that
  works. The scale is in decibels, floored at -60 dBFS — a linear bar leaves
  ordinary speech against the left edge and makes a working microphone look
  broken.
- A recording that never rose above silence says so when it stops. It is still
  queued: the file is real, and Whisper turning it into nothing is a better
  thing to learn now than in half an hour.
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

- **The OpenVINO backend no longer transcribes the overlap between its windows
  twice.** A recording longer than Whisper's thirty-second window has to be
  broken up, and this backend was using the Hugging Face pipeline's fixed
  windows: thirty seconds at a time with five of overlap, stitched back
  together afterwards by matching the words two windows have in common. Over a
  silence or a crosstalk that match fails, and then both copies are kept — the
  tail of one passage reappearing at the head of the next, three or four times
  in a twenty-minute meeting, each time introduced by a phrase the model
  invented over the silence ("Grazie a tutti"). It now asks for Whisper's own
  long-form loop instead, which starts each window at the timestamp the last
  one reached: no overlap to stitch, so nothing to double, and the model's own
  safeguards apply — retry a window at a higher temperature, reject one whose
  output is too repetitive or too unlikely, skip one that is probably silence.
  Where `optimum-intel` is too old to run that loop it falls back to fixed
  windows and says so, dropping the keyword prompt on the way, because prompt
  tokens are what makes the stitching mismatch in the first place.
- **The OpenVINO backend now honours `word_timestamps`, and admits that it
  cannot honour `vad`.** Both were being swallowed by `**_unused`. Asking for
  subtitles asks the engine to time every word, so that a cue is cut where the
  speaker paused; this backend was silently ignoring that and handing back
  segments of a minute, whose cue times were then interpolated across them by
  character count — a plausible-looking clock that had never been measured.
  It now asks for word timings and rebuilds its segments from them, falling
  back with a warning on a model that cannot produce them. There is still no
  voice-activity filter here, which is one reason phrases get invented over
  silence, and that is now said out loud with a pointer to the backend that
  has one.
- **A doubled passage is cut from the transcript whichever engine produced
  it.** `clean_segments()` compared each segment with the whole of the one
  before it, which catches an exact repeat and misses the shape the failure
  actually takes: a partial overlap, differing by a word or two, sometimes
  with the botched half of a sentence in front of it, sometimes both copies
  inside one segment. The head of each segment is now *aligned* against the
  two before it, and what they already said is cut, along with a hallucinated
  phrase glued to either edge of a segment rather than making up all of it.
  Word timings are trimmed with the text so the two cannot drift apart, and a
  segment that lost its opening keeps an honest start instead of one that puts
  every subtitle in it early by the length of the doubling. The thresholds are
  deliberately shy of speech: six words repeated back to back inside a
  segment, eight for a repeat across two, and an alignment that has to account
  for three quarters of what it cuts — "ogni asset ha i suoi impatti" said by
  three people in one conversation is the record, not an artefact.
- **The subtitle report was printing message keys.** Every `subtitles.*`
  remark and both `cli.subtitles_*` lines were missing from the catalogues, so
  writing an `.srt` from the command line reported `subtitles.too_fast x38`.
  They are written out now, and grouped by who can do anything about them:
  what comes from how fast people spoke (the trade's remedy is to shorten the
  text, which this program declines), what comes from the times the engine
  reported, and what comes from this program's own layout. Where the times
  were interpolated rather than measured the report says so, because half the
  remarks then rest on a clock nobody measured. The library entry keeps the
  same tally in `metadata.json`, so a run filed in the library reports what a
  run written beside its input reports.

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
