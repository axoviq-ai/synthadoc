# tests/test_workflow_tools_ext.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for the 5 new generic tools added to synthadoc/agents/workflows/_tools.py.

These tools are shared across workflows — not contradiction-resolver-specific.
"""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from synthadoc.storage.wiki import WikiPage, WikiStorage, LifecycleState


# ── fixtures ─────────────────────────────────────────────────────────────────

def _make_store(tmp_path: Path, pages: dict) -> WikiStorage:
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    store = WikiStorage(wiki_dir)
    for slug, page in pages.items():
        store.write_page(slug, page)
    return store


def _page(status=LifecycleState.ACTIVE, content="body", warnings=None, note=None):
    return WikiPage(
        title="T", tags=[], content=content, status=status,
        confidence="high", sources=[],
        lint_warnings=warnings or [],
        contradiction_note=note,
    )


def _ctx(tmp_path: Path, store: WikiStorage) -> MagicMock:
    ctx = MagicMock()
    ctx.wiki_root = tmp_path
    ctx.store = store
    ctx.send_sse_event = AsyncMock()
    ctx.confirm_registry = {}
    ctx.confirm_result_registry = {}
    ctx.session_id = "test-session"
    ctx.queue = AsyncMock()
    ctx.audit_db = AsyncMock()
    return ctx


# ── tool_read_page_content ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_read_page_content_returns_all_fields(tmp_path):
    store = _make_store(tmp_path, {
        "alan-turing": _page(content="Turing content", note="conflict X",
                             warnings=[{"claim": "c"}])
    })
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows._tools import tool_read_page_content
    result = await tool_read_page_content(ctx, slug="alan-turing")
    assert result["slug"] == "alan-turing"
    assert result["content"] == "Turing content"
    assert result["contradiction_note"] == "conflict X"
    assert result["lint_warnings"] == [{"claim": "c"}]
    assert "status" in result


@pytest.mark.asyncio
async def test_read_page_content_missing_page(tmp_path):
    store = _make_store(tmp_path, {})
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows._tools import tool_read_page_content
    result = await tool_read_page_content(ctx, slug="ghost")
    assert "error" in result


# ── tool_run_scoped_lint ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_scoped_lint_passes_clean_page(tmp_path):
    store = _make_store(tmp_path, {
        "target": _page(status=LifecycleState.CONTRADICTED, warnings=[], note=None)
    })
    ctx = _ctx(tmp_path, store)
    ctx.queue.enqueue = AsyncMock(return_value="j1")

    with patch("synthadoc.agents.workflows._tools.tool_poll_job",
               new_callable=AsyncMock, return_value={"status": "success"}):
        from synthadoc.agents.workflows._tools import tool_run_scoped_lint
        result = await tool_run_scoped_lint(ctx, slug="target")

    assert result["pass"] is True
    assert result["warnings_count"] == 0
    assert result["contradiction_note"] is None


@pytest.mark.asyncio
async def test_run_scoped_lint_fails_when_note_remains(tmp_path):
    store = _make_store(tmp_path, {
        "target": _page(status=LifecycleState.CONTRADICTED, note="still conflicted")
    })
    ctx = _ctx(tmp_path, store)
    ctx.queue.enqueue = AsyncMock(return_value="j2")

    with patch("synthadoc.agents.workflows._tools.tool_poll_job",
               new_callable=AsyncMock, return_value={"status": "success"}):
        from synthadoc.agents.workflows._tools import tool_run_scoped_lint
        result = await tool_run_scoped_lint(ctx, slug="target")

    assert result["pass"] is False
    assert result["contradiction_note"] == "still conflicted"


@pytest.mark.asyncio
async def test_run_scoped_lint_enqueues_correct_payload(tmp_path):
    store = _make_store(tmp_path, {"t": _page()})
    ctx = _ctx(tmp_path, store)
    ctx.queue.enqueue = AsyncMock(return_value="j3")

    with patch("synthadoc.agents.workflows._tools.tool_poll_job",
               new_callable=AsyncMock, return_value={"status": "success"}):
        from synthadoc.agents.workflows._tools import tool_run_scoped_lint
        await tool_run_scoped_lint(ctx, slug="t")

    call_args = ctx.queue.enqueue.call_args
    assert call_args[0][0] == "lint"
    payload = call_args[0][1]
    assert payload["scope"] == "slug"
    assert payload["slug"] == "t"
    assert payload["lifecycle"] is False


# ── tool_propose_and_apply ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_propose_and_apply_writes_on_approval(tmp_path):
    store = _make_store(tmp_path, {"p": _page(content="old")})
    ctx = _ctx(tmp_path, store)

    with patch("synthadoc.agents.workflows._tools.tool_confirm",
               new_callable=AsyncMock, return_value={"confirmed": True}):
        from synthadoc.agents.workflows._tools import tool_propose_and_apply
        result = await tool_propose_and_apply(
            ctx, slug="p", new_content="new",
            strategy_name="Rewrite", rationale="fix"
        )

    assert result["applied"] is True
    assert store.read_page("p").content == "new"


@pytest.mark.asyncio
async def test_propose_and_apply_no_write_on_rejection(tmp_path):
    store = _make_store(tmp_path, {"p": _page(content="old")})
    ctx = _ctx(tmp_path, store)

    with patch("synthadoc.agents.workflows._tools.tool_confirm",
               new_callable=AsyncMock, return_value={"confirmed": False}):
        from synthadoc.agents.workflows._tools import tool_propose_and_apply
        result = await tool_propose_and_apply(
            ctx, slug="p", new_content="new",
            strategy_name="Rewrite", rationale="fix"
        )

    assert result["applied"] is False
    assert store.read_page("p").content == "old"


@pytest.mark.asyncio
async def test_propose_and_apply_diff_in_confirm_message(tmp_path):
    store = _make_store(tmp_path, {"p": _page(content="line a\nline b\n")})
    ctx = _ctx(tmp_path, store)
    captured = []

    async def _capture_confirm(ctx, message, yes_label="", no_label="", *, diff=None):
        captured.append({"message": message, "diff": diff})
        return {"confirmed": False}

    with patch("synthadoc.agents.workflows._tools.tool_confirm", side_effect=_capture_confirm):
        from synthadoc.agents.workflows._tools import tool_propose_and_apply
        await tool_propose_and_apply(
            ctx, slug="p", new_content="line a\nline c\n",
            strategy_name="S", rationale="r"
        )

    assert captured
    # The diff is now passed separately as the `diff` kwarg, not embedded in the message.
    # Check that the unified diff shows the removed line.
    assert captured[0]["diff"] is not None
    assert "-line b" in captured[0]["diff"] or "line b" in captured[0]["diff"]


@pytest.mark.asyncio
async def test_propose_and_apply_clears_contradiction_note_on_approval(tmp_path):
    """Approving a content change must clear contradiction_note so scoped lint can pass.

    Root cause of source-conflict pages always failing: tool_run_scoped_lint
    evaluates `passed = gate_ok and not contradiction_note`.  If the note
    is not cleared when new content is applied, the lint gate is permanently
    locked for conflict-type pages.
    """
    store = _make_store(tmp_path, {
        "p": _page(content="old", note="New source contradicts claim X")
    })
    ctx = _ctx(tmp_path, store)

    with patch("synthadoc.agents.workflows._tools.tool_confirm",
               new_callable=AsyncMock, return_value={"confirmed": True}):
        from synthadoc.agents.workflows._tools import tool_propose_and_apply
        result = await tool_propose_and_apply(
            ctx, slug="p", new_content="reconciled content",
            strategy_name="Strategy 1 — Content rewrite", rationale="fix conflict"
        )

    assert result["applied"] is True
    # contradiction_note MUST be None after applying so scoped lint can pass
    assert store.read_page("p").contradiction_note is None


@pytest.mark.asyncio
async def test_propose_and_apply_preserves_contradiction_note_on_rejection(tmp_path):
    """Rejecting a change must leave contradiction_note intact."""
    store = _make_store(tmp_path, {
        "p": _page(content="old", note="conflict note")
    })
    ctx = _ctx(tmp_path, store)

    with patch("synthadoc.agents.workflows._tools.tool_confirm",
               new_callable=AsyncMock, return_value={"confirmed": False}):
        from synthadoc.agents.workflows._tools import tool_propose_and_apply
        await tool_propose_and_apply(
            ctx, slug="p", new_content="new",
            strategy_name="Rewrite", rationale="fix"
        )

    assert store.read_page("p").contradiction_note == "conflict note"


@pytest.mark.asyncio
async def test_propose_and_apply_missing_page_returns_error(tmp_path):
    store = _make_store(tmp_path, {})
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows._tools import tool_propose_and_apply
    result = await tool_propose_and_apply(
        ctx, slug="ghost", new_content="x", strategy_name="S", rationale="r"
    )
    assert result["applied"] is False
    assert "error" in result


# ── tool_transition_lifecycle_state ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_transition_lifecycle_state_contradicted_to_active(tmp_path):
    store = _make_store(tmp_path, {
        "p": _page(status=LifecycleState.CONTRADICTED)
    })
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows._tools import tool_transition_lifecycle_state
    result = await tool_transition_lifecycle_state(
        ctx, slug="p", to_state="active",
        reason="resolved by resolver — strategy: Content rewrite"
    )
    assert result["success"] is True
    assert store.read_page("p").status == LifecycleState.ACTIVE


@pytest.mark.asyncio
async def test_transition_lifecycle_state_records_audit_event(tmp_path):
    store = _make_store(tmp_path, {
        "p": _page(status=LifecycleState.CONTRADICTED)
    })
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows._tools import tool_transition_lifecycle_state
    await tool_transition_lifecycle_state(ctx, slug="p", to_state="active", reason="test")
    assert ctx.audit_db.record_lifecycle_event.called


@pytest.mark.asyncio
async def test_transition_lifecycle_state_updates_page_states_db(tmp_path):
    """set_page_state must be called so GET /lifecycle/pages reflects the change.

    tool_transition_lifecycle_state writes the file (store) and must also update
    the page_states DB table so the lifecycle API endpoint returns the new state
    without requiring a subsequent lint run to sync it.
    """
    store = _make_store(tmp_path, {"p": _page(status=LifecycleState.CONTRADICTED)})
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows._tools import tool_transition_lifecycle_state
    result = await tool_transition_lifecycle_state(ctx, slug="p", to_state="active", reason="test")
    assert result["success"] is True
    ctx.audit_db.set_page_state.assert_awaited_once_with("p", "active", "workflow")


@pytest.mark.asyncio
async def test_transition_lifecycle_state_missing_page(tmp_path):
    store = _make_store(tmp_path, {})
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows._tools import tool_transition_lifecycle_state
    result = await tool_transition_lifecycle_state(ctx, slug="ghost", to_state="active", reason="x")
    assert result["success"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_transition_lifecycle_state_invalid_state_string(tmp_path):
    store = _make_store(tmp_path, {"p": _page(status=LifecycleState.ACTIVE)})
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows._tools import tool_transition_lifecycle_state
    result = await tool_transition_lifecycle_state(ctx, slug="p", to_state="banana", reason="x")
    assert result["success"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_transition_lifecycle_state_updates_markdown_file_frontmatter(tmp_path):
    """The markdown file on disk must have status: active after transition.

    Regression guard for the concern that the workflow might update only the
    audit DB while leaving the .md file with status: contradicted in its
    YAML frontmatter.  We read the raw file bytes — not WikiStorage — so
    the assertion is independent of any in-memory cache or ORM layer.
    """
    store = _make_store(tmp_path, {
        "grace-hopper": _page(status=LifecycleState.CONTRADICTED)
    })
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows._tools import tool_transition_lifecycle_state
    result = await tool_transition_lifecycle_state(
        ctx, slug="grace-hopper", to_state="active",
        reason="resolved by resolver — strategy: Content rewrite, attempt 1",
    )
    assert result["success"] is True
    # Read the RAW FILE to verify frontmatter — not just the in-memory store.
    page_file = tmp_path / "wiki" / "grace-hopper.md"
    raw = page_file.read_text(encoding="utf-8")
    assert "status: active" in raw, (
        "Expected 'status: active' in markdown frontmatter after transition; "
        f"got:\n{raw[:500]}"
    )
    assert "status: contradicted" not in raw


@pytest.mark.asyncio
async def test_propose_then_transition_raw_file_consistent(tmp_path):
    """End-to-end: propose→apply clears contradiction_note; transition sets status active.

    Both operations write to the same .md file.  This test reads the raw file
    after each step to confirm the on-disk state is always internally consistent:
    no contradiction_note left behind when content is approved, and status is
    definitively 'active' after the lifecycle transition.
    """
    store = _make_store(tmp_path, {
        "grace-hopper": _page(
            status=LifecycleState.CONTRADICTED,
            content="old content",
            note="New source contradicts claim about COBOL",
        )
    })
    ctx = _ctx(tmp_path, store)
    page_file = tmp_path / "wiki" / "grace-hopper.md"

    # Step 1: apply new content — this clears contradiction_note.
    with patch("synthadoc.agents.workflows._tools.tool_confirm",
               new_callable=AsyncMock, return_value={"confirmed": True}):
        from synthadoc.agents.workflows._tools import tool_propose_and_apply
        applied = await tool_propose_and_apply(
            ctx, slug="grace-hopper",
            new_content="reconciled content with explicit sourcing",
            strategy_name="Strategy 1 — Content rewrite",
            rationale="addresses source conflict",
        )
    assert applied["applied"] is True
    raw_after_apply = page_file.read_text(encoding="utf-8")
    # contradiction_note must be gone; status is still contradicted at this stage.
    assert "contradiction_note" not in raw_after_apply
    assert "status: contradicted" in raw_after_apply

    # Step 2: transition to active — only changes status.
    from synthadoc.agents.workflows._tools import tool_transition_lifecycle_state
    result = await tool_transition_lifecycle_state(
        ctx, slug="grace-hopper", to_state="active",
        reason="resolved by resolver — strategy: Content rewrite, attempt 1",
    )
    assert result["success"] is True
    raw_after_transition = page_file.read_text(encoding="utf-8")
    assert "status: active" in raw_after_transition, (
        "Expected 'status: active' in markdown frontmatter after transition; "
        f"got:\n{raw_after_transition[:500]}"
    )
    assert "status: contradicted" not in raw_after_transition
    assert "contradiction_note" not in raw_after_transition


# ── tool_transition_lifecycle_state — cache invalidation hooks ───────────────

@pytest.mark.asyncio
async def test_transition_calls_bump_epoch_and_invalidate_search_on_success(tmp_path):
    """bump_epoch and invalidate_search must fire after a successful transition."""
    store = _make_store(tmp_path, {
        "grace-hopper": _page(status=LifecycleState.CONTRADICTED),
    })
    ctx = _ctx(tmp_path, store)
    ctx.bump_epoch = MagicMock()
    ctx.invalidate_search = MagicMock()

    from synthadoc.agents.workflows._tools import tool_transition_lifecycle_state
    result = await tool_transition_lifecycle_state(
        ctx, slug="grace-hopper", to_state="active",
        reason="resolver fixed it",
    )

    assert result["success"] is True
    ctx.bump_epoch.assert_called_once()
    ctx.invalidate_search.assert_called_once()


@pytest.mark.asyncio
async def test_transition_skips_hooks_when_page_not_found(tmp_path):
    """bump_epoch and invalidate_search must NOT fire when the page doesn't exist."""
    store = _make_store(tmp_path, {})
    ctx = _ctx(tmp_path, store)
    ctx.bump_epoch = MagicMock()
    ctx.invalidate_search = MagicMock()

    from synthadoc.agents.workflows._tools import tool_transition_lifecycle_state
    result = await tool_transition_lifecycle_state(
        ctx, slug="nonexistent-slug", to_state="active",
        reason="should not matter",
    )

    assert result["success"] is False
    ctx.bump_epoch.assert_not_called()
    ctx.invalidate_search.assert_not_called()


