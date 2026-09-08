# The desktop window

```bash
pip install -e ".[gui]"       # PySide6 (Qt 6)
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

The window records straight from a microphone with QtMultimedia, which is the
one thing it does better than the browser: a page needs a secure context
(`https://` or `localhost`) before it may touch a microphone, a window does
not. Pick the input, press *Record*, pause and resume as needed, press *Stop* —
and the recording is queued for transcription immediately, because whoever
pressed stop has just finished a meeting.

The microphone menu follows the machine: Qt reports a device being plugged in
or taken away, so a headset connected after the window opened appears by
itself, and one unplugged mid-session does not leave a stale name behind.

Recordings are mono, in the best container this Qt build can encode (AAC in
MP4, then FLAC, then WAV): speech, and Whisper resamples to 16 kHz anyway. The
file is written into the cache directory — the volume `[paths] cache` points at
— and *moved* into the library entry when the transcription succeeds.

QtMultimedia ships in `PySide6-Addons`, which is why the `[gui]` extra names
both halves of PySide6 explicitly: pip only checks the name `PySide6`, so an
environment that already has `PySide6-Essentials` — or a Qt installed from
conda-forge — satisfies the requirement and never gains multimedia. If it is
missing anyway, the window still opens and both the recorder and the player
say so on the page:

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
| `gui/recorder.py` | the microphone |
| `gui/system_panel.py` | hardware and directories |
| `gui/multimedia.py` | QtMultimedia when it is there, and a clear answer when it is not |

Keeping the decisions in `options.py` is what lets the test suite check them on
a server with no display and no PySide6 installed; `tests/test_gui_window.py`
drives the widgets themselves on Qt's *offscreen* platform, and skips when Qt
is absent.
