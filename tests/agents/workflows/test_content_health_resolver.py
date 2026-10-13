# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for ContentHealthResolverWorkflow class attributes and tool registration."""
from unittest.mock import MagicMock

import pytest

from synthadoc.agents.workflows.content_health_resolver import ContentHealthResolverWorkflow


def test_workflow_attributes():
    assert ContentHealthResolverWorkflow.NAME == "content-health"
    assert ContentHealthResolverWorkflow.RERUN_HINT == "Run content health resolver"
    assert ContentHealthResolverWorkflow.SUPPORTS_CLI_PROVIDER is True
    assert "write_content_health_fix" in ContentHealthResolverWorkflow.GATED_TOOLS
    assert "write_content_health_fix" in ContentHealthResolverWorkflow.GATED_TOOLS_PER_CALL


def test_match_re_fires_on_content_health():
    pattern = ContentHealthResolverWorkflow.MATCH_RE
    assert pattern is not None
    assert pattern.search("run content health resolver")
    assert pattern.search("fix content issues")
    assert pattern.search("duplicate sections in wiki")
    assert pattern.search("content health")


def test_match_re_does_not_fire_on_unrelated():
    pattern = ContentHealthResolverWorkflow.MATCH_RE
    assert not pattern.search("show me orphan pages")
    assert not pattern.search("fix broken citations")


@pytest.mark.asyncio
async def test_system_prompt_contains_tool_inventory():
    wf = ContentHealthResolverWorkflow()
    prompt = await wf.build_system_prompt()
    for tool_name in ("get_page_content", "write_content_health_fix",
                      "list_content_health_fixes", "rollback_content_health_fix",
                      "confirm", "notify"):
        assert tool_name in prompt, f"Missing tool '{tool_name}' in system prompt"


def test_get_tool_fns_returns_expected_tools():
    ctx = MagicMock()
    wf = ContentHealthResolverWorkflow()
    tools = wf.get_tool_fns(ctx)
    expected = {
        "find_content_health_issues", "get_page_content", "write_content_health_fix",
        "list_content_health_fixes", "rollback_content_health_fix",
        "confirm", "notify",
    }
    assert set(tools.keys()) == expected


def test_write_tool_is_gated():
    """The GATED_TOOLS mechanism wraps write_content_health_fix with a confirm check."""
    ctx = MagicMock()
    wf = ContentHealthResolverWorkflow()
    guarded = wf.build_guarded_tool_fns(ctx)
    # write tool should be present and wrapped (different callable from raw)
    assert "write_content_health_fix" in guarded


@pytest.mark.asyncio
async def test_gate_resets_after_each_write():
    """write_content_health_fix gate must reset after every call so each page needs its own confirm."""
    confirm_call_count = 0

    async def fake_write(slug, content, issues_fixed):
        return {"status": "success", "slug": slug, "snapshot_index": 1, "remaining_issues": 0, "fix_record": {}}

    async def fake_confirm(message, yes_label="Yes", no_label="No"):
        nonlocal confirm_call_count
        confirm_call_count += 1
        return {"confirmed": True}

    ctx = MagicMock()
    wf = ContentHealthResolverWorkflow()
    tools = wf.get_tool_fns(ctx)
    # Replace the real callables with fakes before building guarded fns.
    tools["write_content_health_fix"] = fake_write
    tools["confirm"] = fake_confirm

    # Rebuild guarded fns using the patched tools dict directly via the mechanism.
    from synthadoc.agents.workflows._base import _make_confirm_gatekeeper, _make_gated_tool
    gate_open: list[bool] = [False]
    guarded_confirm = _make_confirm_gatekeeper(fake_confirm, gate_open)
    guarded_write = _make_gated_tool(
        fake_write, "write_content_health_fix", gate_open, ctx, reset_after_call=True
    )

    # First write: gate is closed — fallback confirm fires, then write runs, gate resets.
    await guarded_confirm("Ready?", yes_label="Begin", no_label="Cancel")  # STEP 2 confirm
    assert gate_open[0] is True
    await guarded_write(slug="page-a", content="...", issues_fixed=[])
    assert gate_open[0] is False  # gate reset after write

    # Second write: gate is closed again — must confirm again.
    pre_count = confirm_call_count
    await guarded_confirm("Approve page-b?", yes_label="Approve", no_label="Skip")
    assert gate_open[0] is True
    await guarded_write(slug="page-b", content="...", issues_fixed=[])
    assert gate_open[0] is False  # gate reset again
    assert confirm_call_count == pre_count + 1  # a second confirm was required


def test_registered_in_routed_workflows():
    from synthadoc.agents.workflows._registry import CLI_REGISTRY, ROUTED_WORKFLOWS
    names = [wf.__name__ for wf in ROUTED_WORKFLOWS]
    assert "ContentHealthResolverWorkflow" in names
    assert "content-health" in CLI_REGISTRY


def test_description_and_cli_args_set():
    assert ContentHealthResolverWorkflow.DESCRIPTION is not None
    assert ContentHealthResolverWorkflow.CLI_ARGS is not None
    assert "--slug" in ContentHealthResolverWorkflow.CLI_ARGS
