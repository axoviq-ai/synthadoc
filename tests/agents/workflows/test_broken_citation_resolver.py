# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for BrokenCitationResolverWorkflow."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from synthadoc.agents.workflows._base import WorkflowContext
from synthadoc.agents.workflows.broken_citation_resolver import BrokenCitationResolverWorkflow


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


async def test_system_prompt_contains_all_tool_names():
    wf = BrokenCitationResolverWorkflow()
    prompt = await wf.build_system_prompt()
    for tool in ("find_broken_citations", "apply_citation_fixes", "confirm", "notify", "get_wiki_status"):
        assert tool in prompt, f"Missing tool {tool!r} in system prompt"


async def test_system_prompt_mentions_active_only_scan():
    wf = BrokenCitationResolverWorkflow()
    prompt = await wf.build_system_prompt()
    assert "active" in prompt.lower()


async def test_system_prompt_describes_all_reason_types():
    wf = BrokenCitationResolverWorkflow()
    prompt = await wf.build_system_prompt()
    for reason in ("broken_ref", "malformed", "out_of_range"):
        assert reason in prompt, f"Missing reason type {reason!r} in system prompt"


async def test_system_prompt_step5_calls_wiki_status_first():
    """STEP 5 must instruct the LLM to call get_wiki_status before any plain text."""
    wf = BrokenCitationResolverWorkflow()
    prompt = await wf.build_system_prompt()
    step5_idx = prompt.find("STEP 5")
    get_wiki_idx = prompt.find("get_wiki_status", step5_idx)
    assert step5_idx != -1, "STEP 5 missing from prompt"
    assert get_wiki_idx != -1 and get_wiki_idx > step5_idx, (
        "get_wiki_status must appear within STEP 5 block"
    )


def test_get_tool_fns_returns_all_expected_tools():
    wf = BrokenCitationResolverWorkflow()
    ctx = _make_ctx()
    fns = wf.get_tool_fns(ctx)
    expected = {"find_broken_citations", "apply_citation_fixes", "confirm", "notify", "get_wiki_status"}
    assert set(fns.keys()) == expected


def test_all_tool_fns_are_callable():
    wf = BrokenCitationResolverWorkflow()
    ctx = _make_ctx()
    fns = wf.get_tool_fns(ctx)
    for name, fn in fns.items():
        assert callable(fn), f"Tool {name!r} is not callable"


def test_gated_tools_contains_apply_citation_fixes():
    assert "apply_citation_fixes" in BrokenCitationResolverWorkflow.GATED_TOOLS


def test_match_re_matches_expected_phrases():
    wf = BrokenCitationResolverWorkflow()
    phrases = [
        "fix broken citations",
        "broken citation resolver",
        "citation resolver",
        "malformed citation markers",
        "broken_ref issue",
        "run citation resolver",
    ]
    for phrase in phrases:
        assert wf.MATCH_RE.search(phrase), f"MATCH_RE did not match: {phrase!r}"


def test_name_and_description():
    assert BrokenCitationResolverWorkflow.NAME == "broken-citation-resolver"
    assert "citation" in BrokenCitationResolverWorkflow.DESCRIPTION.lower()


def test_get_tool_budget_sufficient():
    wf = BrokenCitationResolverWorkflow()
    assert wf.get_tool_budget() >= 60


def test_build_initial_message_slug_mode():
    """--slug flag is parsed and injected into the initial message."""
    wf = BrokenCitationResolverWorkflow()
    msg = wf.build_initial_message("fix broken citations --slug my-page")
    assert "my-page" in msg
    assert "page_slug" in msg


def test_build_initial_message_no_slug_passthrough():
    """Without --slug the user input is returned unchanged."""
    wf = BrokenCitationResolverWorkflow()
    raw = "fix broken citations"
    assert wf.build_initial_message(raw) == raw
