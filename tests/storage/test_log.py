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


# ---------------------------------------------------------------------------
# strip_frontmatter — unclosed block (line 28)
# ---------------------------------------------------------------------------

def test_strip_frontmatter_returns_text_when_closing_marker_absent():
    """Text starting with --- but no closing --- → text returned unchanged (line 28)."""
    from synthadoc.storage.log import strip_frontmatter
    text = "---\ntitle: No Closing Marker\nThis text has no end fence"
    assert strip_frontmatter(text) == text


# ---------------------------------------------------------------------------
# Coverage: exception branches in AuditDB
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_citation_failures_handles_invalid_json_metadata(tmp_path):
    """Metadata that is not valid JSON → exception caught, empty dict used (lines 507-508)."""
    import aiosqlite
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    async with aiosqlite.connect(tmp_path / "audit.db") as conn:
        await conn.execute(
            "INSERT INTO audit_events (job_id, event, timestamp, metadata) VALUES (?,?,?,?)",
            ("job-bad", "citation_validation_failed", "2026-01-01T00:00:00", "NOT_VALID_JSON"),
        )
        await conn.commit()
    results = await db.list_citation_failures()
    assert len(results) == 1
    assert results[0]["page_slug"] is None
    assert results[0]["citation"] is None


@pytest.mark.asyncio
async def test_get_last_lint_summary_returns_none_for_invalid_json(tmp_path):
    """lint_complete event with invalid JSON metadata → returns None (lines 603-604)."""
    import aiosqlite
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    async with aiosqlite.connect(tmp_path / "audit.db") as conn:
        await conn.execute(
            "INSERT INTO audit_events (job_id, event, timestamp, metadata) VALUES (?,?,?,?)",
            ("job-lint", "lint_complete", "2026-01-01T00:00:00", "NOT_VALID_JSON"),
        )
        await conn.commit()
    result = await db.get_last_lint_summary()
    assert result is None


@pytest.mark.asyncio
async def test_get_snapshot_by_index_returns_none_when_row_not_found(tmp_path):
    """list_page_snapshots returns an ID that no longer exists → returns None (line 758)."""
    from unittest.mock import AsyncMock, patch
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    with patch.object(db, "list_page_snapshots", new=AsyncMock(return_value=[{"id": 99999}])):
        result = await db.get_snapshot_by_index("ghost-page", 1)
    assert result is None


@pytest.mark.asyncio
async def test_list_sessions_skips_sessions_without_user_messages(tmp_path):
    """Session with only assistant messages is excluded from results (line 1053)."""
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.create_session("s-assistant-only", "POWER_USER")
    await db.append_message("s-assistant-only", "assistant", "I am the assistant.")
    sessions = await db.list_sessions()
    assert not any(s["session_id"] == "s-assistant-only" for s in sessions)


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
    assert result[0]["first_q"] == "What is Turing?"
    assert result[0]["turn_count"] == 1
    assert result[0]["questions"] == ["What is Turing?"]


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
    assert result[0]["questions"] == ["Q1", "Q2"]
    assert result[0]["turn_count"] == 2
    assert result[0]["first_q"] == "Q1"


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


# ---------------------------------------------------------------------------
# list_retract_events — returns only retract_scan rows, newest first
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_retract_events_filters_and_orders(tmp_path):
    """list_retract_events returns only retract_scan rows in DESC id order.

    Mixed event types are inserted so we can confirm non-retract events are
    excluded even when they outnumber retract events.  The two retract events
    must appear newest-first (i.e. 'slug-b' before 'slug-a').
    """
    import aiosqlite, json
    from synthadoc.storage.log import AuditDB

    db = AuditDB(tmp_path / "audit.db")
    await db.init()

    # Insert events in order: lint_complete, retract_scan(slug-a),
    # lint_complete, retract_scan(slug-b), write_event(other type).
    async with aiosqlite.connect(tmp_path / "audit.db") as conn:
        for event, meta in [
            ("lint_complete",  json.dumps({"dangling_removed": 0})),
            ("retract_scan",   json.dumps({"slug": "slug-a", "matches_count": 1,
                                           "pattern_names": ["email"], "applied": True})),
            ("lint_complete",  json.dumps({"dangling_removed": 0})),
            ("retract_scan",   json.dumps({"slug": "slug-b", "matches_count": 3,
                                           "pattern_names": ["api_key"], "applied": False})),
            ("query_complete", json.dumps({"question": "irrelevant"})),
        ]:
            await conn.execute(
                "INSERT INTO audit_events (event, timestamp, metadata) VALUES (?,?,?)",
                (event, "2026-08-27T00:00:00", meta),
            )
        await conn.commit()

    results = await db.list_retract_events(limit=50)

    # Only retract_scan events returned
    assert len(results) == 2
    assert all(r["event"] == "retract_scan" for r in results)

    # Newest first: slug-b was inserted after slug-a
    slugs = [json.loads(r["metadata"])["slug"] for r in results]
    assert slugs == ["slug-b", "slug-a"]


