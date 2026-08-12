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
