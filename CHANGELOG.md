# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **The About box links to the source on GitHub**, in the window and in the
  page, under the version.

- **The window lets you pick the exact summary model.** The *Summary* tab
  of the library has one *Model* menu, in place of *Written by*. It starts
  on automatic, which says which model the plan would pick now; opened, it
  lists every model under *GPU* or *CPU* and its engine, with *No model*
  last, and each one says how much memory it needs and whether that fits in
  what is usable now, measured again every time the menu opens. A model the
  configuration names outside the catalogue stays on the menu.

- **The window says how much memory to free for a better summary model.**
  The footer adds, next to the memory meter, *free 1.2 GiB and summaries use
  Spark-X2.5-4B, a better model*, whenever more free memory would change the
  model the plan picks. It is refreshed with the meters every two seconds
  and is said only for a model left to `auto`.

- **The interface speaks French and German too**, besides English and
  Italian: the command line, its help, the window and the page, every
  message of each. It is picked from a menu of the four, each named in its
  own words — at the foot of the page, and under the About link in the
  window — as well as with `--lang` or `interface_language` in
  `config.toml`, which until now was written down and never read.

  The page keeps its choice in a cookie rather than in the browser's
  storage, because the server reads it too: the status, the errors and the
  jobs that page submits come back in its language while the server goes on
  speaking its own to everybody else. The window keeps its choice in
  `gui.ini` and opens in it the next time; a `--lang` typed on the command
  line still wins.

- **The sections of a summary can be chosen, by name or by hand.** A
  template says *these* are the sections I want and this is what goes under
  each; `audio-transcriber template list` shows the ones that ship —
  `meeting` (what the program does by itself), `minutes` (decisions, actions,
  open questions and nothing else), `requirements`, `interview`, `narrative`
  — and `--template minutes`, `[summary] template`, or the box in the web
  interface picks one. Written by hand they are plain text files in
  `<config>/summary-templates`, a heading and what belongs under it per
  line, shadowing a bundled one of the same name. The same object the keyword
  sets are, on purpose.

  The machinery for it was already in the program and connected to nothing:
  every reading pass looked for the same eight kinds of note, and which ones
  to look for was a parameter no setting ever set. What was missing is that
  the catalogue of kinds was three dictionaries at module level, so a heading
  nobody had written into the source could not exist. It is a value now, and
  it travels with the run.

  In the page and in the window it is a menu beside "how much to keep", whose
  last entry opens a box to write the sections into for one summary rather
  than saving them — the same bargain the terms box makes. A template that
  does not parse is refused when it is asked for, not three minutes into a
  reading pass.

  Worth knowing before restricting them: a template restricts the *reading*,
  not only the page. A pass that is not asked for opinions does not write
  them down, and reading the same recording again under another template
  starts from the transcript. Length is the opposite, deliberately.

- **Spark-X2.5-4B writes the summaries on llama.cpp**, at Q8_0, wherever six
  gigabytes are usable: it wrote the best page measured, 20 of the 21 facts
  of the reference against Granite 4.0 H-Tiny's 18, and none invented. It is
  five to eight times slower, and that was accepted. It needs llama.cpp
  b10828 or later; an older build refuses it on load, and the run says so
  and goes on with the next model down instead of failing.
  `diagnose.cmd` now measures it against Granite on the same recording,
  fetching a new enough llama.cpp build when the installed one is older.
  Before each run it also says when more free memory would change the run —
  a better model, or room for the one named — and asks whether to close
  things and check again or to go on as it is. At the end it sends the files
  of the round to the server with the `scp` Windows ships with, and a round
  already measured on that machine is not measured again unasked: R runs it
  again, S only sends.

### Changed

- **The About box opens on the banner**, in the window and in the page: the
  mark, the name and the tagline as the README shows them, edge to edge,
  instead of the mark and the name set in type. In the window the box now
  also leaves room for the paragraph about what is bundled, which it used to
  draw over the licence.

- **A summary is now the page the recording produced, not five fixed
  headings.** One heading per subject, prose under each written from that
  subject's own notes, and decisions and actions listed at the foot. The
  shape that folded every reading pass into one answer is still there, under
  `shape = "headings"` in `[summary]`.

  The number that decided it is the distance between what the passes read and
  what reached the page. Same twenty-two minute recording, same model, same
  reading passes: the old shape read 41% of the minutes and printed 14% of
  them; the new one read 36% and printed 36%. Measured twice, on two engines.
  The fold had the whole recording to fit into one answer and dropped
  whatever did not fit, and nothing on the finished page said so.

- **The precision the weights are read at can be asked for.** `quant` in
  `[summary]`, or `--quant`, taking `Q8_0`, `Q6_K`, `Q5_K_M` or `Q4_K_M`. The
  plan loads the coarsest file by default because it is the one that fits
  everywhere, and a machine with memory to spare had no way to say so. Asked
  for one it cannot hold, it steps down the same ladder it already uses for
  the context and the cache rather than refusing to summarise.

  Measured straight away, and the default holds — though not for the reason
  it first looked like. The finer file is exactly as fast (184 s against
  182 s; the seven-times-slower first reading was a download inside the
  clock), and it reaches within one minute-bucket of the same coverage once
  its answers are given room. What does not move is the repetition: 6 of the
  coarse file's 82 notes said something already written down, against 22 of
  the fine one's 83. The setting is there for a machine where that goes the
  other way, which is a thing to measure rather than assume.

- **A reading pass is given a chunk it can actually read.** It was handed
  4500 tokens of transcript — eleven minutes of meeting — and it wrote down
  twelve things and stopped. The same recording read 1200 tokens at a time
  went from 36% of its minutes on the page to 96%, for a hundred seconds
  more. Below that the extra passes buy repetition rather than recording, so
  1200 it is, and `chunk_tokens` still overrides it.

  On a machine with a limit on how many passes it will spend, that limit is
  scaled to match. A tier decides how much transcript to read, not how finely
  — without the scaling, the finer reading would hit the cap and the
  transcript would be cut to fit, spending the coverage it had just bought.

### Added

- **The llama.cpp engine now uses the graphics card, where there is one.** It
  was written for a server with two cores and was asking for two cores
  everywhere, including on a laptop whose `llama-server` had been built
  against Vulkan and could see an Intel Arc.

  Before loading anything the binary is asked what it can run on
  (`--list-devices`), and the first device that is not a processor gets every
  layer of the model. `device` in `[summary]` decides instead, when it should:
  `cpu` to stay on the cores, or a name the binary printed. A build with no
  backend, or one too old for the flag, runs exactly where it did before.

  This is the way round the other engine's limit, too. OpenVINO has to convert
  a model before it can run it, and the conversion is what fails on the larger
  ones; llama.cpp runs the GGUF as it arrives, whatever backend is underneath.

  Two smaller things that came with it: a summary run in this shape prefers
  the binary that can see an accelerator over a Python binding that cannot,
  and when `llama-server` refuses to start, what it wrote on its way out is
  now repeated instead of discarded — until now a wrong flag, a file that was
  not a GGUF and a driver that would not load all failed with the same line.

