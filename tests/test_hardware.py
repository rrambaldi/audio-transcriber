"""What the machine says about itself, and what it does when it cannot say.

Every question here is allowed to answer "I don't know": the module runs on a
laptop, in a container with two cores of somebody else's thirty-two, and in CI.
A wrong number is worse than no number, because the summary plan is built on
these and a machine that overstates its memory swaps.
"""
import pytest

from audio_transcriber import hardware, i18n


@pytest.fixture(autouse=True)
def english(monkeypatch):
    monkeypatch.setenv(i18n.ENV_LANGUAGE, "en")
    i18n._current = None
    yield
    i18n._current = None


def test_the_two_memory_figures_answer_different_questions():
    """How much a model may take today, and how big this machine is."""
    total, free = hardware.total_ram_gb(), hardware.available_ram_gb()
    if total is None or free is None:
        pytest.skip("this machine does not report its memory")
    assert total > 0
    assert 0 <= free <= total


def test_memory_that_cannot_be_read_is_none_rather_than_a_guess(monkeypatch):
    def refuse(field):
        raise OSError("no /proc here")

    monkeypatch.setattr(hardware, "_meminfo", refuse)
    monkeypatch.setattr(hardware.sys, "platform", "linux")
    assert hardware.total_ram_gb() is None
    assert hardware.available_ram_gb() is None


def test_cores_are_counted_but_never_overcounted():
    physical = hardware.physical_cores()
    assert physical is None or 1 <= physical <= hardware.cpu_count()


def test_a_machine_that_cannot_tell_threads_from_cores_says_so(monkeypatch):
    monkeypatch.setattr(hardware.sys, "platform", "darwin")
    assert hardware.physical_cores() is None


def test_the_report_carries_both_memory_figures(monkeypatch):
    monkeypatch.setattr(hardware, "available_ram_gb", lambda: 1.6)
    monkeypatch.setattr(hardware, "total_ram_gb", lambda: 3.7)
    monkeypatch.setattr(hardware, "openvino_devices", lambda: [])
    line = hardware.summary()
    assert "1.6 GiB" in line and "3.7 GiB" in line


def test_the_report_names_the_cores_only_when_they_differ(monkeypatch):
    monkeypatch.setattr(hardware, "openvino_devices", lambda: [])
    monkeypatch.setattr(hardware, "cpu_count", lambda: 8)

    monkeypatch.setattr(hardware, "physical_cores", lambda: 4)
    assert "4/8" in hardware.summary()

    # Nothing to disambiguate on a machine without hyperthreading, and a
    # report that says "8/8 cores" is noise.
    monkeypatch.setattr(hardware, "physical_cores", lambda: 8)
    assert "8/8" not in hardware.summary()
    assert "8 cores" in hardware.summary()


def test_a_machine_that_answers_nothing_still_produces_a_line(monkeypatch):
    for name in ("available_ram_gb", "total_ram_gb", "physical_cores"):
        monkeypatch.setattr(hardware, name, lambda: None)
    monkeypatch.setattr(hardware, "openvino_devices", lambda: [])
    line = hardware.summary()
    assert "unknown" in line
    assert "CPU" in line
