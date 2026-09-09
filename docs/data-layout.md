# Where your files live

A command-line tool should not scatter caches and recordings across whatever
directory it happened to be run from. This one keeps everything in the standard
per-user locations for your platform. To see the actual paths on your machine:

```bash
audio-transcriber paths
```

## The managed directories

| purpose | Linux / BSD | macOS | Windows |
|---|---|---|---|
| config | `$XDG_CONFIG_HOME/audio-transcriber` | `~/Library/Application Support/audio-transcriber` | `%APPDATA%\audio-transcriber` |
| data | `$XDG_DATA_HOME/audio-transcriber` | `~/Library/Application Support/audio-transcriber` | `%LOCALAPPDATA%\audio-transcriber` |
| cache | `$XDG_CACHE_HOME/audio-transcriber` | `~/Library/Caches/audio-transcriber` | `%LOCALAPPDATA%\audio-transcriber\Cache` |

`XDG_*` fall back to `~/.config`, `~/.local/share` and `~/.cache`.

Inside the data directory:

```
models/
  faster-whisper/       CTranslate2 weights, downloaded on first use
  openvino/             models converted to OpenVINO on first use
library/                one folder per recording, see below
diarization/            pyannote models, when kept locally
```

Inside the configuration directory:

```
config.toml             defaults; every value is overridable on the command line
.env                    secrets, currently only the Hugging Face token
vocabularies/           keyword sets written by hand, see vocabularies.md
srt-presets.json        your own subtitle presets, see subtitles.md
gui.ini                 what the desktop window remembers: its size and the
                        last options used, including the terms typed into it
```

Only `config.toml`, `.env`, `vocabularies/` and `srt-presets.json` are worth
backing up; `gui.ini` is a convenience the window rewrites as it goes. Nothing
under `cache/` is precious either: deleting it costs a re-download at worst,
and it is also where an upload or a fresh recording waits for its turn in the
queue.

## Overriding the locations

Three levels, strongest first:

1. A per-purpose variable: `AUDIO_TRANSCRIBER_MODELS_DIR`,
   `AUDIO_TRANSCRIBER_LIBRARY_DIR`, `AUDIO_TRANSCRIBER_CONFIG_DIR`,
   `AUDIO_TRANSCRIBER_DATA_DIR`, `AUDIO_TRANSCRIBER_CACHE_DIR`.
2. `AUDIO_TRANSCRIBER_HOME`, which puts config, data and cache under a single
   self-contained folder. This is the portable mode: use it in a container, or
   on a server where everything should sit on one mounted volume.
3. `[paths]` in `config.toml`, for `models`, `library`, `vocabularies` and
   `cache`.

```bash
# everything under one directory
export AUDIO_TRANSCRIBER_HOME=/srv/audio-transcriber
audio-transcriber paths
```

On a server the usual reason to move anything is that the home directory sits
on a small system disk. Three lines in `config.toml` do it without an
environment variable to remember, which matters when the same machine runs both
the command line and the web interface:

```toml
[paths]
models = "/mnt/volume/audio-transcriber/models"
library = "/mnt/volume/audio-transcriber/library"
cache = "/mnt/volume/audio-transcriber/cache"
```

`cache` is easy to forget and the one that bites: an upload from the web
interface is written there in full before it is filed, so a two-hour recording
passes through it. Note also that a configured `models` directory is used
**as it is**, without the per-engine subfolder the managed location adds — move
the contents of `models/faster-whisper/` into it rather than the folder itself,
or the engine will download everything again.

Command-line options (`--model-dir`, `--library-dir`) override all of the above
for a single run.

## The library

`--library` files a transcription as one self-contained folder:

```
2026-09-04_1530_team-sync/
├── metadata.json     what it is, how it was transcribed, how long it took
├── source.mp4        the original recording
├── transcript.txt    the readable text
├── transcript.json   segments with timestamps, and speakers when diarized
├── subtitles.srt     cues, when subtitles were asked for; see subtitles.md
├── subtitles.vtt     the same cues as WebVTT, if that was asked for too
└── notes.md          yours to write
```

The subtitle files are optional and derived: the cues are cut from
`transcript.json` whenever something asks, so an entry can be exported again
later with different numbers, and deleting them loses nothing.

The id is `YYYY-MM-DD_HHMM_slug`, so entries sort chronologically by name. Two
recordings filed in the same minute get a numeric suffix rather than
overwriting each other.

Everything a human needs is plain text or JSON: an entry stays perfectly
readable without this program, which is the point of the format. Metadata is
written through a temporary file and an atomic rename, so an interrupted run
cannot leave half a file behind.

`--library-store` decides what happens to the original recording:

- `copy` (the default) — the entry is self-contained; the original stays where
  it was
- `move` — self-contained, without keeping two copies of a large video
- `reference` — the entry records an absolute path and the file stays put

`metadata.json` records the source file's size and SHA-256 in all three cases,
so you can tell later whether a referenced file still is what it was.

### Browsing it

```bash
audio-transcriber library list
audio-transcriber library show 2026-09-04          # id prefix, or part of the title
audio-transcriber library search "risk assessment" # looks in transcripts and notes
audio-transcriber library path 2026-09-04          # for piping into other tools
audio-transcriber library remove 2026-09-04
```

`remove` refuses any path that is not inside the library directory.

## Files still read from the working directory

Two things are deliberately looked up next to where you run the command, so a
per-project setup keeps working:

- `.env` — read before the one in the config directory, so a project token wins
- `whisper-ov-models/` and `pyannote-diar/` — if these folders exist, they take
  precedence over the managed locations. This is purely for compatibility with
  installs from version 0.2 and earlier; new installs do not create them.
