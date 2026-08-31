# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for synthadoc.agents.workflows._tools (Task 2 — agentic workflow tools)."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from synthadoc.agents.workflows._base import WorkflowContext
from synthadoc.agents.workflows._tools import (
    _apply_single_fix,
    _load_gate_threshold,
    _normalize_slug,
    _resolve_source_path,
    _resolve_stale_pages,
    tool_apply_link_fixes,
    tool_confirm,
    tool_find_broken_wikilinks,
    tool_find_page_source,
    tool_find_stale_pages,
    tool_get_lint_report,
    tool_get_page_states,
    tool_get_scaffold_preview,
    tool_ingest_source,
    tool_poll_job,
    tool_run_lint,
    tool_run_scaffold,
)
from synthadoc.core.queue import JobStatus


# ---------------------------------------------------------------------------
# Fixture helper
# ---------------------------------------------------------------------------

def _make_ctx(audit_db=None, store=None, queue=None):
    events = []

    async def _send(e, d):
        events.append({"event": e, "data": d})

    return WorkflowContext(
        session_id="s1",
        wiki_root=Path("/wiki"),
        queue=queue,
        store=store,
        audit_db=audit_db,
        send_sse_event=_send,
        confirm_registry={},
        confirm_result_registry={},
    ), events


# ---------------------------------------------------------------------------
# Test 1: _resolve_stale_pages happy path
# ---------------------------------------------------------------------------

async def test_resolve_stale_pages_returns_slugs_and_paths(tmp_path):
    """Stale pages are returned; active pages are excluded."""
    audit_db = MagicMock()
    audit_db.get_live_page_states = AsyncMock(
        return_value=[
            {"slug": "page-a", "state": "stale", "updated_at": "2026-01-01"},
            {"slug": "page-b", "state": "active", "updated_at": "2026-01-02"},
        ]
    )
    store = MagicMock()
    source = MagicMock()
    source_file = str(tmp_path / "raw" / "a.md")
    source.file = source_file
    page_a = MagicMock()
    page_a.sources = [source]
    store.read_page = MagicMock(return_value=page_a)
    store.page_exists = MagicMock(return_value=True)

    ctx, _ = _make_ctx(audit_db=audit_db, store=store)
    result = await _resolve_stale_pages(ctx)

    assert len(result) == 1
    assert result[0]["slug"] == "page-a"
    assert result[0]["source_path"] == source_file
    assert "stale_since" in result[0]


# ---------------------------------------------------------------------------
# Test 1b: _resolve_stale_pages resolves relative source paths against wiki_root
# ---------------------------------------------------------------------------

async def test_resolve_stale_pages_resolves_relative_path(tmp_path):
    """Relative source paths: wiki_root/raw_file tried first, raw_sources/ fallback second."""
    audit_db = MagicMock()
    audit_db.get_live_page_states = AsyncMock(
        return_value=[{"slug": "page-a", "state": "stale", "updated_at": "2026-01-01"}]
    )
    store = MagicMock()
    source = MagicMock()
    source.file = "raw/a.md"  # relative path — exists directly under wiki_root
    page_a = MagicMock()
    page_a.sources = [source]
    store.read_page = MagicMock(return_value=page_a)
    store.page_exists = MagicMock(return_value=True)

    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "a.md").write_text("hello")

    events: list = []

    async def _send(e, d):
        events.append({"event": e, "data": d})

    ctx = WorkflowContext(
        session_id="s1",
        wiki_root=tmp_path,
        queue=MagicMock(),
        store=store,
        audit_db=audit_db,
        send_sse_event=_send,
        confirm_registry={},
        confirm_result_registry={},
    )
    result = await _resolve_stale_pages(ctx)

    assert len(result) == 1
    expected = str(tmp_path / "raw" / "a.md")
    assert result[0]["source_path"] == expected


async def test_resolve_stale_pages_resolves_raw_sources_fallback(tmp_path):
    """Relative paths not found at wiki_root are retried under wiki_root/raw_sources/."""
    audit_db = MagicMock()
    audit_db.get_live_page_states = AsyncMock(
        return_value=[{"slug": "page-a", "state": "stale", "updated_at": "2026-01-01"}]
    )
    store = MagicMock()
    source = MagicMock()
    source.file = "public-domain/a.txt"  # legacy format: relative to raw_sources/
    page_a = MagicMock()
    page_a.sources = [source]
    store.read_page = MagicMock(return_value=page_a)
    store.page_exists = MagicMock(return_value=True)

    # File exists only under raw_sources/
    (tmp_path / "raw_sources" / "public-domain").mkdir(parents=True)
    (tmp_path / "raw_sources" / "public-domain" / "a.txt").write_text("content")

    events: list = []

    async def _send(e, d):
        events.append({"event": e, "data": d})

    ctx = WorkflowContext(
        session_id="s1",
        wiki_root=tmp_path,
        queue=MagicMock(),
        store=store,
        audit_db=audit_db,
        send_sse_event=_send,
        confirm_registry={},
        confirm_result_registry={},
    )
    result = await _resolve_stale_pages(ctx)

    assert len(result) == 1
    expected = str(tmp_path / "raw_sources" / "public-domain" / "a.txt")
    assert result[0]["source_path"] == expected


# ---------------------------------------------------------------------------
# Test 2: _resolve_stale_pages skips missing source
# ---------------------------------------------------------------------------

async def test_resolve_stale_pages_skips_missing_source():
    """Page with no sources yields source_path=None."""
    audit_db = MagicMock()
    audit_db.get_live_page_states = AsyncMock(
        return_value=[{"slug": "page-a", "state": "stale"}]
    )
    store = MagicMock()
    page_a = MagicMock()
    page_a.sources = []
    store.read_page = MagicMock(return_value=page_a)
    store.page_exists = MagicMock(return_value=True)

    ctx, _ = _make_ctx(audit_db=audit_db, store=store)
    result = await _resolve_stale_pages(ctx)

    assert len(result) == 1
    assert result[0]["source_path"] is None


# ---------------------------------------------------------------------------
# Test 3: poll_job success
# ---------------------------------------------------------------------------

