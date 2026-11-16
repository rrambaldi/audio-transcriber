"""What the machine says about itself, and what it does when it cannot say.

Every question here is allowed to answer "I don't know": the module runs on a
laptop, in a container with two cores of somebody else's thirty-two, and in CI.
A wrong number is worse than no number, because the summary plan is built on
these and a machine that overstates its memory swaps.
"""
import ctypes

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


def test_avx2_is_read_from_the_processor_flags(monkeypatch, tmp_path):
    cpuinfo = tmp_path / "cpuinfo"
    monkeypatch.setattr(hardware.sys, "platform", "linux")
    real_open = open
    monkeypatch.setattr(hardware, "open", lambda path, *a, **k: real_open(cpuinfo, *a, **k),
                        raising=False)
    cpuinfo.write_text("processor\t: 0\nflags\t\t: fpu sse4_2 avx avx2 fma\n", encoding="ascii")
    assert hardware.has_avx2() is True
    cpuinfo.write_text("processor\t: 0\nflags\t\t: fpu sse4_2 avx\n", encoding="ascii")
    assert hardware.has_avx2() is False


def test_avx2_is_unknown_where_the_question_does_not_apply(monkeypatch):
    monkeypatch.setattr(hardware.sys, "platform", "darwin")
    assert hardware.has_avx2() is None


# --- an OpenCL too old for OpenVINO's GPU plugin -----------------------------

class _OpenCL:
    """An OpenCL.dll as ctypes sees it: its exports are its attributes."""

    def __init__(self, *exports):
        for name in exports:
            setattr(self, name, object())


def test_an_opencl_without_version_3_is_too_old(monkeypatch):
    """The GPU plugin imports clCreateBufferWithProperties; without it Windows
    cannot load the plugin and the iGPU goes unused."""
    monkeypatch.setattr(hardware.sys, "platform", "win32")
    monkeypatch.setattr(hardware.ctypes, "WinDLL",
                        lambda name: _OpenCL("clCreateCommandQueueWithProperties"),
                        raising=False)
    assert hardware.opencl_too_old() is True


def test_an_opencl_3_is_not_too_old(monkeypatch):
    monkeypatch.setattr(hardware.sys, "platform", "win32")
    monkeypatch.setattr(hardware.ctypes, "WinDLL",
                        lambda name: _OpenCL("clCreateBufferWithProperties"),
                        raising=False)
    assert hardware.opencl_too_old() is False


def test_no_opencl_at_all_is_not_a_driver_to_update(monkeypatch):
    def missing(name):
        raise OSError("OpenCL.dll not found")

    monkeypatch.setattr(hardware.sys, "platform", "win32")
    monkeypatch.setattr(hardware.ctypes, "WinDLL", missing, raising=False)
    assert hardware.opencl_too_old() is None


def test_opencl_is_only_asked_about_on_windows(monkeypatch):
    monkeypatch.setattr(hardware.sys, "platform", "linux")
    assert hardware.opencl_too_old() is None


def test_loader_dialogs_are_silenced_without_dropping_the_flags_already_set(monkeypatch):
    """The box that waits for a click is what stopped the window: the mode
    gains the two flags and keeps whatever it had."""
    set_to = []

    class Kernel32:
        def GetErrorMode(self):
            return 0x0002  # SEM_NOGPFAULTERRORBOX, set by somebody else

        def SetErrorMode(self, mode):
            set_to.append(mode)

    class WinDLLs:
        kernel32 = Kernel32()

    monkeypatch.setattr(hardware.sys, "platform", "win32")
    monkeypatch.setattr(hardware.ctypes, "windll", WinDLLs(), raising=False)
    hardware.silence_loader_dialogs()
    assert set_to == [0x0002 | hardware.SEM_FAILCRITICALERRORS
                      | hardware.SEM_NOOPENFILEERRORBOX]


def test_loader_dialogs_are_left_alone_elsewhere(monkeypatch):
    monkeypatch.setattr(hardware.sys, "platform", "linux")
    hardware.silence_loader_dialogs()  # nothing to call, nothing raised


# --- NVIDIA, through CUDA ----------------------------------------------------


class FakeDriver:
    """The handful of driver calls the probe makes, answered from a script."""

    def __init__(self, version=12080, init=0, count=1, name=b"NVIDIA GeForce RTX 3060",
                 total=12 * 1024 ** 3, capability=(8, 6)):
        self.version, self.init, self.count = version, init, count
        self.name, self.total, self.capability = name, total, capability

    @staticmethod
    def _give(pointer, value):
        pointer._obj.value = value
        return 0

    def cuDriverGetVersion(self, out):
        return self._give(out, self.version)

    def cuInit(self, flags):
        return self.init

    def cuDeviceGetCount(self, out):
        return self._give(out, self.count)

    def cuDeviceGet(self, out, ordinal):
        return self._give(out, ordinal)

    def cuDeviceGetName(self, buffer, size, device):
        assert isinstance(size, int) and isinstance(device, ctypes.c_int)
        assert size == len(buffer)
        buffer.value = self.name
        return 0

    def cuDeviceTotalMem_v2(self, out, device):
        assert isinstance(out._obj, ctypes.c_size_t) and isinstance(device, ctypes.c_int)
        return self._give(out, self.total)

    def cuDeviceGetAttribute(self, out, attribute, device):
        assert isinstance(out._obj, ctypes.c_int) and isinstance(device, ctypes.c_int)
        if self.capability is None:
            return 1                                 # CUDA_ERROR_INVALID_VALUE
        return self._give(out, self.capability[{75: 0, 76: 1}[attribute]])


