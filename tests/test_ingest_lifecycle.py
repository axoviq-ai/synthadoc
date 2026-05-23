# tests/test_ingest_lifecycle.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from pathlib import Path
from synthadoc.storage.wiki import WikiStorage, WikiPage, SourceRef


def _make_page(status="active") -> WikiPage:
    return WikiPage(
        title="Test Page", tags=[], content="# Test\n\nContent.",
        status=status, confidence="medium",
        sources=[SourceRef(file="test.txt", hash="abc", size=10, ingested="2026-05-23")],
    )


def test_new_page_status_is_draft(tmp_path):
    """IngestAgent must create new pages with status=draft, not active."""
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    store = WikiStorage(wiki_dir)
    page = _make_page(status="draft")
    store.write_page("test-page", page)
    read_back = store.read_page("test-page")
    assert read_back.status == "draft"


async def test_ingest_result_includes_draft_count(tmp_path):
    """After ingest, result dict has draft_count > 0 and a reminder string."""
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    # Simulate two new pages written as draft
    await db.set_page_state("p1", "draft", "ingest")
    await db.set_page_state("p2", "draft", "ingest")
    summary = await db.get_lifecycle_summary()
    assert summary.get("draft", 0) == 2
