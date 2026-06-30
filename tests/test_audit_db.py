# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
import aiosqlite
import asyncio


@pytest.mark.asyncio
async def test_graph_tables_created_on_init(tmp_path):
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    async with aiosqlite.connect(tmp_path / "audit.db") as conn:
        cur = await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in await cur.fetchall()}
    assert "graph_nodes" in tables
    assert "graph_edges" in tables


@pytest.mark.asyncio
async def test_graph_write_and_read_roundtrip(tmp_path):
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    nodes = [{"slug": "a", "cluster_id": 0}, {"slug": "b", "cluster_id": 1}]
    edges = [{"from_slug": "a", "to_slug": "b", "weight": 2}]
    await db.write_graph(nodes, edges)
    result = await db.read_graph()
    assert result is not None
    assert len(result["nodes"]) == 2
    assert len(result["edges"]) == 1
    assert result["edges"][0]["weight"] == 2


@pytest.mark.asyncio
async def test_graph_empty_returns_none(tmp_path):
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    result = await db.read_graph()
    assert result is None


@pytest.mark.asyncio
async def test_schema_version_bumped(tmp_path):
    from synthadoc.storage.log import DB_SCHEMA_VERSION
    assert DB_SCHEMA_VERSION == 2