async def test_poll_job_returns_success_on_terminal():
    """COMPLETED job returns status=success."""
    queue = MagicMock()
    job = MagicMock()
    job.status = JobStatus.COMPLETED
    queue.get_job = AsyncMock(return_value=job)

    ctx, _ = _make_ctx(queue=queue)
    result = await tool_poll_job(ctx, "job-1")
    assert result["status"] == "success"


# ---------------------------------------------------------------------------
# Test 4: poll_job timeout
# ---------------------------------------------------------------------------

async def test_poll_job_returns_timeout():
    """Elapsed >= timeout_seconds → status=timeout returned immediately."""
    queue = MagicMock()
    job = MagicMock()
    job.status = JobStatus.IN_PROGRESS
    queue.get_job = AsyncMock(return_value=job)

    ctx, _ = _make_ctx(queue=queue)
    with patch("synthadoc.agents.workflows._tools.asyncio.sleep", AsyncMock()):
        result = await tool_poll_job(ctx, "job-1", timeout_seconds=0)
    assert result["status"] == "timeout"


# ---------------------------------------------------------------------------
# Test 5: poll_job backoff intervals
# ---------------------------------------------------------------------------

async def test_poll_job_backoff_intervals():
    """Backoff: attempt 0 → sleep(1), attempt 1 → sleep(2)."""
    queue = MagicMock()
    call_count = 0

    async def _get_job(job_id):
        nonlocal call_count
        call_count += 1
        job = MagicMock()
        job.status = JobStatus.IN_PROGRESS if call_count <= 2 else JobStatus.COMPLETED
        return job

    queue.get_job = _get_job
    sleep_calls: list[float] = []

    async def _sleep(delay):
        sleep_calls.append(delay)

    ctx, _ = _make_ctx(queue=queue)
    with patch("synthadoc.agents.workflows._tools.asyncio.sleep", _sleep):
        result = await tool_poll_job(ctx, "job-1", timeout_seconds=120)

    assert result["status"] == "success"
    assert sleep_calls[0] == 1
    assert sleep_calls[1] == 2


# ---------------------------------------------------------------------------
# Test 6: confirm blocks and unblocks
# ---------------------------------------------------------------------------

async def test_confirm_tool_blocks_until_response():
    """confirm_request SSE is sent; gate.set() unblocks and returns confirmed=True."""
    ctx, events = _make_ctx()

    async def _resolve():
        await asyncio.sleep(0.05)
        gate = ctx.confirm_registry.get("s1")
        if gate:
            ctx.confirm_result_registry["s1"] = True
            gate.set()

    asyncio.create_task(_resolve())
    result = await tool_confirm(ctx, "Are you sure?")
    assert result["confirmed"] is True
    assert any(e["event"] == "confirm_request" for e in events)


async def test_confirm_tool_includes_diff_in_payload():
    """When diff is provided, it is included in the confirm_request SSE payload (line 787)."""
    ctx, events = _make_ctx()

    async def _resolve():
        await asyncio.sleep(0.05)
        gate = ctx.confirm_registry.get("s1")
        if gate:
            ctx.confirm_result_registry["s1"] = True
            gate.set()

    asyncio.create_task(_resolve())
    result = await tool_confirm(ctx, "Apply fix?", diff="--- a\n+++ b\n@@ -1 +1 @@\n-old\n+new")
    assert result["confirmed"] is True
    confirm_events = [e for e in events if e["event"] == "confirm_request"]
    assert confirm_events, "confirm_request SSE must be sent"
    assert "diff" in confirm_events[0]["data"], "diff must be in payload when provided"


# ---------------------------------------------------------------------------
# Test 7: _apply_single_fix — unit tests for the link replacement helper
# ---------------------------------------------------------------------------

def test_apply_single_fix_replaces_plain_link():
    content = "See [[typo-slug]] for details."
    new, n = _apply_single_fix(content, "typo-slug", "correct-slug")
    assert new == "See [[correct-slug]] for details."
    assert n == 1


def test_apply_single_fix_preserves_display_text():
    content = "See [[typo-slug|Display Name]] here."
    new, n = _apply_single_fix(content, "typo-slug", "correct-slug")
    assert new == "See [[correct-slug|Display Name]] here."
    assert n == 1


def test_apply_single_fix_removes_link_when_new_ref_is_none():
    content = "See [[dead-slug]] for details."
    new, n = _apply_single_fix(content, "dead-slug", None)
    assert "[[" not in new
    assert "dead-slug" in new  # display text preserved
    assert n == 1


def test_apply_single_fix_removes_link_keeps_display_text_when_none():
    content = "See [[dead-slug|Nice Name]] here."
    new, n = _apply_single_fix(content, "dead-slug", None)
    assert "[[" not in new
    assert "Nice Name" in new
    assert n == 1


def test_apply_single_fix_ignores_unrelated_links():
    content = "[[other-page]] and [[typo-slug]]"
    new, n = _apply_single_fix(content, "typo-slug", "fixed-slug")
    assert "[[other-page]]" in new
    assert "[[fixed-slug]]" in new
    assert n == 1


def test_apply_single_fix_case_insensitive():
    content = "See [[Typo Slug]] here."
    new, n = _apply_single_fix(content, "typo-slug", "correct-slug")
    assert "[[correct-slug]]" in new
    assert n == 1


# ---------------------------------------------------------------------------
# Test 8: tool_find_broken_wikilinks
# ---------------------------------------------------------------------------

def _make_page(content: str):
    page = MagicMock()
    page.content = content
    return page


async def test_find_broken_wikilinks_happy_path():
    """Broken link is detected; fuzzy suggestion provided when close match exists."""
    audit_db = MagicMock()
    audit_db.get_live_page_states = AsyncMock(
        return_value=[{"slug": "page-a", "state": "active"}]
    )
    store = MagicMock()
    store.all_slugs = MagicMock(return_value=["alan-turing", "ada-lovelace"])
    store.read_page = MagicMock(return_value=_make_page("See [[alan-tunring]] for details."))
    store.page_exists = MagicMock(return_value=True)

    ctx, events = _make_ctx(audit_db=audit_db, store=store)
    result = await tool_find_broken_wikilinks(ctx)

    assert result["total_broken"] == 1
    assert result["scanned"] == 1
    assert result["pages"][0]["slug"] == "page-a"
    broken = result["pages"][0]["broken_links"][0]
    assert broken["ref"] == "alan-tunring"
    assert broken["suggestion"] == "alan-turing"


