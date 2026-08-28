# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Unit tests for server-side sensitive-data helpers in http_server.py.

Covers _retract_touched_pages (post-ingest scan) and the incremental
mtime-filter logic inside _run_sensitive_scan_loop.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _retract_touched_pages — post-ingest scan helper
# ---------------------------------------------------------------------------

def _build_mock_orch(security_enabled: bool, store_root: Path, queue_job):
    """Build a minimal Orchestrator mock sufficient for _retract_touched_pages."""
    orch = MagicMock()
    orch._cfg.security.sensitive_scan_enabled = security_enabled
    orch._store._root = store_root
    orch._queue.get_job = AsyncMock(return_value=queue_job)
    return orch


def _build_mock_job(status: str, pages_created=None, pages_updated=None):
    job = MagicMock()
    job.status = status
    job.result = {
        "pages_created": pages_created or [],
        "pages_updated": pages_updated or [],
    }
    return job


@pytest.mark.asyncio
async def test_retract_touched_pages_no_op_when_disabled(tmp_path):
    """No scanning when sensitive_scan_enabled is False."""
    from synthadoc.integration.http_server import _retract_touched_pages

    orch = _build_mock_orch(security_enabled=False, store_root=tmp_path, queue_job=None)
    audit_db = MagicMock(record_retract_event=AsyncMock())

    await _retract_touched_pages("job-1", orch, audit_db)

    # get_job must not be called — scan is disabled
    orch._queue.get_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_retract_touched_pages_no_op_when_job_not_completed(tmp_path):
    """No scanning when job status is not 'completed'."""
    from synthadoc.integration.http_server import _retract_touched_pages

    job = _build_mock_job(status="failed")
    orch = _build_mock_orch(security_enabled=True, store_root=tmp_path, queue_job=job)
    audit_db = MagicMock(record_retract_event=AsyncMock())

    await _retract_touched_pages("job-1", orch, audit_db)

    audit_db.record_retract_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_retract_touched_pages_no_op_when_no_touched_pages(tmp_path):
    """No scanning when both pages_created and pages_updated are empty."""
    from synthadoc.integration.http_server import _retract_touched_pages

    job = _build_mock_job(status="completed", pages_created=[], pages_updated=[])
    orch = _build_mock_orch(security_enabled=True, store_root=tmp_path, queue_job=job)
    audit_db = MagicMock(record_retract_event=AsyncMock())

    await _retract_touched_pages("job-1", orch, audit_db)

    audit_db.record_retract_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_retract_touched_pages_redacts_sensitive_content(tmp_path):
    """Sensitive data in a newly ingested page is masked and an audit event recorded."""
    from synthadoc.integration.http_server import _retract_touched_pages
    from synthadoc.config import SecurityConfig

    # Write a page with sensitive content
    page_path = tmp_path / "my-page.md"
    page_path.write_text("# My Page\n\napi_key = sk-abcdefghijklmnopqrst\n", encoding="utf-8")

    job = _build_mock_job(status="completed", pages_created=["my-page"])
    orch = _build_mock_orch(security_enabled=True, store_root=tmp_path, queue_job=job)
    orch._cfg.security = SecurityConfig(sensitive_scan_enabled=True)
    audit_db = MagicMock(record_retract_event=AsyncMock())

    await _retract_touched_pages("job-1", orch, audit_db)

    content = page_path.read_text(encoding="utf-8")
    assert "sk-abcdefghijklmnopqrst" not in content
    assert "[REDACTED]" in content
    audit_db.record_retract_event.assert_awaited_once()
    call_kwargs = audit_db.record_retract_event.await_args.kwargs
    assert call_kwargs["slug"] == "my-page"
    assert call_kwargs["applied"] is True


@pytest.mark.asyncio
async def test_retract_touched_pages_skips_missing_page_file(tmp_path):
    """Pages listed in the job result but absent on disk are silently skipped."""
    from synthadoc.integration.http_server import _retract_touched_pages
    from synthadoc.config import SecurityConfig

    job = _build_mock_job(status="completed", pages_created=["ghost-page"])
    orch = _build_mock_orch(security_enabled=True, store_root=tmp_path, queue_job=job)
    orch._cfg.security = SecurityConfig(sensitive_scan_enabled=True)
    audit_db = MagicMock(record_retract_event=AsyncMock())

    await _retract_touched_pages("job-1", orch, audit_db)  # must not raise

    audit_db.record_retract_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_retract_touched_pages_clean_page_no_event(tmp_path):
    """A clean page (no sensitive data) must not trigger an audit event."""
    from synthadoc.integration.http_server import _retract_touched_pages
    from synthadoc.config import SecurityConfig

    page_path = tmp_path / "clean-page.md"
    page_path.write_text("# Clean\n\nNothing sensitive here.\n", encoding="utf-8")

    job = _build_mock_job(status="completed", pages_created=["clean-page"])
    orch = _build_mock_orch(security_enabled=True, store_root=tmp_path, queue_job=job)
    orch._cfg.security = SecurityConfig(sensitive_scan_enabled=True)
    audit_db = MagicMock(record_retract_event=AsyncMock())

    await _retract_touched_pages("job-1", orch, audit_db)

    audit_db.record_retract_event.assert_not_awaited()