@pytest.mark.asyncio
async def test_list_retract_events_limit_applies_to_filtered_set(tmp_path):
    """limit operates on retract_scan rows only, not on all audit_events.

    Insert 3 non-retract events followed by 2 retract events.  With limit=1
    we should still get the single most-recent retract event (not 0).
    """
    import aiosqlite, json
    from synthadoc.storage.log import AuditDB

    db = AuditDB(tmp_path / "audit.db")
    await db.init()

    async with aiosqlite.connect(tmp_path / "audit.db") as conn:
        # 3 non-retract events (would exhaust a naïve global LIMIT 1)
        for _ in range(3):
            await conn.execute(
                "INSERT INTO audit_events (event, timestamp, metadata) VALUES (?,?,?)",
                ("lint_complete", "2026-08-27T00:00:00", "{}"),
            )
        # 2 retract_scan events
        for slug in ("slug-first", "slug-second"):
            await conn.execute(
                "INSERT INTO audit_events (event, timestamp, metadata) VALUES (?,?,?)",
                ("retract_scan", "2026-08-27T00:00:00",
                 json.dumps({"slug": slug, "matches_count": 1,
                             "pattern_names": [], "applied": False})),
            )
        await conn.commit()

    results = await db.list_retract_events(limit=1)

    assert len(results) == 1
    assert results[0]["event"] == "retract_scan"
    assert json.loads(results[0]["metadata"])["slug"] == "slug-second"


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


@pytest.mark.asyncio
async def test_delete_graph_node_removes_node_and_edges(tmp_path):
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()

    # Seed graph
    await db.write_graph(
        nodes=[
            {"slug": "alpha", "cluster_id": 0},
            {"slug": "beta",  "cluster_id": 0},
            {"slug": "gamma", "cluster_id": 1},
        ],
        edges=[
            {"from_slug": "alpha", "to_slug": "beta",  "weight": 1.0},
            {"from_slug": "gamma", "to_slug": "alpha", "weight": 1.0},
            {"from_slug": "beta",  "to_slug": "gamma", "weight": 1.0},
        ],
    )

    await db.delete_graph_node("alpha")

    graph = await db.read_graph()
    slugs = {n["slug"] for n in graph["nodes"]}
    assert "alpha" not in slugs
    # All edges to or from alpha gone
    for e in graph["edges"]:
        assert e["from_slug"] != "alpha"
        assert e["to_slug"] != "alpha"
    # Unrelated edge preserved
    assert any(e["from_slug"] == "beta" and e["to_slug"] == "gamma" for e in graph["edges"])


@pytest.mark.asyncio
async def test_list_all_session_ids_returns_all_ids(tmp_path):
    """list_all_session_ids() must return every session currently in the DB."""
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()

    assert await db.list_all_session_ids() == set()

    await db.create_session("s1", "POWER_USER")
    await db.create_session("s2", "EXPLORER")
    await db.create_session("s3", "NEW_WIKI")

    ids = await db.list_all_session_ids()
    assert ids == {"s1", "s2", "s3"}


@pytest.mark.asyncio
async def test_list_all_session_ids_after_purge_excludes_deleted(tmp_path):
    """list_all_session_ids() must not return sessions that were purged from the DB."""
    import aiosqlite
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()

    await db.create_session("old", "POWER_USER")
    await db.create_session("recent", "POWER_USER")

    # Back-date the old session so purge_old_sessions removes it
    async with aiosqlite.connect(tmp_path / "audit.db") as conn:
        await conn.execute(
            "UPDATE chat_sessions SET last_active=? WHERE session_id=?",
            ("2020-01-01T00:00:00", "old"),
        )
        await conn.commit()

    await db.purge_old_sessions(retention_days=30)

    ids = await db.list_all_session_ids()
    assert "old" not in ids
    assert "recent" in ids


@pytest.mark.asyncio
async def test_delete_graph_node_no_op_when_slug_absent(tmp_path):
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()

    await db.write_graph(
        nodes=[{"slug": "only", "cluster_id": 0}],
        edges=[],
    )
    # Should not raise even if slug not in graph
    await db.delete_graph_node("nonexistent")

    graph = await db.read_graph()
    assert len(graph["nodes"]) == 1