def test_no_nvidia_driver_is_no_card():
    assert hardware.cuda_probe().state == hardware.CUDA_ABSENT


def test_a_usable_card_is_described():
    probe = hardware.probe_driver(FakeDriver())
    assert probe.state == hardware.CUDA_USABLE
    assert probe.name == "NVIDIA GeForce RTX 3060"
    assert probe.vram_gb == pytest.approx(12.0)
    assert probe.capability == (8, 6)
    assert hardware.cuda_version_text(probe.driver) == "12.8"


def test_a_driver_that_will_not_initialise_is_no_card():
    """No card behind the driver answers cuInit with an error."""
    probe = hardware.probe_driver(FakeDriver(init=100))     # CUDA_ERROR_NO_DEVICE
    assert probe.state == hardware.CUDA_ABSENT
    assert hardware.probe_driver(FakeDriver(count=0)).state == hardware.CUDA_ABSENT


def test_a_driver_for_cuda_11_is_too_old():
    probe = hardware.probe_driver(FakeDriver(version=11080))
    assert probe.state == hardware.CUDA_OLD_DRIVER
    assert hardware.needed_cuda(probe.capability) == hardware.CUDA_12_0


def test_a_kepler_card_is_too_old_whatever_the_driver():
    assert hardware.probe_driver(FakeDriver(capability=(3, 5))).state == hardware.CUDA_OLD_GPU
    assert hardware.probe_driver(FakeDriver(capability=(5, 2))).state == hardware.CUDA_OLD_GPU
    assert hardware.probe_driver(FakeDriver(capability=(5, 3))).state == hardware.CUDA_USABLE


def test_a_card_after_the_build_needs_a_driver_that_compiles_its_ptx():
    """8.9 runs the 8.6 machine code; 9.0 and later compile PTX from 12.8."""
    assert hardware.probe_driver(FakeDriver(version=12000, capability=(8, 9))).state \
        == hardware.CUDA_USABLE
    assert hardware.probe_driver(FakeDriver(version=12040, capability=(12, 0))).state \
        == hardware.CUDA_OLD_DRIVER
    assert hardware.probe_driver(FakeDriver(version=12080, capability=(12, 0))).state \
        == hardware.CUDA_USABLE


def test_a_card_whose_capability_goes_unanswered_is_not_called_too_old():
    """Without it there is no telling; "too old" would blame the card."""
    probe = hardware.probe_driver(FakeDriver(capability=None))
    assert probe.state == hardware.CUDA_ABSENT


def test_a_driver_missing_a_function_is_too_old():
    class Ancient:
        def cuDriverGetVersion(self, out):
            out._obj.value = 3020
            return 0

        def cuInit(self, flags):
            return 0

        def cuDeviceGetCount(self, out):
            out._obj.value = 1
            return 0

        def cuDeviceGet(self, out, ordinal):
            return 0

    assert hardware.probe_driver(Ancient()).state == hardware.CUDA_OLD_DRIVER


@pytest.fixture
def cuda_site(monkeypatch, tmp_path):
    """A site-packages with nothing in it yet, and a clean slate of preparations."""
    monkeypatch.setattr(hardware, "_CUDA_PREPARED", set())
    monkeypatch.setattr(hardware, "_CUDA_KEPT", [])
    installed = {}
    monkeypatch.setattr(hardware, "_package_dirs", lambda name: installed.get(name, []))

    def install(package, sub, *files):
        folder = tmp_path.joinpath(*package.split("."))
        (folder / sub).mkdir(parents=True)
        for name in files:
            (folder / sub / name).write_bytes(b"")
        installed[package] = [str(folder)]
        return str(folder / sub)
    return install


def test_cublas_from_pip_is_put_on_both_windows_search_paths_once(monkeypatch, cuda_site):
    """LoadLibrary by name reads the PATH; add_dll_directory serves the rest."""
    monkeypatch.setattr(hardware.sys, "platform", "win32")
    added = []
    monkeypatch.setattr(hardware.os, "add_dll_directory", added.append, raising=False)
    monkeypatch.setenv("PATH", "system")
    folder = cuda_site("nvidia.cublas", "bin", "cublas64_12.dll", "cublasLt64_12.dll")

    assert hardware.prepare_cuda_libraries() == folder
    assert hardware.prepare_cuda_libraries() == folder
    assert added == [folder]
    assert hardware.os.environ["PATH"].split(hardware.os.pathsep) == [folder, "system"]


