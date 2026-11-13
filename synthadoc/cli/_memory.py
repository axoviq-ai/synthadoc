# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Peter White / axoviq.com
"""Memory helpers for ``synthadoc serve --all``.

``serve --all`` starts one server process per registered wiki. Each idle server
costs several hundred MB, so starting every wiki at once can exhaust a machine.
This module provides:

* ``parse_memory_size`` - parse ``6GB`` / ``6000MB`` (a unit is mandatory, so a
  bare ``6000`` can never be misread as MB, GB or bytes).
* ``MemoryGate`` - decides whether another wiki may be started.
* ``system_memory_mb`` / ``process_memory_mb`` - read real memory use without
  adding a dependency (``ctypes`` on Windows, ``/proc`` on Linux, ``vm_stat``
  and ``ps`` on macOS).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Without --max-memory, stop starting wikis before the machine as a whole would
# go past this fraction of its physical memory.
DEFAULT_CEILING_FRACTION = 0.60

# Used for the first wiki, and as a floor when a started wiki's memory could not
# be measured. Deliberately conservative: an idle empty wiki measures ~140-340 MB
# and a wiki with pages and embeddings is larger.
DEFAULT_WIKI_ESTIMATE_MB = 500.0

_SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(MB|GB)\s*$", re.IGNORECASE)


def parse_memory_size(text: str) -> float:
    """Return the size in MB for ``"6GB"`` / ``"6000MB"`` (1 GB = 1024 MB).

    A unit is required. Raises ``ValueError`` for a bare number, an unknown unit
    (``KB``, ``G``, ``TB``), a non-numeric value, or a value of zero or less.
    """
    m = _SIZE_RE.match(text or "")
    if not m:
        raise ValueError(
            f"Memory size needs a unit: GB or MB (for example 6GB or 6000MB), got {text!r}."
        )
    value = float(m.group(1))
    if value <= 0:
        raise ValueError(f"Memory size must be greater than zero, got {text!r}.")
    return value * 1024.0 if m.group(2).upper() == "GB" else value


def _fmt(mb: float) -> str:
    return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb:.0f} MB"


class MemoryGate:
    """Decides whether ``serve --all`` may start another wiki.

    Default mode (no budget): keep whole-machine memory use under
    ``DEFAULT_CEILING_FRACTION`` of physical memory, counting everything running.

    Budget mode (``budget_mb`` given, i.e. ``--max-memory``): the wikis started by
    this command may use at most ``budget_mb`` in total; other programs are
    ignored.

    The first wiki is always allowed, so ``serve --all`` never starts nothing.
    """

    def __init__(self, total_mb: float, used_mb: float, budget_mb: Optional[float] = None):
        self.total_mb = float(total_mb)
        self.used_mb = float(used_mb)
        self.budget_mb = budget_mb
        self.started_mb = 0.0

    def update_used(self, used_mb: float) -> None:
        self.used_mb = float(used_mb)

    def add_started(self, mb: float) -> None:
        self.started_mb += float(mb)

    def allows_next(self, started: int, next_cost_mb: float = DEFAULT_WIKI_ESTIMATE_MB) -> bool:
        if started == 0:
            return True
        if self.budget_mb is not None:
            return self.started_mb + next_cost_mb <= self.budget_mb
        return self.used_mb + next_cost_mb <= DEFAULT_CEILING_FRACTION * self.total_mb

    def describe(self) -> str:
        if self.budget_mb is not None:
            return f"--max-memory budget {_fmt(self.budget_mb)} for the wikis started by this command"
        pct = int(DEFAULT_CEILING_FRACTION * 100)
        return (f"keep system memory under {pct}% "
                f"({_fmt(DEFAULT_CEILING_FRACTION * self.total_mb)} of {_fmt(self.total_mb)})")


# ── OS readers ───────────────────────────────────────────────────────────────

def system_memory_mb() -> Optional[tuple[float, float]]:
    """Return ``(total_mb, used_mb)`` of physical memory, or ``None`` if unreadable."""
    try:
        if sys.platform == "win32":
            return _system_memory_windows()
        if sys.platform == "darwin":
            return _system_memory_macos()
        return _system_memory_linux()
    except Exception:
        return None


def _system_memory_windows() -> tuple[float, float]:
    import ctypes
    from ctypes import wintypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    st = MEMORYSTATUSEX()
    st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
        raise OSError("GlobalMemoryStatusEx failed")
    mib = 1024.0 * 1024.0
    return st.ullTotalPhys / mib, (st.ullTotalPhys - st.ullAvailPhys) / mib


def _system_memory_linux() -> tuple[float, float]:
    info: dict[str, float] = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, rest = line.partition(":")
        info[key] = float(rest.split()[0]) / 1024.0  # kB -> MB
    total = info["MemTotal"]
    available = info.get("MemAvailable", info.get("MemFree", 0.0))
    return total, total - available


def _system_memory_macos() -> tuple[float, float]:
    total = float(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)) / (1024 * 1024)
    out = subprocess.check_output(["vm_stat"], text=True)
    page = float(re.search(r"page size of (\d+) bytes", out).group(1))
    pages = {k: float(v) for k, v in re.findall(r"Pages (free|inactive|speculative):\s+(\d+)", out)}
    available = sum(pages.get(k, 0.0) for k in ("free", "inactive", "speculative")) * page / (1024 * 1024)
    return total, total - available


def process_memory_mb(pid: int) -> Optional[float]:
    """Return the resident memory of ``pid`` in MB, or ``None`` if unreadable."""
    try:
        if sys.platform == "win32":
            return _process_memory_windows(pid)
        if sys.platform == "darwin":
            out = subprocess.check_output(["ps", "-o", "rss=", "-p", str(pid)], text=True)
            return float(out.strip()) / 1024.0
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return float(line.split()[1]) / 1024.0
    except Exception:
        return None
    return None


def _process_memory_windows(pid: int) -> Optional[float]:
    import ctypes
    from ctypes import wintypes

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD]

    PROCESS_QUERY_INFORMATION, PROCESS_VM_READ = 0x0400, 0x0010
    handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not handle:
        return None
    try:
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return None
        return counters.WorkingSetSize / (1024.0 * 1024.0)
    finally:
        kernel32.CloseHandle(handle)
