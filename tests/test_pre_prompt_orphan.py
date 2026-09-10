# tests/test_pre_prompt_orphan.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for _build_pre_prompt orphan-page detection."""
from __future__ import annotations

import pytest
from synthadoc.agents.query_agent import _build_pre_prompt


# ── LLM text output format ────────────────────────────────────────────────────

def test_pre_prompt_fires_for_positive_orphan_count():
    """LLM reply: '2 orphan pages found'."""
    answer = "There are 2 orphan pages with no inbound links: konrad-zuse, quantum-computing."
    result = _build_pre_prompt(answer)
    assert result is not None
    assert "2" in result
    assert "orphan" in result.lower()
    assert "resolver" in result.lower()


def test_pre_prompt_fires_for_one_orphan_page():
    """Singular form when exactly 1 orphan page."""
    answer = "Found 1 orphan page: konrad-zuse."
    result = _build_pre_prompt(answer)
    assert result is not None
    assert "1" in result
    assert "page" in result
    # Must NOT say "pages" (singular)
    assert "1 orphan page" in result


def test_pre_prompt_fires_for_orphaned_variant():
    """'orphaned pages' (past-participle) must also trigger."""
    answer = "The following 3 orphaned pages have no inbound links."
    result = _build_pre_prompt(answer)
    assert result is not None
    assert "3" in result
    assert "orphan" in result.lower()


def test_pre_prompt_does_not_fire_for_zero_orphan():
    answer = "Great news! 0 orphan pages detected."
    result = _build_pre_prompt(answer)
    assert result is None


def test_pre_prompt_does_not_fire_for_no_orphan_phrase():
    answer = "No orphan pages were found."
    result = _build_pre_prompt(answer)
    assert result is None


def test_pre_prompt_does_not_fire_for_zero_orphan_variant():
    answer = "zero orphan pages remain."
    result = _build_pre_prompt(answer)
    assert result is None


def test_pre_prompt_does_not_fire_for_unrelated_orphan_word():
    """The word 'orphan' alone (not 'N orphan pages') must not trigger."""
    answer = "The orphan process was cleaned up by the scheduler."
    result = _build_pre_prompt(answer)
    assert result is None


# ── Lint report CLI summary format ("- Orphan pages: N") ─────────────────────
# This is the format produced by LintReportWorkflow.run_for_cli_provider()
# summary line: f"- Orphan pages: {orphans}"

def test_pre_prompt_fires_for_lint_summary_format():
    """CLI lint report summary line '- Orphan pages: 2' triggers pre-prompt."""
    answer = (
        "### Lint Report (2026-09-10)\n\n"
        "**Summary**\n"
        "- Orphan pages: 2\n"
        "- Contradictions: 0 resolved, 0 flagged\n\n"
        "**Orphan Pages**\n"
        "- konrad-zuse\n"
        "- quantum-computing"
    )
    result = _build_pre_prompt(answer)
    assert result is not None, (
        "pre_prompt must fire when lint summary contains '- Orphan pages: 2'"
    )
    assert "2" in result
    assert "orphan" in result.lower()
    assert "resolver" in result.lower()


def test_pre_prompt_fires_for_lint_summary_single_page():
    """Singular form correct when lint summary shows exactly 1 orphan page."""
    answer = (
        "**Summary**\n"
        "- Orphan pages: 1\n"
        "- Contradictions: 0 resolved, 0 flagged\n\n"
        "**Orphan Pages**\n"
        "- konrad-zuse"
    )
    result = _build_pre_prompt(answer)
    assert result is not None
    assert "1 orphan page" in result


def test_pre_prompt_does_not_fire_for_lint_summary_zero():
    """Lint summary '- Orphan pages: 0' must NOT trigger the hint."""
    answer = (
        "### Lint Report (2026-09-10)\n\n"
        "**Summary**\n"
        "- Orphan pages: 0\n"
        "- Contradictions: 0 resolved, 0 flagged\n\n"
        "**Orphan Pages**\n"
        "(none)"
    )
    result = _build_pre_prompt(answer)
    assert result is None, (
        "pre_prompt must NOT fire when lint summary shows '- Orphan pages: 0'"
    )


# ── Lint report LLM-generated section header format ──────────────────────────

