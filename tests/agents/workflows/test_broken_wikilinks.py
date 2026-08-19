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
