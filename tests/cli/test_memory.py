# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Peter White / axoviq.com
"""Unit tests for the `serve --all` memory helpers (unit parsing + start gate)."""
from __future__ import annotations

import pytest

from synthadoc.cli._memory import (
    DEFAULT_CEILING_FRACTION,
    MemoryGate,
    format_memory_size,
    parse_memory_size,
    suggest_budget_mb,
)


# ── parse_memory_size: a unit is mandatory ───────────────────────────────────

@pytest.mark.parametrize("text, expected_mb", [
    ("6GB", 6144.0),
    ("6000MB", 6000.0),
    ("1.5gb", 1536.0),
    ("512mb", 512.0),
    (" 6 GB ", 6144.0),
])
def test_parse_memory_size_accepts_gb_and_mb(text, expected_mb):
    assert parse_memory_size(text) == expected_mb


@pytest.mark.parametrize("text", ["6000", "6", "0", "abc", "", "6KB", "6G", "6TB", "-1GB", "0GB", "GB"])
def test_parse_memory_size_rejects_bad_values(text):
    with pytest.raises(ValueError):
        parse_memory_size(text)


def test_parse_memory_size_bare_number_error_explains_the_unit():
    with pytest.raises(ValueError, match=r"(?i)unit.*GB.*MB|GB.*MB.*unit"):
        parse_memory_size("6000")


# ── MemoryGate: default mode (keep the machine under ~60% used) ──────────────

def test_default_ceiling_is_sixty_percent():
    assert DEFAULT_CEILING_FRACTION == 0.60


def test_default_gate_always_allows_the_first_wiki_even_on_a_busy_machine():
    gate = MemoryGate(total_mb=16000, used_mb=14000)  # already 87% used
    assert gate.allows_next(started=0) is True


def test_default_gate_allows_until_projected_use_would_cross_ceiling():
    # ceiling = 0.6 * 16000 = 9600 MB. 8000 used + next 500 -> 8500: ok.
    gate = MemoryGate(total_mb=16000, used_mb=8000)
    assert gate.allows_next(started=1, next_cost_mb=500) is True


def test_default_gate_refuses_when_next_wiki_would_cross_ceiling():
    gate = MemoryGate(total_mb=16000, used_mb=9300)
    assert gate.allows_next(started=1, next_cost_mb=500) is False  # 9800 > 9600


def test_default_gate_uses_live_used_memory_after_update():
    gate = MemoryGate(total_mb=16000, used_mb=8000)
    gate.update_used(9500)
    assert gate.allows_next(started=2, next_cost_mb=500) is False


# ── MemoryGate: --max-memory mode (budget = memory of wikis we started) ──────

def test_budget_gate_allows_first_wiki_even_if_budget_is_smaller_than_one_wiki():
    gate = MemoryGate(total_mb=16000, used_mb=14000, budget_mb=100)
    assert gate.allows_next(started=0) is True


def test_budget_gate_counts_only_memory_of_started_wikis():
    gate = MemoryGate(total_mb=16000, used_mb=15000, budget_mb=2000)  # machine busy: irrelevant
    gate.add_started(600)
    gate.add_started(700)
    assert gate.allows_next(started=2, next_cost_mb=600) is True    # 1300 + 600 <= 2000
    gate.add_started(600)
    assert gate.allows_next(started=3, next_cost_mb=600) is False   # 1900 + 600 > 2000


def test_gate_describes_its_limit_in_units():
    default = MemoryGate(total_mb=16000, used_mb=8000)
    budget = MemoryGate(total_mb=16000, used_mb=8000, budget_mb=6144)
    assert "60%" in default.describe()
    assert "6.0 GB" in budget.describe()


# ── OS readers: parsers tested on realistic samples (run on every OS) ────────
# The parsers are pure functions of the text the OS returns, so the Linux and
# macOS code paths are exercised on every CI platform, not just on the matching one.

import os
import sys

from synthadoc.cli import _memory
from synthadoc.cli._memory import process_memory_mb, system_memory_mb

LINUX_MEMINFO = """\
MemTotal:       16384000 kB
MemFree:          812340 kB
MemAvailable:    8192000 kB
Buffers:          204800 kB
Cached:          6144000 kB
SwapTotal:       2097148 kB
"""

LINUX_MEMINFO_NO_AVAILABLE = """\
MemTotal:        8192000 kB
MemFree:         1024000 kB
Buffers:          102400 kB
"""

LINUX_PROC_STATUS = """\
Name:\tpython
VmPeak:\t  412000 kB
VmSize:\t  398000 kB
VmRSS:\t  143360 kB
VmData:\t  120000 kB
"""

MACOS_SYSCTL_MEMSIZE = "17179869184\n"   # 16 GiB
MACOS_VM_STAT = """\
Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                               100000.
Pages active:                             400000.
Pages inactive:                           200000.
Pages speculative:                         20000.
Pages throttled:                               0.
Pages wired down:                         150000.
"""


def test_parse_meminfo_uses_memavailable():
    total, used = _memory._parse_meminfo(LINUX_MEMINFO)
    assert total == pytest.approx(16384000 / 1024)
    assert used == pytest.approx((16384000 - 8192000) / 1024)


def test_parse_meminfo_falls_back_to_memfree_on_old_kernels():
    total, used = _memory._parse_meminfo(LINUX_MEMINFO_NO_AVAILABLE)
    assert total == pytest.approx(8192000 / 1024)
    assert used == pytest.approx((8192000 - 1024000) / 1024)