- **A summary now says how much of the recording it is a summary of.** A page
  about a twenty-two minute meeting came back describing the first seven, and
  nothing anywhere said so: every pass had succeeded, the page was well
  formed, and the only way to find out was to read the transcript and compare.

  Two numbers are computed from every summary, by every engine, and printed
  whether or not anybody asked: what share of the recording's minutes reach
  the page, and how much of the page is word for word out of the transcript.
  Under four fifths of the recording, or over a third copied, and it says so.

  Beside them, for the engine that reads in passes, an account of what each
  pass did — `--debug` for all of it, and always the ones that went wrong: a
  pass that produced nothing, a pass whose answer was the question and was
  replaced by quoted speech, and a fold that produced nothing and kept only
  the first of the partials it was handed. That last one says how many it
  threw away. `--dump-notes` writes the lot to a JSON file, which is how a
  problem of reading is told from a problem of writing without reading an
  hour of audio again.

  The share is measured twice on purpose — once over what the reading passes
  wrote, once over what the finished page carries — because the interesting
  failure is the difference between them. Read and then lost is a different
  bug from never read, and it has its own line.

- **A reading pass now produces notes, and is shown how.** What a pass wrote
  used to be a bullet list whose shape nothing checked and whose lines nothing
  could be said about. It is now read back into notes — one fact each, with a
  kind, a minute and whoever said it — which is the thing grouping and writing
  will be given once they exist, and which can be counted in the meantime.

  The kinds are the catalogue the earlier design worked out for the page's
  headings, kept whole and given a different job: it stops meaning *which
  headings do I print* and starts meaning *which atoms do I collect*. Three of
  its entries left, because they are not kinds of note — a topic is a section,
  and a date and a number are attributes found by looking. One arrived:
  `requirement`, which the catalogue lacked and these recordings are mostly
  made of.

  The prompt that asks for them carries a worked example, and that is not
  decoration. Measured over four runs, the first reading pass wrote eight
  notes and put a minute on none of them — whatever the chunk held and however
  much room it was given — while every later pass placed all of theirs. A
  small model copies the shape of an example far more reliably than it obeys a
  sentence describing one.

  The prompt is also twice the size it was, and the room left for transcript
  is now measured rather than guessed at four hundred tokens. A chunk sized
  against the old figure overflowed the window by the difference, silently,
  because what falls off the end is the end of the transcript.

- **A summary says when closing something would write a better one.** Which
  model writes a summary is decided by the memory that is *free*, not by the
  memory the machine has, and nothing ever said so: a laptop with thirty-two
  gigabytes and a browser open summarises with a two-billion-parameter model
  and reports nothing unusual, because nothing unusual happened. It is simply
  a worse summary than that machine can write, arrived at honestly and
  presented as the only one on offer.

  One line now, before the reading starts, naming the model more room would
  fetch and how much room that is. Only when it is worth acting on: the better
  model has to be one this engine can actually load, and one that would fit in
  the memory the machine really has. Otherwise it is not advice, it is a
  remark about somebody's hardware.

  It also pins something worth knowing. `Qwen/Qwen3.5-4B` is registered by
  optimum-intel as an image-text-to-text architecture and cannot be exported
  for text generation at all, so it joins the models the OpenVINO path will
  not attempt — a refusal that used to cost a download of several gigabytes
  and a failed conversion on every run that reached for it. With it listed,
  **the OpenVINO ladder stops at MiniCPM5-2B**: everything above it in the
  catalogue is a hybrid or a multimodal checkpoint. Through llama.cpp, on the
  processor, the same machine reaches Granite 4.0 H-Tiny with four times the
  context.

- **A summary can be written one section at a time, and nothing sees the
  whole recording.** The shape this feature started with asks a model for a
  page, then to merge pages, then to merge the merges — and every one of those
  steps has to hold the entire recording in one window. Measured on a
  twenty-two minute meeting: the reading covered 41% of it and the page
  carried 14%, and giving the reading more room only moved the loss further
  along. There is no setting of those numbers that gets the meeting onto the
  page, because the throughput of the whole thing is one context window
  applied three times.

  So: a section is written from its own notes and no others, and the question
  stays small however long the meeting was. A title is written from the same
  handful. The opening paragraph is written from the section titles alone,
  which is also what stops it repeating the bullets underneath it — it has
  never seen them, and the page it replaces had an opening identical to its
  own list of key points, word for word.

  The page it makes has a heading per subject the recording actually had,
  with a framing paragraph and its detail under it, and the decisions and the
  actions collected at the foot. No minutes in the body: they are kept with
  the notes, and `--timestamps` puts them back. The document is titled after
  its own sections, never after a fragment of speech — the page this replaces
  was called *"Ne va a Napoli Tutta una cosa"*.

  It is not the default yet, and that is deliberate rather than timid: it has
  never been run against a model, and replacing the only measured path with an
  unmeasured one is how a feature is lost rather than improved. `summary.shape
  = "sections"` turns it on, and it becomes the default the day a run says it
  is better.

- **Notes are grouped into sections by arithmetic, with no model involved.**
  Notes about one subject find each other by the words they share; the
  recording decides how many sections there are, and they come out in the
  order it had them. A note that arrived twice — which happens on every seam,
  because chunks overlap on purpose — is recognised and dropped, keeping the
  fuller telling and the earlier minute. What a note mentions, and any dates
  and figures in it, are read out of its own text rather than asked of a model
  that would sometimes supply ones nobody said.

  Three ways of deciding what a section is, and what they share is everything
  that happens to a note before it is placed. `discover` lets the distances
  decide; `fixed` sends each note to the section its own kind names, computing
  no distances at all, because running a decision through a clustering to
  arrive at a heading called *Decisions* is a lossy way of getting where it
  already was; `hybrid`, the default, discovers the body and collects the
  decisions and the actions into lists of their own as well as leaving them in
  the section that explains them.

  None of it reaches the page yet — that is the next step — but every run now
  measures it, because it costs one matrix multiplication to find out whether
  a real recording falls into themes a reader would recognise.

- **A subtitle file can be summarised as what it is.** `summarize` on an
  `.srt` or a `.vtt` read it as prose, which shreds every time it carries into
  the middle of the text and leaves the summary unable to say when anything
  was said — or how much of the recording it covers. They are read as cues
  now, whatever the file is called: the minutes survive, a cue that names its
  voice hands the name over, and the length of the recording comes from the
  last cue.