@pytest.mark.asyncio
async def test_transition_hooks_none_safe(tmp_path):
    """When bump_epoch / invalidate_search are None (no orchestrator), no error."""
    store = _make_store(tmp_path, {
        "ada-lovelace": _page(status=LifecycleState.DRAFT),
    })
    ctx = _ctx(tmp_path, store)
    # MagicMock auto-creates .bump_epoch and .invalidate_search as MagicMocks;
    # override with None to test the None-safe guard in _tools.py.
    ctx.bump_epoch = None
    ctx.invalidate_search = None

    from synthadoc.agents.workflows._tools import tool_transition_lifecycle_state
    result = await tool_transition_lifecycle_state(
        ctx, slug="ada-lovelace", to_state="active",
        reason="no cache hooks wired",
    )
    assert result["success"] is True  # must not raise


# ── tool_transition_lifecycle_state — state-machine graph enforcement ─────────

@pytest.mark.asyncio
async def test_transition_rejects_forbidden_path_archived_to_active(tmp_path):
    """archived → active is not in ALLOWED_LIFECYCLE_TRANSITIONS; must be rejected."""
    store = _make_store(tmp_path, {
        "alan-turing": _page(status=LifecycleState.ARCHIVED),
    })
    ctx = _ctx(tmp_path, store)

    from synthadoc.agents.workflows._tools import tool_transition_lifecycle_state
    result = await tool_transition_lifecycle_state(
        ctx, slug="alan-turing", to_state="active",
        reason="trying a forbidden path",
    )

    assert result["success"] is False
    assert "not permitted" in result["error"]
    # Verify the page was NOT written.
    page = store.read_page("alan-turing")
    assert page.status == LifecycleState.ARCHIVED


