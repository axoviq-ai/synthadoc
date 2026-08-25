# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for the workflow registry and MATCH_RE class attribute convention."""
from __future__ import annotations

import re


def test_routed_workflows_is_nonempty_list_of_agentic_workflow_subclasses():
    from synthadoc.agents.workflows._base import AgenticWorkflow
    from synthadoc.agents.workflows._registry import ROUTED_WORKFLOWS

    assert isinstance(ROUTED_WORKFLOWS, list)
    assert len(ROUTED_WORKFLOWS) > 0
    for wf_cls in ROUTED_WORKFLOWS:
        assert issubclass(wf_cls, AgenticWorkflow), f"{wf_cls} is not an AgenticWorkflow"


def test_every_routed_workflow_has_compiled_match_re():
    from synthadoc.agents.workflows._registry import ROUTED_WORKFLOWS

    for wf_cls in ROUTED_WORKFLOWS:
        assert wf_cls.MATCH_RE is not None, f"{wf_cls.__name__} must define MATCH_RE"
        assert isinstance(wf_cls.MATCH_RE, re.Pattern), (
            f"{wf_cls.__name__}.MATCH_RE must be a compiled re.Pattern"
        )


def test_base_class_match_re_default_is_none():
    from synthadoc.agents.workflows._base import AgenticWorkflow

    assert AgenticWorkflow.MATCH_RE is None


def test_lint_report_workflow_match_re_hits_action_phrases():
    from synthadoc.agents.workflows.lint_report import LintReportWorkflow

    match = LintReportWorkflow.MATCH_RE
    assert match.search("run lint and show me the report")
    assert match.search("run lint")
    assert match.search("please run a full lint")


def test_lint_report_workflow_match_re_misses_query_phrases():
    from synthadoc.agents.workflows.lint_report import LintReportWorkflow

    match = LintReportWorkflow.MATCH_RE
    assert not match.search("show me my lint report")   # query, not action
    assert not match.search("what is my lint result?")
    assert not match.search("what does lint mean?")


def test_broken_wikilinks_workflow_match_re_hits_action_phrases():
    from synthadoc.agents.workflows.broken_wikilinks import BrokenWikilinksWorkflow

    match = BrokenWikilinksWorkflow.MATCH_RE
    assert match.search("scan for broken wikilinks")
    assert match.search("fix broken links")
    assert match.search("check wikilink integrity")
    assert match.search("find dangling wikilinks")
    assert match.search("dead wikilinks")


def test_broken_wikilinks_workflow_match_re_misses_unrelated_phrases():
    from synthadoc.agents.workflows.broken_wikilinks import BrokenWikilinksWorkflow

    match = BrokenWikilinksWorkflow.MATCH_RE
    assert not match.search("what are wikilinks?")
    assert not match.search("how do I use links?")


def test_registry_loop_routes_lint_question_to_lint_report_workflow():
    from synthadoc.agents.workflows._registry import ROUTED_WORKFLOWS
    from synthadoc.agents.workflows.lint_report import LintReportWorkflow

    question = "run lint and show me the lint report"
    matched = next(
        (wf for wf in ROUTED_WORKFLOWS if wf.MATCH_RE and wf.MATCH_RE.search(question)),
        None,
    )
    assert matched is LintReportWorkflow


def test_registry_loop_routes_wikilinks_question_to_broken_wikilinks_workflow():
    from synthadoc.agents.workflows._registry import ROUTED_WORKFLOWS
    from synthadoc.agents.workflows.broken_wikilinks import BrokenWikilinksWorkflow

    question = "scan for broken wikilinks"
    matched = next(
        (wf for wf in ROUTED_WORKFLOWS if wf.MATCH_RE and wf.MATCH_RE.search(question)),
        None,
    )
    assert matched is BrokenWikilinksWorkflow


def test_scaffold_workflow_match_re_hits_action_phrases():
    from synthadoc.agents.workflows.scaffold import ScaffoldWorkflow

    match = ScaffoldWorkflow.MATCH_RE
    assert match.search("run scaffold")
    assert match.search("please run scaffold now")
    assert match.search("rebuild scaffold")
    assert match.search("regenerate the scaffold")
    assert match.search("regenerate scaffold for my wiki")


def test_scaffold_workflow_match_re_misses_query_phrases():
    from synthadoc.agents.workflows.scaffold import ScaffoldWorkflow

    match = ScaffoldWorkflow.MATCH_RE
    assert not match.search("what is scaffold?")
    assert not match.search("how does scaffold work?")
    assert not match.search("show me the scaffold files")


