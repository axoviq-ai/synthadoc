# tests/test_contradiction_resolver_workflow.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for ContradictionResolverWorkflow registration and routing."""
from __future__ import annotations

import re
import pytest
from unittest.mock import AsyncMock, MagicMock


def test_workflow_is_registered_in_routed_workflows():
    from synthadoc.agents.workflows._registry import ROUTED_WORKFLOWS
    from synthadoc.agents.workflows.contradiction_resolver import ContradictionResolverWorkflow
    class_names = [w.__name__ if isinstance(w, type) else type(w).__name__
                   for w in ROUTED_WORKFLOWS]
    assert "ContradictionResolverWorkflow" in class_names


def test_match_re_matches_contradiction_resolver_phrase():
    from synthadoc.agents.workflows.contradiction_resolver import ContradictionResolverWorkflow
    re_pattern = ContradictionResolverWorkflow.MATCH_RE
    assert re_pattern.search("run contradiction resolver")
    assert re_pattern.search("Run the contradiction resolver now")
    assert re_pattern.search("fix contradicted pages")
    assert re_pattern.search("resolve contradictions")


def test_match_re_does_not_match_unrelated():
    from synthadoc.agents.workflows.contradiction_resolver import ContradictionResolverWorkflow
    re_pattern = ContradictionResolverWorkflow.MATCH_RE
    assert not re_pattern.search("run lint")
    assert not re_pattern.search("ingest my file")
    assert not re_pattern.search("what pages are stale?")


@pytest.mark.asyncio
async def test_build_system_prompt_is_non_empty():
    from synthadoc.agents.workflows.contradiction_resolver import ContradictionResolverWorkflow
    wf = ContradictionResolverWorkflow()
    prompt = await wf.build_system_prompt()
    assert isinstance(prompt, str)
    assert len(prompt) > 200
    assert "Strategy 1" in prompt or "content rewrite" in prompt.lower()
    assert "3" in prompt


def test_build_initial_message_includes_scope_and_slug():
    from synthadoc.agents.workflows.contradiction_resolver import ContradictionResolverWorkflow
    wf = ContradictionResolverWorkflow()
    msg = wf.build_initial_message(
        "run contradiction resolver --slug alan-turing --type gate",
        session_id="sess-1", wiki_root=MagicMock(), store=MagicMock(),
    )
    assert "alan-turing" in msg or "slug" in msg.lower()


def test_get_tool_fns_returns_all_expected_tools():
    from synthadoc.agents.workflows.contradiction_resolver import ContradictionResolverWorkflow
    wf = ContradictionResolverWorkflow()
    ctx = MagicMock()
    ctx.wiki_root = MagicMock()
    fns = wf.get_tool_fns(ctx)
    expected = {
        "tool_get_contradicted_pages",
        "tool_read_page_content",
        "tool_read_source_content",
        "tool_propose_and_apply",
        "tool_run_scoped_lint",
        "tool_transition_lifecycle_state",
        "tool_get_wiki_status",
        "tool_cost_estimate",
        "tool_confirm",
        "tool_ingest_source",
        "tool_poll_job",
    }
    assert expected.issubset(set(fns.keys()))


def test_action_re_routes_contradiction_resolver():
    """_ACTION_RE in action_agent must detect contradiction resolver intent.

    This is satisfied automatically because _ACTION_RE includes _ROUTED_PAT,
    which is derived from ROUTED_WORKFLOWS at module load time.
    No manual editing of action_agent.py is needed — registering in ROUTED_WORKFLOWS
    is sufficient.
    """
    import synthadoc.agents.action_agent as aa
    pattern = aa._ACTION_RE
    assert pattern.search("run contradiction resolver")
    assert pattern.search("fix contradicted pages")
    assert pattern.search("resolve contradictions in my wiki")
