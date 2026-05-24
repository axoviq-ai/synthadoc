# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import asyncio
from synthadoc.storage.log import LogWriter, AuditDB


def test_log_md_append(tmp_wiki):
    writer = LogWriter(tmp_wiki / "wiki" / "log.md")
    writer.log_ingest(source="paper.pdf", pages_created=["new"],
                      pages_updated=["existing"], pages_flagged=[],
                      tokens=1000, cost_usd=0.01, cache_hits=2)
    content = (tmp_wiki / "wiki" / "log.md").read_text()
    assert "paper.pdf" in content
    assert "INGEST" in content


def test_audit_db_record_and_find(tmp_wiki):
    async def run():
        db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
        await db.init()
        await db.record_ingest(source_hash="abc123", source_size=1024,
                               source_path="paper.pdf", wiki_page="new-page",
                               tokens=1000, cost_usd=0.01)
        record = await db.find_by_hash("abc123", 1024)
        assert record is not None
        assert record["wiki_page"] == "new-page"
    asyncio.run(run())


def test_audit_db_hash_size_mismatch_returns_none(tmp_wiki):
    async def run():
        db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
        await db.init()
        await db.record_ingest("abc123", 1024, "paper.pdf", "page", 100, 0.01)
        result = await db.find_by_hash("abc123", 9999)
        assert result is None
    asyncio.run(run())


def test_get_all_page_states_empty(tmp_wiki):
    async def run():
        db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
        await db.init()
        pages = await db.get_all_page_states()
        assert pages == []
    asyncio.run(run())


def test_get_all_page_states_returns_slugs(tmp_wiki):
    async def run():
        db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
        await db.init()
        await db.set_page_state("alan-turing", "active", "ingest")
        await db.set_page_state("grace-hopper", "draft", "ingest")
        pages = await db.get_all_page_states()
        slugs = [p["slug"] for p in pages]
        assert "alan-turing" in slugs
        assert "grace-hopper" in slugs
        states = {p["slug"]: p["state"] for p in pages}
        assert states["alan-turing"] == "active"
        assert states["grace-hopper"] == "draft"
    asyncio.run(run())
