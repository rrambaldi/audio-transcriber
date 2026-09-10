# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **A summary engine for a machine with no accelerator at all.** A GGUF
  through llama.cpp, which is the environment the rest of this feature was
  always about: two cores, no GPU, a few gigabytes. Nothing is converted — the
  file is downloaded already quantised and loaded as it arrives — and the
  weights are mapped from disk, so a model larger than the free memory is slow
  rather than fatal. Either way in works: `llama-cpp-python`, or the
  `llama-server` binary alone, which is one file and no Python and is what a
  server would rather deploy. When the binary is used it is bound to
  `127.0.0.1` on a port the kernel picked, it lives for exactly one summary,
  and it is stopped in a `finally`. `auto` now prefers it over the extractive
  engine and after OpenVINO, and `environment-cpu.yml` offers it commented,
  with what it costs.

- **The model is chosen by what the machine can actually hold.** The old
  policy was three names against three numbers of free gigabytes, written by
  hand; it left out the KV cache, which is what nobody counts until the
  machine starts swapping, and it had no way to say no. The estimate is now
  weights plus cache plus runtime, with the cache calculated from the model's
  own shape and only over its **attention** layers — which is why the
  catalogue prefers hybrids: Granite 4.0 H-Micro keeps a cache in four of its
  forty layers. When a size class does not quite fit, the context goes first,
  then the precision of the cache, then of the weights, then the class below;
  and the key is never quantised below `q8_0`, because a symmetric four-bit
  cache does not fail loudly, it quietly stops being faithful. When nothing
  fits, nothing is loaded: the page is written by the extractive engine and
  says so, with both figures. `audio-transcriber hardware` prints the plan it
  would choose here, which is the only way to inspect the policy without
  reading the code.

- **Handling for what small models actually do.** Every one of these was
  found by running a 1.2-billion-parameter model on a two-core machine, and
  none of them could have been found any other way. A `<think>` block with no
  end never reaches the page, and a model still thinking when its allowance
  ran out is asked again with room — a different failure from a model too
  small for the job, which from the outside it resembles exactly. An answer
  that gives back the question is recognised even when reflowed onto one line,
  and the chunk it came from contributes its own highest-weighted sentences
  instead. A line copied out of this program's own instructions is not treated
  as something the model wrote about the recording. And a heading written as
  `**Punti chiave**` rather than `## Punti chiave` is still a heading:
  unrecognised, every section the model wrote landed in the abstract.

- **The reduction stage is finally called.** It was documented as the thing
  that lets a small model summarise an hour of speech and had no caller but
  its own test. On the smaller classes the transcript is now selected down
  before it is read, and the page says what share arrived.

### Fixed

- **A machine with plenty of memory was told it had none.** The reserve kept
  free for the operating system was a fifth of the *installed* RAM, so a
  desktop with thirty-two gigabytes and seven of them free — an ordinary
  Tuesday — reserved six of the seven and concluded that no model fits, with
  an Intel GPU sitting idle. What has to stay free does not grow with how much
  RAM somebody bought; the reserve is capped at two gigabytes.

- **The Windows installer did not install the summary engine.** Its default
  extras were `openvino,gui,record`, so a machine with an Intel device
  transcribed and then reported that no summary engine was installed, having
  just listed three OpenVINO devices — the devices come from `openvino`,
  writing a summary needs `openvino_genai`. `summarize-ov` is in the default
  now, and it is only the small half of a download that extra already makes.
  There is also a `summarize-cpp` extra at last, for the llama.cpp engine; it
  is in no default, because pip builds it from source.

### Changed

- **A long recording is folded in a tree rather than in one prompt.** A single
  reduce prompt holds every partial summary, so it grows with the length of
  the recording: fifteen chunks of a ninety-thousand-token meeting was a
  twenty-one-thousand-token prompt handed to the model chosen precisely
  because the machine is small. The partials are folded in groups, the groups
  folded again, and the fan-in is what that model's context can hold. Each
  level answers under its own budget — a chunk summary is a list, only the
  last pass writes the page — and reasoning is off while reading a chunk,
  where a model that narrates for its whole allowance is cut off before the
  answer starts.