@pytest.mark.asyncio
async def test_transition_rejects_same_state(tmp_path):
    """active → active must be rejected (same-state is never a valid transition)."""
    store = _make_store(tmp_path, {
        "ada-lovelace": _page(status=LifecycleState.ACTIVE),
    })
    ctx = _ctx(tmp_path, store)

    from synthadoc.agents.workflows._tools import tool_transition_lifecycle_state
    result = await tool_transition_lifecycle_state(
        ctx, slug="ada-lovelace", to_state="active",
        reason="no-op same-state",
    )

    assert result["success"] is False
    assert "already in state" in result["error"]


@pytest.mark.asyncio
async def test_transition_rejects_draft_to_stale(tmp_path):
    """draft → stale is not in ALLOWED_LIFECYCLE_TRANSITIONS; must be rejected."""
    store = _make_store(tmp_path, {
        "eniac": _page(status=LifecycleState.DRAFT),
    })
    ctx = _ctx(tmp_path, store)

    from synthadoc.agents.workflows._tools import tool_transition_lifecycle_state
    result = await tool_transition_lifecycle_state(
        ctx, slug="eniac", to_state="stale",
        reason="trying another forbidden path",
    )

    assert result["success"] is False
    assert "not permitted" in result["error"]


@pytest.mark.asyncio
async def test_transition_allows_contradicted_to_active(tmp_path):
    """contradicted → active is the resolver's valid path; must succeed."""
    store = _make_store(tmp_path, {
        "grace-hopper": _page(status=LifecycleState.CONTRADICTED),
    })
    ctx = _ctx(tmp_path, store)

    from synthadoc.agents.workflows._tools import tool_transition_lifecycle_state
    result = await tool_transition_lifecycle_state(
        ctx, slug="grace-hopper", to_state="active",
        reason="resolved by contradiction-resolver — strategy: Content rewrite, attempt 1",
    )

    assert result["success"] is True
    assert result["from_state"] == "contradicted"
    assert result["to_state"] == "active"