async def test_find_broken_wikilinks_no_broken_links():
    """All wikilinks resolve — returns empty pages list."""
    audit_db = MagicMock()
    audit_db.get_live_page_states = AsyncMock(
        return_value=[{"slug": "page-a", "state": "active"}]
    )
    store = MagicMock()
    store.all_slugs = MagicMock(return_value=["alan-turing"])
    store.read_page = MagicMock(return_value=_make_page("See [[alan-turing]] here."))
    store.page_exists = MagicMock(return_value=True)

    ctx, _ = _make_ctx(audit_db=audit_db, store=store)
    result = await tool_find_broken_wikilinks(ctx)

    assert result["total_broken"] == 0
    assert result["pages"] == []


async def test_find_broken_wikilinks_no_suggestion_for_distant_slug():
    """No suggestion returned when the broken ref has no close fuzzy match."""
    audit_db = MagicMock()
    audit_db.get_live_page_states = AsyncMock(
        return_value=[{"slug": "page-a", "state": "active"}]
    )
    store = MagicMock()
    store.all_slugs = MagicMock(return_value=["completely-different"])
    store.read_page = MagicMock(return_value=_make_page("See [[xyz-nothing]] here."))
    store.page_exists = MagicMock(return_value=True)

    ctx, _ = _make_ctx(audit_db=audit_db, store=store)
    result = await tool_find_broken_wikilinks(ctx)

    assert result["total_broken"] == 1
    assert result["pages"][0]["broken_links"][0]["suggestion"] is None


async def test_find_broken_wikilinks_skips_stale_pages():
    """Stale pages are not included in the scan."""
    audit_db = MagicMock()
    audit_db.get_live_page_states = AsyncMock(
        return_value=[
            {"slug": "active-page", "state": "active"},
            {"slug": "stale-page",  "state": "stale"},
        ]
    )
    store = MagicMock()
    store.all_slugs = MagicMock(return_value=["real-slug"])

    def _read(slug):
        return _make_page(f"See [[broken-{slug}]] here.")

    store.read_page = MagicMock(side_effect=_read)
    store.page_exists = MagicMock(return_value=True)

    ctx, _ = _make_ctx(audit_db=audit_db, store=store)
    result = await tool_find_broken_wikilinks(ctx)

    scanned_slugs = [p["slug"] for p in result["pages"]]
    assert "stale-page" not in scanned_slugs
    assert result["scanned"] == 1


# ---------------------------------------------------------------------------
# Test 9: tool_apply_link_fixes
# ---------------------------------------------------------------------------

async def test_apply_link_fixes_happy_path():
    """Fixes are applied to page content and written back to the store."""
    page = _make_page("See [[typo-slug]] for details.")
    store = MagicMock()
    store.read_page = MagicMock(return_value=page)
    store.page_lock = MagicMock(return_value=MagicMock(__enter__=MagicMock(return_value=None), __exit__=MagicMock(return_value=False)))
    store.write_page = MagicMock()

    ctx, events = _make_ctx(store=store)
    result = await tool_apply_link_fixes(
        ctx, "page-a", [{"old_ref": "typo-slug", "new_ref": "correct-slug"}]
    )

    assert result["status"] == "success"
    assert result["changes"] == 1
    store.write_page.assert_called_once()
    assert any(e["event"] == "tool_progress" for e in events)


async def test_apply_link_fixes_page_not_found():
    """Returns error when the page slug does not exist."""
    store = MagicMock()
    store.read_page = MagicMock(return_value=None)

    ctx, _ = _make_ctx(store=store)
    result = await tool_apply_link_fixes(ctx, "missing", [{"old_ref": "x", "new_ref": "y"}])

    assert result["status"] == "error"
    assert "not found" in result["error"]


async def test_apply_link_fixes_no_changes():
    """Returns success with changes=0 when old_ref is not found in content."""
    store = MagicMock()
    store.read_page = MagicMock(return_value=_make_page("No wikilinks here."))
    store.page_lock = MagicMock(return_value=MagicMock(__enter__=MagicMock(return_value=None), __exit__=MagicMock(return_value=False)))

    ctx, _ = _make_ctx(store=store)
    result = await tool_apply_link_fixes(ctx, "page-a", [{"old_ref": "ghost", "new_ref": "target"}])

    assert result["status"] == "success"
    assert result["changes"] == 0
    store.write_page.assert_not_called() if hasattr(store, "write_page") else None


# ---------------------------------------------------------------------------
# Test 7: confirm timeout
# ---------------------------------------------------------------------------

async def test_confirm_tool_timeout():
    """asyncio.TimeoutError inside wait_for → confirmed=False."""
    ctx, _ = _make_ctx()

    async def _fake_wait_for(coro, timeout):
        coro.close()  # prevent "coroutine never awaited" warning
        raise asyncio.TimeoutError

    with patch("synthadoc.agents.workflows._tools.asyncio.wait_for", _fake_wait_for):
        result = await tool_confirm(ctx, "Are you sure?")
    assert result["confirmed"] is False


# ---------------------------------------------------------------------------
# Test 8: ingest_source outside wiki root
# ---------------------------------------------------------------------------

async def test_ingest_source_allows_paths_outside_wiki_root(tmp_path):
    """Paths outside wiki_root are allowed: the tool runs server-side and passes
    allow_external_paths=True to the queue so the worker handles them correctly.
    A missing file still returns an error (file-not-found), not a path error.
    """
    wiki_root = tmp_path / "wiki"
    outside = tmp_path / "elsewhere" / "file.md"  # absolute but not under wiki_root (and missing)

    events: list = []

    async def _send(e, d):
        events.append({"event": e, "data": d})

    ctx = WorkflowContext(
        session_id="s1",
        wiki_root=wiki_root,
        queue=MagicMock(),
        store=None,
        audit_db=None,
        send_sse_event=_send,
        confirm_registry={},
        confirm_result_registry={},
    )
    result = await tool_ingest_source(ctx, str(outside))
    # Must fail with "File not found", NOT "outside wiki root"
    assert "error" in result
    assert "outside wiki root" not in result["error"]
    assert "not found" in result["error"].lower() or "File not found" in result["error"]


# ---------------------------------------------------------------------------
# Test 9: ingest_source missing file
# ---------------------------------------------------------------------------