- **A recording can be seen as well as read.** Two drawings of the same
  thing — how loud it was, moment by moment — in both the window and the page.

  While you record, the last five seconds scroll past beside the level meter,
  one column every tenth of a second. The meter stays: it answers whether
  anything is arriving at all, and that is worth its own bar. The trace answers
  the question after it, which the bar cannot — a meter holding steady at two
  thirds and a meter moving with every syllable are the same meter, and only
  one of them is somebody talking. Same decibel scale, floored at -60 dBFS, so
  the newest column is exactly what the bar is showing.

  And under the name of every recording, in the library and in the queue, the
  whole of it at once. An hour of meeting and an hour of empty room have the
  same date, the same length and the same model, and they look nothing alike.
  It is four hundred measurements kept with the entry in `waveform.json`,
  written while the recording is being transcribed — the audio is decoded then
  anyway, so it costs nothing — and derived like the subtitles, so deleting it
  loses a second of ffmpeg and nothing else.

  A recording filed before this existed is measured the first time somebody
  looks at a row of it, once, and kept afterwards. One at a time, and only for
  the rows on screen: measuring is a pass of ffmpeg over the whole file, and a
  library of forty must not start forty of them to draw a page. A queued
  recording is measured on a thread of its own rather than behind the
  transcriptions, because a drawing that arrives after the job it describes is
  a drawing of nothing anybody is still looking at.

### Fixed

- **No blank band between the recorder's buttons and the queue.** The two
  message lines under the buttons each kept two lines reserved, empty, so
  that a wrapped sentence would not be cut: four blank lines, all day. They
  now take room only while they say something, and a long message still
  gets every line it needs.

- **A model named by hand no longer hears about a better one.** The note
  that more free memory would buy a better model was said even when the
  model had been chosen by name, where no amount of free memory changes
  which model runs.

- **A section no longer carries a minute nobody said.** The notes a section
  is written from have no minutes in them, and the instructions every answer
  is given say to cite the minute "like [12:34]": a model with nothing to
  cite copied the example. Spark-X2.5-4B wrote it eleven times on one page,
  Granite 4.0 H-Tiny once. A minute in a section or in the opening paragraph
  is now taken out, since none of them could have been copied from the
  recording.
- **A section title written as one word is split into words.** Spark-X2.5-4B
  names sections like a programmer — `MonitoraggioUtentiCampagna` — and the
  page now says "Monitoraggio utenti campagna". A name like "GitHub" is left
  alone.

- **`short`, `medium` and `long` now do something on a model engine.** They
  had only ever reached the extractive one: on the two engines that write
  prose the setting was read, carried through the settings, printed in the
  job's description, and then never looked at — so all three names produced
  the same page, word for word.

  They now change the questions and never the answers. A short section is
  asked for as one paragraph of one or two sentences with no list, a long one
  as a paragraph with a bullet per note, and the opening paragraph and the
  number of sections move with them. Short is asked in those words and held
  to them by its allowance as well: told merely to keep it brief, a model
  writes the bullets anyway and the page comes out a little shorter instead
  of short. What does not move: the reading, which covers the whole
  recording at every length — asking again for a longer page re-uses every
  pass, which is what the pass cache was keyed without the length for — and
  the decisions and the actions, because there were as many of them as there
  were.

- **A summary in the new shape no longer falls over at the last step.** It
  read the recording, grouped what it found, wrote every section, and then
  crashed measuring how much of the recording it had covered — because the
  decisions and actions at the foot of the page are notes, and a note says
  when it happened in a field of its own. Minutes on the page are counted the
  same way whichever shape the page has, and in one place rather than two —
  there were two copies of that count, and fixing the first left the run
  ending in the same line a step earlier.

- **A llama-server named in the configuration now counts as installed.**
  Asking for the engine by name was refused — "summary engine 'llamacpp' is
  not installed on this machine" — on the one kind of machine the setting
  exists for: the binary was named in `config.toml`, and the question of
  whether the engine was there was being asked without the settings that held
  the answer. The same was true of the engine list in the window and on the
  page, and of what `audio-transcriber hardware` reported about this machine.

- **A heading in the wrong language no longer loses its notes.** Asked for
  Italian headings, a small model answers in the nearest language it knows
  better: a real run came back with `Decisões`, `Ações` and `Requisitos`, and
  every note under them was demoted to a plain fact, which emptied the
  decisions and actions at the foot of the page. A heading close enough to
  one that was asked for now counts as that one — including `Questioni
  apert`, which is the right language with the end missing — and a word that
  is close to none of them still counts as none.

- **Being told an engine is missing now says what would install it.** Both
  ways in for llama.cpp, the configuration key included, and the one `pip
  install` for OpenVINO. The bare refusal sent somebody reading the source
  for the name of a setting.

## [0.9.0] — 2026-09-17

### Added

- **The window and the server keep a log, and both can show it.** They used
  to print into whatever terminal they were started from: a terminal the
  person using them has usually closed, and on Windows, from a shortcut, one
  that does not exist at all. So a recording that failed at four in the
  morning failed silently, and the only honest answer to "what did it say"
  was "nothing, anywhere".

  Everything they would have printed now goes to a file — under the cache
  directory, capped, with one older copy kept beside it — and both front ends
  read it back: a *Messages* panel on the window's *This machine* tab, and one
  under the job list on the page, each with a button to empty it. It is a
  redirection of the two output streams rather than a logging framework, which
  is what makes it catch the things worth catching: this program's own
  messages, but also uvicorn's, pyannote's, and the traceback of whatever went
  wrong. Every line is stamped, and a line built by several threads at once is
  still one line.

  The command line is untouched, on purpose: there the output *is* the
  interface. `AUDIO_TRANSCRIBER_LOG_CONSOLE=1` gets the terminal copy back in
  the window and the server, for somebody who is watching one;
  `AUDIO_TRANSCRIBER_LOG_DIR` moves the file, and `audio-transcriber paths`
  says where it is.

- **The speakers in a transcript can be given names.** *Name the speakers*, in
  the library — the window and the page both — on any recording that was
  transcribed with "who said what". One field per voice, in the order they are
  first heard, each with the first thing that voice says under it, because
  "which one was `SPEAKER_01`" is a question the dialog should answer rather
  than ask.

  The transcript and the timestamps are rewritten to use the names: the rule
  for the library is that an entry stays as readable without this program as
  with it, and a transcript that says `SPEAKER_01` beside a metadata file that
  says it means Anna is a puzzle rather than a document. What the metadata
  keeps is where the names came from — which label the machine handed out, and
  what it was called afterwards — so a folder opened in a year still says so.
  A voice left blank keeps its label, which is how one person is named without
  a decision about the others; two labels given the same name are one person,
  and their turns are run together.

  It is done afterwards and not asked for up front on purpose: which voice is
  whose is in the room, not in the sound, and nothing here guesses at a name
  it heard in the audio — the person addressed is not the person speaking.

### Changed

