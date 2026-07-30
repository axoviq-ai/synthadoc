# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import pytest
import aiosqlite
from pathlib import Path

from synthadoc.storage.log import AuditDB, DB_SCHEMA_VERSION


# ── Task 1 tests ────────────────────────────────────────────────────────────

def test_schema_version_is_4():
    assert DB_SCHEMA_VERSION == 4


@pytest.mark.asyncio
async def test_schema_migration_adds_column(tmp_path: Path):
    """An existing v3 DB gains content_snapshot after AuditDB.init()."""
    db_path = tmp_path / "audit.db"
    # Seed a v3 schema (no content_snapshot column)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE lifecycle_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL,
                from_state TEXT,
                to_state TEXT NOT NULL,
                reason TEXT,
                triggered_by TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )""")
        await db.execute("PRAGMA user_version = 3")
        await db.commit()

    audit = AuditDB(db_path)
    await audit.init()

    async with aiosqlite.connect(db_path) as db:
        async with db.execute("PRAGMA table_info(lifecycle_events)") as cur:
            cols = [row[1] for row in await cur.fetchall()]
    assert "content_snapshot" in cols


@pytest.mark.asyncio
async def test_record_event_with_snapshot(tmp_path: Path):
    db_path = tmp_path / "audit.db"
    audit = AuditDB(db_path)
    await audit.init()

    await audit.record_lifecycle_event(
        "quantum-computing", "draft", "active", "reviewed", "user",
        content_snapshot="# Quantum Computing\n\nContent here.",
    )

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT content_snapshot FROM lifecycle_events"
        ) as cur:
            row = await cur.fetchone()
    assert row["content_snapshot"] == "# Quantum Computing\n\nContent here."


@pytest.mark.asyncio
async def test_record_event_without_snapshot_defaults_null(tmp_path: Path):
    db_path = tmp_path / "audit.db"
    audit = AuditDB(db_path)
    await audit.init()

    await audit.record_lifecycle_event(
        "my-page", "draft", "active", "reason", "user"
    )

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT content_snapshot FROM lifecycle_events"
        ) as cur:
            row = await cur.fetchone()
    assert row["content_snapshot"] is None


# ── Task 2 tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_page_snapshots_empty(tmp_path: Path):
    audit = AuditDB(tmp_path / "audit.db")
    await audit.init()
    assert await audit.list_page_snapshots("no-such-slug") == []


@pytest.mark.asyncio
async def test_list_page_snapshots_newest_first(tmp_path: Path):
    audit = AuditDB(tmp_path / "audit.db")
    await audit.init()
    for i, state in enumerate(["active", "archived", "draft"]):
        await audit.record_lifecycle_event(
            "my-page", "draft", state, f"r{i}", "user",
            content_snapshot=f"content {i}",
        )
    snapshots = await audit.list_page_snapshots("my-page")
    assert len(snapshots) == 3
    assert snapshots[0]["index"] == 1          # index 1 = newest
    assert snapshots[0]["to_state"] == "draft"  # third insert = newest


@pytest.mark.asyncio
async def test_list_page_snapshots_excludes_null(tmp_path: Path):
    audit = AuditDB(tmp_path / "audit.db")
    await audit.init()
    await audit.record_lifecycle_event("my-page", "draft", "active", "r", "user")  # NULL
    await audit.record_lifecycle_event(
        "my-page", "active", "archived", "r", "user", content_snapshot="content A"
    )
    snapshots = await audit.list_page_snapshots("my-page")
    assert len(snapshots) == 1
    assert snapshots[0]["to_state"] == "archived"


@pytest.mark.asyncio
async def test_list_page_snapshots_excludes_other_slugs(tmp_path: Path):
    audit = AuditDB(tmp_path / "audit.db")
    await audit.init()
    await audit.record_lifecycle_event(
        "page-a", "draft", "active", "r", "user", content_snapshot="A content"
    )
    await audit.record_lifecycle_event(
        "page-b", "draft", "active", "r", "user", content_snapshot="B content"
    )
    snapshots = await audit.list_page_snapshots("page-a")
    assert len(snapshots) == 1
    assert snapshots[0]["content_length"] == len("A content")


@pytest.mark.asyncio
async def test_get_snapshot_by_index_valid(tmp_path: Path):
    audit = AuditDB(tmp_path / "audit.db")
    await audit.init()
    await audit.record_lifecycle_event(
        "p", "draft", "active", "r", "user", content_snapshot="older body"
    )
    await audit.record_lifecycle_event(
        "p", "active", "archived", "r", "user", content_snapshot="newer body"
    )
    snap = await audit.get_snapshot_by_index("p", 1)  # 1 = newest
    assert snap is not None
    assert snap["content_snapshot"] == "newer body"
    assert snap["index"] == 1


@pytest.mark.asyncio
async def test_get_snapshot_by_index_out_of_range(tmp_path: Path):
    audit = AuditDB(tmp_path / "audit.db")
    await audit.init()
    await audit.record_lifecycle_event(
        "p", "draft", "active", "r", "user", content_snapshot="content"
    )
    assert await audit.get_snapshot_by_index("p", 99) is None


# ── Task 3 tests ────────────────────────────────────────────────────────────


def test_transition_stores_content_snapshot(tmp_wiki):
    """POST /lifecycle/transition captures page.content in the snapshot column."""
    import asyncio
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    from synthadoc.storage.log import AuditDB

    wiki_dir = tmp_wiki / "wiki"
    page_body = "The page body that should be snapshotted."
    (wiki_dir / "snap-test.md").write_text(
        f"---\ntitle: Snap Test\nstatus: draft\nconfidence: medium\n"
        f"tags: []\nsources: []\n---\n\n{page_body}\n",
        encoding="utf-8",
    )

    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.post("/lifecycle/transition", json={
            "slug": "snap-test",
            "to_state": "active",
            "reason": "verified",
        })
    assert resp.status_code == 200

    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")

    async def _check():
        await audit.init()
        snapshots = await audit.list_page_snapshots("snap-test")
        assert len(snapshots) == 1
        snap = await audit.get_snapshot_by_index("snap-test", 1)
        assert page_body in snap["content_snapshot"]

    asyncio.run(_check())


# ── Task 4 tests ────────────────────────────────────────────────────────────

def _make_wiki_with_snapshots(tmp_wiki):
    """Write a page with two lifecycle transitions so the audit DB has snapshots."""
    import asyncio
    from synthadoc.storage.log import AuditDB

    wiki_dir = tmp_wiki / "wiki"
    (wiki_dir / "hist-page.md").write_text(
        "---\ntitle: Hist\nstatus: draft\nconfidence: medium\ntags: []\nsources: []\n---\n\nBody v1.\n",
        encoding="utf-8",
    )
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")

    async def _seed():
        await audit.init()
        await audit.record_lifecycle_event(
            "hist-page", "draft", "active", "r1", "user",
            content_snapshot="Body v1.",
        )
        await audit.record_lifecycle_event(
            "hist-page", "active", "archived", "r2", "user",
            content_snapshot="Body v2.",
        )
    asyncio.run(_seed())


def test_history_endpoint_list(tmp_wiki):
    """GET /pages/{slug}/history returns a summary list, newest first."""
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    _make_wiki_with_snapshots(tmp_wiki)
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/pages/hist-page/history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["slug"] == "hist-page"
    snaps = data["snapshots"]
    assert len(snaps) == 2
    assert snaps[0]["index"] == 1          # newest first
    assert snaps[0]["to_state"] == "archived"
    assert "content_snapshot" not in snaps[0]  # content not in list view
    assert "content_length" in snaps[0]
    assert resp.headers.get("cache-control") == "no-store"


def test_history_endpoint_single_no_content(tmp_wiki):
    """GET /pages/{slug}/history?index=1 without include_content omits the body."""
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    _make_wiki_with_snapshots(tmp_wiki)
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/pages/hist-page/history?index=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["index"] == 1
    assert "content" not in data


def test_history_endpoint_single_with_content(tmp_wiki):
    """GET /pages/{slug}/history?index=1&include_content=true returns Markdown."""
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    _make_wiki_with_snapshots(tmp_wiki)
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/pages/hist-page/history?index=1&include_content=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data["index"] == 1
    assert "Body v2." in data["content"]  # index 1 = newest = archived snapshot


# ── Task 5 tests ────────────────────────────────────────────────────────────

def test_rollback_endpoint_restores_file(tmp_wiki):
    """POST /pages/{slug}/rollback writes the snapshot body back to the .md file."""
    import asyncio
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    from synthadoc.storage.log import AuditDB

    wiki_dir = tmp_wiki / "wiki"
    original_body = "This is the original body before editing."
    (wiki_dir / "rollback-page.md").write_text(
        f"---\ntitle: Rollback Test\nstatus: draft\nconfidence: medium\n"
        f"tags: []\nsources: []\n---\n\n{original_body}\n",
        encoding="utf-8",
    )

    # Seed one snapshot in the audit DB
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    async def _seed():
        await audit.init()
        await audit.record_lifecycle_event(
            "rollback-page", "draft", "active", "activated", "user",
            content_snapshot=original_body,
        )
    asyncio.run(_seed())

    # Now "accidentally edit" the page on disk
    (wiki_dir / "rollback-page.md").write_text(
        "---\ntitle: Rollback Test\nstatus: active\nconfidence: medium\n"
        "tags: []\nsources: []\n---\n\nThis is the WRONG body after editing.\n",
        encoding="utf-8",
    )

    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.post("/pages/rollback-page/rollback", json={
            "index": 1,
            "reason": "reverting accidental edit",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["slug"] == "rollback-page"
    assert data["snapshot_index"] == 1
    assert data["restored_chars"] == len(original_body)

    # Verify the file on disk now contains the original body
    on_disk = (wiki_dir / "rollback-page.md").read_text(encoding="utf-8")
    assert original_body in on_disk
    assert "WRONG body" not in on_disk


def test_rollback_endpoint_records_pre_rollback_snapshot(tmp_wiki):
    """The rollback event itself has content_snapshot = the pre-rollback body."""
    import asyncio
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    from synthadoc.storage.log import AuditDB

    wiki_dir = tmp_wiki / "wiki"
    pre_rollback_body = "Body that will be overwritten by rollback."
    (wiki_dir / "rb2-page.md").write_text(
        f"---\ntitle: RB2\nstatus: active\nconfidence: medium\ntags: []\nsources: []\n"
        f"---\n\n{pre_rollback_body}\n",
        encoding="utf-8",
    )
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    async def _seed():
        await audit.init()
        await audit.record_lifecycle_event(
            "rb2-page", "draft", "active", "activated", "user",
            content_snapshot="original snap body",
        )
    asyncio.run(_seed())

    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.post("/pages/rb2-page/rollback", json={
            "index": 1,
            "reason": "testing undo",
        })
    assert resp.status_code == 200
    rb_event_index = resp.json()["rollback_event_index"]

    async def _check():
        await audit.init()
        snap = await audit.get_snapshot_by_index("rb2-page", rb_event_index)
        assert snap is not None
        assert pre_rollback_body in snap["content_snapshot"]
    asyncio.run(_check())
