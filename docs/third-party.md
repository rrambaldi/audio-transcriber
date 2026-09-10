# Other people's work

This program is [licensed](../LICENSE) as MIT with a wish in front of it. That
covers the code in this repository and nothing else, so this file is the list
of what else is involved and under what terms.

Two of them are **copyleft** and are named in the program's own About box —
the desktop window's and the web page's — because that is where a user can
reasonably be expected to find them: Qt, which the window is built on, and
ffmpeg, which reads the audio. Everything else on this page is permissive
(MIT, BSD, Apache-2.0), and the About box points here rather than reciting it.

## What ships inside the program

| What | Where | Licence |
|---|---|---|
| **Fraunces** (four cuts: the variable file and three static instances) | `src/audio_transcriber/data/brand/fonts/` | SIL Open Font License 1.1 — `fraunces-OFL.txt` beside it |
| **Karla** | same | SIL Open Font License 1.1 — `karla-OFL.txt` beside it |
| The mark, the icon set, the banner | `data/brand/`, `docs/assets/` | This project's, under this project's licence |

The static cuts of Fraunces are instanced from its variable file and carry
derived family names (`Fraunces Display`, `Fraunces Text`). The OFL allows
that here: neither licence declares a reserved font name. [brand.md](brand.md)
says how they are made.

Nothing else is vendored. Everything below is installed by pip, into the
user's own environment, and stays under its own licence.

## What pip installs

Checked against the metadata of the installed distributions on 2026-09-10
where this machine had them, and marked *declared* where the licence is the
one the project publishes but was not verified here.

| Package | For | Licence | |
|---|---|---|---|
| `PySide6`, `PySide6-Addons`, `shiboken6` | the desktop window (`[gui]`) | **LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only** (Qt also sells a commercial licence) | checked |
| `imageio-ffmpeg` | decoding audio and video | BSD-2-Clause — but it ships an **ffmpeg** build, and ffmpeg is **LGPL-2.1-or-later** (some builds GPL) | declared |
| `numpy` | audio as arrays | BSD-3-Clause (with 0BSD, MIT, Zlib parts) | checked |
| `faster-whisper` | transcription on CPU (`[cpu]`), through CTranslate2 | MIT | declared |
| `optimum-intel`, `transformers` | converting and running Whisper on Intel devices (`[openvino]`) | Apache-2.0 | declared |
| `openvino`, `openvino-genai` | the Intel runtime, and the summary engine (`[summarize-ov]`) | Apache-2.0 | declared |
| `pyannote.audio` | "who said what" (`[diarize]`) | MIT — its **models** are gated and have their own terms | declared |
| `llama-cpp-python` | summaries on plain CPU (`[summarize-cpp]`), through llama.cpp | MIT | declared |
| `fastapi`, `starlette`, `pydantic` | the web interface (`[web]`) | MIT / BSD-3-Clause / MIT | checked |
| `uvicorn` | the web server (`[web]`) | BSD-3-Clause | declared |
| `python-multipart` | uploads (`[web]`) | Apache-2.0 | checked |
| `sounddevice` | audio systems and input devices (`[record]`), through PortAudio | MIT | declared |
| `soundcard` | recording what the speakers play (`[record]`) | BSD-3-Clause | declared |
| `pytest`, `ruff`, `httpx` | development only | MIT / MIT / BSD-3-Clause | checked |

## What the program downloads at run time

Model weights are not distributed with this program and are not covered by its
licence. It fetches them on first use, from Hugging Face, and each carries its
own terms:

| Model | Terms |
|---|---|
| Whisper (`openai/whisper-*`, and the CTranslate2 and OpenVINO conversions of it) | MIT, from OpenAI |
| pyannote speaker-diarization models | Their own licence *and* an acceptance step on Hugging Face: the program cannot do that for you, and says so when the model is missing |
| The GGUF summary models (`LiquidAI/LFM2.5-*`, `openbmb/MiniCPM5-*`) | Each model's own licence, on its own model card |

`audio-transcriber paths` says where they end up.

## Keeping this honest

Two things make this file rot: a new dependency, and a licence changing
upstream. `tests/test_licence.py` checks that every extra named in
`pyproject.toml` appears here, so the first one fails the suite. The second
one is a reading job, not a test — the *checked* rows above were read from
installed metadata, and the date at the top is when.