# ── tool_get_wiki_status ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_wiki_status_counts_all_states(tmp_path):
    store = _make_store(tmp_path, {
        "a1": _page(status=LifecycleState.ACTIVE),
        "a2": _page(status=LifecycleState.ACTIVE),
        "c1": _page(status=LifecycleState.CONTRADICTED),
        "s1": _page(status=LifecycleState.STALE),
    })
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows._tools import tool_get_wiki_status
    result = await tool_get_wiki_status(ctx)
    assert result["active"] == 2
    assert result["contradicted"] == 1
    assert result["stale"] == 1
    assert result["draft"] == 0
    assert result["archived"] == 0


@pytest.mark.asyncio
async def test_get_wiki_status_empty_wiki(tmp_path):
    store = _make_store(tmp_path, {})
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows._tools import tool_get_wiki_status
    result = await tool_get_wiki_status(ctx)
    assert all(v == 0 for v in result.values())


@pytest.mark.asyncio
async def test_get_wiki_status_excludes_system_pages(tmp_path):
    """System pages (index, log, dashboard, etc.) must not appear in the count.

    These pages are in SYSTEM_PAGE_SLUGS and are excluded by synthadoc status.
    tool_get_wiki_status must match that behaviour so the final workflow summary
    is consistent with what the user sees in the CLI.
    """
    store = _make_store(tmp_path, {
        "real-page": _page(status=LifecycleState.ACTIVE),
        # System pages — must all be excluded from counts
        "index":     _page(status=LifecycleState.ACTIVE),
        "log":       _page(status=LifecycleState.ACTIVE),
        "dashboard": _page(status=LifecycleState.ACTIVE),
        "purpose":   _page(status=LifecycleState.ACTIVE),
        "overview":  _page(status=LifecycleState.ACTIVE),
    })
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows._tools import tool_get_wiki_status
    result = await tool_get_wiki_status(ctx)
    # Only "real-page" counts — the 5 system pages must be excluded.
    assert result["active"] == 1
    assert sum(result.values()) == 1


