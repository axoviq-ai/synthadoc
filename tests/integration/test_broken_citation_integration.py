# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration tests for broken_citations count in /lifecycle/status."""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from synthadoc.storage.log import AuditDB
from synthadoc.integration.http_server import create_app
from synthadoc.storage.wiki import WikiPage, WikiStorage, SourceRef


def test_lifecycle_status_reports_broken_citations(tmp_wiki):
    """GET /lifecycle/status includes 'broken_citations' when active pages have broken markers."""
    # Page with a citation to a file not in sources[]
    page = WikiPage(
        title="Page A", tags=[],
        content="A claim.^[missing.txt:1-5]",
        status="active", confidence="high",
        sources=[SourceRef(file="real.txt", hash="x", size=1, ingested="2026-01-01")],
    )
    WikiStorage(tmp_wiki / "wiki").write_page("page-a", page)
    db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    asyncio.run(db.init())
    asyncio.run(db.set_page_state("page-a", "active", "ingest"))

    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/lifecycle/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("broken_citations", 0) >= 1, (
        "Expected broken_citations >= 1 in /lifecycle/status when a page has a broken marker"
    )


def test_lifecycle_status_no_broken_citations_when_all_valid(tmp_wiki):
    """GET /lifecycle/status omits 'broken_citations' when all citations are valid."""
    # Page with NO citations at all
    page = WikiPage(
        title="Clean Page", tags=[],
        content="This page has no citation markers.",
        status="active", confidence="high", sources=[],
    )
    WikiStorage(tmp_wiki / "wiki").write_page("clean-page", page)
    db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    asyncio.run(db.init())
    asyncio.run(db.set_page_state("clean-page", "active", "ingest"))

    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/lifecycle/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("broken_citations", 0) == 0, (
        "Expected broken_citations == 0 for a page with no citation markers"
    )
