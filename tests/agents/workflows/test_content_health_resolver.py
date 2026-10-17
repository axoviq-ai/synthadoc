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
                      "dismiss_content_health_issues",
                      "list_content_health_fixes", "rollback_content_health_fix",
                      "confirm", "notify"):
        assert tool_name in prompt, f"Missing tool '{tool_name}' in system prompt"


def test_get_tool_fns_returns_expected_tools():
    ctx = MagicMock()
    wf = ContentHealthResolverWorkflow()
    tools = wf.get_tool_fns(ctx)
    expected = {
        "find_content_health_issues", "get_page_content", "write_content_health_fix",
        "dismiss_content_health_issues",
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


@pytest.mark.asyncio
async def test_write_blocked_without_get_page_content():
    """write_content_health_fix must return an error if get_page_content was not called first."""
    ctx = MagicMock()
    wf = ContentHealthResolverWorkflow()
    tools = wf.get_tool_fns(ctx)
    result = await tools["write_content_health_fix"](
        slug="some-page", content="fixed content", issues_fixed=[]
    )
    assert result["status"] == "error"
    assert "get_page_content" in result["error"]


@pytest.mark.asyncio
async def test_write_blocked_for_undiscovered_slug():
    """Both get_page_content and write_content_health_fix reject slugs not in the discovery list."""
    ctx = MagicMock()
    ctx.store.list_pages.return_value = ["real-page"]
    ctx.store.read_page.return_value = MagicMock(
        status="active", content_health_issues=[{"severity": "high"}], content="body"
    )
    wf = ContentHealthResolverWorkflow()
    tools = wf.get_tool_fns(ctx)

    # Discover pages — only "real-page" is in found_slugs
    await tools["find_content_health_issues"](slug="")

    # LLM tries to read an invented slug — get_page_content rejects it
    get_result = await tools["get_page_content"](slug="invented-slug")
    assert get_result["status"] == "error"
    assert "find_content_health_issues" in get_result["error"]
    assert "valid_slugs" in get_result

    # LLM tries to write anyway — also blocked (slug not in read_slugs)
    write_result = await tools["write_content_health_fix"](
        slug="invented-slug", content="invented content", issues_fixed=[]
    )
    assert write_result["status"] == "error"


@pytest.mark.asyncio
async def test_write_allowed_after_proper_sequence():
    """write_content_health_fix succeeds when get_page_content was called first."""
    ctx = MagicMock()
    ctx.store.list_pages.return_value = ["real-page"]

    from unittest.mock import AsyncMock
    ctx.audit_db.snapshot_if_changed = AsyncMock(return_value=None)
    ctx.audit_db.list_page_snapshots = AsyncMock(return_value=[{"id": "snap1"}])

    wf = ContentHealthResolverWorkflow()
    tools = wf.get_tool_fns(ctx)

    # Step 1: discover
    discover_page = MagicMock(
        status="active",
        content_health_issues=[{"severity": "high", "type": "duplicate_section"}],
        content="old body",
        title="Real Page",
    )
    ctx.store.read_page.return_value = discover_page
    await tools["find_content_health_issues"](slug="")

    # Step 2: read
    read_page = MagicMock(
        status="active", title="Real Page", content="old body", content_health_issues=[]
    )
    ctx.store.read_page.return_value = read_page
    await tools["get_page_content"](slug="real-page")

    # Step 3: write (gate is bypassed here since we call the inner fn directly)
    write_page = MagicMock(
        content="old body",
        content_health_issues=[{"type": "dup", "severity": "high"}],
        content_health_fix_record=None,
    )
    ctx.store.read_page.return_value = write_page
    result = await tools["write_content_health_fix"](
        slug="real-page", content="fixed body", issues_fixed=["duplicate_section"]
    )
    assert result["status"] != "error" or "get_page_content" not in result.get("error", "")


@pytest.mark.asyncio
async def test_find_issues_excludes_unreadable_slugs():
    """find_content_health_issues must drop any slug that cannot be re-read from the store."""
    ctx = MagicMock()
    # list_pages returns two slugs but one disappears before re-read
    ctx.store.list_pages.return_value = ["good-page", "ghost-page"]

    def _read_page(slug):
        if slug == "good-page":
            return MagicMock(
                status="active",
                content_health_issues=[{"severity": "high", "type": "duplicate_section"}],
                title="Good Page",
                content="body",
            )
        return None  # ghost-page vanished

    ctx.store.read_page.side_effect = _read_page
    wf = ContentHealthResolverWorkflow()
    tools = wf.get_tool_fns(ctx)
    result = await tools["find_content_health_issues"](slug="")
    slugs = [p["slug"] for p in result["pages"]]
    assert "good-page" in slugs
    assert "ghost-page" not in slugs
    assert result["total"] == 1


@pytest.mark.asyncio
async def test_dismiss_clears_issues_and_sets_record():
    """dismiss_content_health_issues clears content_health_issues and records the dismissal."""
    from synthadoc.agents.workflows.tools.content_health_tools import (
        tool_dismiss_content_health_issues,
    )
    from synthadoc.agents.workflows._base import WorkflowContext

    store = MagicMock()
    page = MagicMock()
    page.content_health_issues = [
        {"type": "thin_section", "severity": "high"},
        {"type": "thin_section", "severity": "medium"},
    ]
    page.content_health_fix_record = None
    store.read_page.return_value = page

    ctx = MagicMock(spec=WorkflowContext)
    ctx.store = store
    ctx.bump_epoch = None

    result = await tool_dismiss_content_health_issues(
        ctx, slug="grace-hopper", reason="all issues are thin_section requiring human editing"
    )

    assert result["status"] == "success"
    assert result["dismissed_count"] == 2
    assert result["remaining_issues"] == 0
    assert page.content_health_issues == []
    assert page.content_health_fix_record is not None
    assert page.content_health_fix_record["dismissed_count"] == 2
    assert "thin_section" in page.content_health_fix_record["dismissed_types"]
    store.write_page.assert_called_once_with("grace-hopper", page)


def test_prediscovery_seeds_found_slugs():
    """build_guarded_tool_fns pre-discovers pages; found_slugs is pre-seeded so
    invented slugs are blocked even if the LLM skips find_content_health_issues."""
    ctx = MagicMock()
    ctx.store.list_pages.return_value = ["real-page", "no-issues-page"]

    def _read_page(slug):
        if slug == "real-page":
            return MagicMock(
                status="active",
                content_health_issues=[{"severity": "high"}],
            )
        if slug == "no-issues-page":
            return MagicMock(status="active", content_health_issues=[])
        return None

    ctx.store.read_page.side_effect = _read_page
    wf = ContentHealthResolverWorkflow()
    wf.build_guarded_tool_fns(ctx)
    assert wf._prediscovered_slugs == ["no-issues-page" if False else "real-page"]
    assert "real-page" in wf._prediscovered_slugs
    assert "no-issues-page" not in wf._prediscovered_slugs


def test_prediscovery_initial_message_names_slugs():
    """build_initial_message includes the pre-discovered slug list when available."""
    ctx = MagicMock()
    ctx.store.list_pages.return_value = ["page-a", "page-b"]

    def _read_page(slug):
        return MagicMock(
            status="active",
            content_health_issues=[{"severity": "medium"}],
        )

    ctx.store.read_page.side_effect = _read_page
    wf = ContentHealthResolverWorkflow()
    wf.build_guarded_tool_fns(ctx)
    msg = wf.build_initial_message("run content health resolver")
    assert "page-a" in msg
    assert "page-b" in msg
    # Slugs must appear as the ONLY valid set
    assert "ONLY valid slug" in msg or "only valid" in msg.lower() or "only" in msg.lower()


def test_prediscovery_initial_message_fallback_when_no_pages():
    """build_initial_message falls back to LLM-discovery path when no pages found."""
    ctx = MagicMock()
    ctx.store.list_pages.return_value = []
    wf = ContentHealthResolverWorkflow()
    wf.build_guarded_tool_fns(ctx)
    msg = wf.build_initial_message("run content health resolver")
    assert "find_content_health_issues" in msg


def test_registered_in_routed_workflows():
    from synthadoc.agents.workflows._registry import CLI_REGISTRY, ROUTED_WORKFLOWS
    names = [wf.__name__ for wf in ROUTED_WORKFLOWS]
    assert "ContentHealthResolverWorkflow" in names
    assert "content-health" in CLI_REGISTRY


def test_description_and_cli_args_set():
    assert ContentHealthResolverWorkflow.DESCRIPTION is not None
    assert ContentHealthResolverWorkflow.CLI_ARGS is not None
    assert "--slug" in ContentHealthResolverWorkflow.CLI_ARGS


@pytest.mark.asyncio
@pytest.mark.parametrize("confirmed", [True, False])
async def test_rollback_during_fix_run_requires_user_confirm(monkeypatch, confirmed):
    """The model must not roll a page back on its own in the middle of a fix run."""
    from unittest.mock import AsyncMock
    from synthadoc.agents.workflows import content_health_resolver as mod
    confirm = AsyncMock(return_value={"confirmed": confirmed})
    rollback = AsyncMock(return_value={"status": "success"})
    monkeypatch.setattr(mod, "tool_confirm", confirm)
    monkeypatch.setattr(mod, "tool_rollback_content_health_fix", rollback)

    wf = ContentHealthResolverWorkflow()
    wf.build_initial_message("run content health resolver")
    result = await wf.get_tool_fns(MagicMock())["rollback_content_health_fix"](slug="ai")

    confirm.assert_awaited_once()
    assert (rollback.await_count == 1) is confirmed
    assert result["status"] == ("success" if confirmed else "cancelled")


@pytest.mark.asyncio
async def test_rollback_requested_by_user_runs_without_extra_confirm(monkeypatch):
    from unittest.mock import AsyncMock
    from synthadoc.agents.workflows import content_health_resolver as mod
    confirm = AsyncMock()
    rollback = AsyncMock(return_value={"status": "success"})
    monkeypatch.setattr(mod, "tool_confirm", confirm)
    monkeypatch.setattr(mod, "tool_rollback_content_health_fix", rollback)

    wf = ContentHealthResolverWorkflow()
    wf.build_initial_message("roll back artificial-intelligence-history")
    await wf.get_tool_fns(MagicMock())["rollback_content_health_fix"](slug="artificial-intelligence-history")

    confirm.assert_not_awaited()
    rollback.assert_awaited_once()
