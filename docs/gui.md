# The desktop window

```bash
pip install -e ".[gui]"           # PySide6 (Qt 6)
pip install -e ".[gui,record]"    # and the audio-system, loopback and mix menus
audio-transcriber gui
```

Or the script for it: `./install.sh` on Linux and macOS, `install.cmd` on
Windows. Both pull, install into the right environment and check what usually
goes wrong on that platform.

The same transcriptions as the command line and the web page, in a window. It
exists for the machine you actually sit at: dropping files in, recording a
meeting as it happens, and reading last month's transcript while listening to
the moment it came from — without a browser, a server or a port.

## What it does

Three tabs.

**Transcribe** is a header and a queue, and nothing else. Across the top, a
framed area with *Add files…* in it for people who would rather not drag
anything, and beside it the recorder — audio system, source, *Record*,
*Pause*, the level meter. Dropping a recording anywhere on the tab puts it in
the queue; the frame is where that is written down, and it lights up while
something is being dragged over the window. Under that, the queue itself, taking the
rest of the window.

There is deliberately **no column of options**. What a recording is for —
plain text, who said what, subtitles, with which model and which keywords —
is asked about *one* recording, in the dialog its *Transcribe* button opens.
Options beside the queue were answering those questions for a file that did
not exist yet, and answering them once for all of them; a queue is half a
dozen recordings at a time and one of them is the interview that needs
subtitles.

**A file you add goes into the queue and waits there**, marked *not started*.
It is started from its own row, or all of them together from the button under
the list — which asks the same four questions once, for the lot. Deliberately
two steps rather than one: the first version of this tab kept the chosen
files in a separate list waiting for a button and nobody could tell how to
begin, and the version after it started each file the moment it was added,
which left no room to say what that file was for.

The answers are remembered, so the second recording of the morning starts
from what the first one was told: six meetings in the queue should be six
confirmations, not six forms.

**The queue** — the whole of the tab under the header — holds every job newest
first. A row is a recording: its title, and under it the facts known so far
(the model, the length, the word count) or, if it failed, the reason with the
whole width of the column. The state is a word, and only the job that is
actually running carries a bar. *Transcribe* is the one filled button on the
tab and says how much it will start — "Transcribe 2 recordings" — and it is
the default, so Enter does what the screen is for. Under it:

| button | when |
|---|---|
| *Transcribe* | anything is waiting to be started |
| *Open in the library* | the job produced an entry |
| *Take out of the queue* | it has not started; the row goes, nothing happened to it, and the file is untouched |
| *Stop* | it is the one running (see below) |
| *Remove from the list* | it has finished, and the transcription stays in the library |
| *Clear the finished* | all of them at once |

**Every row carries its own buttons**, because "select the row, then press
the button under the table" is one step more than there needs to be and one
more thing to get wrong:

| button | what it does |
|---|---|
| *Transcribe* · *Stop* · *Open* · *Try again* | the same place in the row, whichever of the four applies to its state |
| *Play* | listens to the recording — the file itself before it is transcribed, the copy in the library entry afterwards |
| *Remove* | takes it out of the queue, or off the list once it has finished |

**Transcribing one recording asks what it is for**, in a dialog holding the
same four sections as the column, seeded from them. That is the point of the
arrangement: half a dozen recordings go in at once and one of them is the
interview that needs subtitles, so the answers belong to the recording rather
than to the tab. The button under the list still starts everything that is
waiting, with the answers on the left, for when they are all the same.

Four keys, for the people who do this a dozen times a day: <kbd>Ctrl</kbd>+<kbd>O</kbd>
adds files, <kbd>Ctrl</kbd>+<kbd>Enter</kbd> transcribes, <kbd>Delete</kbd> takes
the selected row out of the queue or off the list, and the tabs answer
<kbd>Ctrl</kbd>+<kbd>Tab</kbd> as Qt's own.


**The progress bar and the stage.** A run reports what it is doing as well as
how far along it is: starting, audio decoded, loading the model, converting it
(the first time, with OpenVINO), compiling for the device, transcribing, who
said what, laying out the text. The status column shows the stage next to the
state — *running: loading the model* — and the engine's own count of the audio
it has got through is mapped into the slice of the bar that belongs to
transcribing, so it never sends the bar backwards. With diarization on, the
transcription gets the first half of that slice and diarization the second,
because it takes about as long again.

