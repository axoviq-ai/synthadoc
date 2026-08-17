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

    async def _capture_confirm(ctx, message, yes_label="", no_label=""):
        captured.append(message)
        return {"confirmed": False}

    with patch("synthadoc.agents.workflows._tools.tool_confirm", side_effect=_capture_confirm):
        from synthadoc.agents.workflows._tools import tool_propose_and_apply
        await tool_propose_and_apply(
            ctx, slug="p", new_content="line a\nline c\n",
            strategy_name="S", rationale="r"
        )

    assert captured
    assert "line b" in captured[0] or "-line b" in captured[0]


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