# ── additional coverage tests ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_scoped_lint_enqueue_exception(tmp_path):
    store = _make_store(tmp_path, {"t": _page()})
    ctx = _ctx(tmp_path, store)
    ctx.queue.enqueue = AsyncMock(side_effect=RuntimeError("queue down"))
    from synthadoc.agents.workflows._tools import tool_run_scoped_lint
    result = await tool_run_scoped_lint(ctx, slug="t")
    assert result["pass"] is False
    assert "queue down" in result["error"]


@pytest.mark.asyncio
async def test_run_scoped_lint_poll_job_failed(tmp_path):
    store = _make_store(tmp_path, {"t": _page()})
    ctx = _ctx(tmp_path, store)
    ctx.queue.enqueue = AsyncMock(return_value="j99")
    with patch("synthadoc.agents.workflows._tools.tool_poll_job",
               new_callable=AsyncMock,
               return_value={"status": "failed", "message": "job exploded"}):
        from synthadoc.agents.workflows._tools import tool_run_scoped_lint
        result = await tool_run_scoped_lint(ctx, slug="t")
    assert result["pass"] is False
    assert "job exploded" in result["error"]


@pytest.mark.asyncio
async def test_run_scoped_lint_page_disappeared_after_lint(tmp_path):
    store = _make_store(tmp_path, {"t": _page()})
    ctx = _ctx(tmp_path, store)
    ctx.queue.enqueue = AsyncMock(return_value="j100")

    # Simulate page disappearing between lint job and the read-back
    store.read_page = MagicMock(return_value=None)

    with patch("synthadoc.agents.workflows._tools.tool_poll_job",
               new_callable=AsyncMock, return_value={"status": "success"}):
        from synthadoc.agents.workflows._tools import tool_run_scoped_lint
        result = await tool_run_scoped_lint(ctx, slug="t")

    assert result["pass"] is False
    assert "disappeared" in result["error"]