- **A button now looks like one.** It used to be a word with a hairline under
  it and nothing else — which is exactly the drawing a field gets here, so a
  row of buttons read as a row of empty fields and people could not tell what
  was pressable. The style is the same; what was missing was a *surface*. A
  button is now a small sheet lifted off the paper, closed on four sides by
  hairlines, with the rule it always had along its foot, heavier than the
  three that close it — so the family resemblance survives the change. Hover
  and focus are still said in the accent, and the primary action is the accent
  on the accent's own wash rather than a box filled with it: nothing here is
  filled, which was the point of the old drawing and is kept.

  In both front ends, because they are meant to be one program. A tab, a
  timestamp and the small "delete"/"stop" asides are deliberately left as they
  were: those are words you can click, not the actions of the row they sit in.

- **The page copies a pane the way the window does.** The transcript, the
  summary and the notes each have a copy button beside them, on the pane's own
  bottom line — the window's layout for the same three boxes, rather than one
  word in the footer that only ever applied to the summary. It is drawn and
  not spelled, off the same vendored file the window paints its own from: the
  page masks it and fills the mask with the current text colour, so it follows
  the palette into dark and turns to the accent under the mouse, and there is
  still exactly one copy of the drawing in the package.

- **The rename and copy buttons are drawn rather than spelled.** They were
  characters borrowed from the text font, which is the cheap way to have an
  icon and looked it: thin at nine points beside a hairline rule, missing
  altogether from some faces, and a different size on every platform. They are
  drawings now — two from Microsoft's Fluent set, MIT, bundled with the fonts
  and the mark — rendered in the window's own ink at the interface font's
  size, following the desktop into dark and back, and going to the accent
  under the mouse like every other button. A build that shipped without them
  falls back to the character, the way a missing typeface falls back to the
  next family in the stack.

### Added

- **A recording can be named after what was said in it.** *Name it after what
  was said in it* — a tick box beside the four answers, in the window and on
  the page, `--auto-title` on the command line, `[general] auto_title` in
  `config.toml`. When the transcription is filed, the entry is titled from the
  transcript instead of from the file it arrived as: a library of
  `2026-09-15_1830` is a library nobody can look through, and the date is
  already in the row.

  No model is loaded and nothing is sent anywhere. The transcript is ranked
  the way the extractive summary ranks it — TextRank over the sentences — and
  the strongest sentence is trimmed into a label: the opening filler dropped
  ("allora", "so", "dunque"), cut at a clause boundary rather than at a word
  count, never left ending on a preposition or an article. Where a summary has
  already been written, its first sentence is used instead, because a sentence
  written about the whole recording beats the best sentence taken out of it.
  A recording with nothing in it keeps its file name rather than being given a
  title made of noise.

- **Every queue row says how long the recording is, how big, and when it was
  made — whatever state it is in.** The length is read from the file's header
  when the job is made, which costs milliseconds and no decoding, so a
  recording waiting its turn can already say it is fifty minutes long. A failed
  row carries the same three facts and then the reason, rather than the reason
  alone: it is still the file it was. A row written down by an older version,
  which recorded none of the three, has them filled in when the queue is read
  back rather than staying blank for the rest of its life.

### Added

- **The silence filter works on the OpenVINO backend too.** It used to be
  faster-whisper's alone, and the OpenVINO run said so and handed Whisper the
  silences as they were — which is exactly what Whisper invents phrases over.
  The detector is Silero, shipped inside the faster-whisper package and run by
  onnxruntime: no download, no token, no torch, so installing both engines is
  all it takes. The timings come back onto the recording's own clock
  afterwards, so subtitles and speaker turns land where the words were said.
  An interview with long pauses is also quicker to transcribe, because the
  model is never given the pauses.

### Fixed

- **A small model that says "there was nothing here" in its own words is now
  believed.** The one-section-at-a-time summary asks for a fixed marker when a
  section has nothing in it, and an xs-tier model answers "nessuna
  informazione disponibile" instead: meaning it and being able to obey are not
  the same thing. That line was read as content, became the only non-empty
  draft of the summary, and the pass that checks the four sections against
  each other was then skipped for having nothing to compare — so an hour of
  meeting came out as one line saying there was nothing in it. A short answer
  that opens on a denial now counts as the marker, in either language. The
  length is what makes that safe: a real finding about something that did not
  happen — "no decision on the hires, but the budget passed" — is longer than
  a refusal, and is kept.

- **The summary no longer narrates itself to the console.** Twelve `[TRACE]`
  and `[DEBUG]` lines left over from debugging in September printed on every
  run, unconditionally: when a model was loaded, when each prompt started and
  how long it took. They were never anybody's business but the author's, and
  with the log file they had begun to be written down as well as printed.

- **Two upstream warnings printed over every run are no longer repeated.**
  transformers said, twice per transcription, that a token-suppression
  processor had been passed to `generate()` as well as created inside it —
  about an argument optimum-intel passes itself, which nobody running a
  transcription can change. torch said, from C++, that a speaker turn one
  frame long has no standard deviation, which happens on ordinary recordings
  and whose embedding pyannote discards anyway. Both are matched on the exact
  wording of the line and dropped in `audio_transcriber.quiet`, which is where
  anything else of the sort goes and where each one has to say why: a changed
  or new message from either library comes through as it should.

- **A fallback to fixed windows now says how to get out of it.** When
  `optimum-intel` and `transformers` disagree, Whisper's own long-form loop
  cannot run and the OpenVINO backend drops to thirty-second windows, where
  overlapping text can come out twice. It said what it had given up but not
  what to do about it; it now names the cause — a version mismatch, not the
  recording — prints the `pip install -U` line that settles it, and points at
  `--backend faster-whisper` for the meantime.

- **transformers lectured the console about an option nobody chose.** When
  the long-form loop is unavailable and the OpenVINO backend falls back to
  fixed windows, transformers printed a paragraph about `chunk_length_s`
  being experimental on seq2seq models — over a transcription that was
  running, after the fallback had already said in its own words what it gave
  up. The remedy the warning itself names (`ignore_warning=True`) is sent
  now, and only to an installation whose pipeline knows the keyword.

- **A summary in the queue looked like a recording nobody could identify.** A
  summary job is made with the title of the library entry it reads, and has no
  audio of its own — no length, no size, no date — so on the list it was the
  twin of the transcription that produced that entry, and four retries of one
  summary read as four unknown files with nothing under them. The row says
  *Summary: <entry>* now, over *summary of the transcript*, in the window and
  on the page.

- **The About box showed the licence as it was on the day the program was
  installed.** An editable install copies the licence into its own metadata
  once and never looks at it again, and that copy was preferred over the file
  in the checkout — so a licence changed afterwards was invisible to everyone
  running from the source tree, which is everyone working on it. The checkout
  wins now; a wheel, which has no source tree beside it, still finds the copy
  its metadata points at.

## [0.8.0] — 2026-09-15

### Added

