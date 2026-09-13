# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for v1.2 hint engine patterns and pre_prompt generation."""
from __future__ import annotations
import pytest
from pathlib import Path


def _engine():
    from synthadoc.agents.hint_engine import HintEngine
    # Reload working copies from the bundled hints.json so pattern changes
    # in hints.json are visible even if the module was imported earlier.
    HintEngine.configure()
    return HintEngine()


def test_stale_pages_in_answer_emits_reingest_hint():
    engine = _engine()
    hints, _ = engine.after_response_windowed(
        answer="You have 3 stale pages: page-a, page-b, page-c.",
        mode="wiki", cursor=0
    )
    assert any("re-ingest" in h.lower() or "reingest" in h.lower() for h in hints), \
        f"Expected reingest hint, got: {hints}"


def test_reingest_completed_emits_lint_hint():
    engine = _engine()
    hints, _ = engine.after_response_windowed(
        answer="All 2 pages re-ingested successfully. Everything looks good.",
        mode="wiki", cursor=0
    )
    assert any("lint" in h.lower() for h in hints), \
        f"Expected lint hint, got: {hints}"


def test_pre_prompt_generated_for_stale_pages_list():
    from synthadoc.agents.query_agent import _build_pre_prompt
    answer = (
        "You have 2 stale pages:\n"
        "- wiki-maintenance-session (since 2026-07-29)\n"
        "- 44f313d4 (since 2026-07-21)"
    )
    prompt = _build_pre_prompt(answer)
    assert prompt is not None
    assert "re-ingest" in prompt.lower() or "reingest" in prompt.lower()
    assert "wiki-maintenance-session" in prompt
    assert "44f313d4" in prompt


def test_pre_prompt_absent_when_no_stale_pages():
    from synthadoc.agents.query_agent import _build_pre_prompt
    answer = "Your wiki is up to date. No stale pages found."
    prompt = _build_pre_prompt(answer)
    assert prompt is None


def test_pre_prompt_generated_for_reingest_complete():
    from synthadoc.agents.query_agent import _build_pre_prompt
    answer = "All 2 pages re-ingested successfully."
    prompt = _build_pre_prompt(answer)
    assert prompt is not None
    assert "lint" in prompt.lower()


def test_pre_prompt_generated_for_broken_wikilinks():
    from synthadoc.agents.query_agent import _build_pre_prompt
    answer = "Your wiki has 3 broken wikilinks: [[missingA]], [[missingB]], [[missingC]]."
    prompt = _build_pre_prompt(answer)
    assert prompt is not None
    assert "broken" in prompt.lower() or "wikilink" in prompt.lower()


def test_pre_prompt_generated_for_dead_links():
    from synthadoc.agents.query_agent import _build_pre_prompt
    answer = "Lint found 2 dead links in your active pages."
    prompt = _build_pre_prompt(answer)
    assert prompt is not None
    assert "broken" in prompt.lower() or "wikilink" in prompt.lower()


def test_pre_prompt_absent_when_no_broken_links():
    from synthadoc.agents.query_agent import _build_pre_prompt
    answer = "No broken wikilinks detected. Link integrity is clean."
    prompt = _build_pre_prompt(answer)
    assert prompt is None


def test_pre_prompt_absent_when_zero_broken_links():
    from synthadoc.agents.query_agent import _build_pre_prompt
    answer = "Scan complete: 0 broken links found across all active pages."
    prompt = _build_pre_prompt(answer)
    assert prompt is None


def test_broken_wikilinks_hint_chip_in_answer():
    engine = _engine()
    hints, _ = engine.after_response_windowed(
        answer="Your wiki has 2 broken wikilinks pointing to non-existent pages.",
        mode="wiki", cursor=0,
    )
    assert any("broken" in h.lower() or "wikilink" in h.lower() for h in hints), \
        f"Expected broken wikilinks hint, got: {hints}"


# ── _build_pre_prompt — broken citation patterns ──────────────────────────────

