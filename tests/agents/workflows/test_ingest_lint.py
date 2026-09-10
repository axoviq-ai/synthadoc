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
        "ingest_source", "run_lint", "get_page_states", "confirm",
    }
    for name, fn in fns.items():
        assert callable(fn), f"{name} not callable"


def test_ingest_lint_tool_fns_are_partial_bound():
    """Each fn is a functools.partial bound to ctx — calling fn() won't need ctx."""
    import functools
    wf = IngestLintWorkflow()
    ctx, _ = _make_ctx()
    fns = wf.get_tool_fns(ctx)
    for name, fn in fns.items():
        assert isinstance(fn, functools.partial), f"{name} should be a functools.partial"
        assert fn.args[0] is ctx, f"{name} partial not bound to ctx"


def test_ingest_lint_build_initial_message_returns_user_input():
    wf = IngestLintWorkflow()
    msg = wf.build_initial_message("re-ingest stale pages")
    assert "re-ingest" in msg


# ---------------------------------------------------------------------------
# system prompt — markdown format rules
# ---------------------------------------------------------------------------

async def test_system_prompt_no_bullet_character():
    """System prompt must not instruct the LLM to use Unicode bullet characters."""
    wf = IngestLintWorkflow()
    prompt = await wf.build_system_prompt()
    assert "•" not in prompt, (
        "System prompt must not use • bullet characters — use markdown '- ' list syntax "
        "so each item renders on its own line in ReactMarkdown"
    )


async def test_system_prompt_workflow_a_step6_markdown_list():
    """Workflow A step 6 must show a markdown list template with '- ' items."""
    wf = IngestLintWorkflow()
    prompt = await wf.build_system_prompt()
    # Step 6 template must contain a markdown list item with icon
    assert "- ✓" in prompt or "- ○" in prompt or "- ✗" in prompt, (
        "Workflow A step 6 must demonstrate '- icon slug:' markdown list items "
        "so the LLM mirrors that format in its output"
    )


# ---------------------------------------------------------------------------
# CLI path confirm message — markdown format
# ---------------------------------------------------------------------------

async def test_cli_confirm_message_uses_markdown_list(monkeypatch):
    """run_for_cli_provider builds confirm message with markdown list items.

    Each stale page must appear as '- **slug**: source' so ReactMarkdown
    renders each entry on its own line instead of collapsing them.
    """
    wf = IngestLintWorkflow()
    ctx, _ = _make_ctx()

    scan_result = {
        "pages": [
            {"slug": "alan-turing",    "source_path": "raw_sources/alan-turing.md",  "stale_since": "2026-01-01"},
            {"slug": "grace-hopper",   "source_path": "raw_sources/grace-hopper.md", "stale_since": ""},
            {"slug": "orphan-no-src",  "source_path": None,                          "stale_since": ""},
        ],
    }

    captured: list[str] = []

    async def _fake_find_stale(_ctx):
        return scan_result

    async def _fake_confirm(_ctx, message: str, yes_label: str = "", no_label: str = ""):
        captured.append(message)
        return {"confirmed": False}  # decline — no further mocks needed

    monkeypatch.setattr("synthadoc.agents.workflows.ingest_lint.tool_find_stale_pages", _fake_find_stale)
    monkeypatch.setattr("synthadoc.agents.workflows.ingest_lint.tool_confirm", _fake_confirm)

    _events = [e async for e in wf.run_for_cli_provider(ctx, "re-ingest stale pages", provider=None)]

    assert captured, "tool_confirm was never called"
    msg = captured[0]

    # Each page must appear as a markdown list item
    assert "- **alan-turing**:" in msg, "alan-turing must be a '- **slug**:' markdown list item"
    assert "- **grace-hopper**:" in msg, "grace-hopper must be a '- **slug**:' markdown list item"
    assert "- **orphan-no-src**:" in msg, "orphan-no-src must be a '- **slug**:' markdown list item"
    # Must NOT use bullet character
    assert "•" not in msg, "Confirm message must not use • bullet characters"
    # Blank line must separate header from list (prevents header + first item collapsing)
    assert "\n\n" in msg, "Confirm message must contain a blank line (\\n\\n) before the list"


# ---------------------------------------------------------------------------
# CLI path summary — markdown list items for page states
# ---------------------------------------------------------------------------

async def test_cli_summary_page_states_use_markdown_list(monkeypatch):
    """run_for_cli_provider summary uses '- icon slug:' list items for page states.

    Plain '  icon slug:' lines without the '- ' prefix collapse into a single
    paragraph in ReactMarkdown; list items render on separate lines.
    """
    wf = IngestLintWorkflow()
    ctx, _ = _make_ctx()

    async def _fake_find_stale(_ctx):
        return {"pages": [{"slug": "alan-turing", "source_path": "raw_sources/alan-turing.md", "stale_since": ""}]}

    async def _fake_confirm(_ctx, message, yes_label="", no_label=""):
        return {"confirmed": True}

    async def _fake_ingest(_ctx, source_path):
        return {"status": "success", "message": "ingested"}

    async def _fake_lint(_ctx):
        return {"status": "success", "message": ""}

    async def _fake_states(_ctx, slugs):
        return {"pages": [{"slug": s, "state": "active"} for s in slugs]}

    monkeypatch.setattr("synthadoc.agents.workflows.ingest_lint.tool_find_stale_pages", _fake_find_stale)
    monkeypatch.setattr("synthadoc.agents.workflows.ingest_lint.tool_confirm", _fake_confirm)
    monkeypatch.setattr("synthadoc.agents.workflows.ingest_lint.tool_ingest_source", _fake_ingest)
    monkeypatch.setattr("synthadoc.agents.workflows.ingest_lint.tool_run_lint", _fake_lint)
    monkeypatch.setattr("synthadoc.agents.workflows.ingest_lint.tool_get_page_states", _fake_states)

    events = [e async for e in wf.run_for_cli_provider(ctx, "re-ingest stale pages", provider=None)]

    final = next((e["data"]["text"] for e in events if e["event"] == "final_text"), None)
    assert final is not None, "No final_text event emitted"

    # Each page state must be a markdown list item
    assert "- ✓ alan-turing:" in final, (
        "Page state line must start with '- ' to render as a markdown list item; "
        f"got: {final!r}"
    )
    # Must NOT use plain indented icon without dash
    assert "  ✓ alan-turing:" not in final, (
        "Plain '  ✓ slug:' (no '- ' prefix) collapses in ReactMarkdown"
    )


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
