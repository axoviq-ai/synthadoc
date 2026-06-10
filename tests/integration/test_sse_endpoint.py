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


def _make_wiki_pages(wiki_dir, count=5, stale_index=None):
    """Create count wiki pages; if stale_index is set, that page gets status: stale."""
    for i in range(count):
        status = "stale" if i == stale_index else "active"
        (wiki_dir / f"page{i}.md").write_text(
            f"---\ntitle: Page {i}\nstatus: {status}\n---\n\nContent.\n",
            encoding="utf-8",
        )


def test_post_sessions_explorer_mode(tmp_wiki):
    """POST /sessions with 5+ pages and no prior sessions must return EXPLORER."""
    from fastapi.testclient import TestClient
    _make_wiki_pages(tmp_wiki / "wiki")
    app = _make_app(tmp_wiki)
    with TestClient(app) as client:
        resp = client.post("/sessions")
    assert resp.status_code == 200
    assert resp.json()["mode"] == "EXPLORER"


def test_post_sessions_power_user_mode(tmp_wiki):
    """POST /sessions on second call with no stale pages returns POWER_USER."""
    from fastapi.testclient import TestClient
    _make_wiki_pages(tmp_wiki / "wiki")
    app = _make_app(tmp_wiki)
    with TestClient(app) as client:
        client.post("/sessions")          # first call → EXPLORER + records session
        resp = client.post("/sessions")   # second call → has_prior_sessions=True → POWER_USER
    assert resp.status_code == 200
    assert resp.json()["mode"] == "POWER_USER"


def test_post_sessions_health_check_mode(tmp_wiki):
    """POST /sessions on second call with a stale page returns HEALTH_CHECK."""
    from fastapi.testclient import TestClient
    _make_wiki_pages(tmp_wiki / "wiki", stale_index=0)
    app = _make_app(tmp_wiki)
    with TestClient(app) as client:
        client.post("/sessions")          # first call records session
        resp = client.post("/sessions")   # second call → stale page → HEALTH_CHECK
    assert resp.status_code == 200
    assert resp.json()["mode"] == "HEALTH_CHECK"


def test_query_stream_with_session_updates_cursor(tmp_wiki):
    """GET /query/stream with a valid session_id must update cursor and last_hints."""
    from fastapi.testclient import TestClient
    app = _make_app(tmp_wiki)

    async def _fake_stream(question, session_id=None, session_mode="NEW_WIKI", history=None):
        yield {"event": "status", "data": {"phase": "synthesizing", "sources": 0}}
        yield {"event": "token", "data": {"text": "your wiki covers several topics"}}
        yield {"event": "done", "data": {"cacheable": True}}

    with TestClient(app) as client:
        # Replace instance attr to avoid self-binding issues with class-level patch
        sess = client.post("/sessions").json()
        sid = sess["session_id"]
        app.state.orch.query_stream = _fake_stream
        resp = client.get(f"/query/stream?q=test&session_id={sid}")

    assert resp.status_code == 200
    assert b"done" in resp.content
    assert b"next_hints" in resp.content


def test_query_stream_gap_stored_and_replayed_from_cache(tmp_wiki):
    """A gap response must store knowledge_gap+suggested_searches and replay them on cache hit."""
    from fastapi.testclient import TestClient
    app = _make_app(tmp_wiki)

    async def _gap_stream(question, session_id=None, session_mode="POWER_USER", history=None):
        yield {"event": "status", "data": {"phase": "retrieving"}}
        yield {"event": "token", "data": {"text": "No pages on this topic."}}
        yield {"event": "citations", "data": {"citations": []}}
        yield {"event": "gap", "data": {"suggested_searches": ["ingest quantum computing", "add quantum page"]}}
        yield {"event": "done", "data": {"cacheable": True, "next_hints": []}}

    # First request — live stream; verify gap event is forwarded
    with TestClient(app) as client:
        app.state.orch.query_stream = _gap_stream
        resp = client.get("/query/stream?q=quantum+computing")

    assert resp.status_code == 200
    assert b"gap" in resp.content
    assert b"quantum" in resp.content

    # Second request — served from cache; the gap event must still appear
    # (verifies both that cache stored knowledge_gap=True and that _cached_stream replays it)
    with TestClient(app) as client:
        # Replace stream with one that would not emit a gap — any gap in resp2 must come from cache
        async def _no_gap_stream(question, session_id=None, session_mode="POWER_USER"):
            raise AssertionError("live stream must not be called on cache hit")
            yield  # make it a generator

        app.state.orch.query_stream = _no_gap_stream
        resp2 = client.get("/query/stream?q=quantum+computing")

    assert resp2.status_code == 200
    assert b"gap" in resp2.content
    assert b"quantum" in resp2.content


def test_spa_not_built_returns_503(tmp_wiki):
    """GET /app returns 503 with helpful message when web-ui/dist is missing."""
    import pytest
    from fastapi.testclient import TestClient
    from pathlib import Path

    app = _make_app(tmp_wiki)
    # If the developer has built the UI, the 503 path is unreachable — skip
    import synthadoc.integration.http_server as srv_mod
    dist_path = Path(srv_mod.__file__).parent.parent.parent / "web-ui" / "dist"
    if dist_path.exists() and (dist_path / "index.html").is_file():
        pytest.skip("web-ui/dist exists; 503 path not reachable")

    with TestClient(app) as client:
        resp = client.get("/app")
    assert resp.status_code == 503
    assert b"npm run build" in resp.content