@pytest.mark.asyncio
async def test_propose_and_apply_large_diff_truncated(tmp_path):
    old_content = "\n".join(f"line {i}" for i in range(100)) + "\n"
    new_content = "\n".join(f"changed {i}" for i in range(100)) + "\n"
    store = _make_store(tmp_path, {"big": _page(content=old_content)})
    ctx = _ctx(tmp_path, store)
    with patch("synthadoc.agents.workflows._tools.tool_confirm",
               new_callable=AsyncMock, return_value={"confirmed": False}):
        from synthadoc.agents.workflows._tools import tool_propose_and_apply
        result = await tool_propose_and_apply(
            ctx, slug="big", new_content=new_content,
            strategy_name="Bulk", rationale="test"
        )
    assert "more lines not shown" in result["diff_preview"]


@pytest.mark.asyncio
async def test_transition_lifecycle_state_audit_exception_swallowed(tmp_path):
    store = _make_store(tmp_path, {"p": _page(status=LifecycleState.CONTRADICTED)})
    ctx = _ctx(tmp_path, store)
    ctx.audit_db.record_lifecycle_event = AsyncMock(side_effect=RuntimeError("db down"))
    from synthadoc.agents.workflows._tools import tool_transition_lifecycle_state
    result = await tool_transition_lifecycle_state(ctx, slug="p", to_state="active", reason="test")
    # audit failure must not abort the workflow
    assert result["success"] is True
    assert store.read_page("p").status == LifecycleState.ACTIVE


