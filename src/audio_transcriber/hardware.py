"""What this machine can do: OpenVINO devices, CUDA, cores, free memory.

The point is to let one command line work on a laptop with an Intel iGPU and on
a headless server, by choosing the backend, device and precision automatically.

Nothing here raises: a missing library simply means "not available". Nothing
here imports a heavy dependency either, unless the answer requires it, so
``--hardware`` stays instant.
"""
import ctypes
import os
import sys
import time

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


def has_openvino_accelerator(devices=None):
    """Whether OpenVINO sees anything beyond the CPU (iGPU, dGPU, NPU)."""
    found = openvino_devices() if devices is None else devices
    return any(name.upper().startswith(("GPU", "NPU")) for name in found)


def has_cuda():
    """Whether torch can see a usable NVIDIA GPU."""
    if not module_available("torch"):
        return False
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


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