async def test_ingest_source_rejects_missing_file():
    """Non-existent source file → error key present."""
    queue = MagicMock()
    ctx, _ = _make_ctx(queue=queue)
    result = await tool_ingest_source(ctx, "/nonexistent_xyz_file_abc123.md")
    assert "error" in result


# ---------------------------------------------------------------------------
# Extra tests for coverage of tool_find_stale_pages, tool_run_lint,
# ingest happy path, and poll_job failed status.
# ---------------------------------------------------------------------------

async def test_tool_find_stale_pages_returns_wrapped_list():
    """tool_find_stale_pages wraps _resolve_stale_pages output in {"pages": [...]}."""
    audit_db = MagicMock()
    audit_db.get_live_page_states = AsyncMock(return_value=[])
    store = MagicMock()
    store.page_exists = MagicMock(return_value=True)
    ctx, _ = _make_ctx(audit_db=audit_db, store=store)
    result = await tool_find_stale_pages(ctx)
    assert "pages" in result
    assert result["pages"] == []


async def test_tool_find_stale_pages_returns_error_on_exception():
    """Exception inside _resolve_stale_pages → error key + empty pages list."""
    audit_db = MagicMock()
    audit_db.get_live_page_states = AsyncMock(side_effect=RuntimeError("db error"))
    store = MagicMock()
    ctx, _ = _make_ctx(audit_db=audit_db, store=store)
    result = await tool_find_stale_pages(ctx)
    assert "error" in result
    assert result["pages"] == []


async def test_tool_run_lint_enqueues_job():
    """tool_run_lint enqueues a lint job, polls it, and returns final status."""
    queue = MagicMock()
    queue.enqueue = AsyncMock(return_value="lint-001")
    completed_job = MagicMock()
    completed_job.status = JobStatus.COMPLETED
    queue.get_job = AsyncMock(return_value=completed_job)
    ctx, _ = _make_ctx(queue=queue)
    result = await tool_run_lint(ctx)
    assert result["status"] == "success"
    queue.enqueue.assert_called_once_with(
        "lint",
        {"scope": "all", "auto_resolve": False, "adversarial": False, "lifecycle": True},
    )


async def test_tool_run_lint_custom_scope():
    """tool_run_lint passes through a custom scope."""
    queue = MagicMock()
    queue.enqueue = AsyncMock(return_value="lint-002")
    completed_job = MagicMock()
    completed_job.status = JobStatus.COMPLETED
    queue.get_job = AsyncMock(return_value=completed_job)
    ctx, _ = _make_ctx(queue=queue)
    result = await tool_run_lint(ctx, scope="page-a")
    assert result["status"] == "success"
    queue.enqueue.assert_called_once_with(
        "lint",
        {"scope": "page-a", "auto_resolve": False, "adversarial": False, "lifecycle": True},
    )


async def test_ingest_source_enqueues_valid_file(tmp_path):
    """Valid in-root file → enqueued, polled, and success returned."""
    source_file = tmp_path / "raw" / "doc.md"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("hello")

    queue = MagicMock()
    queue.enqueue = AsyncMock(return_value="job-xyz")
    completed_job = MagicMock()
    completed_job.status = JobStatus.COMPLETED
    queue.get_job = AsyncMock(return_value=completed_job)

    events: list = []

    async def _send(e, d):
        events.append({"event": e, "data": d})

    ctx = WorkflowContext(
        session_id="s1",
        wiki_root=tmp_path,
        queue=queue,
        store=None,
        audit_db=None,
        send_sse_event=_send,
        confirm_registry={},
        confirm_result_registry={},
    )
    result = await tool_ingest_source(ctx, str(source_file))
    assert result["status"] == "success"
    assert result["job_id"] == "job-xyz"
    queue.enqueue.assert_called_once_with("ingest", {"source": str(source_file), "force": True, "bust_cache": False, "allow_external_paths": True})
    queue.get_job.assert_called_once_with("job-xyz")


async def test_poll_job_returns_failed_for_dead_status():
    """DEAD terminal status → status=failed."""
    queue = MagicMock()
    job = MagicMock()
    job.status = JobStatus.DEAD
    queue.get_job = AsyncMock(return_value=job)

    ctx, _ = _make_ctx(queue=queue)
    result = await tool_poll_job(ctx, "job-dead")
    assert result["status"] == "failed"


async def test_poll_job_handles_none_job():
    """get_job returns None then COMPLETED → keeps polling."""
    queue = MagicMock()
    call_count = 0

    async def _get_job(job_id):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return None
        job = MagicMock()
        job.status = JobStatus.COMPLETED
        return job

    queue.get_job = _get_job
    sleep_calls: list = []

    async def _sleep(delay):
        sleep_calls.append(delay)

    ctx, _ = _make_ctx(queue=queue)
    with patch("synthadoc.agents.workflows._tools.asyncio.sleep", _sleep):
        result = await tool_poll_job(ctx, "job-none", timeout_seconds=120)

    assert result["status"] == "success"
    assert len(sleep_calls) == 1


async def test_ingest_source_rejects_relative_path():
    """Relative path → error with 'absolute' in message."""
    ctx, _ = _make_ctx()
    result = await tool_ingest_source(ctx, "relative/path/file.md")
    assert "error" in result
    assert "absolute" in result["error"]


async def test_poll_job_returns_failed_on_queue_error():
    """Queue.get_job raising → status=failed with error message."""
    queue = MagicMock()
    queue.get_job = AsyncMock(side_effect=RuntimeError("db unavailable"))
    ctx, _ = _make_ctx(queue=queue)
    result = await tool_poll_job(ctx, "job-err", timeout_seconds=120)
    assert result["status"] == "failed"
    assert "db unavailable" in result["message"]


async def test_confirm_returns_false_when_send_sse_raises():
    """send_sse_event raising → confirmed=False, registry cleaned up."""
    async def _bad_send(e, d):
        raise RuntimeError("stream closed")

    ctx = WorkflowContext(
        session_id="s1",
        wiki_root=Path("/wiki"),
        queue=None, store=None, audit_db=None,
        send_sse_event=_bad_send,
        confirm_registry={},
        confirm_result_registry={},
    )
    result = await tool_confirm(ctx, "Proceed?")
    assert result["confirmed"] is False
    assert "s1" not in ctx.confirm_registry