- **Every folding pass is given a piece of the transcript, not only the
  summaries it is merging.** From the second level up the model is summarising
  its own writing and cannot tell what it invented one level down; a few
  hundred tokens of the highest-weighted original sentences, with the
  instruction to correct against them, is the measured cure and costs nothing
  this program did not already have. Chunks are also kept below what the
  window allows and overlap by a tenth: faithfulness sags in the middle of a
  long input, and a decision taken across a boundary was otherwise half in
  each pass.

- **Italian is counted at the rate Italian costs.** Four characters to the
  token is the figure everybody quotes and it is wrong here by a third:
  measured with the tokenizers of the models in the catalogue, over spoken
  Italian, the rate is 2.8 to 3.2. Undercounting is the direction that
  produces chunks larger than the budget claims, so the divisor is per
  language, the worst measured case is kept, and an unnamed language is
  charged the careful rate.

- **Passes already read are not read again.** A map pass is deterministic and
  independent, so it is kept under the cache directory: asking for the same
  recording at a different length re-reads nothing, and an interrupted job
  resumes where it stopped. The key carries a version of the prompts, because
  a cache that survives a prompt change is a bug that accumulates.

- **The program has a mark.** A padlock cut through by a waveform — what it
  does and the fact that nothing leaves the machine, in one shape — as an icon
  set in `src/audio_transcriber/data/brand/`: the master drawing on its plate,
  a three-bar simplification for 32 px and below where five bars turn to mud,
  the lock without its plate, and renders from 16 to 512 px plus a
  `favicon.ico`. It is package data, so a wheel carries it, and `branding.py`
  is the one module that knows where it is. The browser tab and the home-screen
  icon now have it, the page shows it next to the title, the desktop window
  takes every size rather than one render scaled twice, and the
  README opens with the banner. The files are served from `/brand`, next to
  `/static`, with relative URLs, so they keep working behind a `--root-path`
  prefix; `GET /favicon.ico` answers as well, for the tab restored before the
  page has loaded. What has to be uploaded by hand is listed in
  [docs/brand.md](docs/brand.md): the GitHub social preview and the avatar.

- **The window opens with the mark, the name and the promise.** A masthead
  above the tabs — the padlock, "Audio Transcriber", and the same line the web
  page leads with, "Local transcription. Nothing leaves this machine." The
  title bar was the only place the window said whose it was, and a title bar
  is 16 px tall, is truncated when the window is narrow, and on a maximised
  Windows window or a tiling desktop is not drawn at all. It paints none of
  the brand's colours over the desktop's, for the reason in `gui/style.py`:
  the mark carries the colour, the name is the window's own text at a larger
  size, and the tagline is muted only as far as it can be and still clear the
  contrast floor. On a dark theme the mark is drawn from `icon-mark.svg`
  instead, whose missing plate is exactly the point — the plate is a dark navy
  and would sink into a dark window — and it is redrawn when the desktop
  switches theme under a running window.

- **The window is painted like the web page, typefaces included.** One
  program, one look: the desktop window now takes the page's palette — the
  light scheme the brand inverted, the dark scheme the mark's own colours,
  following the desktop the way the page follows `prefers-color-scheme` and
  changing under a running window — and its two typefaces, Fraunces for
  headings and Karla for everything read while typing, which are handed to Qt
  from the same files the page loads. The chrome follows: a field is one rule
  under the text, a button is typographic and never boxy, the primary action
  is the accent and a heavier rule rather than a filled box, a tab is a word
  with a line under it, a queue row's title is set in the serif, and the drop
  area is dashed. `gui/theme.py` holds it, and `tests/test_gui_theme.py`
  compares every token with `web/static/style.css` itself and holds both
  schemes to the same WCAG rules the page is held to.

  This **reverses** the window's earlier rule that the desktop should paint
  it, which was in `gui/style.py` for good reasons — a repainted window looks
  foreign next to native ones — and the price is paid deliberately: a custom
  desktop theme is no longer followed, and the style is forced to Fusion on
  all three platforms, because the native Windows and macOS styles each ignore
  a different half of the rules. The contrast floor stays and matters more: a
  palette the program chose has no desktop to blame for its greys.
  [docs/gui.md](docs/gui.md) records what it cost and the two things Qt cannot
  do at all — there is no `text-transform` and no `letter-spacing` in a Qt
  style sheet, and a font set on a container is inherited by everything in it.

