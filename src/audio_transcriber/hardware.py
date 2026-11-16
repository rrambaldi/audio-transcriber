"""What this machine can do: OpenVINO devices, CUDA, cores, free memory.

The point is to let one command line work on a laptop with an Intel iGPU and on
a headless server, by choosing the backend, device and precision automatically.

Nothing here raises: a missing library simply means "not available". Nothing
here imports a heavy dependency either, unless the answer requires it, so
``--hardware`` stays instant.
"""
import ctypes
import functools
import os
import sys
import time
from collections import namedtuple

from .i18n import t


def module_available(name):
    """Whether a module could be imported, without importing it.

    Importing openvino or torch just to find out costs seconds."""
    try:
        from importlib.util import find_spec
        return find_spec(name) is not None
    except Exception:
        return False


def openvino_devices():
    """Devices OpenVINO can see, e.g. ``['CPU', 'GPU.0', 'NPU']``.

    Empty when OpenVINO is missing or fails to initialise."""
    if not module_available("openvino"):
        return []
    try:
        import openvino
        return list(openvino.Core().available_devices)
    except Exception:
        return []


#: ``SetErrorMode`` flags: no message box from the loader for a DLL or an
#: entry point it cannot resolve, nor for a file it cannot open.
SEM_FAILCRITICALERRORS = 0x0001
SEM_NOOPENFILEERRORBOX = 0x8000


def silence_loader_dialogs():
    """Stop Windows from halting the program on a message box over a DLL.

    OpenVINO's GPU plugin imports ``clCreateBufferWithProperties``, an
    OpenCL 3.0 function, from the system's OpenCL.dll. Where the graphics
    driver is older, that OpenCL.dll lacks it, and Windows answers the
    plugin's load with "entry point not found" in a box that waits for a
    click - under pythonw, with nothing else on screen, and once for every
    ``openvino.Core`` made. OpenVINO already handles the failure itself: it
    leaves the GPU out of its devices and the program runs on the processor.
    Without the box that is all that happens. The mode is per process and
    inherited by the processes this one starts."""
    if sys.platform != "win32":
        return
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.SetErrorMode(kernel32.GetErrorMode()
                              | SEM_FAILCRITICALERRORS | SEM_NOOPENFILEERRORBOX)
    except Exception:
        pass


def opencl_too_old():
    """Whether the OpenCL.dll this PC has is too old for OpenVINO's GPU plugin.

    True means the iGPU will go unused until the graphics driver is updated;
    False, that OpenCL 3.0 is there; None, that the question does not apply
    or cannot be answered - not Windows, or no OpenCL.dll at all, which is a
    PC with no graphics driver to update. Needs no OpenVINO, so the installer
    can say it before downloading it."""
    if sys.platform != "win32":
        return None
    try:
        library = ctypes.WinDLL("OpenCL.dll")
    except OSError:
        return None
    return not hasattr(library, "clCreateBufferWithProperties")


def has_openvino_accelerator(devices=None):
    """Whether OpenVINO sees anything beyond the CPU (iGPU, dGPU, NPU)."""
    found = openvino_devices() if devices is None else devices
    return any(name.upper().startswith(("GPU", "NPU")) for name in found)


# --- NVIDIA, through CUDA ---------------------------------------------------
#
# faster-whisper runs on CTranslate2, whose wheels carry their own CUDA runtime
# and load cuBLAS by name when the first model is put on the GPU. So whether a
# PC can transcribe on its NVIDIA card is three questions: whether the driver
# and the card suit the CTranslate2 build, whether a cuBLAS can be found, and
# whether faster-whisper is installed. None needs torch, which this program
# does not install for transcription; asking torch is how a PC with only an
# NVIDIA card used to be told it had none.

#: What :func:`cuda_probe` can answer.
CUDA_ABSENT = "absent"          # no NVIDIA driver, or no card behind it
CUDA_OLD_DRIVER = "old_driver"  # a card, and a driver too old for the build
CUDA_OLD_GPU = "old_gpu"        # a card the build has no code for
CUDA_USABLE = "usable"

#: ``cuDriverGetVersion`` counts CUDA as 1000 * major + 10 * minor.
CUDA_12_0, CUDA_12_8 = 12000, 12080