def test_pre_prompt_fires_for_lint_report_format():
    """LLM-generated format 'Orphan pages (2) — no inbound links:' triggers pre-prompt."""
    answer = (
        "**Orphan Pages**\n\n"
        "Orphan pages (2) — no inbound links:\n\n"
        "- `konrad-zuse`\n- `quantum-computing`"
    )
    result = _build_pre_prompt(answer)
    assert result is not None, "pre_prompt should fire for parens orphan format"
    assert "2" in result
    assert "orphan" in result.lower()
    assert "resolver" in result.lower()


def test_pre_prompt_fires_for_lint_report_single_page():
    """Singular form is correct when lint report shows exactly one page."""
    answer = "Orphan pages (1) — no inbound links:\n- `konrad-zuse`"
    result = _build_pre_prompt(answer)
    assert result is not None
    assert "1 orphan page" in result


def test_pre_prompt_does_not_fire_for_lint_report_zero():
    """Parens format with (0) must NOT trigger the hint."""
    answer = "Orphan pages (0) — all pages are reachable via wikilinks."
    result = _build_pre_prompt(answer)
    assert result is None


# ── Wiki-status table format ──────────────────────────────────────────────────

def test_pre_prompt_fires_for_wiki_status_table_format():
    """Wiki status renders '| orphan | N |' — number after the word in a table."""
    answer = (
        "**Wiki status** — 15 pages total\n\n"
        "| State | Count | Note |\n"
        "|---|---|---|\n"
        "| draft | 0 | awaiting lint review |\n"
        "| active | 13 | published |\n"
        "| stale | 0 | source changed |\n"
        "| contradicted | 0 | |\n"
        "| orphan | 2 | no inbound links |\n"
    )
    result = _build_pre_prompt(answer)
    assert result is not None, "pre_prompt should fire for wiki-status table format"
    assert "2" in result
    assert "orphan" in result.lower()
    assert "resolver" in result.lower()


def test_pre_prompt_does_not_fire_for_wiki_status_zero():
    """Wiki status table with 0 orphan must NOT trigger the hint."""
    answer = (
        "**Wiki status** — 10 pages total\n\n"
        "| State | Count | Note |\n"
        "|---|---|---|\n"
        "| active | 10 | published |\n"
        "| orphan | 0 | no inbound links |\n"
    )
    result = _build_pre_prompt(answer)
    assert result is None


# ── Priority ordering ─────────────────────────────────────────────────────────

def test_orphan_does_not_shadow_contradicted():
    """Contradicted pages take priority over orphan pages in the same response."""
    answer = (
        "Lint report: 3 contradicted pages and "
        "Orphan pages (2) — no inbound links."
    )
    result = _build_pre_prompt(answer)
    assert result is not None
    assert "contradicted" in result.lower(), (
        "Contradicted hint must fire before orphan hint when both are present"
    )


def test_orphan_does_not_shadow_stale_with_slugs():
    """Stale pages (with slugs) take priority over orphan pages."""
    answer = (
        "Stale pages:\n- konrad-zuse (stale since 2026-01-01)\n\n"
        "Also: Orphan pages (2) — no inbound links."
    )
    result = _build_pre_prompt(answer)
    assert result is not None
    assert "stale" in result.lower(), (
        "Stale hint must fire before orphan hint when both are present with named slugs"
    )


def test_orphan_fires_when_stale_has_no_slugs():
    """Orphan fires if stale appears without parseable slugs (avoids false stale prompt)."""
    answer = (
        "Some pages are in a stale state.\n"
        "Orphan pages (2) — no inbound links."
    )
    result = _build_pre_prompt(answer)
    # Stale with no slugs → stale branch skips → orphan branch fires
    assert result is not None
    assert "orphan" in result.lower()


def test_orphan_takes_priority_over_broken_wikilinks():
    """Orphan fires before broken-wikilinks when both are present."""
    answer = (
        "Orphan pages (1) — no inbound links: konrad-zuse\n"
        "There are also broken wikilinks detected."
    )
    result = _build_pre_prompt(answer)
    assert result is not None
    assert "orphan" in result.lower(), (
        "Orphan hint must fire before broken-wikilinks hint"
    )
