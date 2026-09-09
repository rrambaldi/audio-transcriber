# The desktop window

```bash
pip install -e ".[gui]"           # PySide6 (Qt 6)
pip install -e ".[gui,record]"    # and the audio-system, loopback and mix menus
audio-transcriber gui
```

The same transcriptions as the command line and the web page, in a window. It
exists for the machine you actually sit at: dropping files in, recording a
meeting as it happens, and reading last month's transcript while listening to
the moment it came from — without a browser, a server or a port.

## What it does

Three tabs.

**Transcribe.** Drop recordings on the list (or *Add files…*), or press
*Record* and speak. Choose the model — `auto` is labelled with what it resolves
to on this machine — the spoken language, the engine, "who said what" (greyed
out, with the reason, when this machine cannot do it), and the keyword sets:
the installed ones, your own, or both. See
[vocabularies.md](vocabularies.md). The table underneath follows every job:
queued, transcribing with a progress bar, done, or failed with the reason.

**Library.** Every transcribed recording, newest first. Search the transcripts
and the notes, read the transcript with a clickable timestamp per block, play
the recording while reading along, jump to any moment, write notes, rename,
export the text, open the folder, delete.

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

The engine underneath the menus is `recording.py`, next to `pipeline.py` and
with no Qt in it: the two audio libraries are objects it is handed, so
enumeration, mixing and what ends up in the WAV are tested with fakes rather
than with a microphone.

Keeping the decisions in `options.py` is what lets the test suite check them on
a server with no display and no PySide6 installed; `tests/test_gui_window.py`
drives the widgets themselves on Qt's *offscreen* platform, and skips when Qt
is absent.