#: What the CTranslate2 4.9 wheels are built for, read from their build
#: scripts: CUDA 12.8, machine code for compute capability 5.3 to 8.6 - which
#: every 8.x runs, 8.9 included - and PTX for 8.6. A card from 9.0 on runs that
#: PTX, compiled by the driver when the model loads, and only a driver that
#: knows CUDA 12.8 can compile it; anything older than 5.3 has no code at all.
MIN_CAPABILITY = (5, 3)
LAST_NATIVE_MAJOR = 8

#: ``CUdevice_attribute`` values for the compute capability.
_CC_MAJOR, _CC_MINOR = 75, 76

CudaProbe = namedtuple("CudaProbe", "state name vram_gb capability driver")
CudaProbe.__new__.__defaults__ = (None, None, None, None)


def _cuda_driver():
    """The NVIDIA driver library, or None where there is none."""
    name = ("nvcuda.dll" if sys.platform == "win32"
            else "libcuda.so.1" if sys.platform.startswith("linux") else None)
    if name is None:
        return None
    try:
        return ctypes.CDLL(name)
    except OSError:
        return None


@functools.lru_cache(maxsize=1)
def cuda_probe():
    """The NVIDIA card a transcription would run on, as a :class:`CudaProbe`.

    Asked of the driver itself through ctypes - no CTranslate2, no torch - so
    the installer can ask it before either is installed. Never raises: no
    driver, or a driver that will not answer, is :data:`CUDA_ABSENT`. Asked
    once per process: a driver updated while the window is open is seen the
    next time it opens."""
    driver = _cuda_driver()
    return CudaProbe(CUDA_ABSENT) if driver is None else probe_driver(driver)


def probe_driver(driver):
    """:func:`cuda_probe`'s questions, put to a driver already loaded.

    Only the first card is examined: it is the one faster-whisper uses unless
    told otherwise.
    ParceEtRecte: device 0 only; look at every card if a PC ever pairs an old
    one first with a new one second."""
    def ok(function, *args):
        return getattr(driver, function)(*args) == 0      # CUDA_SUCCESS

    version, count, device = ctypes.c_int(0), ctypes.c_int(0), ctypes.c_int(0)
    major, minor, total = ctypes.c_int(0), ctypes.c_int(0), ctypes.c_size_t(0)
    name = ctypes.create_string_buffer(256)
    try:
        if not ok("cuDriverGetVersion", ctypes.byref(version)):
            return CudaProbe(CUDA_ABSENT)
        if not (ok("cuInit", 0) and ok("cuDeviceGetCount", ctypes.byref(count))
                and count.value > 0 and ok("cuDeviceGet", ctypes.byref(device), 0)):
            return CudaProbe(CUDA_ABSENT, driver=version.value)
        # The name and the memory may go unanswered - an unnamed card, a model
        # chosen as if its memory were ample. The compute capability may not:
        # without it there is no telling whether the build has code for it.
        ok("cuDeviceGetName", name, len(name), device)
        ok("cuDeviceTotalMem_v2", ctypes.byref(total), device)
        if not (ok("cuDeviceGetAttribute", ctypes.byref(major), _CC_MAJOR, device)
                and ok("cuDeviceGetAttribute", ctypes.byref(minor), _CC_MINOR, device)):
            return CudaProbe(CUDA_ABSENT, driver=version.value)
    except AttributeError:
        # A function this old a driver does not export: older than anything
        # CUDA 12 runs on.
        return CudaProbe(CUDA_OLD_DRIVER, driver=version.value or None)

    capability = (major.value, minor.value)
    state = (CUDA_OLD_GPU if capability < MIN_CAPABILITY
             else CUDA_OLD_DRIVER if version.value < needed_cuda(capability)
             else CUDA_USABLE)
    return CudaProbe(state, name=name.value.decode("utf-8", "replace").strip() or None,
                     vram_gb=total.value / 1024.0 ** 3 if total.value else None,
                     capability=capability, driver=version.value)


def cuda_version_text(version):
    """``12080`` as ``12.8``."""
    return f"{version // 1000}.{version % 1000 // 10}" if version else "?"


def needed_cuda(capability):
    """The CUDA a driver must know for a card of this compute capability,
    counted as ``cuDriverGetVersion`` counts it."""
    return CUDA_12_0 if (capability or (0, 0))[0] <= LAST_NATIVE_MAJOR else CUDA_12_8


