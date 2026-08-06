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
    _resolve_stale_pages,
    tool_confirm,
    tool_find_stale_pages,
    tool_ingest_source,
    tool_poll_job,
    tool_run_lint,
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

async def test_ingest_source_rejects_outside_wiki_root(tmp_path):
    """Path outside wiki_root → error with 'outside wiki root'.

    Uses tmp_path so the path is a genuine OS-absolute path on all platforms.
    """
    wiki_root = tmp_path / "wiki"
    outside = tmp_path / "elsewhere" / "file.md"  # absolute but not under wiki_root

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
    assert "error" in result
    assert "outside wiki root" in result["error"]


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
    """tool_run_lint enqueues a lint job and returns the job_id."""
    queue = MagicMock()
    queue.enqueue = AsyncMock(return_value="lint-001")
    ctx, _ = _make_ctx(queue=queue)
    result = await tool_run_lint(ctx)
    assert result == {"job_id": "lint-001"}
    queue.enqueue.assert_called_once_with(
        "lint",
        {"scope": "all", "auto_resolve": False, "adversarial": False, "lifecycle": True},
    )


async def test_tool_run_lint_custom_scope():
    """tool_run_lint passes through a custom scope."""
    queue = MagicMock()
    queue.enqueue = AsyncMock(return_value="lint-002")
    ctx, _ = _make_ctx(queue=queue)
    result = await tool_run_lint(ctx, scope="page-a")
    assert result == {"job_id": "lint-002"}
    queue.enqueue.assert_called_once_with(
        "lint",
        {"scope": "page-a", "auto_resolve": False, "adversarial": False, "lifecycle": True},
    )


async def test_ingest_source_enqueues_valid_file(tmp_path):
    """Valid in-root file → job_id returned and enqueue called."""
    source_file = tmp_path / "raw" / "doc.md"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("hello")

    queue = MagicMock()
    queue.enqueue = AsyncMock(return_value="job-xyz")

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
    assert result == {"job_id": "job-xyz"}
    queue.enqueue.assert_called_once_with("ingest", {"source": str(source_file), "force": True})


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