def test_parse_meminfo_rejects_text_without_memtotal():
    with pytest.raises(ValueError):
        _memory._parse_meminfo("Buffers: 1 kB\n")


def test_parse_proc_status_reads_vmrss_in_mb():
    assert _memory._parse_proc_status_rss(LINUX_PROC_STATUS) == pytest.approx(140.0)


def test_parse_proc_status_without_vmrss_is_none():
    assert _memory._parse_proc_status_rss("Name:\tkthreadd\n") is None


def test_parse_macos_memory_counts_free_inactive_and_speculative_as_available():
    total, used = _memory._parse_macos_memory(MACOS_SYSCTL_MEMSIZE, MACOS_VM_STAT)
    assert total == pytest.approx(16384.0)
    available = (100000 + 200000 + 20000) * 16384 / (1024 * 1024)
    assert used == pytest.approx(16384.0 - available)


def test_parse_macos_memory_handles_4k_pages():
    vm = MACOS_VM_STAT.replace("16384", "4096")
    total, used = _memory._parse_macos_memory(MACOS_SYSCTL_MEMSIZE, vm)
    assert used == pytest.approx(16384.0 - (320000 * 4096 / (1024 * 1024)))


def test_parse_ps_rss_kb_to_mb():
    assert _memory._parse_ps_rss("  143360\n") == pytest.approx(140.0)


def test_parse_ps_rss_rejects_empty_output():
    with pytest.raises(ValueError):
        _memory._parse_ps_rss("\n")


# ── dispatch: the right reader for each platform; failure -> None ────────────

@pytest.mark.parametrize("platform, reader", [
    ("win32", "_system_memory_windows"),
    ("darwin", "_system_memory_macos"),
    ("linux", "_system_memory_linux"),
])
def test_system_memory_dispatches_by_platform(monkeypatch, platform, reader):
    monkeypatch.setattr(_memory.sys, "platform", platform)
    monkeypatch.setattr(_memory, reader, lambda: (1000.0, 250.0))
    assert system_memory_mb() == (1000.0, 250.0)


def test_system_memory_returns_none_when_the_reader_fails(monkeypatch):
    def boom():
        raise OSError("no /proc")
    monkeypatch.setattr(_memory.sys, "platform", "linux")
    monkeypatch.setattr(_memory, "_system_memory_linux", boom)
    assert system_memory_mb() is None


def test_process_memory_linux_reads_proc_status(monkeypatch):
    monkeypatch.setattr(_memory.sys, "platform", "linux")
    monkeypatch.setattr(_memory, "_read_text", lambda path: LINUX_PROC_STATUS)
    assert process_memory_mb(1234) == pytest.approx(140.0)


def test_process_memory_macos_reads_ps(monkeypatch):
    monkeypatch.setattr(_memory.sys, "platform", "darwin")
    monkeypatch.setattr(_memory, "_run_text", lambda cmd: "  143360\n")
    assert process_memory_mb(1234) == pytest.approx(140.0)


def test_process_memory_returns_none_for_a_vanished_process(monkeypatch):
    def gone(path):
        raise FileNotFoundError(path)
    monkeypatch.setattr(_memory.sys, "platform", "linux")
    monkeypatch.setattr(_memory, "_read_text", gone)
    assert process_memory_mb(999999) is None


# ── real readers on the CI runner's own OS (ubuntu, windows, macos) ──────────

def test_real_system_memory_is_sane_on_this_os():
    result = system_memory_mb()
    assert result is not None, f"system memory unreadable on {sys.platform}"
    total, used = result
    assert total > 256                      # any CI runner has more than 256 MB
    assert 0 < used < total


def test_real_process_memory_of_this_process_is_sane_on_this_os():
    rss = process_memory_mb(os.getpid())
    assert rss is not None, f"process memory unreadable on {sys.platform}"
    assert 5 < rss < 8192                   # a running pytest is tens to hundreds of MB


def test_real_process_memory_of_a_missing_pid_is_none():
    assert process_memory_mb(2_000_000_000) is None


# ── suggested budget + parseable formatting ──────────────────────────────────



@pytest.mark.parametrize("mb, expected", [
    (2048.0, "2GB"), (1536.0, "1.5GB"), (2560.0, "2.5GB"), (800.0, "800MB"), (1024.0, "1GB"),
])
def test_format_memory_size_is_always_a_valid_flag_value(mb, expected):
    assert format_memory_size(mb) == expected
    assert parse_memory_size(format_memory_size(mb)) == mb


def test_suggest_budget_adds_headroom_and_rounds_up_to_half_a_gb():
    # (400 started + 3 x 400 skipped) = 1600 MB, +25% = 2000 MB -> 2048 MB
    assert suggest_budget_mb(started_mb=400, per_wiki_mb=400, remaining=3) == 2048.0


def test_suggest_budget_rounds_small_budgets_up_to_100mb():
    assert suggest_budget_mb(started_mb=100, per_wiki_mb=100, remaining=1) == 300.0   # 200*1.25=250 -> 300


def test_suggested_budget_always_parses_and_fits_the_wikis():
    for started, per, rem in [(160, 160, 10), (1500, 700, 4), (50, 50, 1)]:
        mb = suggest_budget_mb(started_mb=started, per_wiki_mb=per, remaining=rem)
        assert parse_memory_size(format_memory_size(mb)) == mb
        assert mb >= started + per * rem