def _cublas_names():
    """cuBLAS as the CTranslate2 wheels load it, by name. On Linux the Lt half
    is named too, first: the other one needs it loaded to be loaded by name."""
    if sys.platform == "win32":
        return ("cublas64_12.dll",)
    return ("libcublasLt.so.12", "libcublas.so.12")


def _cublas_packages():
    """Where pip puts it, per package: nvidia-cublas-cu12 first, which the
    ``[cuda]`` extra installs; then a CUDA build of torch, which carries a copy."""
    return (("nvidia.cublas", "bin" if sys.platform == "win32" else "lib"),
            ("torch", "lib"))


#: Kept for the life of the process: a collected ``add_dll_directory`` handle
#: takes its folder off the search path again, and a collected CDLL may unload.
_CUDA_KEPT = []
_CUDA_PREPARED = set()


def _package_dirs(name):
    """The folders a package is installed in, without importing it."""
    try:
        from importlib.util import find_spec
        spec = find_spec(name)
    except (ImportError, ValueError):
        return []
    return list(spec.submodule_search_locations or []) if spec else []


def cublas_dir():
    """The folder holding a cuBLAS that pip installed, or None."""
    wanted = _cublas_names()[-1]
    for package, sub in _cublas_packages():
        for root in _package_dirs(package):
            folder = os.path.join(root, sub)
            if os.path.isfile(os.path.join(folder, wanted)):
                return folder
    return None


def _cublas_on_system():
    """Whether a cuBLAS outside pip's reach - the CUDA Toolkit - is findable by
    the name CTranslate2 asks for: on Windows a file on the PATH; on Linux
    whatever ``dlopen`` finds, which is the answer itself, and only version 12."""
    wanted = _cublas_names()[-1]
    if sys.platform == "win32":
        return any(os.path.isfile(os.path.join(folder, wanted))
                   for folder in os.environ.get("PATH", "").split(os.pathsep) if folder)
    try:
        ctypes.CDLL(wanted)
    except OSError:
        return False
    return True


def prepare_cuda_libraries():
    """Make the cuBLAS pip installed findable by the name CTranslate2 asks for.

    CTranslate2 calls ``LoadLibrary("cublas64_12.dll")`` when a model first
    goes on the GPU. A plain name like that is searched for on the PATH, not
    in a folder given to ``os.add_dll_directory`` - which only the loads that
    ask for it see - so the folder goes on both. On Linux the libraries are
    loaded now, globally, and ``dlopen`` then finds them by name already in
    the process. Returns the folder, or None when pip installed none; a second
    call changes nothing."""
    folder = cublas_dir()
    if folder is None or folder in _CUDA_PREPARED:
        return folder
    if sys.platform == "win32":
        os.environ["PATH"] = folder + os.pathsep + os.environ.get("PATH", "")
        _CUDA_KEPT.append(os.add_dll_directory(folder))
    else:
        for name in _cublas_names():
            _CUDA_KEPT.append(ctypes.CDLL(os.path.join(folder, name),
                                          mode=ctypes.RTLD_GLOBAL))
    _CUDA_PREPARED.add(folder)
    return folder


# DefunctumEst: torch.cuda.is_available() as the test for CUDA, replaced by
# cuda_probe() and a cuBLAS search: torch is not installed to transcribe.
@functools.lru_cache(maxsize=1)
def has_cuda():
    """Whether faster-whisper can transcribe on an NVIDIA card here.

    A driver and a card the CTranslate2 build can use, faster-whisper itself,
    and a cuBLAS for it to load. Asked once per process, like the probe."""
    return (cuda_probe().state == CUDA_USABLE and module_available("faster_whisper")
            and (cublas_dir() is not None or _cublas_on_system()))


def cpu_count():
    """Usable cores, honouring process affinity.

    Containers and cgroups routinely grant fewer cores than the host has."""
    try:
        return len(os.sched_getaffinity(0))
    except AttributeError:  # not Linux
        return os.cpu_count() or 1


