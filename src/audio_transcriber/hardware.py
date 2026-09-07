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


def available_ram_gb():
    """Actually available RAM in GiB, or None if it cannot be determined.

    Done by hand rather than with psutil to keep the dependency list short."""
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/meminfo", encoding="ascii") as handle:
                for line in handle:
                    if line.startswith("MemAvailable:"):
                        return int(line.split()[1]) / (1024.0 * 1024.0)
        elif sys.platform == "win32":
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
                return status.ullAvailPhys / (1024.0 ** 3)
        else:  # macOS, BSD
            return (os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
                    / (1024.0 ** 3))
    except Exception:
        pass
    return None


def summary():
    """One line describing the machine, for diagnostics."""
    ram = available_ram_gb()
    devices = openvino_devices()
    return t("hardware.summary",
             cores=cpu_count(),
             ram=f"{ram:.1f} GiB" if ram is not None else t("hardware.unknown"),
             openvino=", ".join(devices) if devices else t("hardware.not_installed"),
             cuda=t("hardware.yes") if has_cuda() else t("hardware.no"))
