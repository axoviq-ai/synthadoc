# tests/test_http_sessions.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import asyncio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from synthadoc.storage.log import AuditDB


def _make_sessions_app(db: AuditDB) -> FastAPI:
    app = FastAPI()

    @app.get("/sessions")
    async def list_sessions(limit: int = 20):
        return await db.list_sessions(limit=limit)

    @app.get("/sessions/{session_id}/messages")
    async def get_session_messages(session_id: str):
        return await db.get_all_messages(session_id)

    @app.get("/hints")
    async def get_hints(mode: str = "POWER_USER"):
        from synthadoc.agents.hint_engine import HintEngine
        return {"hints": HintEngine.initial_hints(mode)}

    return app


@pytest.fixture
def client_and_db(tmp_path):
    db = AuditDB(tmp_path / "audit.db")
    asyncio.run(db.init())
    app = _make_sessions_app(db)
    return TestClient(app), db


def test_get_sessions_empty(client_and_db):
    client, _ = client_and_db
    resp = client.get("/sessions")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_sessions_returns_session_with_turns(client_and_db):
    client, db = client_and_db
    asyncio.run(db.create_session("s1", "POWER_USER"))
    asyncio.run(db.append_message("s1", "user", "What is Turing?"))
    asyncio.run(db.append_message("s1", "assistant", "A mathematician."))
    resp = client.get("/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["session_id"] == "s1"
    assert data[0]["questions"] == ["What is Turing?"]
    assert data[0]["first_q"] == "What is Turing?"
    assert data[0]["turn_count"] == 1


def test_get_sessions_limit_param(client_and_db):
    client, db = client_and_db
    for i in range(4):
        asyncio.run(db.create_session(f"s{i}", "WIKI_QUERY"))
        asyncio.run(db.append_message(f"s{i}", "user", f"q{i}"))
    resp = client.get("/sessions?limit=2")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_session_messages_returns_all_messages(client_and_db):
    client, db = client_and_db
    asyncio.run(db.create_session("s1", "POWER_USER"))
    asyncio.run(db.append_message("s1", "user", "hello"))
    asyncio.run(db.append_message(
        "s1", "assistant", "hi there",
        citations=["alan-turing"],
        gap_suggestions=["Alan Turing cause of death"],
    ))
    asyncio.run(db.append_message("s1", "user", "follow up"))
    resp = client.get("/sessions/s1/messages")
    assert resp.status_code == 200
    msgs = resp.json()
    assert len(msgs) == 3
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "hello"
    assert msgs[0]["citations"] == []
    assert msgs[0]["gap_suggestions"] == []
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["citations"] == ["alan-turing"]
    assert msgs[1]["gap_suggestions"] == ["Alan Turing cause of death"]
    assert msgs[2]["content"] == "follow up"


def test_get_session_messages_unknown_session_returns_empty(client_and_db):
    client, _ = client_and_db
    resp = client.get("/sessions/nonexistent/messages")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_sessions_multi_turn_lists_all_user_turns(client_and_db):
    client, db = client_and_db
    asyncio.run(db.create_session("s1", "WIKI_QUERY"))
    asyncio.run(db.append_message("s1", "user", "first question"))
    asyncio.run(db.append_message("s1", "assistant", "first answer"))
    asyncio.run(db.append_message("s1", "user", "follow-up question"))
    resp = client.get("/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["questions"] == ["first question", "follow-up question"]
    assert data[0]["turn_count"] == 2


def test_get_hints_returns_list_for_known_mode(client_and_db):
    client, _ = client_and_db
    for mode in ("NEW_WIKI", "EXPLORER", "HEALTH_CHECK", "POWER_USER"):
        resp = client.get(f"/hints?mode={mode}")
        assert resp.status_code == 200
        data = resp.json()
        assert "hints" in data
        assert isinstance(data["hints"], list)
        assert len(data["hints"]) > 0


def test_get_hints_defaults_to_power_user(client_and_db):
    client, _ = client_and_db
    resp = client.get("/hints")
    assert resp.status_code == 200
    assert "hints" in resp.json()


@pytest.mark.asyncio
async def test_session_state_pruned_to_match_db(tmp_path):
    """_prune_stale_session_state() must evict entries absent from the DB.

    Simulates the hourly purge path: POST /sessions populates _session_state,
    purge_old_sessions deletes the row from the DB, then _prune_stale_session_state
    removes the orphaned in-memory entry.
    """
    from synthadoc.integration.http_server import _prune_stale_session_state

    db = AuditDB(tmp_path / "audit.db")
    await db.init()

    # Simulate three sessions added to in-memory state (as POST /sessions would do)
    session_state: dict[str, dict] = {
        "alive-1": {"mode": "POWER_USER", "cursor": 0, "last_hints": []},
        "alive-2": {"mode": "EXPLORER",   "cursor": 2, "last_hints": ["hint-a"]},
        # gone-1 is in RAM but absent from the DB (purged or never persisted)
        "gone-1":  {"mode": "POWER_USER", "cursor": 0, "last_hints": []},
    }

    # Only alive-1 and alive-2 exist in the DB
    await db.create_session("alive-1", "POWER_USER")
    await db.create_session("alive-2", "EXPLORER")

    pruned = await _prune_stale_session_state(db, session_state)

    # gone-1 must be evicted; the return count must reflect it
    assert pruned == 1
    assert "gone-1" not in session_state
    # Alive entries must be preserved intact
    assert "alive-1" in session_state
    assert "alive-2" in session_state
    assert session_state["alive-2"]["cursor"] == 2
    assert session_state["alive-2"]["last_hints"] == ["hint-a"]


# ---------------------------------------------------------------------------
# POST /sessions mode-selection — verifies the DB-query path (no read_page)
# ---------------------------------------------------------------------------

def _make_sessions_create_app(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    return create_app(wiki_root=tmp_wiki, enable_mcp=False)


def test_post_sessions_new_wiki_mode(tmp_wiki):
    """With fewer than 5 pages, mode must be NEW_WIKI regardless of DB state."""
    app = _make_sessions_create_app(tmp_wiki)
    # tmp_wiki has no pages — list_pages() returns []
    with patch("synthadoc.storage.log.AuditDB.has_prior_sessions",
               new=AsyncMock(return_value=False)):
        with patch("synthadoc.storage.log.AuditDB.create_session",
                   new=AsyncMock()):
            with TestClient(app) as client:
                resp = client.post("/sessions")
    assert resp.status_code == 200
    assert resp.json()["mode"] == "NEW_WIKI"


def test_post_sessions_explorer_mode(tmp_wiki):
    """With ≥5 pages and no prior sessions, mode must be EXPLORER."""
    # Create 5 dummy page files so list_pages() returns 5
    wiki_dir = tmp_wiki / "wiki"
    for i in range(5):
        (wiki_dir / f"page{i}.md").write_text(
            "---\ntitle: P\nstatus: active\n---\n\nbody\n", encoding="utf-8"
        )
    app = _make_sessions_create_app(tmp_wiki)
    with patch("synthadoc.storage.log.AuditDB.has_prior_sessions",
               new=AsyncMock(return_value=False)):
        with patch("synthadoc.storage.log.AuditDB.create_session",
                   new=AsyncMock()):
            with TestClient(app) as client:
                resp = client.post("/sessions")
    assert resp.status_code == 200
    assert resp.json()["mode"] == "EXPLORER"


def test_post_sessions_health_check_mode_uses_db_not_read_page(tmp_wiki):
    """HEALTH_CHECK mode must be selected via get_lifecycle_summary(), not read_page().

    Specifically: the response must be HEALTH_CHECK when the DB reports stale
    pages, and read_page must NOT have been called for any page.
    """
    wiki_dir = tmp_wiki / "wiki"
    for i in range(5):
        (wiki_dir / f"page{i}.md").write_text(
            "---\ntitle: P\nstatus: active\n---\n\nbody\n", encoding="utf-8"
        )
    app = _make_sessions_create_app(tmp_wiki)
    with patch("synthadoc.storage.log.AuditDB.has_prior_sessions",
               new=AsyncMock(return_value=True)):
        with patch("synthadoc.storage.log.AuditDB.get_lifecycle_summary",
                   new=AsyncMock(return_value={"active": 4, "stale": 1})) as mock_summary:
            with patch("synthadoc.storage.log.AuditDB.create_session",
                       new=AsyncMock()):
                with patch("synthadoc.storage.wiki.WikiStorage.read_page") as mock_read:
                    with TestClient(app) as client:
                        resp = client.post("/sessions")
    assert resp.status_code == 200
    assert resp.json()["mode"] == "HEALTH_CHECK"
    mock_summary.assert_awaited_once()
    mock_read.assert_not_called()


def test_post_sessions_power_user_mode(tmp_wiki):
    """With ≥5 pages, prior sessions, and no stale/contradicted pages, mode is POWER_USER."""
    wiki_dir = tmp_wiki / "wiki"
    for i in range(5):
        (wiki_dir / f"page{i}.md").write_text(
            "---\ntitle: P\nstatus: active\n---\n\nbody\n", encoding="utf-8"
        )
    app = _make_sessions_create_app(tmp_wiki)
    with patch("synthadoc.storage.log.AuditDB.has_prior_sessions",
               new=AsyncMock(return_value=True)):
        with patch("synthadoc.storage.log.AuditDB.get_lifecycle_summary",
                   new=AsyncMock(return_value={"active": 5})):
            with patch("synthadoc.storage.log.AuditDB.create_session",
                       new=AsyncMock()):
                with TestClient(app) as client:
                    resp = client.post("/sessions")
    assert resp.status_code == 200
    assert resp.json()["mode"] == "POWER_USER"


def test_post_sessions_health_check_on_contradicted(tmp_wiki):
    """contradicted count alone is sufficient to trigger HEALTH_CHECK."""
    wiki_dir = tmp_wiki / "wiki"
    for i in range(5):
        (wiki_dir / f"page{i}.md").write_text(
            "---\ntitle: P\nstatus: active\n---\n\nbody\n", encoding="utf-8"
        )
    app = _make_sessions_create_app(tmp_wiki)
    with patch("synthadoc.storage.log.AuditDB.has_prior_sessions",
               new=AsyncMock(return_value=True)):
        with patch("synthadoc.storage.log.AuditDB.get_lifecycle_summary",
                   new=AsyncMock(return_value={"active": 4, "contradicted": 1})):
            with patch("synthadoc.storage.log.AuditDB.create_session",
                       new=AsyncMock()):
                with TestClient(app) as client:
                    resp = client.post("/sessions")
    assert resp.status_code == 200
    assert resp.json()["mode"] == "HEALTH_CHECK"