- **A suggested model this installation cannot use hands over to the next
  one.** The summary model is chosen by the plan — `auto`, by tier and by free
  memory — and the newest model in the catalogue is exactly the one most
  likely to be missing from the OpenVINO exporter's list of architectures:
  asking for `Qwen/Qwen3.5-4B` came back "the exporter only supports
  image-text-to-text for qwen3_5", and the summary ended there. A refused
  conversion now moves down the catalogue instead, says which model it gave
  up on and why, and writes the page with the next one. A model asked for *by
  name* is never replaced: somebody who names one wants that one, and the
  error is the answer.

  The model is also converted before the transcript is reduced rather than
  after, so a model this machine cannot use is found out in the first seconds
  instead of after the minutes that reduction takes.

- **The queue says how big each recording is and when it was made.** In the
  window's rows and on the page, beside the model and the language: a queue of
  a dozen files named by date is told apart by those two before it is told
  apart by anything else. Both are read from the file when the job is made,
  not when the row is drawn — a finished transcription moves its upload into
  the library entry, and a queue read back after a restart would have nothing
  left to ask. "When it was made" is as close as each platform gets: the
  creation time on Windows and macOS, the modification time on Linux, which
  has no creation time to offer.

- **A summary can be asked for with the transcription, and it says where it
  has got to.** *Write a summary as well, when it is done* — a tick box beside
  the four answers, in the window and on the page (`[summary]
  with_transcription` in `config.toml` preselects it). It queues a second job
  behind the transcription rather than making the first one longer: the same
  two cores either way, and as its own row it can be watched, cancelled and
  retried, and a summary that fails leaves a finished transcription finished.

  And a running summary now draws a bar and names its stage, like every other
  job: choosing what matters, reading the transcript, writing the summary —
  with the percentage and how long it has been at it. A model reading an hour
  of transcript is minutes of nothing at all otherwise.

- **Working out who said what now reports its own progress, and every running
  job carries a clock.** Diarization was one blocking call: the bar jumped to
  the start of its band and stood there for the whole phase — which on a long
  recording is the longer half of the wait — with nothing to say whether it
  was working or hung. pyannote announces each step it starts and how far
  through it is, so the bar now moves across that band and the row says which
  step it is on: *finding the speech*, *measuring the voices*, *counting the
  speakers*, *telling them apart*. A pyannote too old to report anything says
  so once and runs as before.

  Because a single step can still take twenty minutes, the row also shows how
  long the job has been running, in the page and in the window. A bar that
  does not move next to a clock that does is a job working; the same bar with
  nothing beside it is a job you start to doubt.

  The hook is also the first place a *running* diarization can be
  interrupted: *Stop* now reaches it, where before it could only be asked and
  had to run to the end.

- **The load meters are in the window's footer as well.** CPU, memory and the
  engine-and-device a run would use, at the right-hand end of the status line,
  where they can be watched while a transcription runs — a meter that lives in
  a tab is one you open after wondering rather than before. The *This machine*
  tab keeps the full version with the run queue, and both draw from the same
  sampler, so the two places cannot disagree by an interval. Still no GPU
  percentage, for the same reason as before: OpenVINO publishes none, and the
  tooltip says so rather than leaving it to be wondered about.

- **`audio-transcriber diarize fetch` downloads the diarization models into
  one folder of ordinary files.** Left to itself, pyannote scatters them
  through the Hugging Face cache — a tree of commit hashes and symlinks that
  cannot be backed up, copied to another machine, or described in a README,
  and where the only fix for a refused file is editing that tree by hand.

  The command fetches the pipeline *and the repositories its config names*
  (they are gated separately) into subfolders of one directory, and rewrites
  the config to point at them. What is left is self-contained: it works with
  no token and no network, it can go on a stick or into a backup, and
  `--diar-model` points at it. Into the managed folder by default, where it is
  found automatically; `--to` puts it anywhere, `--model` chooses the pipeline.

- **The queue survives a restart.** It lived in memory: closing the window or
  restarting the service threw away everything that had not run yet — the
  files, the titles, and the answers about what each recording was for — and a
  transcription interrupted at minute fifty had to be set up and started again
  from nothing.

  It is now written down beside the uploads (`queue.json` in the cache
  directory) after every change, and read back at startup. What was waiting is
  still waiting, with its settings and keyword sets; what was *running* goes
  back in the queue and starts again, because the recording is still there and
  nobody has its transcript. A job interrupted three times is marked failed and
  left alone instead — that is what a recording which takes the process down
  with it looks like from here, and without the count every restart would pick
  it up again. A job whose upload has gone is dropped; an upload with no job
  pointing at it still appears as *not started*, which is the behaviour that
  was already there and is now kept without duplicating the restored rows.

- **`diarize check` tries the Hugging Face token instead of noting that it
  exists.** With no local files the models are downloaded, so the download is
  what the check has to test — and it asks about the pipeline *and every model
  its config names*, because those are separate gated repositories whose
  conditions are accepted one at a time. That is how a run downloads the
  pipeline and is then refused its segmentation model, an hour in. Each
  repository is printed with OK or the refusal, and a refusal is followed by
  the two things that have to be true: the conditions accepted with that
  account, and a token allowed to read gated repositories — the checkbox a
  fine-grained token does not have by default. Two seconds, no weights.

- **`audio-transcriber diarize init` writes the `config.yaml` a folder of
  downloaded models does not come with**, filled in with the model files it
  finds there — the right keys, the published thresholds, and paths relative to
  the folder, so it keeps working wherever the folder is moved. Weights are
  recognised by the names pyannote publishes them under, and a folder holding
  both sets (which is what downloading twice, from two sets of instructions,
  leaves behind) gets the 3.1 pair the written config is for; a `plda/` beside
  them says the folder is a pyannote 4 clone and gets a note saying the
  config written here ignores it.

  **`audio-transcriber diarize check`** runs the pre-flight the transcription
  runs — which config would be used, whether the files it names are there —
  without transcribing anything, because an hour is a long time to wait to be
  told that a file is missing.

- **"Open the folder", next to the record button.** A recording is a file
  before it is a transcription, and the first thing wanted of it is often to
  keep it, send it, or play it in something else — but the window wrote into a
  folder it never named. The button shows the recording just made in the
  system's file manager, with the file *selected* where the platform can do
  that (Explorer, the Finder), and opens the folder around it everywhere else.
  Once a recording has been filed by its transcription it lives with its
  library entry, which the Library tab opens; the button then shows the folder
  the next recording will be written to. It is on both recorders, including
  the plain Qt one a machine without the audio extras gets.

