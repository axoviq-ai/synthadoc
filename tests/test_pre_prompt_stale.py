# tests/test_pre_prompt_stale.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
"""Tests for _build_pre_prompt stale-page detection."""
from __future__ import annotations

from synthadoc.agents.query_agent import _build_pre_prompt


# ── True positives: stale "in qualifier" format ───────────────────────────────

def test_stale_paren_qualifier():
    """Slug with '(stale since ...)' qualifier triggers pre-prompt."""
    answer = (
        "The following pages need re-ingesting:\n"
        "- alan-turing (stale since 2026-01-15)\n"
        "- konrad-zuse (stale since 2026-02-01)\n"
    )
    result = _build_pre_prompt(answer)
    assert result is not None
    assert "Re-ingest" in result
    assert "alan-turing" in result
    assert "konrad-zuse" in result


def test_stale_colon_qualifier():
    """Slug with ': stale since ...' qualifier triggers pre-prompt."""
    answer = "Stale pages detected:\n- transistor-and-microchip: stale since 2026-03-01\n"
    result = _build_pre_prompt(answer)
    assert result is not None
    assert "transistor-and-microchip" in result


def test_stale_emdash_qualifier():
    """Slug with '— stale' qualifier triggers pre-prompt."""
    answer = "These pages are outdated:\n- programming-languages-overview — stale\n"
    result = _build_pre_prompt(answer)
    assert result is not None
    assert "programming-languages-overview" in result


def test_stale_section_header_simple_list():
    """Simple slug list under a 'Stale pages:' section header triggers pre-prompt."""
    answer = (
        "Wiki status summary:\n\n"
        "Stale pages:\n"
        "- alan-turing\n"
        "- konrad-zuse\n"
        "- transistor-and-microchip\n"
    )
    result = _build_pre_prompt(answer)
    assert result is not None
    assert "Re-ingest" in result
    assert "alan-turing" in result


def test_stale_section_header_mid_sentence():
    """'You have N stale pages:' header with (since DATE) qualifiers — no 'stale' per item."""
    answer = (
        "You have 2 stale pages:\n"
        "- wiki-maintenance-session (since 2026-07-29)\n"
        "- 44f313d4 (since 2026-07-21)\n"
    )
    result = _build_pre_prompt(answer)
    assert result is not None
    assert "wiki-maintenance-session" in result
    assert "44f313d4" in result


def test_stale_count_in_prompt():
    """Slug count is reflected in the pre-prompt text."""
    answer = (
        "Stale pages:\n"
        "- alan-turing (stale since 2026-01-01)\n"
        "- konrad-zuse (stale since 2026-01-02)\n"
        "- transistor-and-microchip (stale since 2026-01-03)\n"
    )
    result = _build_pre_prompt(answer)
    assert result is not None
    assert "Re-ingest 3 stale pages" in result


# ── True negatives: should NOT fire ───────────────────────────────────────────

def test_no_stale_changed_pages_list():
    """Bug: 'what changed this week' answer lists pages without stale qualifier — must not fire."""
    answer = (
        "The wiki saw activity on 7 pages this week:\n"
        "- artificial-intelligence-history (updated Monday)\n"
        "- alan-turing (reviewed Tuesday)\n"
        "- transistor-and-microchip (re-ingested Wednesday)\n"
        "- konrad-zuse (active)\n"
        "- programming-languages-overview (active)\n"
        "- personal-computer-revolution (active)\n"
        "- youtube-o5nskjz-goi (active)\n\n"
        "No stale pages found in this wiki."
    )
    result = _build_pre_prompt(answer)
    assert result is None


def test_no_stale_when_explicitly_negated():
    """'no stale' in answer suppresses the pre-prompt."""
    answer = "There are no stale pages. All content is current."
    assert _build_pre_prompt(answer) is None


def test_no_stale_wiki_status_table_zero():
    """Wiki-status table with stale=0 suppresses the pre-prompt."""
    answer = "| active | 12 |\n| stale | 0 |\n| contradicted | 0 |"
    assert _build_pre_prompt(answer) is None


def test_no_stale_lint_header_zero():
    """Lint header 'Stale pages (0)' suppresses the pre-prompt."""
    answer = "**Stale pages (0)** — none detected."
    assert _build_pre_prompt(answer) is None


def test_no_stale_historical_context():
    """'was stale but re-ingested' — historical reference, no current stale pages."""
    answer = (
        "alan-turing was stale but has been successfully re-ingested.\n"
        "The wiki is fully up to date."
    )
    # The word "stale" appears, but no slug has a stale qualifier and no
    # stale section header is present — so no pre-prompt should fire.
    assert _build_pre_prompt(answer) is None


def test_no_stale_zero_count_phrasing():
    """'0 stale' phrasing suppresses the pre-prompt."""
    answer = "Lifecycle summary: 0 stale, 15 active, 0 contradicted."
    assert _build_pre_prompt(answer) is None


def test_no_stale_no_pages_are_stale_phrasing():
    """'no pages are currently stale' suppresses the pre-prompt."""
    answer = (
        "Here are the 7 pages updated this week: alan-turing (updated), konrad-zuse (updated).\n"
        "No pages are currently stale."
    )
    assert _build_pre_prompt(answer) is None
