"""What every test in this suite may assume about the machine it runs on.

The promise in CONTRIBUTING is that the suite needs no models, no GPU and no
network. Most of it keeps that promise by construction, but anything that
asks for a summary with the engine unset gets whichever engine happens to be
installed — and on a developer's machine that may be one that loads a model,
downloads a model, or takes four minutes. The default is pinned here so that
the suite tests this program rather than the laptop it is on.

A test that means to exercise the choice itself overrides it, as several do.
"""
import os
import sys

import pytest

from audio_transcriber import hardware, logs, summarizers


@pytest.fixture(autouse=True)
def no_log_left_running():
    """Undo the redirection a test that starts a front end leaves behind.

    ``cli.main(["gui"])`` sends this process's own output to a log file, which
    is right for a window and wrong for the rest of a test session: left in
    place it takes pytest's capture with it, and every later test writes into
    a temporary directory that has already been deleted."""
    before = (sys.stdout, sys.stderr)
    yield
    if logs.started():
        logs.stop()
        sys.stdout, sys.stderr = before


@pytest.fixture(autouse=True)
def no_model_by_default(monkeypatch):
    """"auto" is the extractive engine, whatever is installed here.

    Outside the tests "auto" only ever names an engine with a model on the
    disk; in here the extractive engine stands in for one, so that a summary
    can be written without a model. The tests of that rule put the real
    :func:`summarizers.ready_engines` back."""
    monkeypatch.setattr(
        summarizers, "is_installed",
        lambda name, settings=None: name == summarizers.EXTRACTIVE)
    monkeypatch.setattr(summarizers, "ready_engines",
                        lambda settings=None: [summarizers.EXTRACTIVE])


@pytest.fixture(autouse=True)
def no_nvidia_card(monkeypatch):
    """No NVIDIA driver, whatever this machine has.

    A developer's card would otherwise turn "auto" into CUDA and the model
    into whatever its memory holds; the tests that mean a card hand one in."""
    remembered = (hardware.cuda_probe, hardware.has_cuda)   # a test may replace them
    for function in remembered:
        function.cache_clear()
    monkeypatch.setattr(hardware, "_cuda_driver", lambda: None)
    yield
    for function in remembered:
        function.cache_clear()


#: pytest's exit status, kept for the last hook: see pytest_unconfigure.
_FINISHED = {}


def pytest_sessionfinish(session, exitstatus):
    _FINISHED["status"] = int(exitstatus)


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    """Leave without taking Qt apart, once everything has been reported.

    Every test of the window passes, and the process then dies in Qt's own
    teardown of what the session left behind - with the [record] extra and
    Qt's media backend on Linux, a segmentation fault, as on 2026.11.2
    already. Deleting each test's window as it ends only moved the crash
    into the middle of the session. Nothing a test checks happens after this
    point, so the process ends here, with pytest's own status.

    ParceEtRecte: skips the teardown rather than mending it; find the object
    whose deletion crashes - the pane's media player is the suspect - and
    drop this."""
    if "PySide6.QtWidgets" in sys.modules and "status" in _FINISHED:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(_FINISHED["status"])