- **The window holds its content off its own frame, and its tabs look like
  tabs.** Two things the first pass got wrong. A group box's rule was flush
  against the window: there is now one gutter, set on the tab widget's pane,
  and the masthead, the tab strip, every panel and the status line all start
  on the same vertical — which took the status line out of `showMessage`,
  because Qt draws a status message seven pixels from the frame and neither
  contents margins nor a style sheet will move it. And the three tabs read as
  a row of captions: the page's 0.72rem label is a ratio written against a
  16 px body, so on a 9pt desktop font it came out near seven points, with an
  underline the colour of the text — which reads as underlined text. The strip
  keeps the case and the tracking, gives up the shrinking, has room to be
  pressed, and marks the tab you are on in the accent.

  One thing fell out of that: a finished transcription now stays in the status
  line for its eight seconds. It was announced and then overwritten by the
  library count in the next statement, so the one message worth reading after
  forty minutes of work was the one nobody ever saw.

- **The typefaces moved in with the icons.** They were under
  `web/static/fonts/`, which was the right place while only the page used
  them; both front ends do now, so they are `data/brand/fonts/`, served at
  `/brand` for the page and handed to `QFontDatabase` for the window, with
  `branding.py` the only module that knows the path. A wheel carries them
  through a second package-data line — a glob does not recurse.

- **The task bar and the dock draw the mark too, and not Python's.** Setting
  the window icon turned out to be enough on one platform of three. Windows
  takes a task-bar button's icon from the process's Application User Model ID,
  whose default is the interpreter's, so the window wore the mark and the
  button people click wore the Python logo; it is now claimed before the first
  window exists, which is the only moment Explorer looks at it. Wayland has no
  counterpart to X11's `_NET_WM_ICON` — a window cannot hand the compositor a
  picture — so what the dock draws is the icon of the desktop entry the
  application declares: there is now one, `packaging/audio-transcriber.desktop`,
  `./install.sh` installs it on Linux with the renders copied into the icon
  theme under the same name, and the window declares it by name. macOS needed
  nothing. [docs/gui.md](docs/gui.md) says which fix is for which.

### Changed

- **The web page is painted in the program's own colours.** It was an ivory
  sheet with forest-green ink, chosen before there was a mark to match; the
  mark is `#0C1526` with a cyan-to-blue gradient, so the page and its icon
  were two palettes sitting next to each other. Now the dark scheme *is* the
  brand — the same ground, the same `#22D3EE` — and the light one is that
  identity inverted: the ground colour becomes the ink, the paper a cool
  near-white instead of a warm ivory, and the accent steps back along its own
  gradient to the blue end, darkened to `#1C4FD8` because cyan is not text on
  white. Neither scheme is the default; the reader's setting still decides.
  The accent variable is called `--signal` rather than `--forest`, which had
  stopped being true, and the unused `--ochre` is gone. Every text pair still
  clears WCAG AA in both schemes, and the accent *wash* — the banner, a
  hovered segment, a keyword chip — is now measured too, which it never was.

- **The web page offers one action while it is working: stop.** Uploading,
  recording, transcribing, summarising, renaming, deleting, saving notes and
  clearing finished rows all go off for as long as a job is queued or running,
  dimmed and with the reason on them. On two cores anything asked for during a
  transcription either waits for nothing or competes for the same cores and
  makes it slower, so a page that lets you ask is a page that lets you make
  things worse by accident. Reading stays: opening an entry, reading it,
  playing the recording and downloading the text cost the machine nothing and
  are the obvious thing to do while waiting. A control that is off because
  this machine cannot do the thing at all — "who said what" without pyannote —
  is marked separately so the end of a job cannot hand it back, and the ways
  round a disabled button are closed too: a file dropped on the zone is
  refused, and so is a form submitted with the keyboard. The block is the
  page's own; the endpoints still accept what they always did, because the
  queue is what actually serialises the work.

