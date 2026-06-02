# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def _make_app(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    return create_app(wiki_root=tmp_wiki)


def test_query_stream_returns_event_stream(tmp_wiki):
    """GET /query/stream must return text/event-stream content type."""
    from fastapi.testclient import TestClient
    app = _make_app(tmp_wiki)

    async def _fake_stream(question, session_id=None, session_mode="POWER_USER"):
        yield {"event": "status", "data": {"phase": "retrieving"}}
        yield {"event": "token", "data": {"text": "hello"}}
        yield {"event": "done", "data": {"next_hints": []}}

    with patch("synthadoc.core.orchestrator.Orchestrator.query_stream",
               new=_fake_stream):
        with TestClient(app) as client:
            resp = client.get("/query/stream?q=test")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]


def test_query_stream_rejects_empty_question(tmp_wiki):
    """GET /query/stream with empty q must return 400."""
    from fastapi.testclient import TestClient
    app = _make_app(tmp_wiki)
    with TestClient(app) as client:
        resp = client.get("/query/stream?q=")
    assert resp.status_code == 400


def test_query_stream_cache_hit_returns_stream(tmp_wiki):
    """GET /query/stream with a warm cache must return cached content as SSE burst."""
    from fastapi.testclient import TestClient
    app = _make_app(tmp_wiki)

    cached = {"answer": "cached answer", "citations": ["p1"], "knowledge_gap": False,
              "suggested_searches": []}

    with patch("synthadoc.core.cache.CacheManager.get_query",
               new=AsyncMock(return_value=cached)):
        async def _should_not_be_called(*a, **kw):
            raise AssertionError("should not call LLM on cache hit")
            yield  # make it a generator
        with patch("synthadoc.core.orchestrator.Orchestrator.query_stream",
                   new=_should_not_be_called):
            with TestClient(app) as client:
                resp = client.get("/query/stream?q=test")
    assert resp.status_code == 200
    assert b"cached" in resp.content


def test_post_sessions_returns_session_id_and_mode(tmp_wiki):
    """POST /sessions must return session_id (UUID) and a mode string."""
    import re
    from fastapi.testclient import TestClient
    app = _make_app(tmp_wiki)
    with TestClient(app) as client:
        resp = client.post("/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert "mode" in data
    assert data["mode"] in ("NEW_WIKI", "EXPLORER", "HEALTH_CHECK", "POWER_USER")
    assert re.match(r"[0-9a-f-]{36}", data["session_id"])
