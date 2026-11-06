# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for ContentHealthResolverWorkflow class attributes and tool registration."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

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
    """Phase 2: _write_fix calls tool_scoped_confirm for user approval.

    Uses a prose-level block edit (extending a sentence) that passes apply_blocks'
    guards: the original sentence text is still present in the proposed content so
    sentence_loss is not triggered.  After the user approves via the scoped card,
    tool_write_content_health_fix is called with the accumulated body.
    """
    from synthadoc.agents.workflows import content_health_resolver as mod

    captured_args: list[dict] = []

    async def fake_scoped_confirm(ctx, slug, apply_result, current_body, **_kw):
        captured_args.append({"slug": slug, "apply_result": apply_result,
                               "current_body": current_body})
        return {"confirmed": True, "final_body": apply_result.accumulated_body}

    write_fix = AsyncMock(return_value={
        "status": "success", "slug": "...", "snapshot_index": 1, "remaining_issues": 0,
    })
    monkeypatch.setattr(mod, "tool_scoped_confirm", fake_scoped_confirm)
    monkeypatch.setattr(mod, "tool_write_content_health_fix", write_fix)

    ctx = _wiki_with_stray_h1(tmp_path, ["page-a", "page-b"])
    wf = ContentHealthResolverWorkflow()
    wf._prediscovered_slugs = ["page-a", "page-b"]
    tools = wf.build_guarded_tool_fns(ctx)
    # Block appends " See also." — no heading change, no sentence loss.
    fix_blocks = [{"old_text": "has one sentence.", "new_text": "has one sentence. See also."}]
    for slug in ("page-a", "page-b"):
        await tools["get_page_content"](slug=slug)
        result = await tools["write_content_health_fix"](
            slug=slug, blocks=fix_blocks, issues_fixed=["orphaned_heading x1"])
        assert result["status"] == "success"

    assert len(captured_args) == 2
    last = captured_args[-1]
    assert "has one sentence. See also." in last["apply_result"].accumulated_body


@pytest.mark.asyncio
async def test_write_that_loses_text_skips_full_page_and_errors(tmp_path, monkeypatch):
    """Phase 2: apply_blocks drops sentence-losing blocks, leaving 0 applied.

    write_content_health_fix must skip tool_scoped_confirm's full-page card
    entirely in this degenerate case — a confusing empty diff to review — and
    return status="error" instead, so STEP 3d's existing "error → leave for
    3e" instruction routes the model straight to dismissal. This mirrors
    contradiction_resolver's tool_propose_and_apply_blocks auto-skip to
    Strategy 2 (both share describe_all_blocks_rejected).
    """
    from synthadoc.agents.workflows import content_health_resolver as mod

    scoped_confirm = AsyncMock()
    monkeypatch.setattr(mod, "tool_scoped_confirm", scoped_confirm)
    ctx = _wiki_with_stray_h1(tmp_path, ["page-a"])
    wf = ContentHealthResolverWorkflow()
    wf._prediscovered_slugs = ["page-a"]
    tools = wf.build_guarded_tool_fns(ctx)
    await tools["get_page_content"](slug="page-a")
    result = await tools["write_content_health_fix"](
        slug="page-a",
        blocks=[{"old_text": "The page body has one sentence.", "new_text": ""}],
        issues_fixed=["orphaned_heading x1"],
    )

    # apply_blocks rejected the sentence-losing block — no "dropped_sentences" error
    assert "dropped_sentences" not in result
    # Full-page card never shown for an all-rejected result
    scoped_confirm.assert_not_called()
    assert result["status"] == "error"
    assert "STEP 3e" in result["action"] or "dismiss" in result["action"].lower()


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
        slug="some-page", blocks=[], issues_fixed=[]
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
        slug="invented-slug", blocks=[], issues_fixed=[]
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
        slug="real-page", blocks=[], issues_fixed=["duplicate_section"]
    )
    assert result["status"] != "error" or "get_page_content" not in result.get("error", "")


