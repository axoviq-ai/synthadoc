# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Integration tests for POST /ingest and POST /action/confirm endpoints (Task 3)."""
from __future__ import annotations

import asyncio
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def app_client(tmp_path):
    """TestClient with a proper wiki directory and JobQueue.enqueue mocked."""
    from synthadoc.integration.http_server import create_app

    # Build a complete wiki root under a subdirectory so that tmp_path itself
    # is NOT the wiki root — this lets tests create paths in tmp_path that are
    # genuinely outside wiki_root.
    wiki_root = tmp_path / "wiki_root"
    wiki_root.mkdir()
    (wiki_root / "wiki").mkdir()
    (wiki_root / "raw_sources").mkdir()
    (wiki_root / "hooks").mkdir()
    (wiki_root / "skills").mkdir()
    sd = wiki_root / ".synthadoc"
    sd.mkdir()
    (sd / "logs").mkdir()
    # Pre-create DB files to avoid AV-scan delays on Windows CI.
    for _db in ("jobs.db", "cache.db"):
        with sqlite3.connect(sd / _db):
            pass

    app = create_app(wiki_root=wiki_root)
    with patch(
        "synthadoc.core.queue.JobQueue.enqueue",
        new=AsyncMock(return_value="abc12345"),
    ):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c, wiki_root


# ---------------------------------------------------------------------------
# POST /ingest — happy path
# ---------------------------------------------------------------------------

def test_post_ingest_queues_job_for_valid_source(app_client):
    """A source file inside wiki_root must be accepted and return a job_id."""
    client, wiki_root = app_client
    src = wiki_root / "raw_sources" / "file.md"
    src.write_text("# Test")
    resp = client.post("/ingest", json={"source_path": str(src)})
    assert resp.status_code == 200
    assert "job_id" in resp.json()


# ---------------------------------------------------------------------------
# POST /ingest — path outside wiki root → 403
# ---------------------------------------------------------------------------

def test_post_ingest_rejects_path_outside_wiki_root(app_client, tmp_path):
    """A source path outside wiki_root must be rejected with 403."""
    client, wiki_root = app_client
    # tmp_path is the parent of wiki_root, so anything directly under tmp_path
    # (but not under wiki_root) is genuinely outside the wiki.
    outside = tmp_path / "outside" / "file.md"
    outside.parent.mkdir()
    outside.write_text("# Bad")
    resp = client.post("/ingest", json={"source_path": str(outside)})
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /ingest — file does not exist → 404
# ---------------------------------------------------------------------------

def test_post_ingest_rejects_nonexistent_source(app_client):
    """A source path that does not exist on disk must return 404."""
    client, wiki_root = app_client
    resp = client.post(
        "/ingest",
        json={"source_path": str(wiki_root / "raw_sources" / "missing.md")},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /action/confirm — unknown session → 404
# ---------------------------------------------------------------------------

def test_action_confirm_unknown_session_returns_404(app_client):
    """A session_id with no entry in confirm_registry must return 404."""
    client, _ = app_client
    resp = client.post(
        "/action/confirm",
        json={"session_id": "unknown-session", "confirmed": True},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /action/confirm — already processed → 409
# ---------------------------------------------------------------------------

def test_action_confirm_already_processed_returns_409(app_client):
    """A session whose gate is already set must return 409."""
    client, _ = app_client
    gate = asyncio.Event()
    gate.set()  # already resolved
    client.app.state.confirm_registry["dup-session"] = gate
    resp = client.post(
        "/action/confirm",
        json={"session_id": "dup-session", "confirmed": True},
    )
    assert resp.status_code == 409