def physical_cores():
    """Cores rather than threads, or None when they cannot be told apart.

    Hyperthreading does not help a memory-bound matrix multiplication and
    costs cache, so a model runs better told how many cores there really are;
    where that cannot be established :func:`cpu_count` stands, which is the
    honest answer rather than a guess dressed as one.

    Only Linux answers, and only from the cores this process may actually use:
    a container granted two of a host's thirty-two must not be told it has
    sixteen."""
    if not sys.platform.startswith("linux"):
        return None
    try:
        usable = set(os.sched_getaffinity(0))
        cores, processor = set(), None
        with open("/proc/cpuinfo", encoding="ascii") as handle:
            package, core = None, None
            for line in handle:
                key, _, value = line.partition(":")
                key, value = key.strip(), value.strip()
                if key == "processor":
                    processor = int(value)
                    package, core = None, None
                elif key == "physical id":
                    package = value
                elif key == "core id":
                    core = value
                elif not line.strip() and processor in usable:
                    if core is not None:
                        cores.add((package, core))
                    processor = None
            if processor in usable and core is not None:
                cores.add((package, core))
        return len(cores) or None
    except Exception:
        return None


#: What ``IsProcessorFeaturePresent`` calls AVX2.
PF_AVX2_INSTRUCTIONS_AVAILABLE = 40


def has_avx2():
    """Whether the processor has AVX2, or None where this cannot tell.

    llama.cpp leans on it for every matrix product on the processor: without
    it a summary model still runs, many times slower, and an installer should
    say so before downloading gigabytes for it. Not x86 at all (an ARM Mac,
    a Raspberry Pi) is None rather than False - the question does not apply."""
    try:
        if sys.platform == "win32":
            return bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(
                PF_AVX2_INSTRUCTIONS_AVAILABLE))
        if sys.platform.startswith("linux"):
            with open("/proc/cpuinfo", encoding="ascii", errors="replace") as handle:
                for line in handle:
                    if line.startswith("flags"):
                        return "avx2" in line.split()
    except OSError:
        return None
    return None


def _meminfo(field):
    """One ``/proc/meminfo`` field in GiB, or None."""
    with open("/proc/meminfo", encoding="ascii") as handle:
        for line in handle:
            if line.startswith(field + ":"):
                return int(line.split()[1]) / (1024.0 * 1024.0)
    return None


def total_ram_gb():
    """Installed RAM in GiB, or None if it cannot be determined.

    Worth having next to :func:`available_ram_gb`, because the two answer
    different questions: how much a model may take today, and how big this
    machine is. A gigabyte free out of two is a small machine and a gigabyte
    free out of sixty-four is a busy one, and only the second is worth waiting
    out."""
    try:
        if sys.platform.startswith("linux"):
            return _meminfo("MemTotal")
        if sys.platform == "win32":
            return _windows_memory("ullTotalPhys")
        return (os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
                / (1024.0 ** 3))
    except Exception:
        return None


def _windows_memory(field):
    """``GlobalMemoryStatusEx`` in GiB, by field name, or None."""
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(MemoryStatus)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return getattr(status, field) / (1024.0 ** 3)
    return None


def available_ram_gb():
    """Actually available RAM in GiB, or None if it cannot be determined.

    Done by hand rather than with psutil to keep the dependency list short."""
    try:
        if sys.platform.startswith("linux"):
            return _meminfo("MemAvailable")
        elif sys.platform == "win32":
            return _windows_memory("ullAvailPhys")
        else:  # macOS, BSD
            return (os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
                    / (1024.0 ** 3))
    except Exception:
        pass
    return None


# --- how busy it is right now ---------------------------------------------


def _linux_cpu_ticks():
    """Busy and total jiffies, from the first line of ``/proc/stat``."""
    with open("/proc/stat", encoding="ascii") as handle:
        fields = [int(value) for value in handle.readline().split()[1:9]]
    # user nice system idle iowait irq softirq steal. Waiting for a disk is
    # not work, so iowait is counted as idle rather than as load.
    return sum(fields) - (fields[3] + fields[4]), sum(fields)


def _windows_cpu_ticks():
    """Busy and total 100ns ticks, from ``GetSystemTimes``."""
    idle, kernel, user = (ctypes.c_ulonglong() for _ in range(3))
    if not ctypes.windll.kernel32.GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        return None
    total = kernel.value + user.value   # the kernel figure includes the idle one
    return total - idle.value, total


def cpu_ticks():
    """``(busy, total)`` CPU time since boot, or None where it cannot be read.

    The unit does not matter and differs between systems: only the ratio
    between two samples is ever used. Done by hand rather than with psutil for
    the same reason as :func:`available_ram_gb`."""
    try:
        if sys.platform.startswith("linux"):
            return _linux_cpu_ticks()
        if sys.platform == "win32":
            return _windows_cpu_ticks()
    except Exception:
        pass
    return None


