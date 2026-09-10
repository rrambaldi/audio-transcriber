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