This is worth more than it sounds. faster-whisper reports every segment, so
its bar really moves; the OpenVINO backend hands nothing back until it has
finished the whole recording, and there the bar stops at the low thirties for
the duration. The stage is what says the difference between waiting and
wondering. Making that bar move for real would mean chunking the audio in the
backend and calling the pipeline per chunk.

**Stopping the transcription that is running** asks first, and says what it can
honestly promise. The engines run inside one long blocking call, and the only
moment they hand control back is the progress callback: with faster-whisper
that is every segment, so it stops within seconds. The OpenVINO backend reports
no progress at all until it has finished the whole file — there the
transcription runs to the end and its result is discarded instead. Either way
nothing reaches the library, and the recording stays where it is, so it can be
queued again.

**Subtitles**, when they are the answer, get their own box: a preset (netflix,
bbc, ebu_broadcast, fcc_verbatim, social_vertical, social_karaoke,
kids_accessible), characters per line, words per subtitle, and whether to keep
an `.srt`, a `.vtt` or both with the entry — one of them is written either way,
so choosing subtitles ticks `.srt` rather than saving a file behind an empty
box. The cues exist even for the other two answers: *Export the subtitles* in
the library cuts an old entry with today's numbers. See
[subtitles.md](subtitles.md).

**The window paints with the desktop's palette**, with one floor imposed on
it. A note that explains a control is coloured rather than disabled — greying
a label is the cheap way to make it look secondary and it lands at 1.75:1,
where WCAG 1.4.3 asks for 4.5:1 — and the disabled group of the palette is
lifted to the same floor, so the answers this machine cannot produce stay
legible: reading why is the only thing left to do with one of them. It is
`gui/style.py`, and `tests/test_gui_style.py` measures it.

**Library.** Every transcribed recording, newest first. Search the transcripts
and the notes, read the transcript with a clickable timestamp per block, play
the recording while reading along, jump to any moment, write notes, rename,
export the text, open the folder, delete.

A **Summary** tab sits beside the transcript and the notes, with the button
that writes one under it and — when this machine has more than one engine — a
menu saying which will. What comes back says who wrote it and when: a page
that does not say is one somebody will quote in a meeting without knowing
whether a model or a sentence-picker produced it. See
[summary.md](summary.md).

The summary goes into the **same queue** as the transcriptions, not onto the
thread that draws the window. Two reasons, and both are the same reason: a
model reading an hour of transcript is minutes of the same cores a
transcription needs, and a window that does that work itself is a window that
has stopped responding.

**This machine.** What `audio-transcriber hardware` and `paths` report:
the CPU and memory found, the engine and model `auto` would pick, whether
diarization is available, and every directory in use — with a button that opens
`config.toml` and one that opens the library folder.

## Recording

The window records straight from the machine's own devices, which is the one
thing it does better than the browser: a page needs a secure context
(`https://` or `localhost`) before it may touch a microphone, a window does
not. Press *Record*, pause and resume as needed, press *Stop* — and the
recording is queued for transcription immediately, because whoever pressed
stop has just finished a meeting.

With the `[record]` extra installed there are two menus, the ones Audacity
puts in front of you:

**Audio system** — MME, DirectSound, WASAPI, WDM-KS. WASAPI is the native path
on Windows and the only one that can record what the speakers are playing; the
others are older wrappers over the same devices, kept for drivers that want
them. The same microphone therefore appears under several of them, which is not
a bug in the list but the shape of Windows audio.

**Source** — the devices of that audio system, with one addition: under WASAPI
each output device also appears as `[loopback] …`. Recording *that* records
what the machine plays, which for a call is everyone except you.

**Together with** — a second source mixed into the same file. A microphone plus
the loopback of the speakers are the two halves of a meeting held over Teams:
your voice and everyone else's. Without it a loopback recording has the others
and not you, and a microphone recording has you and, if you are lucky and
wearing no headphones, a thin echo of the others.

The mix is honest about its one limitation. Two sound cards run on independent
clocks and drift apart over an hour, so the first source sets the pace and the
second is held alongside it: whatever it has arrived is used, silence fills a
gap, and audio more than half a second ahead is dropped rather than allowed to
slide further and further behind. For a transcript that is invisible; for
music it would not be good enough.

**Test audio** opens the chosen source without recording anything: the meters
move, and after a second and a half the window says whether what is arriving
behaves like somebody talking. It stops itself after thirty seconds, because it
holds the microphone open while it runs, and pressing *Record* takes the device
back from it.

The verdict is one of three, with the numbers behind it:

| | what it means |
|---|---|
| *Nothing is arriving* | under -50 dBFS: the wrong source, a muted microphone, or Windows refusing this application the microphone |
| *Sound, but not a voice* | something is there and it holds one level: a fan, a tone, music, a hiss |
| *Sounds like speech* | bursts and pauses, in the band a voice lives in |

It is a guess, and it says so. Three measurements over the last few seconds —
the level, the decibels between the quiet moments and the loud ones, and how
much of the energy sits between 100 Hz and 4 kHz — are enough to tell a voice
from the two things a level meter cannot: a steady noise at the right level,
and silence with a hum in it. Whether the words are *words* is Whisper's job,
and Whisper needs a model, a file and a few minutes. The thresholds were
calibrated on synthetic signals, which are now the tests: a tone, mains hum,
white noise and constant noise inside the speech band all have to come out as
"sound", while bursts with pauses — loud, quiet, over a noisy room, and without
long pauses at all — have to come out as speech.

**The level meters** sit on the row of the source they measure, one per
source, and move while recording. They exist for one question — is anything
arriving at all — because the classic failure is a recording that turns out to
be an hour of digital silence: the wrong device, a muted microphone, or Windows
refusing this application the microphone (Settings, Privacy, Microphone). Two
bars rather than one for the mix, because a loopback that delivers nothing has
to be visible next to a microphone that works; with a single mixed bar it would
not be.

They are read in decibels, floored at -60 dBFS. A linear bar would be a useless
meter: ordinary speech peaks at around a tenth of full scale and would barely
leave the left edge, so a working microphone would look broken. On this scale
speech fills about two thirds.

And when a recording stops having never risen above silence, the window says
so. The file is queued anyway — it is real, and the decision is not this
program's — but a muted microphone otherwise produces a perfectly valid hour of
zeros that Whisper transcribes into nothing at all, half an hour later.

*Reload* asks for the device list again. PortAudio reads it once, when it
initialises, so a headset connected after the window opened is genuinely
invisible until something restarts it — which is what that button does.

Recordings are mono 16-bit WAV at the device's own sample rate. No resampling
happens in this program on purpose: every recording goes through ffmpeg on its
way to Whisper anyway, and ffmpeg resamples better than a few lines of numpy
would. An hour is about 350 MB at 48 kHz. The file is written into the cache
directory — the volume `[paths] cache` points at — and *moved* into the library
entry when the transcription succeeds.

### Without the [record] extra

The window falls back to recording through Qt: one flat list of microphones,
no host API to choose, no loopback, no mixing. It says so, and what to install.
Qt is also the fallback wherever the two audio libraries do not work —
`sounddevice` needs a PortAudio shared library, and `soundcard` speaks WASAPI
on Windows, PulseAudio on Linux and CoreAudio on macOS, where there is no
system loopback without a virtual device.

QtMultimedia itself ships in `PySide6-Addons`, which is why the `[gui]` extra
names both halves of PySide6 explicitly: pip only checks the name `PySide6`, so
an environment that already has `PySide6-Essentials` — or a Qt installed from
conda-forge — satisfies the requirement and never gains multimedia. If it is
missing anyway, the window still opens and both the recorder and the player say
so on the page:

```bash
python -m pip install "PySide6-Addons>=6.6"
```

### Linux and macOS

**The window is the same on the three platforms**, and not by coincidence:
there is not one `sys.platform` in `gui/`. The tab is a header and a queue,
the sections of the dialog are the same four, the buttons on a row are the
same three, everywhere. Qt draws them with the desktop's own palette, which
is why a Windows window looks like Windows and a Mac one like a Mac while the
layout under it does not move.

What does differ is what the machine can *do*, and the window says so in
place rather than by rearranging itself: the words in the *audio system* menu,
whether there is anything to record the speakers with, and whether "who said
what" is offered at all. The one visible consequence is the height of the
recorder in the header — with the `[record]` extra it has the audio system,
the source and the second source to mix in; without it, a microphone menu.

| | Windows | Linux | macOS |
|---|---|---|---|
| audio systems | MME, DirectSound, WASAPI, WDM-KS | ALSA, JACK, OSS | Core Audio |
| recording the speakers | WASAPI loopback | PulseAudio monitor sources | **not possible** without a virtual device |

