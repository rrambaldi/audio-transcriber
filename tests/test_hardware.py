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


# --- how busy it is right now ---------------------------------------------


def test_a_percentage_needs_two_samples():
    """One sample is the average since boot: on a machine up for a month it
    says nothing about what is happening now."""
    assert hardware.cpu_percent_between(None, (10, 20)) is None
    assert hardware.cpu_percent_between((10, 20), None) is None
    # and two samples with nothing between them measure nothing
    assert hardware.cpu_percent_between((10, 20), (10, 20)) is None


def test_the_percentage_is_the_share_of_the_interval_that_was_busy():
    assert hardware.cpu_percent_between((100, 200), (140, 240)) == 100.0
    assert hardware.cpu_percent_between((100, 200), (110, 240)) == 25.0
    assert hardware.cpu_percent_between((100, 200), (100, 240)) == 0.0


def test_a_meter_that_measures_nothing_says_so_rather_than_zero(monkeypatch):
    """A zero would draw an idle machine in the middle of a transcription."""
    monkeypatch.setattr(hardware, "cpu_ticks", lambda: None)
    meter = hardware.Meter()
    assert meter.measurable is False
    assert meter.read()["cpu_percent"] is None


def test_a_reading_taken_too_soon_keeps_the_last_real_one(monkeypatch):
    """Two reads in the same millisecond have nothing between them: the page
    polls on a timer, and one early poll must not blank the bar."""
    samples = [(100, 200), (140, 240), (140, 240)]
    monkeypatch.setattr(hardware, "cpu_ticks", lambda: samples.pop(0))
    meter = hardware.Meter()
    assert meter.read()["cpu_percent"] == 100.0
    assert meter.read()["cpu_percent"] == 100.0


def test_a_sample_left_over_from_an_hour_ago_is_thrown_away(monkeypatch):
    """Nobody polls a meter they are not looking at. The first reading after
    an idle spell would otherwise be that whole spell's average."""
    samples = [(100, 200), (140, 240), (180, 340)]
    monkeypatch.setattr(hardware, "cpu_ticks", lambda: samples.pop(0))
    meter = hardware.Meter()
    meter._taken -= hardware.Meter.STALE_AFTER + 1
    assert meter.read()["cpu_percent"] is None      # no answer, not a stale one
    assert meter.read()["cpu_percent"] == 40.0      # measured from the new sample


def test_a_reading_carries_the_memory_and_the_cores(monkeypatch):
    monkeypatch.setattr(hardware, "available_ram_gb", lambda: 1.6)
    monkeypatch.setattr(hardware, "total_ram_gb", lambda: 3.7)
    reading = hardware.Meter().read()
    assert reading["ram_used_gb"] == 2.1 and reading["ram_total_gb"] == 3.7
    assert reading["ram_percent"] == round(100 * 2.1 / 3.7, 1)
    assert reading["cores"] >= 1


def test_memory_that_cannot_be_read_leaves_the_bar_undrawn(monkeypatch):
    monkeypatch.setattr(hardware, "available_ram_gb", lambda: None)
    monkeypatch.setattr(hardware, "total_ram_gb", lambda: None)
    reading = hardware.Meter().read()
    assert reading["ram_percent"] is None and reading["ram_used_gb"] is None


def test_iowait_is_not_counted_as_work(tmp_path, monkeypatch):
    """A core waiting for a disk is not a core transcribing."""
    stat = tmp_path / "stat"
    stat.write_text("cpu  10 0 10 60 20 0 0 0 0 0\ncpu0 1 2 3 4 5 6 7 8\n")
    real_open = open

    def fake_open(path, *args, **kwargs):
        return real_open(stat if path == "/proc/stat" else path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)
    assert hardware._linux_cpu_ticks() == (20, 100)


def test_the_engine_and_its_device_are_named_together(monkeypatch):
    """A bar at 100% does not say what is working: on a machine with an iGPU
    that is the whole question."""
    from audio_transcriber import backends
    from audio_transcriber.backends import faster_whisper

    monkeypatch.setattr(backends, "resolve_backend", lambda *a: backends.FASTER_WHISPER)
    # Patched where it is looked up: the backend bound the name at import.
    monkeypatch.setattr(faster_whisper, "has_cuda", lambda: False)
    assert hardware.engine_in_use({"device": "auto"}) == ("faster-whisper", "CPU")


def test_no_engine_installed_is_not_an_exit(monkeypatch):
    """``resolve_backend`` exits the program when nothing is installed, and a
    page asking how busy the machine is must not take the server with it."""
    from audio_transcriber import backends

    def nothing(*args):
        raise SystemExit("no backend")

    monkeypatch.setattr(backends, "resolve_backend", nothing)
    assert hardware.engine_in_use({}) == (None, None)


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