@pytest.mark.asyncio
async def test_get_wiki_status_skips_none_pages(tmp_path):
    store = _make_store(tmp_path, {"a": _page(status=LifecycleState.ACTIVE)})
    ctx = _ctx(tmp_path, store)

    original_list = store.list_pages
    original_read = store.read_page

    def _list():
        return list(original_list()) + ["ghost-slug"]

    call_count = {"n": 0}

    def _read(slug):
        if slug == "ghost-slug":
            return None
        return original_read(slug)

    store.list_pages = _list
    store.read_page = _read

    from synthadoc.agents.workflows._tools import tool_get_wiki_status
    result = await tool_get_wiki_status(ctx)
    assert result["active"] == 1
    assert result["draft"] == 0


# ── tool_notify ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tool_notify_sends_notice_sse_event(tmp_path):
    """tool_notify sends a notice SSE event and returns {"sent": True}.

    This tool exists specifically so the contradiction resolver can communicate
    escalation messages mid-workflow without emitting plain text, which would
    terminate the tool-call loop.
    """
    store = _make_store(tmp_path, {})
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows._tools import tool_notify
    result = await tool_notify(ctx, message="⚠ grace-hopper failed after 3 attempts", level="warning")
    assert result == {"sent": True}
    ctx.send_sse_event.assert_awaited_once_with(
        "notice",
        {"text": "⚠ grace-hopper failed after 3 attempts", "level": "warning"},
    )


@pytest.mark.asyncio
async def test_tool_notify_default_level_is_info(tmp_path):
    store = _make_store(tmp_path, {})
    ctx = _ctx(tmp_path, store)
    from synthadoc.agents.workflows._tools import tool_notify
    await tool_notify(ctx, message="status update")
    _, event_data = ctx.send_sse_event.call_args.args
    assert event_data["level"] == "info"