def test_registry_loop_routes_scaffold_question_to_scaffold_workflow():
    from synthadoc.agents.workflows._registry import ROUTED_WORKFLOWS
    from synthadoc.agents.workflows.scaffold import ScaffoldWorkflow

    question = "run scaffold"
    matched = next(
        (wf for wf in ROUTED_WORKFLOWS if wf.MATCH_RE and wf.MATCH_RE.search(question)),
        None,
    )
    assert matched is ScaffoldWorkflow


def test_registry_loop_returns_none_for_unrouted_question():
    from synthadoc.agents.workflows._registry import ROUTED_WORKFLOWS

    question = "what does the alan-turing page say about the ACE?"
    matched = next(
        (wf for wf in ROUTED_WORKFLOWS if wf.MATCH_RE and wf.MATCH_RE.search(question)),
        None,
    )
    assert matched is None


# ---------------------------------------------------------------------------
# LintReportWorkflow method coverage (lines 100, 103, 106)
# ---------------------------------------------------------------------------

from pathlib import Path as _Path


def _make_wf_ctx():
    async def _send(e, d):
        pass
    from synthadoc.agents.workflows._base import WorkflowContext
    return WorkflowContext(
        session_id="wf-test",
        wiki_root=_Path("/tmp/wiki"),
        queue=None, store=None, audit_db=None,
        send_sse_event=_send,
        confirm_registry={}, confirm_result_registry={},
    )


async def test_lint_report_workflow_build_system_prompt_returns_string():
    from synthadoc.agents.workflows.lint_report import LintReportWorkflow
    wf = LintReportWorkflow()
    prompt = await wf.build_system_prompt()
    assert isinstance(prompt, str)
    assert len(prompt) > 50


def test_lint_report_workflow_build_initial_message_echoes_input():
    from synthadoc.agents.workflows.lint_report import LintReportWorkflow
    wf = LintReportWorkflow()
    assert wf.build_initial_message("run lint") == "run lint"
    assert wf.build_initial_message("some other phrase") == "some other phrase"


def test_lint_report_workflow_get_tool_fns_returns_expected_keys():
    from synthadoc.agents.workflows.lint_report import LintReportWorkflow
    wf = LintReportWorkflow()
    ctx = _make_wf_ctx()
    fns = wf.get_tool_fns(ctx)
    assert set(fns.keys()) == {"run_lint", "get_lint_report"}
    assert all(callable(f) for f in fns.values())


# ---------------------------------------------------------------------------
# ScaffoldWorkflow method coverage (lines 103, 106, 109)
# ---------------------------------------------------------------------------

async def test_scaffold_workflow_build_system_prompt_returns_string():
    from synthadoc.agents.workflows.scaffold import ScaffoldWorkflow
    wf = ScaffoldWorkflow()
    prompt = await wf.build_system_prompt()
    assert isinstance(prompt, str)
    assert len(prompt) > 50


def test_scaffold_workflow_build_initial_message_echoes_input():
    from synthadoc.agents.workflows.scaffold import ScaffoldWorkflow
    wf = ScaffoldWorkflow()
    assert wf.build_initial_message("run scaffold") == "run scaffold"


def test_scaffold_workflow_get_tool_fns_returns_expected_keys():
    from synthadoc.agents.workflows.scaffold import ScaffoldWorkflow
    wf = ScaffoldWorkflow()
    ctx = _make_wf_ctx()
    fns = wf.get_tool_fns(ctx)
    # "confirm" is no longer a separate LLM tool — it is embedded inside
    # tool_run_scaffold (Pattern A), so the registry no longer exposes it.
    assert set(fns.keys()) == {"get_scaffold_preview", "run_scaffold"}
    assert all(callable(f) for f in fns.values())


# ---------------------------------------------------------------------------
# build_guarded_tool_fns — framework-level confirm gate (AgenticWorkflow base)
# ---------------------------------------------------------------------------

def _make_wf_ctx_for_gate():
    """Create a minimal WorkflowContext for gate tests."""
    import asyncio
    from pathlib import Path
    from synthadoc.agents.workflows._base import WorkflowContext
    events = []
    async def _send(e, d):
        events.append({"event": e, "data": d})
    ctx = WorkflowContext(
        session_id="gate-test",
        wiki_root=Path("/wiki"),
        queue=None,
        store=None,
        audit_db=None,
        send_sse_event=_send,
        confirm_registry={},
        confirm_result_registry={},
    )
    return ctx, events


