"""What every test in this suite may assume about the machine it runs on.

The promise in CONTRIBUTING is that the suite needs no models, no GPU and no
network. Most of it keeps that promise by construction, but anything that
asks for a summary with the engine unset gets whichever engine happens to be
installed — and on a developer's machine that may be one that loads a model,
downloads a model, or takes four minutes. The default is pinned here so that
the suite tests this program rather than the laptop it is on.

A test that means to exercise the choice itself overrides it, as several do.
"""
import pytest

from audio_transcriber import summarizers


@pytest.fixture(autouse=True)
def no_model_by_default(monkeypatch):
    """"auto" is the extractive engine, whatever is installed here."""
    monkeypatch.setattr(
        summarizers, "is_installed",
        lambda name, settings=None: name == summarizers.EXTRACTIVE)
