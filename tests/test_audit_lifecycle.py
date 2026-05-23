# tests/test_audit_lifecycle.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from pathlib import Path
from synthadoc.storage.log import AuditDB


@pytest.fixture
async def db(tmp_path):
    d = AuditDB(tmp_path / "audit.db")
    await d.init()
    return d


async def test_set_and_get_page_state(db):
    await db.set_page_state("alan-turing", "draft", "ingest")
    row = await db.get_page_state("alan-turing")
    assert row["state"] == "draft"
    assert row["triggered_by"] == "ingest"
    # upsert
    await db.set_page_state("alan-turing", "active", "lint")
    row = await db.get_page_state("alan-turing")
    assert row["state"] == "active"


async def test_record_and_get_lifecycle_events(db):
    await db.record_lifecycle_event("alan-turing", None, "draft", "new page", "ingest")
    await db.record_lifecycle_event("alan-turing", "draft", "active", "lint passed", "lint")
    events = await db.get_lifecycle_events(slug="alan-turing")
    assert len(events) == 2
    assert events[0]["from_state"] is None
    assert events[1]["to_state"] == "active"


async def test_get_lifecycle_events_filter_by_state(db):
    await db.record_lifecycle_event("p1", None, "draft", "", "ingest")
    await db.record_lifecycle_event("p2", None, "draft", "", "ingest")
    await db.record_lifecycle_event("p2", "draft", "active", "", "lint")
    events = await db.get_lifecycle_events(to_state="draft")
    assert all(e["to_state"] == "draft" for e in events)
    assert len(events) == 2


async def test_get_lifecycle_summary(db):
    await db.set_page_state("p1", "draft", "ingest")
    await db.set_page_state("p2", "active", "lint")
    await db.set_page_state("p3", "active", "lint")
    await db.set_page_state("p4", "stale", "lint")
    summary = await db.get_lifecycle_summary()
    assert summary["draft"] == 1
    assert summary["active"] == 2
    assert summary["stale"] == 1
    assert summary.get("contradicted", 0) == 0


async def test_purge_before_date(db):
    await db.record_lifecycle_event("p1", None, "draft", "", "ingest")
    await db.record_lifecycle_event("p1", "draft", "active", "", "lint")
    await db.purge_lifecycle_events(before_date="2099-01-01")
    events = await db.get_lifecycle_events()
    assert events == []


async def test_purge_keep_latest(db):
    for i in range(5):
        await db.record_lifecycle_event("p1", "draft", "active", f"reason {i}", "lint")
    await db.purge_lifecycle_events(keep_latest=2)
    events = await db.get_lifecycle_events(slug="p1")
    assert len(events) == 2
    assert events[0]["reason"] == "reason 3"
    assert events[1]["reason"] == "reason 4"


async def test_get_lifecycle_events_pagination(db):
    for i in range(10):
        await db.record_lifecycle_event(f"p{i}", None, "draft", "", "ingest")
    page1 = await db.get_lifecycle_events(limit=5, offset=0)
    page2 = await db.get_lifecycle_events(limit=5, offset=5)
    assert len(page1) == 5
    assert len(page2) == 5
    assert {e["slug"] for e in page1}.isdisjoint({e["slug"] for e in page2})