- **Four answers to "what do you want out of it?", and who said what is one of
  them.** It was three answers and a tick box: *just the text*, *the text with
  who said what*, *subtitles* — and, down in the subtitle section, a *who said
  what* box that meant nothing beside two of the three and made the third two
  different runs wearing one name. The menu now asks the question once:

  1. just the text
  2. the text, with who said what
  3. subtitles
  4. subtitles, with who said what

  **How many voices there are is asked on the line that asks who they were**,
  beside the second answer, which is the one detail those two answers have and
  was previously a spin box two sections below, next to that tick box. It is
  greyed out rather than hidden while another answer is chosen, so picking one
  does not move the rest of the list out from under the pointer, and it is the
  same number for both answers that ask.

  The same four in the window, on the page and on the command line
  (`--output subtitles_speakers`, `output = "subtitles_speakers"` in
  `config.toml`), because they are one decision made in one place: every answer
  now settles diarization, instead of leaving it to a box elsewhere. Settings
  written before this — `--diarize` with subtitles, or the flags in a
  `config.toml` — are read back as the answer they describe, so nothing has to
  be rewritten. A machine without pyannote offers neither of the two answers
  that ask who was speaking, with the reason on both.

- **How busy the machine is, on the page and in the window.** Two meters above
  the job list and a group on the *This machine* tab: the CPU, the memory, and
  a line saying which engine would run a transcription and on what device.
  Two figures rather than one, because they answer different questions — on a
  two-core server the CPU sits at 100% for the whole of a transcription and
  says nothing, while the memory left is what decides whether the next job
  survives; below a tenth free that bar turns to the alarm colour. And a
  percentage never says *what* is working, which on a machine with an Intel
  iGPU is the whole question, so the device is named next to it.

  No new dependency: the CPU share comes from `/proc/stat` on Linux and
  `GetSystemTimes` on Windows, read the same way the memory figures already
  were, and a system that reports neither gets no bar rather than a zero that
  would read as an idle machine. The page polls `/api/machine` every two and a
  half seconds and stops while the tab is not on screen; the window samples
  only while its tab is visible. A GPU *percentage* is deliberately not
  offered: OpenVINO exposes no such counter, and the honest answer is the
  device, not a number that would have to be invented.

- **Two launchers, `run.cmd` and `run.sh`.** They do what everybody was doing
  by hand: get into the environment — the conda one named by `AT_ENV`,
  `srt-ov2` by default on Windows, the active one or the checkout's virtualenv
  elsewhere — and then run the program with whatever they were given.
  `run.cmd hardware`, `./run.sh meeting.mp4 --lang it --summary`. With no
  arguments they open the desktop window, so a double-click on `run.cmd` from
  Explorer is a way to start the program. When this environment's `Scripts`
  folder is not on `PATH` they use the module form, which always works.

- **A text you already have can help the transcription and correct it.** The
  case: you have the recording *and* something written for it — a script, a
  press release, the slides, a transcript from somewhere else. Paste it (a box
  in the window's *Subtitles* section, the same box on the page,
  `--reference FILE` on the command line) and it is used twice, never as a
  replacement.

  Before the run, as a prompt: its distinctive words — names, acronyms,
  numbers, compounds, long rare words — go to the engine, which is the same
  mechanism a keyword set uses and the only lever Whisper offers over
  spelling. The prose between them is left out, because a prompt is a few
  hundred characters and "and then we agreed that" buys nothing; keyword sets
  asked for by name keep first claim on that budget.

  After the run, as a proof-reader: each word the engine produced is lined up
  with the word the text has in that position and corrected *only where the
  two are plainly the same word* — an accent dropped (`perche` → `perché`), a
  name misheard (`rambardi` → `Rambaldi`), a word cut short (`trascriz` →
  `trascrizioni`). "Plainly the same word" is a Levenshtein distance of one,
  inside a word of at least six letters, and not at the last letter — where
  one edit is a plural or a tense, which the audio decides. That rule is
  measured rather than felt: on thirty-two pairs drawn from real engine slips
  and real near-misses it puts none on the wrong side, where a similarity
  *ratio* at any threshold gets between three and fifteen wrong — `premesso`
  and `permesso` are 87% alike and two different words. **The audio decides what was said; the text decides how it
  is written.** A word that is simply another word stands as heard, a sentence
  the text has and the audio does not is not added, a sentence the speaker
  improvised is not removed, and a capital that is only a sentence start in
  the text is not imposed — while a name keeps its capital, because the text
  never writes it in lower case. Nothing is re-timed and no word is added or
  dropped, so the transcript, the cues and the audio cannot come to disagree.

  It reports what it corrected *and* how much of the text turned up in the
  audio at all — "corrected 41 of 3980 words heard", "92% of it turned up" —
  warning under 60%, because a text of another recording corrects almost
  nothing and "corrected 3 words" reads like a success. The figures are kept
  with the library entry under `reference`.
  [docs/subtitles.md](docs/subtitles.md) has the whole of it, including the
  list of what it will not do and why.

- **Both front ends can show the licence, in an About box.** In the browser it
  is one click from the bottom of the page — *About this program*, in the
  footer — and in the window it is the version in the masthead, which now
  reads `v0.3.0 · About`, or F1: there is no menu bar to hide an About box
  behind, and a version is what somebody clicks when they want to know what
  they are running. Both show the licence **whole** rather than by name,
  because it is the MIT license with a wish in front of it and the wish is the
  half worth a screen. Both also say what is bundled that is not ours: the two
  typefaces, under OFL, whose licences the page links to and the window names.
  The text comes from `audio_transcriber/about.py`, which finds the file
  wherever this copy keeps it — a wheel's `dist-info`, or the top of a
  checkout — so neither front end carries a copy to drift from, and a build
  with no licence file at all says so instead of showing a blank box.

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

- **The caveat about a model that failed was written in the wrong language,
  and at the wrong length.** It went through the interface's catalogue, so an
  Italian summary carried an English explanation of why it was quoted rather
  than written — while the caveat next to it, from the same page, was in
  Italian. Every note on a summary is in the language that was *spoken*; this
  one is now too. And what the model or its runtime said is cut to a line: a
  failed OpenVINO export is three hundred characters of stack-adjacent prose,
  and this is a caveat on a page somebody is reading, not a log.

- **A model that gives nothing back no longer costs the summary.** "`{model}`
  returned nothing usable" was the end of the road after minutes of a model
  reading an hour of transcript — and it is true of three different failures
  that are not fixed the same way. The message now says which one it was: no
  text at all, an answer that is *all* the model narrating its own reasoning
  (a thinking model cut off before it began, which is what a small MiniCPM
  does with a tight token allowance), or an answer that is about something
  other than the recording, quoted back so it can be recognised.

  And the page gets written either way: a model engine that fails now falls
  back to the quoted sentences, with the reason at the top — the same
  treatment a model that will not fit in memory already got. An error with
  nothing to show for it is the one outcome worth avoiding after a wait that
  long. The extractive engine failing is still a failure: there is nothing
  under it to fall back to.