**Linux.** The PySide6 wheel does not carry the system libraries Qt links
against, and a window that will not open says which one is missing. Usually
`libgl1 libegl1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4
libxcb-keysyms1 libdbus-1-3` on Debian and Ubuntu, and `mesa-libGL
libxkbcommon-x11 xcb-util-cursor xcb-util-wm xcb-util-keysyms dbus-libs` on
Fedora. `sounddevice` needs PortAudio (`libportaudio2`, or `portaudio` on
Fedora); without it the window records through Qt, from a microphone only.
The loopbacks are PulseAudio's monitor sources, which PipeWire also provides,
so recording a call works the way it does on Windows.

**macOS.** The wheels carry everything, including PortAudio: `./install.sh` and
nothing else. The one thing missing is loopback — Core Audio cannot record what
it is playing, and no flag changes that. The menu therefore offers no loopback
at all rather than an entry that fails when used; a virtual device such as
BlackHole, installed separately, appears as an ordinary input and can be
recorded and mixed like any other.

### If Qt came from conda

A `conda install pyside6` registers itself without the metadata pip needs in
order to replace it, so installing the PyPI halves over it stops with

```
Cannot uninstall shiboken6 6.11.0
The package's contents are unknown: no RECORD file was found for shiboken6.
```

Nothing is broken at that point — pip abandons the whole transaction — but the
fix is to take Qt out of conda's hands rather than to force pip past it:

```bash
conda remove pyside6 shiboken6        # --force if conda objects
python -m pip install -e ".[gui]"
```

Do **not** follow the hint pip prints (`--ignore-installed --no-deps`): it
leaves half the binding managed by conda and half by pip, which is one way to
end up with a Qt that imports and still has no QtMultimedia. Conda is the right
tool for the interpreter here; the Qt wheels come from PyPI.

### If it went into conda's `base` by mistake

`install.cmd` refuses that environment now, but an install by hand can still
land there. Nothing is lost; the way back is to remove what pip put in and give
conda its Qt back, in that order. The list comes from the machine rather than
from memory — `conda list` marks pip-installed packages `pypi_0`:

```bash
conda list > pip-in-base.txt
python -c "print('python -m pip uninstall -y '+' '.join(l.split()[0] for l in open('pip-in-base.txt') if 'pypi_0' in l and 'conda-pypi' not in l))"
```

The second line prints the command; read it, then run it. `conda-pypi` is
excluded on purpose: despite the name it is a conda package. Then, because
PySide6 is shipped in two halves that `conda list` does not always show:

```bash
python -m pip uninstall -y PySide6-Addons PySide6-Essentials
conda install --force-reinstall pyside6
```

A complaint about being unable to uninstall `PySide6` itself is expected —
that entry is conda's, and `--force-reinstall` is what puts it right. In the
`defaults` channel there is no separate `shiboken6` package: Anaconda ships it
inside `pyside6`, which is also why pip found a `shiboken6` with no RECORD in
the first place. Afterwards, `conda list | findstr /I pypi` should list only
`conda-pypi`, and `where Qt6Core.dll` only one copy.

The same clash has a second face, and this one is not an install error but a
startup failure:

```
PySide6 is installed but cannot be loaded: DLL load failed while importing
QtCore: the specified procedure could not be found
```

Both Qt builds are present, and an activated conda environment puts its own
`Library\bin` on PATH ahead of the DLLs pip ships next to the `.pyd` files —
so a 6.11.2 binding loads a 6.11.0 `Qt6Core.dll` and looks for an export that
is not in it. Nothing can be patched into place here: the search order is the
bug. Rebuild the environment with conda providing only the interpreter.

Do not reach for `conda remove qt6-main` in a full Anaconda `base` either:
Navigator, Spyder and qtconsole are Qt applications, and they go with it.

Order matters, and only in that direction. Once pip has written its wheels into
`site-packages/PySide6`, a later `conda remove pyside6` deletes the paths conda
still has on record — which are now pip's files — and takes the working install
with it. An environment that already got there is better left alone, or rebuilt
with conda providing nothing but the interpreter:

```bash
conda create -n at python=3.12 pip
conda activate at
python -m pip install -e ".[openvino,gui,record]"
```

## Jobs

The queue is the one the web interface uses (`jobs.py`), running in a worker
thread inside the window's own process. Jobs run **one at a time**: two
transcriptions at once finish neither any sooner and risk running out of
memory. The window polls it twice a second, which is why a progress bar can
move for an hour without anything being pushed at the GUI from the worker
thread.

Closing the window ends any transcription still running, so it asks first.
Every finished job is filed in the library, exactly as `--library` does.

