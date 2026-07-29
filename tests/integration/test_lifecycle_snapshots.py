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