- **A diarization with pyannote 4 crashed at the last step, and took the
  whole transcription with it.** pyannote 3 returns the annotation; pyannote 4
  returns a structured object with the annotation inside it, beside the
  overlap-free variant and the confidence scores — so reading `.itertracks`
  off it raised `AttributeError: 'DiarizeOutput' object has no attribute
  'itertracks'`, after the audio had been transcribed and the speakers worked
  out. Both shapes are now read, by the names the annotation is known to go
  under and, failing those, by looking for the one field that can be iterated
  as turns: a version that renames it should cost a line of hunting, not an
  hour of work.

  And it no longer costs the transcript either way. A diarization that falls
  over — for any reason short of being cancelled — now leaves the text written
  plain, with a warning saying what went wrong, exactly as a diarization that
  produces no turns already did. The audio was transcribed; that part is not
  thrown away because the half that runs second failed.

- **The token advice now says the step that actually unblocks it.** Every
  message about a refused download talked about accepting the conditions and
  ticking the gated-repos box, and stopped there — but a *fine-grained* token
  grants nothing it does not name: the pyannote repositories have to be added
  to the token itself, under *Repository permissions*, with read access. That
  is the step this was stuck on, and the hub's refusal does not mention it.
  `diarize check`, `--diarize` without a token, `diarize fetch` and the README
  now all say: accept the conditions, **edit the token and name those
  repositories**, tick the gated-repos box — or use a classic *Read* token,
  which needs neither of the last two.

- **`diarize check` asked the hub for metadata and called it access.** A
  gated repository hands its card to anybody and refuses its *files* to a
  token without the scope for them — which is the exact failure the check
  exists to catch, and which `model_info` reports as fine. Worse, the one call
  that did fetch a file had its failure swallowed, so a token that could not
  download a byte was given a clean bill of health while the run it was
  checked for died on `resolve/.../config.yaml`. The check now really fetches
  a file from the pipeline and from every repository its config names; "no
  such file" from a repository that let us in still counts as access, because
  it is an answer.

- **A hub that cannot be reached is no longer reported as a licence
  problem.** Every failure to get the models printed the same wall of text
  about accepting conditions and ticking a token scope — including "we cannot
  find the requested files in the local cache", which is what
  `HF_HUB_OFFLINE=1` produces. That variable is precisely what somebody sets
  to work around a refused file, so the message arrived at the worst possible
  moment and pointed at the wrong thing. The two are now told apart: a
  refusal still gets the licence and token advice; a hub out of reach says so,
  and when offline mode is what silenced it, it names the variable, the
  command to unset it and the `.env` files it may be written in.

- **An engine the machine does not have can no longer be chosen, or
  remembered.** The window offered all of them and remembered the last one in
  `gui.ini`, which outlives an environment: a `faster-whisper` chosen once —
  or carried over from another install — turned every job on a machine without
  it into the same failure, raised deep inside the run, after the audio had
  been decoded, with nothing on screen saying why. The menu now greys out what
  is not installed, with the reason on it, and a remembered engine that is not
  in this environment is left on `auto` instead of being restored.

  `resolve_backend` refuses it too, before anything starts: an engine asked
  for by name has to be here, and the message says what *is* here. That covers
  the command line and the page as well as the window.

- **"Diarization: available (token)" on a machine that has the models on
  disk.** The report looked at the token first and the local files second,
  while the run does the opposite — with both, the folder is what gets loaded.
  So `hardware`, the *This machine* tab and the web page all announced a
  network trip that had not happened for weeks, and hid which config was in
  use. They now name the file or folder when there is one, and fall back to
  the token only when there is not.

- **"The package is not installed" is no longer said about a package that is
  installed.** An engine that will not import was always reported as missing,
  which sends somebody to install what they have just installed — the Windows
  classic being a `faster_whisper` whose `ctranslate2` cannot load its DLLs, or
  an OpenVINO that lost its place in the search path. The failing module names
  itself in the exception, so the two cases are now told apart: a package that
  is genuinely absent still gets the `pip install` line, and one that is there
  and will not load says so, with the real error underneath and a reminder to
  check which environment the program is running from.

- **A mixed recording kept only a tenth of its second source.** "Together
  with" — a microphone plus the loopback of the speakers, which is the only
  way to record both halves of a call — read the second device once per block
  of the first, asking for "whatever has arrived since". Both audio libraries
  answer that question with a *single packet*, and on Windows a packet is the
  device period: ten milliseconds out of every hundred. The rest never reached
  the file, and the driver said so on the console, hundreds of times, as
  `SoundcardRuntimeWarning: data discontinuity in recording`. The far end of a
  meeting came out chopped.

  Each source now has a reader thread of its own and is drained continuously,
  so the mix is both halves in full. What arrives while the mixing loop is
  elsewhere is held (capped at thirty seconds, oldest first, so a paused
  recording cannot grow it without end), and a second device that dies no
  longer ends the recording: the microphone keeps writing and the reason is
  kept for afterwards.

  The platform's own API is also asked to hold **half a second** instead of
  the one device period it holds by default, so a thread that is momentarily
  late — a garbage collection, a transcription running on the same two cores —
  loses nothing. The warning now means what it says, and is rare.

- **A local pyannote folder is found wherever the program was started from,
  and a repo id asked for by name is the one loaded.** Three things stood
  between a hand-downloaded set of diarization models and being used.

  The paths inside a `config.yaml` are resolved by pyannote against the
  *working directory*, not against the config, so a folder that is plainly
  there is invisible to a window launched from the desktop or a service with a
  `WorkingDirectory` of its own — the pre-flight only warned about it. They are
  now settled before the config is handed over, looked for beside the config
  and one level up as well, and pyannote gets a copy with absolute paths in it.
  The file you pointed at is never rewritten; the copy goes in the cache.

  `--diar-model` (and `model` under `[diarization]`) now accepts the
  **directory** of a pipeline repository cloned from the hub, which is the
  layout pyannote 4 documents for offline use — `config.yaml` and the weights
  in one folder. Before, a directory was read as if it were the config file
  and the run stopped on "cannot read the config".

  And a repo id is no longer mistaken for a missing file: `owner/name` has a
  slash in it, which was enough to have
  `--diar-model pyannote/speaker-diarization-community-1` reported as a missing
  path and **silently replaced by the default pipeline**, so the model that ran
  was not the model that was asked for.

- **The models are looked for where people actually put them, and the command
  that lists directories says where that is.** A folder of pyannote models is
  found beside the command (as before), in the managed `diarization/`
  directory, and now also as `pyannote-diar/` **inside** that directory —
  moved in whole, under its own name, which is what keeps the relative paths
  written in its config working. So a window started from a desktop shortcut,
  with no `config.toml` anywhere, finds a folder that was simply dropped in.
  `audio-transcriber paths` and the window's *This machine* tab now print a
  `diarization` line naming the exact file being looked for, which is the
  question — where do these files go? — that neither of them answered.