async def test_confirm_cleanup_on_timeout():
    """Registry entries are cleaned up even on TimeoutError."""
    ctx, _ = _make_ctx()

    async def _fake_wait_for(coro, timeout):
        coro.close()  # prevent "coroutine never awaited" warning
        raise asyncio.TimeoutError

    with patch("synthadoc.agents.workflows._tools.asyncio.wait_for", _fake_wait_for):
        await tool_confirm(ctx, "OK?")
    assert "s1" not in ctx.confirm_registry
    assert "s1" not in ctx.confirm_result_registry


# ---------------------------------------------------------------------------
# _resolve_source_path helper
# ---------------------------------------------------------------------------

def test_resolve_source_path_absolute(tmp_path):
    """Absolute paths are returned unchanged."""
    p = str(tmp_path / "file.md")
    assert _resolve_source_path(tmp_path, p) == p


def test_resolve_source_path_relative_direct(tmp_path):
    """Relative path found directly under wiki_root → wiki_root / raw_file."""
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "a.md").write_text("x")
    result = _resolve_source_path(tmp_path, "raw/a.md")
    assert result == str(tmp_path / "raw" / "a.md")


def test_resolve_source_path_relative_raw_sources_fallback(tmp_path):
    """Relative path not found at wiki_root → retried under wiki_root/raw_sources/."""
    (tmp_path / "raw_sources" / "sub").mkdir(parents=True)
    (tmp_path / "raw_sources" / "sub" / "b.txt").write_text("x")
    result = _resolve_source_path(tmp_path, "sub/b.txt")
    assert result == str(tmp_path / "raw_sources" / "sub" / "b.txt")


# ---------------------------------------------------------------------------
# tool_find_page_source
# ---------------------------------------------------------------------------

async def test_find_page_source_happy_path(tmp_path):
    """Known slug with an absolute source path → slug and source_path returned."""
    src = tmp_path / "doc.md"
    src.write_text("content")

    store = MagicMock()
    source = MagicMock()
    source.file = str(src)
    page = MagicMock()
    page.sources = [source]
    store.read_page = MagicMock(return_value=page)

    ctx, events = _make_ctx(store=store)
    result = await tool_find_page_source(ctx, "my-slug")

    assert result == {"slug": "my-slug", "source_path": str(src)}
    assert any(e["event"] == "tool_progress" for e in events)


async def test_find_page_source_unknown_slug():
    """Unknown slug → error dict."""
    store = MagicMock()
    store.read_page = MagicMock(return_value=None)
    ctx, _ = _make_ctx(store=store)
    result = await tool_find_page_source(ctx, "no-such-page")
    assert "error" in result
    assert "no-such-page" in result["error"]


async def test_get_page_states_returns_state_for_each_slug():
    """tool_get_page_states maps each slug to its current lifecycle state."""
    audit_db = MagicMock()
    audit_db.get_page_state = AsyncMock(side_effect=lambda slug: {
        "slug": slug, "state": "active" if slug == "page-a" else "stale",
        "updated_at": "2026-01-01", "triggered_by": "lint",
    })
    ctx, events = _make_ctx(audit_db=audit_db)
    result = await tool_get_page_states(ctx, ["page-a", "page-b"])
    assert result == {"pages": [{"slug": "page-a", "state": "active"}, {"slug": "page-b", "state": "stale"}]}
    assert any(e["event"] == "tool_progress" for e in events)


async def test_get_page_states_returns_unknown_when_no_db_row():
    """Slug with no page_states row → state='unknown'."""
    audit_db = MagicMock()
    audit_db.get_page_state = AsyncMock(return_value=None)
    ctx, _ = _make_ctx(audit_db=audit_db)
    result = await tool_get_page_states(ctx, ["ghost-page"])
    assert result == {"pages": [{"slug": "ghost-page", "state": "unknown"}]}


async def test_get_page_states_handles_db_exception_gracefully():
    """DB error for a slug → state='unknown', no exception raised."""
    audit_db = MagicMock()
    audit_db.get_page_state = AsyncMock(side_effect=RuntimeError("db error"))
    ctx, _ = _make_ctx(audit_db=audit_db)
    result = await tool_get_page_states(ctx, ["some-page"])
    assert result == {"pages": [{"slug": "some-page", "state": "unknown"}]}


async def test_get_page_states_empty_slugs_list():
    """Empty slug list → empty pages list."""
    ctx, _ = _make_ctx()
    result = await tool_get_page_states(ctx, [])
    assert result == {"pages": []}


async def test_find_page_source_no_sources():
    """Page with empty sources list → error dict."""
    store = MagicMock()
    page = MagicMock()
    page.sources = []
    store.read_page = MagicMock(return_value=page)
    ctx, _ = _make_ctx(store=store)
    result = await tool_find_page_source(ctx, "no-source-page")
    assert "error" in result


# ---------------------------------------------------------------------------
# _resolve_source_path — URL passthrough (line 47)
# ---------------------------------------------------------------------------

def test_resolve_source_path_url_is_returned_unchanged():
    """HTTP and HTTPS URLs are returned as-is without any path manipulation."""
    url = "https://example.com/article"
    assert _resolve_source_path(Path("/wiki"), url) == url

    http_url = "http://example.com/page"
    assert _resolve_source_path(Path("/wiki"), http_url) == http_url


# ---------------------------------------------------------------------------
# tool_ingest_source — URL enqueue path (line 136) and failure branches
# ---------------------------------------------------------------------------

async def test_ingest_source_url_enqueues_and_succeeds():
    """URL source_path → label=URL, enqueue called, returns success on COMPLETED job."""
    url = "https://example.com/doc"
    queue = MagicMock()
    queue.enqueue = AsyncMock(return_value="job-url-1")
    completed_job = MagicMock()
    completed_job.status = JobStatus.COMPLETED
    queue.get_job = AsyncMock(return_value=completed_job)

    ctx, _ = _make_ctx(queue=queue)
    result = await tool_ingest_source(ctx, url)
    assert result["status"] == "success"
    call_kwargs = queue.enqueue.call_args[0]
    assert call_kwargs[1]["source"] == url


