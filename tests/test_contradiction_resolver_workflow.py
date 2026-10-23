# tests/test_contradiction_resolver_workflow.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for ContradictionResolverWorkflow registration and routing."""
from __future__ import annotations

import re
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


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


@pytest.mark.asyncio
async def test_cli_provider_routes_error_rejection_to_unresolved_with_suggestion():
    from synthadoc.agents.workflows.contradiction_resolver import ContradictionResolverWorkflow
    from synthadoc.agents.workflows.tools.contradiction_resolver_tools import (
        ContradictionPageType as PT,
    )

    ctx = MagicMock()
    ctx.store = MagicMock()
    ctx.send_sse_event = AsyncMock()

    with (
        patch("synthadoc.agents.workflows.contradiction_resolver.tool_get_contradicted_pages",
              new=AsyncMock(return_value={"pages": [
                  {"slug": "alan-turing", "type": PT.GATE, "contradiction_note": None},
              ]})),
        patch("synthadoc.agents.workflows.contradiction_resolver.tool_cost_estimate",
              new=AsyncMock(return_value={"confirmed": True})),
        patch("synthadoc.agents.workflows.contradiction_resolver.tool_read_page_content",
              new=AsyncMock(return_value={"content": "# Page\n", "lint_warnings": ["dubious claim"],
                                           "contradiction_note": None})),
        patch.object(ContradictionResolverWorkflow, "_cli_rewrite_page",
                     new=AsyncMock(return_value="# Page\n\nRevised.\n")),
        patch("synthadoc.agents.workflows.contradiction_resolver.tool_propose_and_apply",
              new=AsyncMock(return_value={"applied": False, "diff_preview": "",
                                           "error": "heading mismatch"})),
        patch("synthadoc.agents.workflows._tools.tool_get_wiki_status",
              new=AsyncMock(return_value={"active": 1, "draft": 0, "stale": 0,
                                           "contradicted": 0, "archived": 0})),
    ):
        events = [e async for e in
                  ContradictionResolverWorkflow().run_for_cli_provider(
                      ctx, question="run contradiction resolver", provider=MagicMock())]

    # The per-page loop path delivers its final summary via tool_format_summary's
    # ctx.send_sse_event("final_text", ...) call (see contradiction_resolver_tools.py),
    # not via a generator yield — only the early-return paths (no pages / cancelled)
    # yield directly. Pull the final text from the mocked ctx call, same convention
    # as tests/test_contradiction_resolver_tools.py.
    final_calls = [c for c in ctx.send_sse_event.call_args_list if c.args[0] == "final_text"]
    final = final_calls[-1].args[1]["text"]
    assert "heading mismatch" in final
    assert "provider=anthropic" in final
    assert "alan-turing" in final


@pytest.mark.asyncio
async def test_cli_provider_routes_user_decline_to_skipped_unchanged():
    from synthadoc.agents.workflows.contradiction_resolver import ContradictionResolverWorkflow
    from synthadoc.agents.workflows.tools.contradiction_resolver_tools import (
        ContradictionPageType as PT,
    )

    ctx = MagicMock()
    ctx.store = MagicMock()
    ctx.send_sse_event = AsyncMock()

    with (
        patch("synthadoc.agents.workflows.contradiction_resolver.tool_get_contradicted_pages",
              new=AsyncMock(return_value={"pages": [
                  {"slug": "alan-turing", "type": PT.GATE, "contradiction_note": None},
              ]})),
        patch("synthadoc.agents.workflows.contradiction_resolver.tool_cost_estimate",
              new=AsyncMock(return_value={"confirmed": True})),
        patch("synthadoc.agents.workflows.contradiction_resolver.tool_read_page_content",
              new=AsyncMock(return_value={"content": "# Page\n", "lint_warnings": ["dubious claim"],
                                           "contradiction_note": None})),
        patch.object(ContradictionResolverWorkflow, "_cli_rewrite_page",
                     new=AsyncMock(return_value="# Page\n\nRevised.\n")),
        patch("synthadoc.agents.workflows.contradiction_resolver.tool_propose_and_apply",
              new=AsyncMock(return_value={"applied": False, "diff_preview": ""})),  # no error key
        patch("synthadoc.agents.workflows._tools.tool_get_wiki_status",
              new=AsyncMock(return_value={"active": 1, "draft": 0, "stale": 0,
                                           "contradicted": 0, "archived": 0})),
    ):
        events = [e async for e in
                  ContradictionResolverWorkflow().run_for_cli_provider(
                      ctx, question="run contradiction resolver", provider=MagicMock())]

    # See comment in test_cli_provider_routes_error_rejection_to_unresolved_with_suggestion
    # above re: final summary delivery via ctx.send_sse_event rather than a generator yield.
    final_calls = [c for c in ctx.send_sse_event.call_args_list if c.args[0] == "final_text"]
    final = final_calls[-1].args[1]["text"]
    assert "**⏭ Skipped (1):**" in final
    assert "provider=anthropic" not in final


def test_build_initial_message_rollback_intent_with_slug():
    from synthadoc.agents.workflows.contradiction_resolver import ContradictionResolverWorkflow
    workflow = ContradictionResolverWorkflow()
    msg = workflow.build_initial_message(
        "roll back alan-turing", session_id="sess-1", wiki_root=MagicMock(), store=MagicMock(),
    )
    assert "tool_rollback_last_fix" in msg
    assert "alan-turing" in msg


def test_build_initial_message_rollback_intent_no_slug():
    from synthadoc.agents.workflows.contradiction_resolver import ContradictionResolverWorkflow
    workflow = ContradictionResolverWorkflow()
    msg = workflow.build_initial_message(
        "roll back", session_id="sess-1", wiki_root=MagicMock(), store=MagicMock(),
    )
    assert "tool_list_recent_fixes" in msg


@pytest.mark.asyncio
async def test_cli_provider_rollback_short_circuit_no_model_call():
    from synthadoc.agents.workflows.contradiction_resolver import ContradictionResolverWorkflow

    ctx = MagicMock()
    ctx.store = MagicMock()
    ctx.send_sse_event = AsyncMock()

    rollback_calls = []
    async def _fake_rollback(ctx, slug):
        rollback_calls.append(slug)
        return {"status": "success", "message": f"Rolled back '{slug}'."}

    class _FakeProvider:
        async def complete(self, *a, **kw):
            raise AssertionError("model should not be called for a rollback request")

    with patch(
        "synthadoc.agents.workflows.contradiction_resolver.tool_rollback_last_fix",
        new=_fake_rollback,
    ):
        events = [e async for e in ContradictionResolverWorkflow().run_for_cli_provider(
            ctx, question="roll back my-page", provider=_FakeProvider())]

    assert rollback_calls == ["my-page"]
    assert events[-1]["data"]["text"] == "Rolled back 'my-page'."
