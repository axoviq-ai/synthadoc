# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for IngestLintWorkflow (Task 4)."""
from __future__ import annotations
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from synthadoc.agents.workflows._base import WorkflowContext
from synthadoc.agents.workflows.ingest_lint import IngestLintWorkflow


def _make_ctx():
    events = []
    async def _send(e, d): events.append({"event": e, "data": d})
    return WorkflowContext(
        session_id="wf-test",
        wiki_root=Path("/wiki"),
        queue=AsyncMock(),
        store=MagicMock(),
        audit_db=AsyncMock(),
        send_sse_event=_send,
        confirm_registry={},
        confirm_result_registry={},
    ), events


async def test_ingest_lint_system_prompt_mentions_tools():
    wf = IngestLintWorkflow()
    prompt = await wf.build_system_prompt()
    assert "find_stale_pages" in prompt
    assert "find_page_source" in prompt
    assert "ingest_source" in prompt
    assert "get_page_states" in prompt
    assert "confirm" in prompt


def test_ingest_lint_tool_fns_are_all_callable():
    wf = IngestLintWorkflow()
    ctx, _ = _make_ctx()
    fns = wf.get_tool_fns(ctx)
    assert set(fns) == {
        "find_stale_pages", "find_page_source",
        "ingest_source", "poll_job", "run_lint", "get_page_states", "confirm",
    }
    for name, fn in fns.items():
        assert callable(fn), f"{name} not callable"


def test_ingest_lint_tool_fns_are_partial_bound():
    """Each fn is bound to ctx via functools.partial — calling fn() won't need ctx."""
    import inspect, functools
    wf = IngestLintWorkflow()
    ctx, _ = _make_ctx()
    fns = wf.get_tool_fns(ctx)
    for name, fn in fns.items():
        assert isinstance(fn, functools.partial), f"{name} should be a functools.partial"
        # The partial's first arg should be ctx
        assert fn.args[0] is ctx, f"{name} partial not bound to ctx"


def test_ingest_lint_build_initial_message_returns_user_input():
    wf = IngestLintWorkflow()
    msg = wf.build_initial_message("re-ingest stale pages")
    assert "re-ingest" in msg


async def test_action_agent_run_gen_yields_sse_for_orchestrate():
    """run_gen() with orchestrate action → yields token and done events."""
    from synthadoc.agents.action_agent import ActionAgent
    from synthadoc.providers.base import CompletionResponse

    provider = AsyncMock()
    # Call 1: _extract → returns orchestrate action
    # Call 2: tool-call loop → returns final text (no tool call)
    provider.complete = AsyncMock(side_effect=[
        CompletionResponse(
            text='{"action": "orchestrate", "params": {"intent": "reingest"}}',
            input_tokens=10, output_tokens=5,
        ),
        CompletionResponse(
            text="There are no stale pages at this time.",
            input_tokens=10, output_tokens=8,
        ),
    ])

    orch = MagicMock()
    orch.queue = AsyncMock()
    orch._store = MagicMock()
    orch._audit = AsyncMock()
    orch._audit.get_live_page_states = AsyncMock(return_value=[])
    orch._confirm_registry = {}
    orch._confirm_result_registry = {}

    agent = ActionAgent(provider, orch, Path("/wiki"))
    events = [e async for e in agent.run_gen("re-ingest stale pages")]

    assert len(events) > 0
    event_types = {e["event"] for e in events}
    assert "done" in event_types or "token" in event_types or "final_text" in event_types


async def test_action_agent_run_gen_returns_none_action_silently():
    """run_gen() when action=none: only the initial tool_progress is emitted, no token/done."""
    from synthadoc.agents.action_agent import ActionAgent
    from synthadoc.providers.base import CompletionResponse

    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=CompletionResponse(
        text='{"action": "none", "params": {}}',
        input_tokens=5, output_tokens=3,
    ))
    orch = MagicMock()
    orch._confirm_registry = {}
    orch._confirm_result_registry = {}
    agent = ActionAgent(provider, orch, Path("/wiki"))
    events = [e async for e in agent.run_gen("hello world")]
    # Only the initial "Analyzing your request..." tool_progress fires before _extract()
    assert all(e["event"] == "tool_progress" for e in events)
    assert not any(e["event"] in ("token", "done") for e in events)


async def test_action_agent_run_gen_non_orchestrate_yields_token_and_done():
    """run_gen() with a non-orchestrate action (lint) yields token, citations, done."""
    from synthadoc.agents.action_agent import ActionAgent, ActionResult
    from synthadoc.providers.base import CompletionResponse
    from unittest.mock import patch

    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=CompletionResponse(
        text='{"action": "lint", "params": {"scope": "all", "auto_resolve": false}}',
        input_tokens=10, output_tokens=5,
    ))
    orch = MagicMock()
    orch._confirm_registry = {}
    orch._confirm_result_registry = {}
    agent = ActionAgent(provider, orch, Path("/wiki"))

    lint_result = ActionResult(
        action_type="lint", success=True,
        message="Lint queued — job ID abc123",
        job_id="abc123",
    )
    with patch.object(agent, "_dispatch", AsyncMock(return_value=lint_result)):
        # "queue a lint check" avoids the _LINT_RUN_RE fast-path while still
        # exercising the _extract → _dispatch SSE flow under test.
        events = [e async for e in agent.run_gen("queue a lint check")]

    event_types = [e["event"] for e in events]
    assert "token" in event_types
    assert "done" in event_types
    assert "citations" in event_types
    done_evt = next(e for e in events if e["event"] == "done")
    assert done_evt["data"]["job_id"] == "abc123"
    assert done_evt["data"]["gap"] is False