async def test_ingest_source_all_retries_fail_returns_error(tmp_path):
    """All enqueue attempts raise → error key returned; sleep is called for non-zero delays."""
    source_file = tmp_path / "doc.md"
    source_file.write_text("content")

    queue = MagicMock()
    queue.enqueue = AsyncMock(side_effect=RuntimeError("queue down"))

    ctx, _ = _make_ctx(queue=queue)
    with patch("synthadoc.agents.workflows._tools.asyncio.sleep", AsyncMock()):
        result = await tool_ingest_source(ctx, str(source_file))

    assert "error" in result
    assert "queue down" in result["error"]


async def test_ingest_source_failed_poll_returns_failed_status(tmp_path):
    """Enqueue succeeds but job ends with DEAD status → failure SSE progress and failed result."""
    source_file = tmp_path / "doc.md"
    source_file.write_text("content")

    queue = MagicMock()
    queue.enqueue = AsyncMock(return_value="job-fail-1")
    dead_job = MagicMock()
    dead_job.status = JobStatus.DEAD
    queue.get_job = AsyncMock(return_value=dead_job)

    ctx, events = _make_ctx(queue=queue)
    result = await tool_ingest_source(ctx, str(source_file))

    assert result["status"] == "failed"
    progress_msgs = [e["data"]["message"] for e in events if e["event"] == "tool_progress"
                     and e["data"].get("tool") == "ingest_source"]
    assert any("✗" in m or "failed" in m.lower() for m in progress_msgs)


async def test_ingest_source_timeout_poll_emits_timed_out_message(tmp_path):
    """Poll times out → status=timeout and SSE progress message says 'timed out'."""
    source_file = tmp_path / "doc.md"
    source_file.write_text("content")

    queue = MagicMock()
    queue.enqueue = AsyncMock(return_value="job-timeout-1")

    ctx, events = _make_ctx(queue=queue)
    timeout_result = {"status": "timeout", "message": "Job job-timeout-1 timed out after 300s"}
    with patch("synthadoc.agents.workflows._tools.tool_poll_job", AsyncMock(return_value=timeout_result)):
        result = await tool_ingest_source(ctx, str(source_file))

    assert result["status"] == "timeout"
    progress_msgs = [e["data"]["message"] for e in events if e["event"] == "tool_progress"
                     and e["data"].get("tool") == "ingest_source"]
    assert any("timed out" in m for m in progress_msgs)


# ---------------------------------------------------------------------------
# tool_run_lint — enqueue failure branch (lines 255-256)
# ---------------------------------------------------------------------------

async def test_tool_run_lint_returns_error_when_enqueue_fails():
    """Queue.enqueue raising → error key returned."""
    queue = MagicMock()
    queue.enqueue = AsyncMock(side_effect=RuntimeError("queue unavailable"))
    ctx, _ = _make_ctx(queue=queue)
    result = await tool_run_lint(ctx)
    assert "error" in result
    assert "queue unavailable" in result["error"]


# ---------------------------------------------------------------------------
# tool_get_lint_report (lines 276-301)
# ---------------------------------------------------------------------------

async def test_tool_get_lint_report_returns_full_structure():
    """Returns last_run, contradicted_pages, adversarial_warnings, orphan_slugs."""
    audit_db = MagicMock()
    audit_db.get_last_lint_summary = AsyncMock(return_value={
        "timestamp": "2026-07-01T10:00:00",
        "dangling_removed": 2,
        "orphans": 1,
        "contradictions_resolved": 0,
        "contradictions_flagged": 1,
    })
    audit_db.get_live_page_states = AsyncMock(return_value=[
        {"slug": "page-c", "state": "contradicted", "updated_at": "2026-07-01T09:00:00"},
        {"slug": "page-a", "state": "active", "updated_at": "2026-07-01"},
    ])

    store = MagicMock()
    store.page_exists = MagicMock(return_value=True)
    store.list_pages = MagicMock(return_value=["page-a", "page-c"])

    warned_page = MagicMock()
    warned_page.lint_warnings = ["adversarial content detected"]
    warned_page.orphan = False

    orphan_page = MagicMock()
    orphan_page.lint_warnings = []
    orphan_page.orphan = True

    def _read(slug):
        return warned_page if slug == "page-a" else orphan_page

    store.read_page = MagicMock(side_effect=_read)

    ctx, events = _make_ctx(audit_db=audit_db, store=store)
    result = await tool_get_lint_report(ctx)

    assert "last_run" in result
    assert result["last_run"]["dangling_removed"] == 2
    assert any(p["slug"] == "page-c" for p in result["contradicted_pages"])
    assert any(p["slug"] == "page-a" for p in result["adversarial_warnings"])
    assert "page-c" in result["orphan_slugs"]
    assert any(e["event"] == "tool_progress" for e in events)


async def test_tool_get_lint_report_with_no_audit_db():
    """When audit_db is None, returns empty last_run and empty lists."""
    store = MagicMock()
    store.list_pages = MagicMock(return_value=[])

    ctx, _ = _make_ctx(store=store)
    result = await tool_get_lint_report(ctx)

    assert result["last_run"] == {}
    assert result["contradicted_pages"] == []
    assert result["adversarial_warnings"] == []
    assert result["orphan_slugs"] == []


# ---------------------------------------------------------------------------
# tool_find_broken_wikilinks — page with no content branch (line 403)
# ---------------------------------------------------------------------------

async def test_find_broken_wikilinks_skips_page_with_none_content():
    """Active page whose read_page returns None is skipped silently."""
    audit_db = MagicMock()
    audit_db.get_live_page_states = AsyncMock(
        return_value=[{"slug": "null-page", "state": "active"}]
    )
    store = MagicMock()
    store.all_slugs = MagicMock(return_value=["real-slug"])
    store.read_page = MagicMock(return_value=None)
    store.page_exists = MagicMock(return_value=True)

    ctx, _ = _make_ctx(audit_db=audit_db, store=store)
    result = await tool_find_broken_wikilinks(ctx)

    assert result["total_broken"] == 0
    assert result["pages"] == []


async def test_find_broken_wikilinks_skips_page_with_empty_content():
    """Active page with empty content string is skipped silently."""
    audit_db = MagicMock()
    audit_db.get_live_page_states = AsyncMock(
        return_value=[{"slug": "empty-page", "state": "active"}]
    )
    store = MagicMock()
    store.all_slugs = MagicMock(return_value=["real-slug"])
    empty_page = MagicMock()
    empty_page.content = ""
    store.read_page = MagicMock(return_value=empty_page)
    store.page_exists = MagicMock(return_value=True)

    ctx, _ = _make_ctx(audit_db=audit_db, store=store)
    result = await tool_find_broken_wikilinks(ctx)

    assert result["total_broken"] == 0