def test_pre_prompt_broken_citations_count_before():
    """'2 citation issue(s)' — CLI summary format with count before keyword."""
    from synthadoc.agents.query_agent import _build_pre_prompt
    prompt = _build_pre_prompt("Lint found 2 citation issue(s) across 1 page.")
    assert prompt is not None, "Expected a pre-prompt for broken citations"
    assert "citation" in prompt.lower()
    assert "2" in prompt


def test_pre_prompt_broken_citations_natural_language():
    """'2 broken citations' — natural language from LLM response."""
    from synthadoc.agents.query_agent import _build_pre_prompt
    prompt = _build_pre_prompt("There are 2 broken citations that need fixing.")
    assert prompt is not None
    assert "citation" in prompt.lower()
    assert "2" in prompt


def test_pre_prompt_broken_citations_cli_header():
    """'Citation Issues (2 across 1 pages)' — CLI section header format."""
    from synthadoc.agents.query_agent import _build_pre_prompt
    prompt = _build_pre_prompt(
        "Citation Issues (2 across 1 pages):\n  grace-hopper: ^[sources/bib.txt:1-5]"
    )
    assert prompt is not None
    assert "citation" in prompt.lower()
    assert "2" in prompt


def test_pre_prompt_broken_citations_colon_form():
    """'citation issues: 2' — colon-separated form."""
    from synthadoc.agents.query_agent import _build_pre_prompt
    prompt = _build_pre_prompt("Summary: citation issues: 2, orphans: 0")
    assert prompt is not None
    assert "citation" in prompt.lower()


def test_pre_prompt_broken_citations_singular():
    """'1 broken citation' → singular word in returned prompt."""
    from synthadoc.agents.query_agent import _build_pre_prompt
    prompt = _build_pre_prompt("1 citation issue found in grace-hopper.")
    assert prompt is not None
    assert "citation" in prompt.lower()
    assert "1" in prompt


def test_pre_prompt_no_broken_citations_when_zero():
    """'0 citation issue(s)' → no pre-prompt."""
    from synthadoc.agents.query_agent import _build_pre_prompt
    prompt = _build_pre_prompt("Lint complete: 0 citation issues found. All good.")
    assert prompt is None


def test_pre_prompt_no_broken_citations_when_none():
    """'no citation issues' → no pre-prompt."""
    from synthadoc.agents.query_agent import _build_pre_prompt
    prompt = _build_pre_prompt("There are no citation issues in your wiki.")
    assert prompt is None


def test_pre_prompt_broken_citations_triggers_resolver_phrase():
    """The returned pre-prompt must contain 'citation resolver' so the router
    routes it to BrokenCitationResolverWorkflow."""
    from synthadoc.agents.query_agent import _build_pre_prompt
    prompt = _build_pre_prompt("2 citation issue(s) detected.")
    assert prompt is not None
    assert "citation resolver" in prompt.lower()


def test_pre_prompt_broken_citations_summary_wins_over_per_page_detail():
    """Lint report shows 'Broken citations: 2' in the summary but each
    per-page entry says '1 broken citation(s)'.  The total (2) must win."""
    from synthadoc.agents.query_agent import _build_pre_prompt
    answer = (
        "Broken citations: 2\n"
        "[[artificial-intelligence-history]] (1 broken citation(s))\n"
        "[[programming-languages-overview]] (1 broken citation(s))\n"
    )
    prompt = _build_pre_prompt(answer)
    assert prompt is not None
    assert "2" in prompt, f"Expected total '2', got: {prompt!r}"
    assert "1" not in prompt, f"Per-page count '1' leaked into prompt: {prompt!r}"


def test_pre_prompt_broken_citations_bare_summary_line():
    """'Broken citations: N' alone (lint-report summary line format) is matched."""
    from synthadoc.agents.query_agent import _build_pre_prompt
    prompt = _build_pre_prompt("Broken citations: 3")
    assert prompt is not None
    assert "3" in prompt
