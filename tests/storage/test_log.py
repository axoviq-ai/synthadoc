# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import asyncio
import pytest
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


@pytest.mark.asyncio
async def test_get_history_returns_last_n_turns(tmp_path):
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.create_session("s1", "POWER_USER")
    for i in range(8):
        await db.append_message("s1", "user", f"q{i}")
        await db.append_message("s1", "assistant", f"a{i}")
    result = await db.get_history("s1", turns=3)
    assert len(result) == 6
    assert result[0]["content"] == "q5"
    assert result[-1]["content"] == "a7"


@pytest.mark.asyncio
async def test_get_history_unknown_session_returns_empty(tmp_path):
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    result = await db.get_history("nonexistent", turns=5)
    assert result == []


@pytest.mark.asyncio
async def test_get_history_zero_turns_returns_empty(tmp_path):
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.create_session("s1", "POWER_USER")
    await db.append_message("s1", "user", "hello")
    result = await db.get_history("s1", turns=0)
    assert result == []


@pytest.mark.asyncio
async def test_update_and_get_summary(tmp_path):
    import aiosqlite
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.create_session("s1", "POWER_USER")
    await db.update_summary("s1", "Earlier: user asked about Turing.", covered_turns=3)
    summary, covered = await db.get_summary("s1")
    assert summary == "Earlier: user asked about Turing."
    assert covered == 3


@pytest.mark.asyncio
async def test_get_summary_unknown_session_returns_none(tmp_path):
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    summary, covered = await db.get_summary("nonexistent")
    assert summary is None
    assert covered == 0


@pytest.mark.asyncio
async def test_purge_old_sessions_removes_inactive(tmp_path):
    import aiosqlite
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.create_session("old", "POWER_USER")
    await db.create_session("recent", "POWER_USER")
    async with aiosqlite.connect(tmp_path / "audit.db") as conn:
        await conn.execute(
            "UPDATE chat_sessions SET last_active=? WHERE session_id=?",
            ("2020-01-01T00:00:00", "old"),
        )
        await conn.commit()
    purged = await db.purge_old_sessions(retention_days=30)
    assert purged == 1
    async with aiosqlite.connect(tmp_path / "audit.db") as conn:
        async with conn.execute("SELECT session_id FROM chat_sessions") as cur:
            rows = await cur.fetchall()
    session_ids = [r[0] for r in rows]
    assert "old" not in session_ids
    assert "recent" in session_ids


@pytest.mark.asyncio
async def test_purge_cascades_messages(tmp_path):
    import aiosqlite
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.create_session("old", "POWER_USER")
    await db.append_message("old", "user", "hello")
    async with aiosqlite.connect(tmp_path / "audit.db") as conn:
        await conn.execute(
            "UPDATE chat_sessions SET last_active=? WHERE session_id=?",
            ("2020-01-01T00:00:00", "old"),
        )
        await conn.commit()
    await db.purge_old_sessions(retention_days=30)
    async with aiosqlite.connect(tmp_path / "audit.db") as conn:
        async with conn.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE session_id=?", ("old",)
        ) as cur:
            count = (await cur.fetchone())[0]
    assert count == 0


@pytest.mark.asyncio
async def test_get_all_messages_returns_all_oldest_first(tmp_path):
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.create_session("s1", "POWER_USER")
    await db.append_message("s1", "user", "first")
    await db.append_message("s1", "assistant", "second")
    await db.append_message("s1", "user", "third")
    result = await db.get_all_messages("s1")
    assert len(result) == 3
    assert result[0]["content"] == "first"
    assert result[2]["content"] == "third"
    # new fields always present
    assert result[0]["citations"] == []
    assert result[0]["gap_suggestions"] == []


@pytest.mark.asyncio
async def test_append_message_stores_citations(tmp_path):
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.create_session("s1", "POWER_USER")
    await db.append_message("s1", "user", "Who is Turing?")
    await db.append_message(
        "s1", "assistant", "Alan Turing was a mathematician.",
        citations=["alan-turing", "computing-pioneers"],
    )
    result = await db.get_all_messages("s1")
    assert result[1]["citations"] == ["alan-turing", "computing-pioneers"]
    assert result[1]["gap_suggestions"] == []


@pytest.mark.asyncio
async def test_append_message_stores_gap_suggestions(tmp_path):
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.create_session("s1", "POWER_USER")
    await db.append_message("s1", "user", "Why did Turing die?")
    await db.append_message(
        "s1", "assistant", "The wiki does not cover this.",
        gap_suggestions=["Alan Turing death cause", "Alan Turing 1954 cyanide"],
    )
    result = await db.get_all_messages("s1")
    assert result[1]["gap_suggestions"] == ["Alan Turing death cause", "Alan Turing 1954 cyanide"]
    assert result[1]["citations"] == []


@pytest.mark.asyncio
async def test_append_message_no_metadata_returns_empty_lists(tmp_path):
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.create_session("s1", "POWER_USER")
    await db.append_message("s1", "user", "hello")
    await db.append_message("s1", "assistant", "hi")
    result = await db.get_all_messages("s1")
    assert result[0]["citations"] == []
    assert result[0]["gap_suggestions"] == []
    assert result[1]["citations"] == []
    assert result[1]["gap_suggestions"] == []


@pytest.mark.asyncio
async def test_list_sessions_empty_returns_empty(tmp_path):
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    result = await db.list_sessions()
    assert result == []


@pytest.mark.asyncio
async def test_list_sessions_excludes_sessions_without_messages(tmp_path):
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.create_session("empty", "POWER_USER")
    result = await db.list_sessions()
    assert result == []


@pytest.mark.asyncio
async def test_list_sessions_returns_sessions_with_user_turns(tmp_path):
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.create_session("s1", "POWER_USER")
    await db.append_message("s1", "user", "What is Turing?")
    await db.append_message("s1", "assistant", "A mathematician.")
    result = await db.list_sessions()
    assert len(result) == 1
    assert result[0]["session_id"] == "s1"
    assert result[0]["mode"] == "POWER_USER"
    assert result[0]["turns"] == ["What is Turing?"]


@pytest.mark.asyncio
async def test_list_sessions_multi_turn_collects_all_user_turns(tmp_path):
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.create_session("s1", "WIKI_QUERY")
    await db.append_message("s1", "user", "Q1")
    await db.append_message("s1", "assistant", "A1")
    await db.append_message("s1", "user", "Q2")
    await db.append_message("s1", "assistant", "A2")
    result = await db.list_sessions()
    assert len(result) == 1
    assert result[0]["turns"] == ["Q1", "Q2"]


@pytest.mark.asyncio
async def test_list_sessions_respects_limit(tmp_path):
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    for i in range(5):
        sid = f"s{i}"
        await db.create_session(sid, "POWER_USER")
        await db.append_message(sid, "user", f"question {i}")
    result = await db.list_sessions(limit=3)
    assert len(result) == 3


@pytest.mark.asyncio
async def test_list_sessions_multiple_sessions_ordered_by_last_active(tmp_path):
    import aiosqlite
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.create_session("old", "POWER_USER")
    await db.append_message("old", "user", "old question")
    await db.create_session("new", "POWER_USER")
    await db.append_message("new", "user", "new question")
    async with aiosqlite.connect(tmp_path / "audit.db") as conn:
        await conn.execute(
            "UPDATE chat_sessions SET last_active=? WHERE session_id=?",
            ("2020-01-01T00:00:00", "old"),
        )
        await conn.commit()
    result = await db.list_sessions()
    assert result[0]["session_id"] == "new"
    assert result[1]["session_id"] == "old"