# ---------------------------------------------------------------------------
# tool_find_broken_wikilinks — single-page mode (lines 433-434, 454, 483)
# ---------------------------------------------------------------------------

async def test_find_broken_wikilinks_single_page_mode_active():
    """Single-page mode returns results scoped to the requested active slug."""
    audit_db = MagicMock()
    audit_db.get_live_page_states = AsyncMock(
        return_value=[
            {"slug": "target-page", "state": "active"},
            {"slug": "other-page",  "state": "active"},
        ]
    )
    store = MagicMock()
    store.all_slugs = MagicMock(return_value=["target-page", "other-page"])
    store.page_exists = MagicMock(return_value=True)

    target = MagicMock()
    target.content = "Link to [[totally-nonexistent-slug]] here."
    target.title = "Target Title"
    store.read_page = MagicMock(return_value=target)

    ctx, _ = _make_ctx(audit_db=audit_db, store=store)
    result = await tool_find_broken_wikilinks(ctx, page_slug="target-page")

    # Single-page mode must include a page_title in the result
    assert "page_title" in result
    assert result["page_title"] == "Target Title"
    # Only the target was scanned
    assert result["scanned"] == 1
    assert result["total_broken"] == 1


async def test_find_broken_wikilinks_single_page_mode_inactive_returns_empty():
    """Single-page mode returns empty result when the requested slug is inactive."""
    audit_db = MagicMock()
    audit_db.get_live_page_states = AsyncMock(
        return_value=[{"slug": "inactive-page", "state": "stale"}]
    )
    store = MagicMock()
    store.all_slugs = MagicMock(return_value=["inactive-page"])
    store.page_exists = MagicMock(return_value=True)
    store.read_page = MagicMock()

    ctx, _ = _make_ctx(audit_db=audit_db, store=store)
    result = await tool_find_broken_wikilinks(ctx, page_slug="inactive-page")

    assert result["total_broken"] == 0
    assert result["pages"] == []
    assert result["scanned"] == 0


# ---------------------------------------------------------------------------
# tool_apply_link_fixes — empty old_ref skip branch (line 458)
# ---------------------------------------------------------------------------

async def test_apply_link_fixes_skips_fix_with_empty_old_ref():
    """Fixes whose old_ref is empty string are silently skipped (no changes)."""
    page = _make_page("See [[valid-link]] here.")
    store = MagicMock()
    store.read_page = MagicMock(return_value=page)

    ctx, _ = _make_ctx(store=store)
    result = await tool_apply_link_fixes(
        ctx, "page-a", [{"old_ref": "", "new_ref": "something"}]
    )

    assert result["status"] == "success"
    assert result["changes"] == 0


# ---------------------------------------------------------------------------
# tool_get_scaffold_preview (lines 489-506)
# ---------------------------------------------------------------------------

async def test_tool_get_scaffold_preview_returns_domain_and_standard_files(tmp_path):
    """Returns domain from ctx and lists the five standard scaffold files."""
    wiki_sub = tmp_path / "wiki"
    wiki_sub.mkdir()

    ctx, events = _make_ctx()
    # Rebuild ctx with real tmp_path and domain
    events2: list = []

    async def _send(e, d):
        events2.append({"event": e, "data": d})

    from synthadoc.agents.workflows._base import WorkflowContext
    ctx2 = WorkflowContext(
        session_id="s1",
        wiki_root=tmp_path,
        queue=None, store=None, audit_db=None,
        send_sse_event=_send,
        confirm_registry={}, confirm_result_registry={},
        domain="History",
    )

    result = await tool_get_scaffold_preview(ctx2)

    assert result["domain"] == "History"
    files = result["files_to_overwrite"]
    assert any("index.md" in f for f in files)
    assert any("purpose.md" in f for f in files)
    assert any("AGENTS.md" in f for f in files)
    assert any(e["event"] == "tool_progress" for e in events2)


async def test_tool_get_scaffold_preview_includes_routing_when_present(tmp_path):
    """ROUTING.md is appended to files_to_overwrite only when it already exists."""
    routing = tmp_path / "ROUTING.md"
    routing.write_text("# Routing")

    events: list = []

    async def _send(e, d):
        events.append({"event": e, "data": d})

    from synthadoc.agents.workflows._base import WorkflowContext
    ctx = WorkflowContext(
        session_id="s1",
        wiki_root=tmp_path,
        queue=None, store=None, audit_db=None,
        send_sse_event=_send,
        confirm_registry={}, confirm_result_registry={},
        domain="Science",
    )

    result = await tool_get_scaffold_preview(ctx)

    assert any("ROUTING.md" in f for f in result["files_to_overwrite"])


async def test_tool_get_scaffold_preview_defaults_domain_when_empty(tmp_path):
    """When ctx.domain is empty string, 'General' is used as the domain."""
    events: list = []

    async def _send(e, d):
        events.append({"event": e, "data": d})

    from synthadoc.agents.workflows._base import WorkflowContext
    ctx = WorkflowContext(
        session_id="s1",
        wiki_root=tmp_path,
        queue=None, store=None, audit_db=None,
        send_sse_event=_send,
        confirm_registry={}, confirm_result_registry={},
        domain="",
    )

    result = await tool_get_scaffold_preview(ctx)
    assert result["domain"] == "General"


# ---------------------------------------------------------------------------
# tool_run_scaffold (lines 519-547)
# ---------------------------------------------------------------------------

@patch("synthadoc.agents.workflows._tools.scaffold_output_paths",
       return_value=[Path("/wiki/index.md"), Path("/wiki/purpose.md")])
@patch("synthadoc.agents.workflows._tools.tool_confirm",
       new_callable=AsyncMock, return_value={"confirmed": True})
