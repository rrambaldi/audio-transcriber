# Security policy

## Reporting a vulnerability

Please report security issues privately, through
[GitHub's private vulnerability reporting](https://github.com/rrambaldi/audio-transcriber/security/advisories/new),
rather than in a public issue. You can expect an acknowledgement within a few
days.

## What this tool touches

Understanding the shape of the program helps in judging what counts as a
vulnerability.

- **Transcription is local.** Audio never leaves the machine. The only network
  access is downloading model weights from Hugging Face on first run.
- **Secrets.** The only secret handled is a Hugging Face token, used for the
  optional online diarization models. It is read from the environment or from a
  `.env` file, never written to `config.toml`, and never included in output. If
  you keep a token in `.env`, that file should not be world-readable.
- **The library holds your recordings.** Entries under the library directory
  contain the original audio and the transcript. Nothing encrypts them; the
  directory has whatever permissions your filesystem gives it.
- **Model weights are third-party code.** Loading a model executes code from
  the packages that read it (`ctranslate2`, `optimum-intel`, `pyannote`). Only
  point `--model` or `--diar-model` at sources you trust.
- **Input files are handed to ffmpeg.** They are passed as arguments to a
  subprocess, never through a shell.

## Supported versions

Fixes land on the latest release. This is a small project: there are no
long-term support branches.
