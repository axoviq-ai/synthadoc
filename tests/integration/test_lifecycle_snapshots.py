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