def cpu_percent_between(before, after):
    """How busy the CPU was between two :func:`cpu_ticks` samples.

    None when a sample is missing or when no time passed between the two: one
    sample on its own is the average since boot, which on a machine that has
    been up for a month says nothing about what it is doing now."""
    if not before or not after:
        return None
    busy, total = after[0] - before[0], after[1] - before[1]
    if total <= 0:
        return None
    return max(0.0, min(100.0, 100.0 * busy / total))


def load_average():
    """The 1/5/15 minute run queue, or None on a system without one.

    Worth having next to the percentage: a CPU is at 100% whether one
    transcription is using it or three processes are fighting over it, and
    only the run queue tells those apart."""
    try:
        return [round(value, 2) for value in os.getloadavg()]
    except (AttributeError, OSError):   # Windows has no such number
        return None


def engine_in_use(settings=None):
    """``(engine, device)`` a transcription would run on right now.

    Either may be None: no engine installed, or one that cannot say. A bar at
    100% does not say *what* is working, and on a machine with an Intel iGPU
    that is the whole question — so the load is shown next to this."""
    # Imported here rather than at the top: backends imports this module.
    from . import backends

    settings = dict(settings or {})
    requested = settings.get("device") or "auto"
    try:
        engine = backends.resolve_backend(settings.get("backend") or "auto", requested)
    except SystemExit:           # nothing installed: the page says so instead
        return None, None
    try:
        device = backends.load(engine).resolve_device(requested)
    except (Exception, SystemExit):
        return engine, None
    return engine, (device.upper() if device else None)


class Meter:
    """Repeated readings of how busy this machine is.

    An object rather than a function because a CPU percentage is a difference
    between two moments: the first sample is taken when the meter is built, so
    the first reading a page or a window asks for already covers a real
    interval.

    Every figure may be None, and a caller must draw nothing rather than a
    zero when it is: a bar built on a number this module had to invent would
    be worse than no bar."""

    #: A sample older than this is thrown away rather than used. Nobody polls
    #: a meter they are not looking at, so the sample waiting for the first
    #: reading after an idle spell can be an hour old, and the percentage
    #: between the two would be that hour's average rather than what the
    #: machine is doing now.
    STALE_AFTER = 15.0

    def __init__(self):
        self._ticks = cpu_ticks()
        self._taken = time.monotonic()
        self._percent = None
        #: Whether this system reports CPU time at all. A reading of None is
        #: "not yet" on a machine where this is true and "never" where it is
        #: false, and only the caller can say which of the two to draw.
        self.measurable = self._ticks is not None

    def read(self):
        """One reading, as plain numbers the page and the window both draw."""
        ticks, now = cpu_ticks(), time.monotonic()
        stale = now - self._taken > self.STALE_AFTER
        percent = None if stale else cpu_percent_between(self._ticks, ticks)
        if percent is not None or stale:
            # Two readings in the same millisecond have nothing between them
            # to measure; there the last real answer stands rather than a
            # zero, which would draw an idle machine in the middle of a job.
            # A stale one is dropped instead: it has no answer yet, and says
            # so, rather than reporting the average of the last hour.
            self._ticks, self._taken, self._percent = ticks, now, percent
        free, total = available_ram_gb(), total_ram_gb()
        used = None if free is None or total is None else total - free
        return {
            "cpu_percent": None if self._percent is None else round(self._percent, 1),
            "cores": cpu_count(),
            "load": load_average(),
            "ram_free_gb": None if free is None else round(free, 2),
            "ram_used_gb": None if used is None else round(used, 2),
            "ram_total_gb": None if total is None else round(total, 2),
            "ram_percent": None if not total or used is None
                           else round(100.0 * used / total, 1),
        }

def summary():
    """One line describing the machine, for diagnostics."""
    ram, total = available_ram_gb(), total_ram_gb()
    cores, physical = cpu_count(), physical_cores()
    devices = openvino_devices()
    return t("hardware.summary",
             cores=f"{physical}/{cores}" if physical and physical != cores
                   else str(cores),
             ram=f"{ram:.1f} GiB" if ram is not None else t("hardware.unknown"),
             total=f"{total:.1f} GiB" if total is not None else t("hardware.unknown"),
             openvino=", ".join(devices) if devices else t("hardware.not_installed"),
             cuda=t("hardware.yes") if has_cuda() else t("hardware.no"))