def test_cublas_from_pip_is_loaded_globally_on_linux(monkeypatch, cuda_site):
    """dlopen by name then finds what is already in the process - Lt first."""
    monkeypatch.setattr(hardware.sys, "platform", "linux")
    loaded = []
    monkeypatch.setattr(hardware.ctypes, "CDLL",
                        lambda path, mode=0: loaded.append((hardware.os.path.basename(path), mode)))
    cuda_site("nvidia.cublas", "lib", "libcublasLt.so.12", "libcublas.so.12")

    hardware.prepare_cuda_libraries()
    hardware.prepare_cuda_libraries()
    assert loaded == [("libcublasLt.so.12", hardware.ctypes.RTLD_GLOBAL),
                      ("libcublas.so.12", hardware.ctypes.RTLD_GLOBAL)]


def test_torchs_cublas_is_the_last_resort(monkeypatch, cuda_site):
    monkeypatch.setattr(hardware.sys, "platform", "linux")
    assert hardware.cublas_dir() is None
    assert hardware.prepare_cuda_libraries() is None
    folder = cuda_site("torch", "lib", "libcublasLt.so.12", "libcublas.so.12")
    assert hardware.cublas_dir() == folder


def test_a_system_cublas_counts_only_at_the_version_ctranslate2_asks_for(
        monkeypatch, tmp_path):
    monkeypatch.setattr(hardware.sys, "platform", "win32")
    monkeypatch.setenv("PATH", str(tmp_path))
    assert not hardware._cublas_on_system()
    (tmp_path / "cublas64_12.dll").write_bytes(b"")
    assert hardware._cublas_on_system()

    monkeypatch.setattr(hardware.sys, "platform", "linux")
    asked = []

    def dlopen(name, *args, **kwargs):
        asked.append(name)
        raise OSError(name)
    monkeypatch.setattr(hardware.ctypes, "CDLL", dlopen)
    assert not hardware._cublas_on_system()
    assert asked == ["libcublas.so.12"]          # a libcublas.so.11 is no use


@pytest.mark.parametrize(("state", "faster", "cublas", "expected"), [
    (hardware.CUDA_USABLE, True, True, True),
    (hardware.CUDA_USABLE, True, False, False),     # nothing for CTranslate2 to load
    (hardware.CUDA_USABLE, False, True, False),     # no engine to put on the card
    (hardware.CUDA_OLD_DRIVER, True, True, False),
])
def test_cuda_needs_the_card_the_engine_and_cublas(monkeypatch, state, faster, cublas,
                                                   expected):
    monkeypatch.setattr(hardware, "cuda_probe", lambda: hardware.CudaProbe(state))
    monkeypatch.setattr(hardware, "module_available", lambda name: faster)
    monkeypatch.setattr(hardware, "cublas_dir", lambda: "/x" if cublas else None)
    monkeypatch.setattr(hardware, "_cublas_on_system", lambda: False)
    assert hardware.has_cuda() is expected


@pytest.mark.parametrize(("adapters", "opencl_old", "expected"), [
    (["PCI\\VEN_10DE&DEV_1C81", "PCI\\VEN_8086&DEV_3E92"], False, True),
    (["PCI\\VEN_10DE&DEV_1C81", "PCI\\VEN_8086&DEV_3E92"], True, False),  # OpenCL too old
    (["PCI\\VEN_10DE&DEV_1C81"], None, False),                              # NVIDIA alone
])
def test_intel_graphics_are_asked_of_the_system(monkeypatch, adapters, opencl_old, expected):
    monkeypatch.setattr(hardware.sys, "platform", "win32")
    monkeypatch.setattr(hardware, "_display_adapters", lambda: adapters)
    monkeypatch.setattr(hardware, "opencl_too_old", lambda: opencl_old)
    assert hardware.intel_graphics() is expected


@pytest.mark.parametrize(("platform", "expected"), [("win32", False), ("linux", True)])
def test_intel_graphics_without_an_opencl_dll_are_none_on_windows(monkeypatch, platform,
                                                                 expected):
    """No OpenCL.dll is a driver that cannot serve OpenVINO either; elsewhere
    the question cannot be asked, and the adapter stands."""
    monkeypatch.setattr(hardware.sys, "platform", platform)
    monkeypatch.setattr(hardware, "_display_adapters", lambda: ["PCI\\VEN_8086&DEV_3E92"])
    monkeypatch.setattr(hardware, "opencl_too_old", lambda: None)
    assert hardware.intel_graphics() is expected


def test_linux_names_the_adapters_by_their_pci_vendor(monkeypatch, tmp_path):
    for card, vendor in (("card0", "0x10de"), ("card1", "0x8086")):
        (tmp_path / card / "device").mkdir(parents=True)
        (tmp_path / card / "device" / "vendor").write_text(vendor + "\n", encoding="ascii")
    monkeypatch.setattr(hardware.sys, "platform", "linux")
    monkeypatch.setattr(hardware.glob, "glob",
                        lambda pattern: [str(p) for p in tmp_path.glob("card*/device/vendor")])
    assert hardware._display_adapters() == ["PCI\\VEN_10DE", "PCI\\VEN_8086"]