### Fixed

- **The window's typefaces did not load on Windows.** They shipped as WOFF2,
  which is the right format for a web page and the wrong one for everything
  else here: Qt does not read a font itself, it hands the bytes to the
  platform's font engine, and while FreeType takes WOFF2, DirectWrite refuses
  it. So the window came up in a fallback face on the platform most of these
  users are on, and said so twice —
  `qt.qpa.fonts: Failed to create DirectWrite face from font data`. Both faces
  now ship as variable TrueType, which every engine and every browser reads;
  the page loads the same two files, 154 KiB instead of 88, which is a
  download from this machine to itself. A test asserts the shipped files are
  sfnt, because the format is the whole bug.

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

- **The half of the header that is not the recorder is the drop area**: a
  framed panel with *Add files…* in it, which lights up while something is
  dragged over the window. The whole tab still takes a dropped file — aiming
  is not part of the job — but with the recorder beside it that half was
  simply empty, and "you can drop things here" has to be somewhere you can
  point at.

- **The Transcribe tab is a header and a queue.** Across the top, *Add
  files…* and the recorder; dropping a recording anywhere on the tab queues
  it. Everything else is the queue. The column of options beside it is gone —
  it was answering "what do you want out of this?" for a file that did not
  exist yet, and answering it once for every recording in the list. Those
  four questions are now only ever asked about one recording, in the dialog
  its own *Transcribe* button opens, and the button under the list asks them
  once for everything that is waiting. The answers are remembered, so the
  second recording of the morning starts from what the first one was told.

- **The buttons on a queue row are push buttons**, which sounds like nothing
  and was the whole bug: a `QToolButton` defaults to *icon only*, there was no
  icon, and where the Fusion style draws the label anyway the Windows one
  draws nothing — three invisible buttons, in a column of exactly the right
  width, on the only platform it mattered on. Painting one and looking at it
  could not catch it, because on the machine the tests run on the broken
  version looked correct; what catches it now is a rule, checked over every
  button in the window: a tool button either carries an icon or says out loud
  that it is showing text.

- **The recordings come first, and each one is asked what it is for.** The
  list down the left starts with where the recordings come from and only then
  asks what to do with them — you have the file in front of you before
  deciding what to make of it — and every row in the queue carries its own
  buttons: *Transcribe* (or *Stop*, or *Open*, or *Try again*, whichever
  applies to its state), *Play*, and *Remove*. Selecting a row and then
  pressing a button under the table was one step more than there needs to be
  and one more thing to get wrong.

  **Starting one recording asks what it is for**, in a dialog holding the same
  four sections as the column and seeded from them. Options used to belong to
  the tab: whatever the column said when a file was dropped in became that
  file's settings for good, which is the wrong shape for the way the queue is
  used — half a dozen recordings at once, and one of them is the interview
  that needs subtitles. The column is now the defaults; the dialog is one
  recording's own answers. Both are the same `OptionsForm`, because two
  implementations of the same four questions is how they start to disagree.

  *Play* listens to a recording before spending an hour on it: the file
  itself while it waits, the copy inside the library entry once it has been
  filed. A failed or cancelled recording can be asked again — nothing was
  filed and the file is still where it was, so the row simply goes back to
  waiting.

- **The left of the Transcribe tab is a list of sections that open.** Five
  rows — the three steps, *Subtitles*, *Keyword sets* — each of which reports
  what it holds while it is shut: "3 · How to transcribe them — auto ·
  Italiano (it) · auto", "Keyword sets — 3 chosen". That is the whole bet of
  the arrangement: a closed section must not hide a choice, or closing it is
  worse than the crowding it fixed. Which rows are left open is remembered,
  and so is where the divider between the list and the queue sits.

  **A section that does not apply stays and goes quiet.** *Subtitles* reads
  "only with «Subtitles»" until that is the answer, and opens itself the
  moment it is: a row that waits is easier to learn than a list that changes
  shape under the pointer.

