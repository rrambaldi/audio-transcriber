# Contributing

Thanks for looking. This is a small tool with a narrow purpose: turning
recordings into readable text, locally, on whatever hardware you happen to
have. Contributions that keep it small are the most welcome kind.

## Getting set up

```bash
git clone https://github.com/rrambaldi/audio-transcriber
cd audio-transcriber
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[cpu,dev]"                      # or ".[openvino,dev]" on an Intel iGPU
pytest
ruff check .
```

The test suite needs no models, no GPU and no network: everything that touches
a transcription engine is behind a seam that tests replace. Please keep it that
way — a suite that runs in a second is a suite people actually run.

Two modules skip themselves when their optional extra is absent:
`tests/test_web.py` without FastAPI, `tests/test_gui_window.py` without
PySide6. What the interfaces *decide* is tested regardless, in
`tests/test_web_page.py` and `tests/test_gui.py`, so a change to either
interface is still covered on a machine with neither installed. Add
`".[gui,dev]"` if you are working on the window; the Qt tests run on the
*offscreen* platform, so no window ever appears.

## House rules

- **Code, comments and docstrings are English.** Text the user reads goes
  through `audio_transcriber.i18n.t()` and is added to every catalogue in
  `i18n.py`. A test fails if the catalogues drift apart.
- **The core stays light.** `numpy` and `imageio-ffmpeg` are the only hard
  dependencies. Anything heavier belongs in an extra, imported lazily inside
  the function that needs it, with a clear message when it is missing.
- **Nothing is written to the working directory.** Files go to the managed
  locations in `paths.py`. See [docs/data-layout.md](docs/data-layout.md).
- **Explain why, not what.** Comments earn their place by recording a decision
  or a trap, not by restating the line below them.
- Follow the existing style; `ruff` settles the rest.

## Pull requests

Keep them focused, describe what changed and why, and add a test when you fix a
bug — a test is how the fix stays fixed. Update `CHANGELOG.md` under
"Unreleased" if the change is visible to users.

If you are thinking about something large, open an issue first so nobody writes
code twice.

## Reporting a bug

Include the output of `audio-transcriber hardware`, the exact command you ran,
and what you expected instead. If the transcription itself is wrong, the model
and language matter more than anything else.
