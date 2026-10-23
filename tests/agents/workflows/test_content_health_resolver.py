# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for ContentHealthResolverWorkflow class attributes and tool registration."""
import asyncio
from unittest.mock import MagicMock

import pytest

from synthadoc.agents.workflows.content_health_resolver import ContentHealthResolverWorkflow


def test_workflow_attributes():
    assert ContentHealthResolverWorkflow.NAME == "content-health"
    assert ContentHealthResolverWorkflow.RERUN_HINT == "Run content health resolver"
    assert ContentHealthResolverWorkflow.SUPPORTS_CLI_PROVIDER is True
    # Writes are approved inside the tools from the real diff, not via a model-called gate.
    assert ContentHealthResolverWorkflow.GATED_TOOLS == frozenset()


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
                      "merge_duplicate_sections", "notify"):
        assert tool_name in prompt, f"Missing tool '{tool_name}' in system prompt"


@pytest.mark.asyncio
async def test_step4_rollback_hint_is_conditioned_on_actually_fixing_something():
    """STEP 4's closing 'list/roll back' lines must be conditional on Fixed > 0.

    When every page was dismissed (needs human editing) or skipped, no
    snapshot exists for this run — telling the user to "review all changes"
    or "roll back <slug>" is misleading when nothing was written.
    """
    wf = ContentHealthResolverWorkflow()
    prompt = await wf.build_system_prompt()
    assert "If Fixed (N pages) > 0, append" in prompt, (
        "STEP 4's rollback/list-fixes closing lines must be gated on Fixed > 0, "
        "not shown unconditionally in the final-summary template"
    )


@pytest.mark.asyncio
async def test_rollback_instruction_does_not_presuppose_content_health_fix():
    """rollback_content_health_fix falls back to a page's generic last_fix_record
    (from contradiction_resolver / orphan_resolver) when it has no
    content-health-specific record. The model must report using the tool's
    own wording, not assume/say "content health fix" for every rollback.
    """
    from synthadoc.agents.workflows.content_health_resolver import ContentHealthResolverWorkflow as WF
    wf = WF()
    msg = wf.build_initial_message("roll back some-page")
    assert "tool's own wording" in msg or "TOOL'S OWN wording" in msg
    assert "may NOT be a content-health fix" in msg


def test_get_tool_fns_returns_expected_tools():
    ctx = MagicMock()
    wf = ContentHealthResolverWorkflow()
    tools = wf.get_tool_fns(ctx)
    expected = {
        "find_content_health_issues", "get_page_content", "write_content_health_fix",
        "merge_duplicate_sections", "dismiss_content_health_issues",
        "list_content_health_fixes", "rollback_content_health_fix",
        "notify",
    }
    assert set(tools.keys()) == expected   # no model-written "confirm" card


def _wiki_with_stray_h1(tmp_path, slugs):
    from synthadoc.storage.wiki import LifecycleState, WikiPage, WikiStorage
    store = WikiStorage(tmp_path / "wiki")
    issue = {"type": "orphaned_heading", "severity": "medium", "location": "line 5", "description": "x"}
    for slug in slugs:
        store.write_page(slug, WikiPage(
            title=slug, tags=[], content="# T\n\nThe page body has one sentence.\n\n# Stray\n",
            status=LifecycleState.ACTIVE, confidence="", sources=[], content_health_issues=[issue]))
    ctx = MagicMock()
    ctx.store = store
    from unittest.mock import AsyncMock
    ctx.audit_db.snapshot_if_changed = AsyncMock(return_value=True)
    ctx.audit_db.list_page_snapshots = AsyncMock(return_value=[{"index": 1, "id": 7}])
    return ctx


@pytest.mark.asyncio
async def test_every_write_asks_the_user_with_the_real_diff(tmp_path, monkeypatch):
    """Each page's write shows a diff computed from the actual content, then writes."""
    from unittest.mock import AsyncMock
    from synthadoc.agents.workflows.tools import content_health_tools as tools_mod
    confirm = AsyncMock(return_value={"confirmed": True})
    monkeypatch.setattr(tools_mod, "tool_confirm", confirm)
    ctx = _wiki_with_stray_h1(tmp_path, ["page-a", "page-b"])

    wf = ContentHealthResolverWorkflow()
    wf._prediscovered_slugs = ["page-a", "page-b"]
    tools = wf.build_guarded_tool_fns(ctx)
    for slug in ("page-a", "page-b"):
        await tools["get_page_content"](slug=slug)
        fixed = "# T\n\nThe page body has one sentence.\n\n## Stray\n"
        result = await tools["write_content_health_fix"](
            slug=slug, content=fixed, issues_fixed=["orphaned_heading x1"])
        assert result["status"] == "success"

    assert confirm.await_count == 2
    diff = confirm.call_args.kwargs["diff"]
    assert "-# Stray" in diff and "+## Stray" in diff


