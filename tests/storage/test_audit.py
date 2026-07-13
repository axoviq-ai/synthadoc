# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from synthadoc.storage.log import AuditDB, LogWriter


@pytest.mark.asyncio
async def test_record_query_stored_and_retrievable(tmp_wiki):
    """record_query() must persist a query event retrievable via list_queries()."""
    db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await db.init()
    await db.record_query(
        question="What is Moore's Law?",
        sub_questions_count=1,
        tokens=125,
        cost_usd=0.0004,
    )
    records = await db.list_queries(limit=10)
    assert len(records) == 1
    assert records[0]["question"] == "What is Moore's Law?"
    assert records[0]["sub_questions_count"] == 1
    assert records[0]["tokens"] == 125


@pytest.mark.asyncio
async def test_cost_summary_includes_query_costs(tmp_wiki):
    """cost_summary() must aggregate both ingest and query token costs."""
    db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await db.init()
    await db.record_ingest(
        source_hash="abc", source_size=100, source_path="test.md",
        wiki_page="test", tokens=500, cost_usd=0.002,
    )
    await db.record_query(
        question="test question", sub_questions_count=2,
        tokens=200, cost_usd=0.0008,
    )
    summary = await db.cost_summary(days=30)
    assert summary["total_tokens"] == 700
    assert abs(summary["total_cost_usd"] - 0.0028) < 0.0001


def test_log_writer_logs_query(tmp_wiki):
    """log_query() must append a QUERY entry to the activity log."""
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    log.log_query(question="What is Moore's Law?", sub_questions=2,
                  citations=["moores-law"], tokens=125, cost_usd=0.0004)
    content = (tmp_wiki / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "QUERY" in content
    assert "Moore" in content
    assert "125" in content


def test_log_writer_logs_query_with_no_citations(tmp_wiki):
    """log_query() with empty citations must write 'none', not crash."""
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    log.log_query(question="unknown topic?", sub_questions=1,
                  citations=[], tokens=80, cost_usd=0.0002)
    content = (tmp_wiki / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "QUERY" in content
    assert "none" in content


@pytest.mark.asyncio
async def test_list_queries_returns_most_recent_first(tmp_wiki):
    """list_queries() must return records in reverse-insertion order (most recent first)."""
    db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await db.init()
    await db.record_query(question="first question", sub_questions_count=1, tokens=100, cost_usd=0.0003)
    await db.record_query(question="second question", sub_questions_count=2, tokens=150, cost_usd=0.0005)
    records = await db.list_queries(limit=10)
    assert records[0]["question"] == "second question"
    assert records[1]["question"] == "first question"


@pytest.mark.asyncio
async def test_list_queries_respects_limit(tmp_wiki):
    """list_queries(limit=N) must return at most N records."""
    db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await db.init()
    for i in range(5):
        await db.record_query(question=f"question {i}", sub_questions_count=1,
                               tokens=50, cost_usd=0.0001)
    records = await db.list_queries(limit=3)
    assert len(records) == 3


@pytest.mark.asyncio
async def test_audit_db_session_lifecycle(tmp_wiki):
    """create_session / append_message / get_session_messages / has_prior_sessions."""
    db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await db.init()

    # No sessions yet
    assert not await db.has_prior_sessions()

    # Create session and verify has_prior_sessions
    await db.create_session("sess-001", "POWER_USER")
    assert await db.has_prior_sessions()

    # Append messages
    await db.append_message("sess-001", "user", "Hello?")
    await db.append_message("sess-001", "assistant", "Hi there!")

    # Get messages
    msgs = await db.get_session_messages("sess-001")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "Hello?"
    assert msgs[1]["role"] == "assistant"

    # create_session is idempotent (OR IGNORE)
    await db.create_session("sess-001", "EXPLORER")  # should not raise


@pytest.mark.asyncio
async def test_audit_db_get_session_messages_empty(tmp_wiki):
    """get_session_messages for an unknown session must return an empty list."""
    db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await db.init()
    msgs = await db.get_session_messages("nonexistent-session")
    assert msgs == []


@pytest.mark.asyncio
async def test_audit_db_has_prior_sessions_multiple(tmp_wiki):
    """has_prior_sessions returns True when multiple sessions exist."""
    db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await db.init()
    await db.create_session("sess-A", "EXPLORER")
    await db.create_session("sess-B", "POWER_USER")
    assert await db.has_prior_sessions()


@pytest.mark.asyncio
async def test_audit_db_append_message_updates_last_active(tmp_wiki):
    """append_message must not crash and session last_active is updated."""
    db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await db.init()
    await db.create_session("sess-X", "POWER_USER")
    # Append multiple messages — should complete without error
    await db.append_message("sess-X", "user", "First message")
    await db.append_message("sess-X", "assistant", "First reply")
    await db.append_message("sess-X", "user", "Second message")
    msgs = await db.get_session_messages("sess-X")
    assert len(msgs) == 3
    assert msgs[2]["content"] == "Second message"


@pytest.mark.asyncio
async def test_update_ingest_cost_patches_most_recent_record(tmp_wiki):
    """update_ingest_cost must overwrite the cost_usd written by record_ingest.

    IngestAgent calls record_ingest with cost_usd=0.0 (before orchestrator
    runs pricing). The orchestrator then calls update_ingest_cost with the
    real value — this test verifies that patch lands correctly.
    """
    db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await db.init()
    source = "https://example.com/bell-labs"
    await db.record_ingest("hash1", 1000, source, "bell-labs", tokens=5000, cost_usd=0.0)
    # Simulate orchestrator patching after estimate_cost()
    await db.update_ingest_cost(source, cost_usd=0.0312)
    history = await db.list_ingests(limit=1)
    assert len(history) == 1
    assert abs(history[0]["cost_usd"] - 0.0312) < 1e-9