- **A folder of models that has been moved or renamed is still found, and a
  file that really is missing is named next to the files that are there.** The
  paths inside a hand-written `config.yaml` usually start with the folder's own
  name (`pyannote-diar/segmentation-3.0/pytorch_model.bin`), which stops being
  true the moment the folder is dropped into the managed `diarization/`
  directory. Those leading folders are now peeled off one at a time and the
  rest looked for under the config's own folder, so what identifies the file is
  its tail; nothing is guessed at, the tail has to match exactly.

  And when a file genuinely is not there, "the config references local files
  that do not exist" was a dead end. The message now also lists the model files
  that *are* in that folder — which is usually the whole answer, because the
  two sets of pyannote weights are named differently (`segmentation-3.0/` in a
  3.1 setup, `segmentation/` in a community-1 clone) and one config was written
  for the other set.

- **A refused download says which of the two settings it is about.** A gated
  repository answers `403 Forbidden: Please enable access to public gated
  repositories in your fine-grained token settings`, and then a page of
  traceback. It is always one of two things — the repository's conditions not
  accepted with that account, or a fine-grained token without *Read access to
  the contents of all public gated repos* — so that is what is printed, with
  the offline alternative next to it, instead of the stack. The pre-flight line
  now also names the repository it is about to download, which is the fastest
  way to notice that the model in use is not the one you meant.

- **The window was still drawing the wrong cut of the serif, on Windows.**
  Twice now the axis was the answer and twice it was ignored, so this time the
  axis is gone: Qt does not apply a variable axis itself, it asks the
  platform's font engine, and where that engine does not it draws the file's
  *default instance* — which in Fraunces is `opsz 9, wght 900`, the Black text
  cut. That is exactly what a screenshot from Windows showed, letterforms and
  weight both. The window now loads three static cuts instanced from the same
  file — `Fraunces Display` for a masthead-sized title, `Fraunces Text` in
  Regular and SemiBold for everything smaller, so a weight is a face and never
  a synthesis — and asks for a family by name. 105 KiB for the three, less
  than the variable file they came from. The page keeps the variable file: a
  browser applies the axes properly, and one file there covers both cuts.

- **The About box reads in the right order.** The version sits directly under
  the name, where somebody looking for it looks, and the licence's own name
  sits under the "license" heading with the text it names, instead of being
  bolted onto the version line. Both front ends.

- **And the wrong weight of it, for the same reason.** `QFont.setWeight`
  chooses among the *named* instances a font declares and never touches the
  `wght` axis, so a variable face answers it with whichever instance it
  happens to have: the masthead came out fatter than the page's own heading,
  and the promise under it came out bold on Windows after being asked for
  regular. The axis is now set as well as the named weight, and the promise
  asks for Light — its italic has to be synthesised, since the bundled subset
  has no italic face, and a slanted regular reads a step heavier than an
  upright one.

- **The window calls itself `audio-transcriber`, in lower case**, as the web
  page and the README do: it is a command's name, not a product's. The name
  the desktop is told is a separate string — the task bar and the application
  menu ask for a human-readable one, and title case is their convention.

- **The version number moved into the About box.** It was in the masthead,
  which is a band somebody reads all day and not where a build number
  belongs; the About box is one click away and is where the rest of what this
  program is already lives.

- **The window was drawing the wrong cut of its own typeface**, and at the
  wrong size. Fraunces has two faces worth having: a sturdy text cut and a
  high-contrast display cut with hairline serifs, and the page sets its
  heading in the second one. The window was drawing the first, at display
  size — heavy and dull beside the page, which is exactly how it looked. It
  now takes the display cut and the page's own proportions: the name at 3×
  the interface font rather than 1.45×, tracked in 2% as the page tracks it;
  the promise in the serif's italic at regular weight, a hair over the
  interface font; the mark at 64 pixels, which is a render drawn pixel for
  pixel. (Two attempts to get the cut by asking the variable font for an
  optical size are further down this section, under Fixed: they worked here
  and not on Windows, and static faces are what settled it.)

- **The rule under the masthead ran out to the window frame** while everything
  above and below it kept the gutter. It is the bottom edge of the masthead,
  not a divider across the window, and the page draws it inside its own
  margins too.

- **A machine with plenty of memory was told it had none.** The reserve kept
  free for the operating system was a fifth of the *installed* RAM, so a
  desktop with thirty-two gigabytes and seven of them free — an ordinary
  Tuesday — reserved six of the seven and concluded that no model fits, with
  an Intel GPU sitting idle. What has to stay free does not grow with how much
  RAM somebody bought; the reserve is capped at two gigabytes.

- **A reasoning model on OpenVINO answered nothing at all.** Its generation
  config has no switch for reasoning — no released version of OpenVINO GenAI
  has one — so the model narrated until its allowance ran out and was cut off
  before the answer began. Every summary came back empty, which is
  indistinguishable from a model too small for the job, and nothing anywhere
  said so. The chat template is the authority: where it knows an
  `enable_thinking` variable, the model was trained to read an empty
  narration as the same instruction, so the template is applied here and the
  answer started for it. Where the template knows no such thing, nothing is
  invented — and that case now says so out loud, once, instead of silently
  returning nothing.

- **A conversion refused for a version pin said so as if it were a bug.** The
  OpenVINO exporter caps the version of transformers each architecture can be
  exported with, and an environment with a newer one simply cannot convert
  that model. The message names the ceiling now, and the line that gets past
  it.

- **The Windows installer did not install the summary engine.** Its default
  extras were `openvino,gui,record`, so a machine with an Intel device
  transcribed and then reported that no summary engine was installed, having
  just listed three OpenVINO devices — the devices come from `openvino`,
  writing a summary needs `openvino_genai`. `summarize-ov` is in the default
  now, and it is only the small half of a download that extra already makes.
  There is also a `summarize-cpp` extra at last, for the llama.cpp engine; it
  is in no default, because pip builds it from source.

### Changed

- **The licence is now the Gratitude & Random Kindness License.** The MIT
  license, word for word, with a wish in front of it: that this software rests
  on tools and ideas that were a gift, and so is given freely, with a wish
  rather than a price. The wish says of itself that nothing in it is a
  condition and that it is not enforceable, which is the only honest way to
  wish for anything — so nothing downstream changes. The packaging metadata
  says exactly that: the license *expression* is `MIT`, because that is what a
  dependency scanner has to tell a user about what they owe, and the file
  itself travels as `License-File`, because that is where a person reads it.
  `tests/test_licence.py` compares the operative paragraphs with the canonical
  MIT text word for word, so the wish can be rewritten freely and the terms
  cannot be rewritten by accident. The metadata also moves to the PEP 639
  form — an expression and `license-files` instead of a table and a
  classifier, both of which setuptools now deprecates — so building needs
  `setuptools>=77`.

  Four files carry `SPDX-License-Identifier: MIT` in their own heads, and only
  four: the two install scripts, which get copied out and run on their own,
  and the stylesheet and the script a browser downloads. Those are the files
  that travel without the repository around them, so they are the ones where a
  header earns its three lines; everything else is covered by `LICENSE` and by
  the package metadata. The header names the licence as well as the
  identifier, because the identifier alone would drop the half of it that is
  the point.

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
