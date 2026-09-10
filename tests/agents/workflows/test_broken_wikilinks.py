# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Unit tests for BrokenWikilinksWorkflow."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from synthadoc.agents.workflows._base import WorkflowContext
from synthadoc.agents.workflows.broken_wikilinks import BrokenWikilinksWorkflow


def _make_ctx():
    async def _noop(e, d):
        pass

    return WorkflowContext(
        session_id="s1",
        wiki_root=Path("/wiki"),
        queue=None,
        store=None,
        audit_db=None,
        send_sse_event=_noop,
        confirm_registry={},
        confirm_result_registry={},
    )


# ---------------------------------------------------------------------------
# System prompt contract
# ---------------------------------------------------------------------------

async def test_system_prompt_contains_all_tool_names():
    wf = BrokenWikilinksWorkflow()
    prompt = await wf.build_system_prompt()
    for tool in ("find_broken_wikilinks", "apply_link_fixes", "confirm", "run_lint", "get_page_states"):
        assert tool in prompt, f"Missing tool {tool!r} in system prompt"


async def test_system_prompt_mentions_active_only_scan():
    wf = BrokenWikilinksWorkflow()
    prompt = await wf.build_system_prompt()
    assert "active" in prompt.lower()
    assert "stale" in prompt.lower()
    assert "draft" in prompt.lower()


async def test_system_prompt_describes_two_phases():
    wf = BrokenWikilinksWorkflow()
    prompt = await wf.build_system_prompt()
    assert "Phase 1" in prompt
    assert "Phase 2" in prompt


# ---------------------------------------------------------------------------
# Tool function registry
# ---------------------------------------------------------------------------

def test_get_tool_fns_returns_all_expected_tools():
    wf = BrokenWikilinksWorkflow()
    ctx = _make_ctx()
    fns = wf.get_tool_fns(ctx)
    expected = {"find_broken_wikilinks", "apply_link_fixes", "confirm", "run_lint", "get_page_states"}
    assert set(fns.keys()) == expected


def test_all_tool_fns_are_callable():
    wf = BrokenWikilinksWorkflow()
    ctx = _make_ctx()
    fns = wf.get_tool_fns(ctx)
    for name, fn in fns.items():
        assert callable(fn), f"Tool {name!r} is not callable"


# ---------------------------------------------------------------------------
# build_initial_message passes user input through unchanged
# ---------------------------------------------------------------------------

def test_build_initial_message_passthrough():
    wf = BrokenWikilinksWorkflow()
    msg = "scan for broken wikilinks"
    assert wf.build_initial_message(msg) == msg


def test_build_initial_message_with_slug():
    """--slug in user input → single-page mode message (broken_wikilinks.py lines 188-189)."""
    wf = BrokenWikilinksWorkflow()
    msg = wf.build_initial_message("scan for broken wikilinks --slug my-page")
    assert "my-page" in msg
    assert "page_slug" in msg or "single-page" in msg.lower() or "Single-page" in msg


# ---------------------------------------------------------------------------
# system prompt — markdown format rules
# ---------------------------------------------------------------------------

async def test_system_prompt_step4_uses_markdown_list():
    """Step 4 must instruct the LLM to use markdown list items, not plain newlines."""
    wf = BrokenWikilinksWorkflow()
    prompt = await wf.build_system_prompt()
    # Must reference markdown list syntax
    assert "- `[[" in prompt or "- [[" in prompt, (
        "Step 4 must show markdown list items (- [[ref]]) in the template"
    )


async def test_system_prompt_step9_no_bullet_character():
    """Step 9 must use markdown list syntax, not Unicode bullet characters."""
    wf = BrokenWikilinksWorkflow()
    prompt = await wf.build_system_prompt()
    assert "•" not in prompt, (
        "System prompt must not use • bullet characters — use markdown '- ' list syntax "
        "so the web UI renders each item on its own line"
    )


async def test_system_prompt_step9_markdown_list():
    """Step 9 summary template uses markdown list items."""
    wf = BrokenWikilinksWorkflow()
    prompt = await wf.build_system_prompt()
    # The step 9 template must contain a markdown list item for per-page results
    assert "- <slug>" in prompt or "- ✓" in prompt, (
        "Step 9 must demonstrate markdown list items (- <slug>: N fix(es)) "
        "so the LLM mirrors that format in its output"
    )


# ---------------------------------------------------------------------------
# CLI path confirm message — markdown format
# ---------------------------------------------------------------------------

async def test_cli_confirm_message_uses_markdown_list(monkeypatch):
    """run_for_cli_provider builds confirm message with markdown list items.

    Each broken link must appear as its own '- [[ref]] → ...' line so that
    ReactMarkdown renders them on separate lines instead of collapsing them
    into a single paragraph.
    """
    wf = BrokenWikilinksWorkflow()
    ctx = _make_ctx()

    # Scan result: 2 broken links on one page — one with a suggestion, one without
    scan_result = {
        "has_issues": True,
        "pages": [
            {
                "slug": "alan-turing",
                "broken_links": [
                    {"ref": "manchester-baby",    "suggestion": None},
                    {"ref": "bletchley-parq",     "suggestion": "bletchley-park"},
                ],
            }
        ],
        "scanned": 5,
        "total_broken": 2,
    }

    captured_confirm_msg: list[str] = []

    async def _fake_find(_ctx, **_kwargs):
        return scan_result

    async def _fake_confirm(_ctx, message: str, yes_label: str = "", no_label: str = ""):
        captured_confirm_msg.append(message)
        return {"confirmed": False}  # decline so we don't need more mocks

    monkeypatch.setattr(
        "synthadoc.agents.workflows.broken_wikilinks.tool_find_broken_wikilinks",
        _fake_find,
    )
    monkeypatch.setattr(
        "synthadoc.agents.workflows.broken_wikilinks.tool_confirm",
        _fake_confirm,
    )

    events = [e async for e in wf.run_for_cli_provider(ctx, "scan for broken wikilinks", provider=None)]

    assert captured_confirm_msg, "tool_confirm was never called"
    msg = captured_confirm_msg[0]

    # Must contain markdown list items (not plain indented lines)
    assert "- `[[manchester-baby]]`" in msg, (
        "Confirm message must use '- `[[ref]]`' markdown list syntax for removal links"
    )
    assert "- `[[bletchley-parq]]`" in msg and "`[[bletchley-park]]`" in msg, (
        "Confirm message must show the fuzzy-match suggestion with backtick-code formatting"
    )
    # Page name must be bold
    assert "**alan-turing:**" in msg, (
        "Confirm message must render page slug as **bold** heading"
    )
    # Must NOT use plain • bullet characters
    assert "•" not in msg, (
        "Confirm message must not use • bullet characters — they collapse to one line in ReactMarkdown"
    )
