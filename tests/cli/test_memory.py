# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Peter White / axoviq.com
"""Unit tests for the `serve --all` memory helpers (unit parsing + start gate)."""
from __future__ import annotations

import pytest

from synthadoc.cli._memory import (
    DEFAULT_CEILING_FRACTION,
    MemoryGate,
    parse_memory_size,
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