- **The Transcribe tab is read as three steps.** *1 what do you want out of it
  · 2 which recordings · 3 how to transcribe them*, down the left of the tab,
  with the queue beside them instead of underneath. It was three panels side
  by side with the button that starts everything in the bottom-left corner:
  the order things were read in was not the order they are done in, and the
  eye crossed the window three times for a task that is a straight line.

  What follows from it: the two ways in are two tabs, *Add files* and
  *Record*, the pair the browser page already had — a microphone is not an
  option of the file list, it is the other half of the question. The keyword
  sets start closed behind a row that says what is inside them ("Keyword sets
  — 3 chosen"), because nineteen of them took a third of the window before
  anything had been chosen. *Transcribe* is the one filled button on the tab,
  says how much it will start ("Transcribe 2 recordings"), and is the default,
  so Enter does what the screen is for; <kbd>Ctrl</kbd>+<kbd>O</kbd>,
  <kbd>Ctrl</kbd>+<kbd>Enter</kbd> and <kbd>Delete</kbd> work, where there was
  not one keyboard shortcut in the whole window.

- **A queue row is a recording, not six columns.** Title, and underneath the
  facts known so far — model, length, words — or, when it failed, the reason
  with the whole width of the column instead of a hundred characters of ffmpeg
  squeezed into the status cell. Model, duration and word count were columns
  of their own, which meant they stood empty for the whole of a job's life and
  filled a moment before the row stopped being interesting. Only the job that
  is actually running carries a progress bar: one at 0% on a row that failed,
  or on one that has not started, measures something that is not happening.

- **The queue line lists the states instead of choosing between them.** With
  one job running at 34% and one waiting it used to say "1 not started, press
  Transcribe" — the table on the same screen contradicted it. It now reads
  "1 running, at 34% · 1 not started. Press Transcribe to start them."

- **The status bar says what is in the library**, not where it is. A path
  parked permanently in the one place a message can appear is why every
  message it showed vanished back into a directory name; where the files live
  is a question the "This machine" tab answers.

### Fixed

- **Accessibility, after an audit of both interfaces.** Nine things, most of
  them one line each, all of them now held by a test.

  In the window: a note explaining a choice was drawn as *disabled* text and
  came out at **1.75:1**, where WCAG 1.4.3 asks for 4.5:1 — measured on the
  pixels of a rendered window, not estimated. Greying a `QLabel` is the cheap
  way to make explanatory text look secondary and it is the wrong one: the
  criterion exempts disabled *controls*, not the sentence that explains what a
  control does. The new `gui/style.py` mutes such text as far as it can while
  still clearing the ratio, and lifts the whole disabled group of the desktop's
  palette to the same floor, so "who said what" on a machine without pyannote
  stays legible — reading why is the only thing left to do with it, and the
  reason is now written on screen, with the command to fix it, rather than
  hiding in a tooltip.

  In the page: it no longer arrives **empty** when `/api/status` fails — every
  label is now in the markup in English and the translation replaces it — and
  every periodic call reports through one banner, so a server that goes away
  says so instead of leaving the last state on screen looking alive. The focus
  ring is drawn for the clipped file input (2.4.7); both progress bars have an
  accessible name (4.1.2) and it is a one-line summary that is announced rather
  than the job list, which was re-read in full every three seconds (4.1.3); the
  library says how many recordings matched, to the reader as well as to the
  screen reader; the recorder line folds instead of scrolling sideways at 320px
  (1.4.10); the transcript panels can be scrolled from the keyboard (2.1.1);
  the tab strips answer the arrow keys and take their label from the catalogue
  instead of announcing "Sorgente" to an English reader; the quiet buttons —
  which are also the destructive ones — are at least 24px high; field labels
  are no longer the smallest, slowest text on the page; and the body honours
  the reader's own font size instead of pinning 16px.

- **"Cancel" now cancels** in the keyword-set dialog. It is a submit button in
  a form whose name field is `required`, so with the name empty — exactly when
  you open a new set and change your mind — it ran the browser's validation and
  the dialog stayed open, with `Esc` as the only way out.

- **The empty part of a progress bar can be seen.** Both tracks were drawn in
  the divider colour, 1.33:1 against the page: at rest the input level meter
  was indistinguishable from not being there, which is the one question it
  exists to answer.

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