**A file you picked is copied into the library entry; a recording the window
made is moved.** Moving someone's own recording out of their Documents folder
is not this program's decision to make; leaving a second copy of a two-gigabyte
recording in the cache directory is not useful either.

## What it remembers

Next to `config.toml` there is a `gui.ini`, holding the window's size and the
choices last used — model, language, engine, ticked keyword sets, and the terms
typed in the *your own terms* box. That box is the desktop counterpart of the
browser's local storage: it stays on this machine and never becomes
configuration. Everything that *is* configuration still comes from
`config.toml`, so the window starts on the same defaults the CLI uses.

## Where it runs, and where it does not

The window needs a graphical session. On a headless server there is nothing for
Qt to draw on — use `audio-transcriber web` there, or run the window on your
own machine against a library on a mounted volume (`[paths] library`).

Under X11 or Wayland, Qt needs the system libraries it links against; on a bare
container that usually means installing the distribution's Qt runtime
dependencies. `audio-transcriber gui` says so rather than showing a traceback.

## How it is put together

| module | what it holds |
|---|---|
| `gui/options.py` | every decision worth testing — the menus, the table rows, the transcript blocks — and **no Qt at all** |
| `gui/window.py` | the window, the three tabs, what happens when it closes |
| `gui/transcribe_panel.py` | sources, options, the queue table |
| `gui/library_panel.py` | the entry list, the reading pane, the notes editor, the player |
| `gui/recorder.py` | the audio-system and source menus, and the mix |
| `gui/qt_recorder.py` | the fallback recorder, on QtMultimedia alone |
| `gui/system_panel.py` | hardware and directories |
| `gui/multimedia.py` | QtMultimedia when it is there, and a clear answer when it is not |
| `gui/masthead.py` | the band above the tabs: the mark, the name, the promise |

## The mark, and whose icon the desktop actually draws

The window icon is not the window's own: `branding.py` hands out the renders
that ship with the package, and `window.app_icon()` builds a `QIcon` from all
of them, so the title bar gets the 16 px drawing and the alt-tab list the
256 px one. It is set on the `QApplication` and on the window, because a
window opened inside another Qt process has no say over that application. See
[brand.md](brand.md).

Setting it is not the end of it, because on two of the three platforms the
thing whose icon gets drawn is not the window:

- **Windows** takes a task-bar button's icon from the process's *Application
  User Model ID*, and the default is the interpreter's — so a `pip install`
  run of this program showed the mark in its own title bar and the Python
  logo on the task bar. `window.claim_taskbar_identity()` sets it to
  `branding.WINDOWS_APP_ID` before the first window exists, which is the only
  moment Explorer looks. A pinned shortcut has to carry the same string in
  `System.AppUserModel.ID` to pin to that button.
- **Wayland** has no counterpart to X11's `_NET_WM_ICON`: a window cannot
  hand the compositor a picture of itself. What GNOME and KDE draw in the dock
  and the alt-tab list is the `Icon=` of the desktop entry whose basename the
  application declares, so `launch()` calls `setDesktopFileName()` with
  `branding.DESKTOP_ENTRY`. The entry is `packaging/audio-transcriber.desktop`
  and `./install.sh` installs it, with the renders copied into
  `~/.local/share/icons/hicolor/*/apps/` under that same name — the icon is
  resolved through the icon theme, not from a path. Without that step the dock
  shows a grey default however many renders the package carries; X11 and macOS
  are unaffected, they take the icon from the window itself.
- **macOS** needs nothing: Qt puts `QApplication.windowIcon()` in the Dock.

Above the tabs there is a masthead — the mark, "Audio Transcriber", and the
same line the web page opens with. It is there because the title bar is not
somewhere to put an identity: it is 16 px tall, and on a maximised Windows
window or a tiling desktop it is not drawn at all. It paints none of the
brand's colours over the desktop's, for the reason in `gui/style.py`; the mark
carries the colour, and on a dark theme it swaps the master drawing for
`icon-mark.svg`, whose plate would otherwise sink into the background.

The engine underneath the menus is `recording.py`, next to `pipeline.py` and
with no Qt in it: the two audio libraries are objects it is handed, so
enumeration, mixing and what ends up in the WAV are tested with fakes rather
than with a microphone.

Keeping the decisions in `options.py` is what lets the test suite check them on
a server with no display and no PySide6 installed; `tests/test_gui_window.py`
drives the widgets themselves on Qt's *offscreen* platform, and skips when Qt
is absent.
