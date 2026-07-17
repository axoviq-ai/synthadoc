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
    edges = [
        {"from_slug": "a", "to_slug": "b", "weight": 3, "edge_type": "mixed"},
        {"from_slug": "b", "to_slug": "a", "weight": 2, "edge_type": "co_source"},
    ]
    await db.write_graph(nodes, edges)
    result = await db.read_graph()
    assert result is not None
    assert len(result["nodes"]) == 2
    assert len(result["edges"]) == 2
    by_dir = {(e["from_slug"], e["to_slug"]): e for e in result["edges"]}
    assert by_dir[("a", "b")]["weight"] == 3
    assert by_dir[("a", "b")]["edge_type"] == "mixed"
    assert by_dir[("b", "a")]["edge_type"] == "co_source"
    # write_graph() defaults edge_type to 'mixed' when the key is absent
    await db.write_graph(nodes, [{"from_slug": "a", "to_slug": "b", "weight": 1}])
    result2 = await db.read_graph()
    assert result2["edges"][0]["edge_type"] == "mixed"


@pytest.mark.asyncio
async def test_graph_empty_returns_none(tmp_path):
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    result = await db.read_graph()
    assert result is None


@pytest.mark.asyncio
async def test_write_claim_citations_no_op_for_empty_list(tmp_path):
    """write_claim_citations with an empty list must return without writing any rows."""
    from synthadoc.storage.log import AuditDB
    import aiosqlite as _aiosqlite
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.record_claim_citations("some-slug", [])
    async with _aiosqlite.connect(tmp_path / "audit.db") as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM claim_citations")
        count = (await cur.fetchone())[0]
    assert count == 0


@pytest.mark.asyncio
async def test_schema_version_bumped(tmp_path):
    from synthadoc.storage.log import DB_SCHEMA_VERSION
    assert DB_SCHEMA_VERSION == 3