# ---------------------------------------------------------------------------
# count_citations / count_citation_failures
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_claim_citations_replaces_on_reingest(tmp_path):
    """Re-ingesting a page must replace its citations, not accumulate duplicates."""
    db = AuditDB(tmp_path / "audit.db")
    await db.init()

    citations_v1 = [
        {"source_file": "src.txt", "line_start": 1, "line_end": 1, "claim_excerpt": "c1"},
        {"source_file": "src.txt", "line_start": 2, "line_end": 2, "claim_excerpt": "c2"},
    ]
    citations_v2 = [
        {"source_file": "src.txt", "line_start": 1, "line_end": 1, "claim_excerpt": "c1-updated"},
    ]

    await db.record_claim_citations("edsac", citations_v1)
    assert await db.count_citations(page_slug="edsac") == 2

    # Re-ingest: must replace, not append
    await db.record_claim_citations("edsac", citations_v2)
    assert await db.count_citations(page_slug="edsac") == 1

    rows = await db.list_citations(page_slug="edsac")
    assert rows[0]["claim_excerpt"] == "c1-updated"


@pytest.mark.asyncio
async def test_count_citations_empty(tmp_path):
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    assert await db.count_citations() == 0


@pytest.mark.asyncio
async def test_count_citations_matches_inserted(tmp_path):
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.record_claim_citations("turing", [
        {"source_file": "bio.txt", "line_start": 1, "line_end": 5, "claim_excerpt": "c1"},
        {"source_file": "bio.txt", "line_start": 6, "line_end": 10, "claim_excerpt": "c2"},
    ])
    await db.record_claim_citations("hopper", [
        {"source_file": "hist.txt", "line_start": 1, "line_end": 3, "claim_excerpt": "c3"},
    ])
    assert await db.count_citations() == 3


@pytest.mark.asyncio
async def test_count_citations_filter_by_page_slug(tmp_path):
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.record_claim_citations("turing", [
        {"source_file": "a.txt", "line_start": 1, "line_end": 2, "claim_excerpt": "x"},
        {"source_file": "a.txt", "line_start": 3, "line_end": 4, "claim_excerpt": "y"},
    ])
    await db.record_claim_citations("hopper", [
        {"source_file": "b.txt", "line_start": 1, "line_end": 2, "claim_excerpt": "z"},
    ])
    assert await db.count_citations(page_slug="turing") == 2
    assert await db.count_citations(page_slug="hopper") == 1
    assert await db.count_citations(page_slug="nobody") == 0


@pytest.mark.asyncio
async def test_count_citations_filter_by_source_file(tmp_path):
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.record_claim_citations("turing", [
        {"source_file": "bio.txt", "line_start": 1, "line_end": 2, "claim_excerpt": "x"},
        {"source_file": "paper.txt", "line_start": 3, "line_end": 4, "claim_excerpt": "y"},
    ])
    assert await db.count_citations(source_file="bio.txt") == 1
    assert await db.count_citations(source_file="paper.txt") == 1


@pytest.mark.asyncio
async def test_count_citation_failures_empty(tmp_path):
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    assert await db.count_citation_failures() == 0


@pytest.mark.asyncio
async def test_count_citation_failures_matches_events(tmp_path):
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.write_event("citation_validation_failed",
                         metadata={"slug": "p1", "citation": "^[x]", "reason": "broken"})
    await db.write_event("citation_validation_failed",
                         metadata={"slug": "p1", "citation": "^[y]", "reason": "broken"})
    await db.write_event("ingest_complete",
                         metadata={"slug": "p1"})  # different event, must not be counted
    assert await db.count_citation_failures() == 2


@pytest.mark.asyncio
async def test_count_citation_failures_filter_by_page_slug(tmp_path):
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.write_event("citation_validation_failed",
                         metadata={"page_slug": "turing", "citation": "^[a]", "reason": "r"})
    await db.write_event("citation_validation_failed",
                         metadata={"page_slug": "hopper", "citation": "^[b]", "reason": "r"})
    assert await db.count_citation_failures(page_slug="turing") == 1
    assert await db.count_citation_failures(page_slug="hopper") == 1
    assert await db.count_citation_failures(page_slug="nobody") == 0


@pytest.mark.asyncio
async def test_record_retract_event(tmp_path):
    import json
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.record_retract_event(
        slug="ada-lovelace",
        matches_count=2,
        pattern_names=["api_key", "email"],
        applied=True,
    )
    events, total = await db.list_events(limit=10)
    assert total == 1
    evt = events[0]
    assert evt["event"] == "retract_scan"
    meta = json.loads(evt["metadata"])
    assert meta["slug"] == "ada-lovelace"
    assert meta["matches_count"] == 2
    assert "api_key" in meta["pattern_names"]
    assert meta["applied"] is True


@pytest.mark.asyncio
async def test_record_retract_event_no_matches(tmp_path):
    import json
    from synthadoc.storage.log import AuditDB
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.record_retract_event(
        slug="empty-page", matches_count=0, pattern_names=[], applied=False,
    )
    events, total = await db.list_events()
    assert total == 1
    meta = json.loads(events[0]["metadata"])
    assert meta["matches_count"] == 0
    assert meta["applied"] is False
