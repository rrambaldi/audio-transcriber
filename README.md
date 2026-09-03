# audio-transcriber

Turn audio/video recordings into readable text — **entirely on your machine**.
Whisper transcription accelerated on **Intel iGPU via OpenVINO** (CPU and NPU
also supported), with optional **speaker diarization** ("who said what") via
pyannote. No cloud, no API keys for transcription, your recordings never leave
your computer.

Built for meeting recordings you want to summarize afterwards.

## Features

- One command: `audio-transcriber meeting.mp4` → `meeting.txt`
- Accepts anything ffmpeg reads (wav, mp3, m4a, mp4, mkv, ...) — ffmpeg is
  bundled via `imageio-ffmpeg`, nothing to install
- Whisper large-v3 by default, or tiny/base/small/medium for speed
- Cleans up Whisper's typical silence hallucinations ("Thanks for watching...")
  and chunk-overlap duplicates
- Groups text into readable paragraphs based on speech pauses
- Optional diarization with pyannote (runs on CPU), including fully **offline**
  mode with local model files
- Domain vocabulary prompt to keep technical terms from being mangled

## Install

```bash
# with conda (see environment.yml) or plain pip:
pip install "optimum-intel[openvino]" transformers imageio-ffmpeg numpy
pip install pyannote.audio        # optional, only for --diarize
pip install -e .
```

## Usage

```bash
# plain transcription (Italian by default, Intel iGPU)
audio-transcriber meeting.wav

# "who said what" with 3 known speakers
audio-transcriber meeting.wav --diarize --speakers 3

# force CPU and a lighter model
audio-transcriber meeting.wav --device CPU --model medium

# another language, custom output file
audio-transcriber talk.mp4 --language en --out talk.txt
```

Run `audio-transcriber` with no arguments for the full option list.

On first run the Whisper model is downloaded and converted to OpenVINO format
(cached in `whisper-ov-models/` in the current directory).

## Diarization setup

Two options:

1. **Online**: set `HUGGINGFACE_TOKEN` (in a `.env` file next to where you run
   the command, or as an environment variable) with *Read access to public
   gated repos*, and accept the terms of `pyannote/speaker-diarization-3.1`,
   `pyannote/segmentation-3.0` and `pyannote/wespeaker-voxceleb-resnet34-LM`
   on huggingface.co.
2. **Offline**: place the pyannote models locally and point a
   `pyannote-diar/config.yaml` at them (default location: current directory).
   No token needed at runtime.

## Roadmap

- [ ] Local web UI: record straight from the browser, drag & drop files,
      background transcription jobs
- [ ] Searchable library of recordings with notes (Markdown)

## License

MIT
