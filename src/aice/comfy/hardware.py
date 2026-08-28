from __future__ import annotations

import ctypes
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import config as cfgmod
from ..utils import atomic_write_json, read_json, utc_now

_SMI_QUERY = "name,memory.total,memory.free,driver_version"


@dataclass(frozen=True)
class HardwareProfile:
    gpu_name: str
    vram_total_mb: int
    vram_free_mb: int
    ram_total_mb: int
    driver: str
    is_blackwell: bool
    has_gpu: bool
    probed_at: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_smi_csv(text: str) -> dict[str, Any] | None:
    """Parse a line of nvidia-smi --query-gpu=<_SMI_QUERY> --format=csv,noheader,nounits."""
    for line in text.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        try:
            return {
                "gpu_name": parts[0],
                "vram_total_mb": int(float(parts[1])),
                "vram_free_mb": int(float(parts[2])),
                "driver": parts[3],
            }
        except ValueError:
            continue
    return None


def is_blackwell(gpu_name: str) -> bool:
    n = gpu_name.lower()
    return (
        "blackwell" in n
        or bool(re.search(r"rtx\s*50\d0", n))
        or bool(re.search(r"rtx\s*pro\s*6000", n))
    )


def _probe_nvidia_smi() -> dict[str, Any] | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--query-gpu=" + _SMI_QUERY, "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    return parse_smi_csv(out.stdout) if out.returncode == 0 else None


def _system_ram_mb() -> int:
    if os.name == "nt":
        class _MEMSTAT(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = _MEMSTAT()
        stat.dwLength = ctypes.sizeof(_MEMSTAT)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return int(stat.ullTotalPhys // (1024 * 1024))
        return 0
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return 0


def detect() -> HardwareProfile:
    smi = _probe_nvidia_smi() or {}
    name = smi.get("gpu_name", "")
    return HardwareProfile(
        gpu_name=name,
        vram_total_mb=int(smi.get("vram_total_mb", 0)),
        vram_free_mb=int(smi.get("vram_free_mb", 0)),
        ram_total_mb=_system_ram_mb(),
        driver=smi.get("driver", ""),
        is_blackwell=is_blackwell(name) if name else False,
        has_gpu=bool(name),
        probed_at=utc_now(),
    )


def cache_path() -> Path:
    return cfgmod.comfy_home() / "hardware_profile.json"


def save_cached(profile: HardwareProfile) -> None:
    atomic_write_json(cache_path(), profile.as_dict())


def load_cached() -> HardwareProfile | None:
    data = read_json(cache_path())
    if not isinstance(data, dict):
        return None
    try:
        return HardwareProfile(**{k: data[k] for k in HardwareProfile.__dataclass_fields__})
    except (KeyError, TypeError):
        return None


def free_vram_from_system_stats(stats: dict[str, Any]) -> int | None:
    """Live free VRAM (MB) from ComfyUI /system_stats (bytes -> MB)."""
    for device in stats.get("devices", []) or []:
        blob = (str(device.get("type", "")) + str(device.get("name", ""))).lower()
        if "cuda" in blob:
            free = device.get("vram_free")
            if isinstance(free, (int, float)):
                return int(free // (1024 * 1024))
    return None