def test_build_guarded_tool_fns_passthrough_when_no_gated_tools():
    """When GATED_TOOLS is empty, build_guarded_tool_fns returns get_tool_fns unchanged."""
    import functools
    from synthadoc.agents.workflows.scaffold import ScaffoldWorkflow
    wf = ScaffoldWorkflow()
    ctx, _ = _make_wf_ctx_for_gate()
    assert wf.GATED_TOOLS == frozenset()
    raw = wf.get_tool_fns(ctx)
    guarded = wf.build_guarded_tool_fns(ctx)
    assert set(raw.keys()) == set(guarded.keys())
    # All tools are still functools.partial (not wrapped)
    for name, fn in guarded.items():
        assert isinstance(fn, functools.partial), f"{name} should be unchanged partial"


# Helper: a minimal workflow that takes callables directly (no functools.partial)
# so tests can inject mocks without fighting partial's captured function reference.

class _GateTestWorkflow:
    """Minimal AgenticWorkflow stand-in for testing build_guarded_tool_fns."""

    GATED_TOOLS: frozenset[str] = frozenset({"risky_tool"})

    def __init__(self, risky_fn, confirm_fn):
        self._risky = risky_fn
        self._confirm = confirm_fn

    def get_tool_fns(self, ctx):
        return {"risky_tool": self._risky, "confirm": self._confirm}

    def build_guarded_tool_fns(self, ctx):
        # Delegate to the real framework method via the base class.
        from synthadoc.agents.workflows._base import (
            _make_confirm_gatekeeper,
            _make_gated_tool,
        )
        fns = self.get_tool_fns(ctx)
        gate_open: list[bool] = [False]
        result = {}
        for name, fn in fns.items():
            if name == "confirm":
                result[name] = _make_confirm_gatekeeper(fn, gate_open)
            elif name in self.GATED_TOOLS:
                result[name] = _make_gated_tool(fn, name, gate_open, ctx)
            else:
                result[name] = fn
        return result


async def test_build_guarded_tool_fns_gate_opens_on_confirm():
    """confirm() returning confirmed=True allows the gated tool to run on next call."""
    from unittest.mock import AsyncMock

    risky_fn  = AsyncMock(return_value={"status": "done"})
    confirm_fn = AsyncMock(return_value={"confirmed": True})

    ctx, _ = _make_wf_ctx_for_gate()
    fns = _GateTestWorkflow(risky_fn, confirm_fn).build_guarded_tool_fns(ctx)

    # Call confirm first — gate should open.
    result = await fns["confirm"]("Review changes?", "Yes", "No")
    assert result["confirmed"] is True
    confirm_fn.assert_awaited_once()

    # Now risky_tool should run directly — no fallback confirm.
    confirm_fn.reset_mock()
    result = await fns["risky_tool"]()

    assert result["status"] == "done"
    risky_fn.assert_awaited_once()
    confirm_fn.assert_not_awaited()  # no second confirm dialog


async def test_build_guarded_tool_fns_fallback_confirm_fires_when_gate_bypassed():
    """If the LLM skips confirm and calls a gated tool directly, a fallback dialog fires."""
    from unittest.mock import AsyncMock, patch

    risky_fn  = AsyncMock(return_value={"status": "done"})
    confirm_fn = AsyncMock()  # registered confirm — should NOT be called by the fallback

    ctx, _ = _make_wf_ctx_for_gate()
    fns = _GateTestWorkflow(risky_fn, confirm_fn).build_guarded_tool_fns(ctx)

    # LLM calls risky_tool directly without calling confirm.
    # The fallback fires via a deferred import of tool_confirm inside _make_gated_tool.
    # Patching the module attribute at call time reaches the deferred import.
    with patch("synthadoc.agents.workflows._tools.tool_confirm",
               new_callable=AsyncMock, return_value={"confirmed": True}) as mock_fallback:
        result = await fns["risky_tool"]()

    mock_fallback.assert_awaited_once()  # fallback confirm fired
    risky_fn.assert_awaited_once()       # underlying tool ran after approval
    confirm_fn.assert_not_awaited()      # the registered confirm was not called
    assert result["status"] == "done"


async def test_build_guarded_tool_fns_cancels_when_fallback_declined():
    """If the fallback confirm is declined, the gated tool returns cancelled status."""
    from unittest.mock import AsyncMock, patch

    risky_fn  = AsyncMock(return_value={"status": "done"})
    confirm_fn = AsyncMock()

    ctx, _ = _make_wf_ctx_for_gate()
    fns = _GateTestWorkflow(risky_fn, confirm_fn).build_guarded_tool_fns(ctx)

    with patch("synthadoc.agents.workflows._tools.tool_confirm",
               new_callable=AsyncMock, return_value={"confirmed": False}):
        result = await fns["risky_tool"]()

    assert result["status"] == "cancelled"
    risky_fn.assert_not_awaited()  # gated tool never ran
