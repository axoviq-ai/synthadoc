# tests/test_http_sessions.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import asyncio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
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
    assert data[0]["turns"] == ["What is Turing?"]


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
    assert data[0]["turns"] == ["first question", "follow-up question"]


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
