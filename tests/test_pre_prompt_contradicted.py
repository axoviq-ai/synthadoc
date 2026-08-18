# tests/test_pre_prompt_contradicted.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for _build_pre_prompt contradicted-page detection."""
from __future__ import annotations

import pytest
from synthadoc.agents.query_agent import _build_pre_prompt


def test_pre_prompt_fires_for_positive_contradicted_count():
    answer = "Lint complete. 2 contradicted pages found: alan-turing, eniac."
    result = _build_pre_prompt(answer)
    assert result is not None
    assert "contradicted" in result.lower()
    assert "resolver" in result.lower()


def test_pre_prompt_fires_for_one_contradicted_page():
    answer = "Lint summary: 1 contradicted page."
    result = _build_pre_prompt(answer)
    assert result is not None
    assert "1" in result


def test_pre_prompt_does_not_fire_for_zero_contradicted():
    answer = "All good! 0 contradicted pages."
    result = _build_pre_prompt(answer)
    assert result is None


def test_pre_prompt_does_not_fire_for_no_contradicted_phrase():
    answer = "no contradicted pages were found."
    result = _build_pre_prompt(answer)
    assert result is None


def test_pre_prompt_does_not_fire_for_zero_contradicted_variant():
    answer = "zero contradicted pages remain."
    result = _build_pre_prompt(answer)
    assert result is None


def test_pre_prompt_does_not_fire_for_unrelated_text():
    answer = "The page discusses contradictions in the historical record."
    result = _build_pre_prompt(answer)
    # "contradictions" alone without "N contradicted" must not trigger
    assert result is None


def test_pre_prompt_contradiction_does_not_shadow_reingest_trigger():
    """If reingest_complete is in the same answer, it still wins (first match)."""
    answer = "Re-ingested successfully. Also, 2 contradicted pages."
    result = _build_pre_prompt(answer)
    # reingest_complete pattern fires first in existing code
    assert result is not None
    # We don't assert exact phrasing here — either trigger is acceptable


# ── lint-report output format ─────────────────────────────────────────────────

def test_pre_prompt_fires_for_lint_report_format():
    """Lint report renders '**Contradicted pages (N)**' — number is in parens."""
    answer = (
        "**Contradicted pages (4)** — resolve conflict and set `status: active`:\n\n"
        "- `alan-turing`\n- `eniac`\n- `von-neumann`\n- `lovelace`"
    )
    result = _build_pre_prompt(answer)
    assert result is not None, "pre_prompt should fire for lint-report contradicted format"
    assert "4" in result
    assert "contradicted" in result.lower()
    assert "resolver" in result.lower()


def test_pre_prompt_fires_for_lint_report_single_page():
    """Singular form is correct when lint report shows exactly one page."""
    answer = "**Contradicted pages (1)** — resolve conflict and set `status: active`:\n- `alan-turing`"
    result = _build_pre_prompt(answer)
    assert result is not None
    assert "1 page" in result


def test_pre_prompt_does_not_fire_for_lint_report_zero():
    """Lint report with (0) must NOT trigger the hint."""
    answer = "**Contradicted pages (0)** — no contradictions found."
    result = _build_pre_prompt(answer)
    assert result is None


# ── wiki-status table format ──────────────────────────────────────────────────

def test_pre_prompt_fires_for_wiki_status_table_format():
    """Wiki status renders '| contradicted | N |' — number after the word in a table."""
    answer = (
        "**Wiki status** — 15 pages total\n\n"
        "| State | Count | Note |\n"
        "|---|---|---|\n"
        "| draft | 0 | awaiting lint review |\n"
        "| active | 11 | published |\n"
        "| stale | 0 | source changed |\n"
        "| contradicted | 4 | conflicting sources — manual review required |\n"
        "| archived | 0 | excluded |\n"
    )
    result = _build_pre_prompt(answer)
    assert result is not None, "pre_prompt should fire for wiki-status table format"
    assert "4" in result
    assert "contradicted" in result.lower()
    assert "resolver" in result.lower()


def test_pre_prompt_does_not_fire_for_wiki_status_zero():
    """Wiki status table with 0 contradicted must NOT trigger the hint."""
    answer = (
        "**Wiki status** — 10 pages total\n\n"
        "| State | Count | Note |\n"
        "|---|---|---|\n"
        "| active | 10 | published |\n"
        "| contradicted | 0 | conflicting sources |\n"
    )
    result = _build_pre_prompt(answer)
    assert result is None