@pytest.mark.asyncio
async def test_write_that_loses_text_is_rejected_before_asking(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock
    from synthadoc.agents.workflows.tools import content_health_tools as tools_mod
    confirm = AsyncMock(return_value={"confirmed": True})
    monkeypatch.setattr(tools_mod, "tool_confirm", confirm)
    ctx = _wiki_with_stray_h1(tmp_path, ["page-a"])

    wf = ContentHealthResolverWorkflow()
    wf._prediscovered_slugs = ["page-a"]
    tools = wf.build_guarded_tool_fns(ctx)
    await tools["get_page_content"](slug="page-a")
    result = await tools["write_content_health_fix"](
        slug="page-a", content="# T\n\n## Stray\n", issues_fixed=["orphaned_heading x1"])

    assert result["status"] == "error" and result["dropped_sentences"] == 1
    confirm.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("confirmed", [True, False])
async def test_dismiss_asks_the_user_first(monkeypatch, confirmed):
    from unittest.mock import AsyncMock
    from synthadoc.agents.workflows import content_health_resolver as mod
    confirm = AsyncMock(return_value={"confirmed": confirmed})
    dismiss = AsyncMock(return_value={"status": "success"})
    monkeypatch.setattr(mod, "tool_confirm", confirm)
    monkeypatch.setattr(mod, "tool_dismiss_content_health_issues", dismiss)
    ctx = MagicMock()
    ctx.store.read_page.return_value = MagicMock(content_health_issues=[
        {"type": "empty_section", "location": "Key Figures"}, {"type": "thin_section", "location": "X"}])

    result = await ContentHealthResolverWorkflow().get_tool_fns(ctx)["dismiss_content_health_issues"](
        slug="ai", reason="needs new prose")

    card = confirm.call_args.kwargs["message"]
    assert "dismiss 1 issue(s)" in card and "empty_section at 'Key Figures'" in card
    assert (dismiss.await_count == 1) is confirmed
    assert result["status"] == ("success" if confirmed else "cancelled")


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
    """dismiss clears the resolvable issues, records the dismissal, keeps report-only ones."""
    from synthadoc.agents.workflows.tools.content_health_tools import (
        tool_dismiss_content_health_issues,
    )
    from synthadoc.agents.workflows._base import WorkflowContext

    store = MagicMock()
    page = MagicMock()
    thin = {"type": "thin_section", "severity": "high"}
    page.content_health_issues = [
        {"type": "empty_section", "severity": "critical"},
        {"type": "orphaned_heading", "severity": "medium"},
        thin,
    ]
    page.content_health_fix_record = None
    store.read_page.return_value = page

    ctx = MagicMock(spec=WorkflowContext)
    ctx.store = store
    ctx.bump_epoch = None

    result = await tool_dismiss_content_health_issues(
        ctx, slug="grace-hopper", reason="needs new prose"
    )

    assert result["status"] == "success"
    assert result["dismissed_count"] == 2
    assert result["remaining_issues"] == 0
    assert page.content_health_issues == [thin]   # stays for the lint report
    assert page.content_health_fix_record is not None
    assert page.content_health_fix_record["dismissed_count"] == 2
    assert set(page.content_health_fix_record["dismissed_types"]) == {"empty_section", "orphaned_heading"}
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


# ---------------------------------------------------------------------------
# _rollback_with_fallback — the universal "roll back X" entry point
# ---------------------------------------------------------------------------
#
# Fast-path routing sends EVERY "roll back X" chat message to this workflow
# (its MATCH_RE is the only one with a bare "roll back" clause, so it wins
# the ROUTED_WORKFLOWS registry-order race against contradiction_resolver's
# and orphan_resolver's own, more specific MATCH_RE patterns). So this
# function is the de-facto universal rollback dispatcher, and must correctly
# cascade through all three fix types: content-health, generic
# (contradiction/orphan direct), and orphan-via-host-page.

async def _auto_confirm_ch(ctx, confirmed=True):
    await asyncio.sleep(0.05)
    gate = ctx.confirm_registry.get(ctx.session_id)
    if gate:
        ctx.confirm_result_registry[ctx.session_id] = confirmed
        gate.set()


class TestRollbackWithFallback:
    async def test_falls_back_to_orphan_host_page_lookup(self, tmp_path):
        """A page with neither a content-health nor a generic record of its
        own (the orphan-resolver case) rolls back via the host page that was
        actually edited — that's the only way to undo its orphan resolution
        — with a message that says explicitly which page was restored."""
        from synthadoc.agents.workflows._base import WorkflowContext
        from synthadoc.agents.workflows._tools import tool_propose_and_apply
        from synthadoc.agents.workflows.content_health_resolver import _rollback_with_fallback
        from synthadoc.storage.log import AuditDB
        from synthadoc.storage.wiki import WikiPage, WikiStorage

        store = WikiStorage(tmp_path / "wiki")
        store.write_page("microprocessor", WikiPage(
            title="Microprocessor", tags=[], content="The CPU on a chip.\n",
            status="active", confidence="", sources=[],
        ))
        store.write_page("computing-history-timeline", WikiPage(
            title="Computing History Timeline", tags=[],
            content="A timeline of computing.\n",
            status="active", confidence="", sources=[],
        ))
        audit_db = AuditDB(tmp_path / "audit.db")
        await audit_db.init()

        events = []
        async def _send(e, d):
            events.append({"event": e, "data": d})
        ctx = WorkflowContext(
            session_id="s1", wiki_root=tmp_path / "wiki", queue=None,
            store=store, audit_db=audit_db, send_sse_event=_send,
            confirm_registry={}, confirm_result_registry={},
        )

        asyncio.create_task(_auto_confirm_ch(ctx))
        applied = await tool_propose_and_apply(
            ctx, slug="computing-history-timeline",
            new_content="A timeline of computing. See [[microprocessor]].\n",
            strategy_name="title_bm25",
            rationale="'computing-history-timeline' identified as related; "
                      "LLM inserted [[microprocessor]].",
        )
        assert applied["applied"] is True

        result = await _rollback_with_fallback(ctx, "microprocessor")

        assert result["status"] == "success"
        assert "move 'microprocessor' back to orphan status" in result["message"]
        assert "computing-history-timeline" in result["message"]
        page = store.read_page("computing-history-timeline")
        assert page.content == "A timeline of computing.\n"

    async def test_content_health_record_still_wins_when_present(self, monkeypatch):
        """Unchanged behavior: a page with its own content-health record
        never reaches the fallback at all."""
        from synthadoc.agents.workflows import content_health_resolver as mod
        from unittest.mock import AsyncMock
        ch_rollback = AsyncMock(return_value={"status": "success", "message": "ok"})
        orphan_fallback = AsyncMock()
        monkeypatch.setattr(mod, "tool_rollback_content_health_fix", ch_rollback)
        monkeypatch.setattr(mod, "tool_rollback_orphan_fix", orphan_fallback)

        result = await mod._rollback_with_fallback(MagicMock(), "some-page")

        assert result["status"] == "success"
        orphan_fallback.assert_not_awaited()

    async def test_direct_generic_record_still_works_unchanged(self, monkeypatch):
        """Unchanged behavior for the pre-existing contradiction_resolver
        fallback case: a page with its own last_fix_record (no content-health
        record) is rolled back directly, same as before this change."""
        from synthadoc.agents.workflows import content_health_resolver as mod
        from unittest.mock import AsyncMock
        ch_rollback = AsyncMock(return_value={"status": "error", "error": "no content health fix"})
        orphan_fallback = AsyncMock(return_value={"status": "success", "message": "rolled back directly"})
        monkeypatch.setattr(mod, "tool_rollback_content_health_fix", ch_rollback)
        monkeypatch.setattr(mod, "tool_rollback_orphan_fix", orphan_fallback)
        page = MagicMock()
        page.content_health_fix_record = None
        store = MagicMock()
        store.read_page.return_value = page
        ctx = MagicMock()
        ctx.store = store

        result = await mod._rollback_with_fallback(ctx, "some-page")

        assert result["status"] == "success"
        orphan_fallback.assert_awaited_once_with(ctx, "some-page")
