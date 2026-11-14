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


def format_memory_display(mb: float) -> str:
    """Short, human-readable size for messages: ``161 MB`` or ``1.5 GB``."""
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
            return f"--max-memory budget {format_memory_display(self.budget_mb)} for the wikis started by this command"
        pct = int(DEFAULT_CEILING_FRACTION * 100)
        return (f"keep system memory under {pct}% "
                f"({format_memory_display(DEFAULT_CEILING_FRACTION * self.total_mb)} of {format_memory_display(self.total_mb)})")


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


# Thin I/O wrappers (patched in tests) and pure parsers. The parsers are plain
# functions of the text the OS returns, so the Linux and macOS logic is tested
# on every platform from recorded samples.

def _read_text(path: str) -> str:
    return Path(path).read_text()


def _run_text(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True)


def _parse_meminfo(text: str) -> tuple[float, float]:
    """``/proc/meminfo`` text -> ``(total_mb, used_mb)``; falls back to MemFree on old kernels."""
    info: dict[str, float] = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        if rest.split():
            info[key] = float(rest.split()[0]) / 1024.0  # kB -> MB
    if "MemTotal" not in info:
        raise ValueError("MemTotal missing from /proc/meminfo")
    total = info["MemTotal"]
    available = info.get("MemAvailable", info.get("MemFree", 0.0))
    return total, total - available


def _parse_proc_status_rss(text: str) -> Optional[float]:
    """``/proc/<pid>/status`` text -> resident memory in MB (``None`` for kernel threads)."""
    for line in text.splitlines():
        if line.startswith("VmRSS:"):
            return float(line.split()[1]) / 1024.0
    return None


def _parse_macos_memory(sysctl_memsize: str, vm_stat: str) -> tuple[float, float]:
    """``sysctl -n hw.memsize`` + ``vm_stat`` output -> ``(total_mb, used_mb)``.

    free, inactive and speculative pages count as available.
    """
    mib = 1024.0 * 1024.0
    total = float(sysctl_memsize.strip()) / mib
    page = float(re.search(r"page size of (\d+) bytes", vm_stat).group(1))
    pages = {k: float(v) for k, v in re.findall(r"Pages (free|inactive|speculative):\s+(\d+)", vm_stat)}
    available = sum(pages.get(k, 0.0) for k in ("free", "inactive", "speculative")) * page / mib
    return total, total - available


def _parse_ps_rss(text: str) -> float:
    """``ps -o rss= -p <pid>`` output (kB) -> MB."""
    return float(text.strip()) / 1024.0


def _system_memory_linux() -> tuple[float, float]:
    return _parse_meminfo(_read_text("/proc/meminfo"))


def _system_memory_macos() -> tuple[float, float]:
    return _parse_macos_memory(_run_text(["sysctl", "-n", "hw.memsize"]), _run_text(["vm_stat"]))


def process_memory_mb(pid: int) -> Optional[float]:
    """Return the resident memory of ``pid`` in MB, or ``None`` if unreadable."""
    try:
        if sys.platform == "win32":
            return _process_memory_windows(pid)
        if sys.platform == "darwin":
            return _parse_ps_rss(_run_text(["ps", "-o", "rss=", "-p", str(pid)]))
        return _parse_proc_status_rss(_read_text(f"/proc/{pid}/status"))
    except Exception:
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


# ── formatting and suggestions ───────────────────────────────────────────────

def format_memory_size(mb: float) -> str:
    """Format MB as a valid ``--max-memory`` value: ``2GB``, ``1.5GB`` or ``800MB``."""
    if mb >= 1024:
        return f"{mb / 1024:g}GB"
    return f"{int(round(mb))}MB"


def suggest_budget_mb(started_mb: float, per_wiki_mb: float, remaining: int,
                      headroom: float = 1.25) -> float:
    """A ``--max-memory`` budget big enough for the started wikis plus ``remaining`` more.

    Adds 25 % headroom (wikis grow once their embedding model loads) and rounds up
    to a tidy value: 100 MB steps below 1 GB, 0.5 GB steps above.
    """
    needed = (started_mb + per_wiki_mb * remaining) * headroom
    step = 100.0 if needed < 1024 else 512.0
    return float(-(-needed // step) * step)