async def test_tool_run_scaffold_success(mock_confirm, mock_paths):
    """Confirmed by user, enqueue succeeds, job completes → success with job result."""
    queue = MagicMock()
    queue.enqueue = AsyncMock(return_value="scaffold-job-1")

    completed_job = MagicMock()
    completed_job.status = JobStatus.COMPLETED
    completed_job.result = {"categories_updated": 5, "routing_regenerated": True}
    queue.get_job = AsyncMock(return_value=completed_job)

    ctx, events = _make_ctx(queue=queue)
    result = await tool_run_scaffold(ctx, "Computing")

    assert result["status"] == "success"
    assert result["domain"] == "Computing"
    assert result["categories_updated"] == 5
    assert result["routing_regenerated"] is True
    assert any(e["event"] == "tool_progress" for e in events)
    mock_confirm.assert_awaited_once()


@patch("synthadoc.agents.workflows._tools.scaffold_output_paths",
       return_value=[Path("/wiki/index.md")])
@patch("synthadoc.agents.workflows._tools.tool_confirm",
       new_callable=AsyncMock, return_value={"confirmed": False})
async def test_tool_run_scaffold_cancelled_when_user_declines(mock_confirm, mock_paths):
    """User declines the confirmation dialog → cancelled status, enqueue never called."""
    queue = MagicMock()
    queue.enqueue = AsyncMock()

    ctx, _ = _make_ctx(queue=queue)
    result = await tool_run_scaffold(ctx, "Computing")

    assert result["status"] == "cancelled"
    assert "cancelled" in result.get("message", "").lower()
    queue.enqueue.assert_not_awaited()


@patch("synthadoc.agents.workflows._tools.scaffold_output_paths",
       return_value=[Path("/wiki/index.md")])
@patch("synthadoc.agents.workflows._tools.tool_confirm",
       new_callable=AsyncMock, return_value={"confirmed": True})
async def test_tool_run_scaffold_returns_error_when_enqueue_fails(mock_confirm, mock_paths):
    """Confirmed, but queue.enqueue raising → error key returned immediately."""
    queue = MagicMock()
    queue.enqueue = AsyncMock(side_effect=RuntimeError("scaffold queue full"))

    ctx, _ = _make_ctx(queue=queue)
    result = await tool_run_scaffold(ctx, "Science")

    assert "error" in result
    assert "scaffold queue full" in result["error"]


@patch("synthadoc.agents.workflows._tools.scaffold_output_paths",
       return_value=[Path("/wiki/index.md")])
@patch("synthadoc.agents.workflows._tools.tool_confirm",
       new_callable=AsyncMock, return_value={"confirmed": True})
async def test_tool_run_scaffold_returns_poll_result_when_job_fails(mock_confirm, mock_paths):
    """Confirmed, job ends with DEAD status → poll_result returned without scaffold result."""
    queue = MagicMock()
    queue.enqueue = AsyncMock(return_value="scaffold-dead-1")

    dead_job = MagicMock()
    dead_job.status = JobStatus.DEAD
    queue.get_job = AsyncMock(return_value=dead_job)

    ctx, _ = _make_ctx(queue=queue)
    result = await tool_run_scaffold(ctx, "History")

    assert result.get("status") == "failed"


@patch("synthadoc.agents.workflows._tools.scaffold_output_paths",
       return_value=[Path("/wiki/index.md")])
@patch("synthadoc.agents.workflows._tools.tool_confirm",
       new_callable=AsyncMock, return_value={"confirmed": True})
async def test_tool_run_scaffold_handles_get_job_exception_after_poll(mock_confirm, mock_paths):
    """Confirmed, second get_job call raises → exception swallowed, defaults returned."""
    queue = MagicMock()
    queue.enqueue = AsyncMock(return_value="scaffold-exc-1")

    call_count = 0

    async def _get_job(job_id):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            job = MagicMock()
            job.status = JobStatus.COMPLETED
            return job
        raise RuntimeError("db gone after poll")

    queue.get_job = _get_job

    ctx, events = _make_ctx(queue=queue)
    result = await tool_run_scaffold(ctx, "Art")

    assert result["status"] == "success"
    assert result["categories_updated"] == 0
    assert result["routing_regenerated"] is False


# ---------------------------------------------------------------------------
# _load_gate_threshold — config file paths (lines 843-847)
# ---------------------------------------------------------------------------

def test_load_gate_threshold_returns_value_from_config(tmp_path):
    """_load_gate_threshold reads adversarial_gate_threshold from a valid config.toml."""
    cfg_dir = tmp_path / ".synthadoc"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.toml").write_text(
        "[lint]\nadversarial_gate_threshold = 5\nadversarial_max_per_page = 5\n",
        encoding="utf-8",
    )
    result = _load_gate_threshold(tmp_path)
    assert result == 5


def test_load_gate_threshold_returns_none_for_malformed_config(tmp_path):
    """_load_gate_threshold returns None when the config file is unparseable (lines 846-847)."""
    cfg_dir = tmp_path / ".synthadoc"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.toml").write_text("not toml = {{{", encoding="utf-8")
    result = _load_gate_threshold(tmp_path)
    assert result is None


def test_load_gate_threshold_returns_none_when_no_config(tmp_path):
    """_load_gate_threshold returns None when config.toml does not exist."""
    result = _load_gate_threshold(tmp_path)
    assert result is None


# ---------------------------------------------------------------------------
# tool_transition_lifecycle — audit_db exception is swallowed (lines 1034-1035)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transition_lifecycle_set_page_state_exception_is_swallowed(tmp_path):
    """set_page_state DB failure does not abort tool_transition_lifecycle (lines 1034-1035)."""
    from synthadoc.agents.workflows._tools import tool_transition_lifecycle_state as tool_transition_lifecycle
    from synthadoc.storage.wiki import WikiPage, WikiStorage

    store = WikiStorage(tmp_path)
    page = WikiPage(
        title="P", tags=[], content="Body.", status="active",
        confidence="high", sources=[],
    )
    store.write_page("my-page", page)

    audit_db = MagicMock()
    audit_db.set_page_state = AsyncMock(side_effect=RuntimeError("DB down"))
    audit_db.record_lifecycle_event = AsyncMock()

    ctx, _ = _make_ctx(audit_db=audit_db, store=store)
    ctx.wiki_root = tmp_path

    result = await tool_transition_lifecycle(
        ctx,
        slug="my-page",
        to_state="stale",
        reason="test forced stale",
    )
    assert result["success"] is True
    # set_page_state raised but the result is still success
    audit_db.set_page_state.assert_awaited_once()