@pytest.mark.asyncio
async def test_write_rejects_duplicate_section_fix_attempt(monkeypatch):
    """write_content_health_fix must refuse a duplicate_section issue — STEP 3a
    makes merge_duplicate_sections its exclusive handler, and a duplicate-heading
    merge can never be expressed as a simple old_text/new_text block, so
    apply_blocks always rejects it (0 applied). Before this guard, that fell
    through to tool_scoped_confirm's full-page manual-edit prompt instead of
    staying on the documented sequence — some providers (e.g. Kimi) call
    write_content_health_fix for duplicate_section anyway even right after
    merge_duplicate_sections already ran, so the prompt alone isn't enough."""
    from synthadoc.agents.workflows import content_health_resolver as mod

    scoped_confirm = AsyncMock()
    monkeypatch.setattr(mod, "tool_scoped_confirm", scoped_confirm)

    ctx = MagicMock()
    ctx.store.list_pages.return_value = ["real-page"]
    wf = ContentHealthResolverWorkflow()
    tools = wf.get_tool_fns(ctx)

    discover_page = MagicMock(
        status="active",
        content_health_issues=[{"severity": "high", "type": "duplicate_section"}],
        content="old body", title="Real Page",
    )
    ctx.store.read_page.return_value = discover_page
    await tools["find_content_health_issues"](slug="")

    read_page = MagicMock(
        status="active", title="Real Page", content="old body", content_health_issues=[]
    )
    ctx.store.read_page.return_value = read_page
    await tools["get_page_content"](slug="real-page")

    result = await tools["write_content_health_fix"](
        slug="real-page", blocks=[{"old_text": "x", "new_text": "y"}],
        issues_fixed=["duplicate_section x1"],
    )
    assert result["status"] == "error"
    assert "merge_duplicate_sections" in result["error"]
    scoped_confirm.assert_not_called()


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
    gate = ctx.confirm_registry.get(ctx.run_id)
    if gate:
        ctx.confirm_result_registry[ctx.run_id] = confirmed
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


# ---------------------------------------------------------------------------
# Task 2 — block-format write_content_health_fix
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_fix_via_blocks_applies_accumulated_body():
    """Phase 2: _write_fix accepts blocks, calls apply_blocks + tool_scoped_confirm,
    then passes the confirmed body to tool_write_content_health_fix."""
    from synthadoc.agents.workflows.content_health_resolver import ContentHealthResolverWorkflow

    wf = ContentHealthResolverWorkflow()
    ctx = MagicMock()
    ctx.store = MagicMock()
    ctx.store.read_page.return_value = MagicMock(content="Old text. Keep this.", status="active")
    ctx.audit_db = AsyncMock()
    ctx.bump_epoch = None
    ctx.session_id = "s1"
    ctx.confirm_registry = {}
    ctx.confirm_result_registry = {}
    ctx.send_sse_event = AsyncMock()
    ctx.wiki_root = None

    applied_body = None

    async def fake_write_fix(ctx_, slug, content, issues_fixed, **kw):
        nonlocal applied_body
        applied_body = content
        return {"status": "success", "slug": slug, "snapshot_index": 1, "remaining_issues": 0}

    async def fake_scoped_confirm(ctx_, slug, apply_result, current_body, **_kw):
        return {"confirmed": True, "final_body": apply_result.accumulated_body}

    from unittest.mock import patch
    with patch("synthadoc.agents.workflows.content_health_resolver.tool_write_content_health_fix",
               side_effect=fake_write_fix), \
         patch("synthadoc.agents.workflows.content_health_resolver.tool_scoped_confirm",
               side_effect=fake_scoped_confirm):
        # Manually seed the guard sets — normally done via _find_issues + _get_content
        wf._prediscovered_slugs = ["alan-turing"]
        fns2 = wf.get_tool_fns(ctx)
        # Call get_page_content to seed read_slugs
        with patch("synthadoc.agents.workflows.content_health_resolver.tool_get_page_content",
                   return_value={"status": "success", "slug": "alan-turing",
                                 "content": "Old text. Keep this.", "issues": []}):
            await fns2["get_page_content"]("alan-turing")
        result = await fns2["write_content_health_fix"](
            slug="alan-turing",
            blocks=[{"old_text": "Old text.", "new_text": "Fixed text."}],
            issues_fixed=["empty_section"],
        )

    assert result["status"] == "success"
    assert applied_body is not None
    assert "Fixed text." in applied_body
    assert "Keep this." in applied_body


@pytest.mark.asyncio
async def test_system_prompt_uses_block_format():
    from synthadoc.agents.workflows.content_health_resolver import ContentHealthResolverWorkflow
    wf = ContentHealthResolverWorkflow()
    prompt = await wf.build_system_prompt()
    assert '"blocks"' in prompt or "old_text" in prompt, (
        "System prompt must describe block format for write_content_health_fix"
    )
