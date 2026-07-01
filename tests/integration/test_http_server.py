# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for http_server.py multi-turn conversation wiring (Task 7)."""
from __future__ import annotations

import asyncio
import logging
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def _make_app(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    return create_app(wiki_root=tmp_wiki)


# ---------------------------------------------------------------------------
# Test 1: get_history called when session_id is present
# ---------------------------------------------------------------------------

def test_query_stream_loads_history_when_session_id_present(tmp_wiki):
    """get_all_messages must be called with (session_id,) when session_id is in the request."""
    from fastapi.testclient import TestClient

    app = _make_app(tmp_wiki)

    async def _fake_stream(question, session_id=None, session_mode="POWER_USER",
                           history=None):
        yield {"event": "token", "data": {"text": "hello"}}
        yield {"event": "done", "data": {"cacheable": False}}

    fake_history = [{"role": "user", "content": "prev"}, {"role": "assistant", "content": "ans"}]

    with patch("synthadoc.core.orchestrator.Orchestrator.query_stream",
               new=_fake_stream):
        with patch("synthadoc.storage.log.AuditDB.get_summary",
                   new=AsyncMock(return_value=(None, 0))):
            with patch("synthadoc.storage.log.AuditDB.get_all_messages",
                       new=AsyncMock(return_value=fake_history)) as mock_get_all_messages:
                with TestClient(app) as client:
                    resp = client.get("/query/stream?q=hello&session_id=test-session-123")

    assert resp.status_code == 200
    mock_get_all_messages.assert_awaited_once_with("test-session-123")


# ---------------------------------------------------------------------------
# Test 2: get_history NOT called when conversation_history_turns=0
# ---------------------------------------------------------------------------

def test_query_stream_no_history_when_turns_zero(tmp_wiki):
    """get_all_messages must NOT be called when conversation_history_turns=0."""
    from fastapi.testclient import TestClient
    from synthadoc.config import load_config

    app = _make_app(tmp_wiki)

    # Patch config so that chat.conversation_history_turns == 0
    orig_load = load_config

    def _patched_load(*args, **kwargs):
        cfg = orig_load(*args, **kwargs)
        cfg.chat.conversation_history_turns = 0
        return cfg

    async def _fake_stream(question, session_id=None, session_mode="POWER_USER",
                           history=None):
        yield {"event": "token", "data": {"text": "hello"}}
        yield {"event": "done", "data": {"cacheable": False}}

    with patch("synthadoc.config.load_config", side_effect=_patched_load):
        app2 = _make_app(tmp_wiki)

    with patch("synthadoc.core.orchestrator.Orchestrator.query_stream",
               new=_fake_stream):
        with patch("synthadoc.storage.log.AuditDB.get_all_messages",
                   new=AsyncMock(return_value=[])) as mock_get_all_messages:
            with TestClient(app2) as client:
                resp = client.get("/query/stream?q=hello&session_id=test-session-456")

    assert resp.status_code == 200
    mock_get_all_messages.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test 3: clarify event forwarded through SSE
# ---------------------------------------------------------------------------

def test_query_stream_clarify_event_forwarded(tmp_wiki):
    """A 'clarify' event from the query agent must be forwarded as SSE event: clarify."""
    from fastapi.testclient import TestClient

    app = _make_app(tmp_wiki)

    async def _fake_stream_with_clarify(question, session_id=None,
                                         session_mode="POWER_USER", history=None):
        yield {"event": "clarify", "data": {"question": "Did you mean X or Y?",
                                             "options": ["X", "Y"]}}
        yield {"event": "done", "data": {"cacheable": False}}

    with patch("synthadoc.storage.log.AuditDB.get_history",
               new=AsyncMock(return_value=[])):
        with patch("synthadoc.storage.log.AuditDB.get_summary",
                   new=AsyncMock(return_value=(None, 0))):
            with patch("synthadoc.storage.log.AuditDB.get_all_messages",
                       new=AsyncMock(return_value=[])):
                with TestClient(app) as client:
                    app.state.orch.query_stream = _fake_stream_with_clarify
                    resp = client.get("/query/stream?q=ambiguous&session_id=sess-clarify")

    assert resp.status_code == 200
    assert b"event: clarify" in resp.content


# ---------------------------------------------------------------------------
# Test 4: notice event emitted on first overflow
# ---------------------------------------------------------------------------

def test_query_stream_notice_emitted_on_first_overflow(tmp_wiki):
    """A 'notice' SSE event must be emitted when history overflows for the first time."""
    from fastapi.testclient import TestClient

    app = _make_app(tmp_wiki)

    # 12 messages = 6 turns, window is 5 → overflow = 1 turn
    many_messages = [
        {"role": ("user" if i % 2 == 0 else "assistant"), "content": f"msg {i}"}
        for i in range(12)
    ]

    async def _fake_stream(question, session_id=None, session_mode="POWER_USER",
                           history=None):
        yield {"event": "token", "data": {"text": "answer"}}
        yield {"event": "done", "data": {"cacheable": False}}

    fake_provider = MagicMock()

    with patch("synthadoc.storage.log.AuditDB.get_history",
               new=AsyncMock(return_value=many_messages[-10:])):
        with patch("synthadoc.storage.log.AuditDB.get_summary",
                   new=AsyncMock(return_value=(None, 0))):
            with patch("synthadoc.storage.log.AuditDB.get_all_messages",
                       new=AsyncMock(return_value=many_messages)):
                with patch("synthadoc.providers.make_provider",
                           return_value=fake_provider):
                    with patch("synthadoc.agents.summarize_agent.SummarizeAgent.summarize",
                               new=AsyncMock(return_value="Earlier topics: X and Y.")):
                        with patch("synthadoc.storage.log.AuditDB.update_summary",
                                   new=AsyncMock()):
                            with TestClient(app) as client:
                                app.state.orch.query_stream = _fake_stream
                                resp = client.get(
                                    "/query/stream?q=what+next&session_id=sess-overflow"
                                )

    assert resp.status_code == 200
    assert b"event: notice" in resp.content


# ---------------------------------------------------------------------------
# Test 5: streaming timeout emits error event
# ---------------------------------------------------------------------------

def test_query_stream_timeout_emits_error_event(tmp_wiki):
    """When the streaming query times out, an error SSE event is yielded with a hint."""
    from fastapi.testclient import TestClient

    app = _make_app(tmp_wiki)

    async def _slow_stream(question, session_id=None, session_mode="POWER_USER",
                           history=None):
        raise TimeoutError("simulated timeout")
        yield  # makes it an async generator

    with patch("synthadoc.storage.log.AuditDB.get_summary",
               new=AsyncMock(return_value=(None, 0))):
        with patch("synthadoc.storage.log.AuditDB.get_all_messages",
                   new=AsyncMock(return_value=[])):
            with TestClient(app) as client:
                app.state.orch.query_stream = _slow_stream
                resp = client.get("/query/stream?q=hello&timeout_seconds=5")

    assert resp.status_code == 200
    assert b"event: error" in resp.content
    assert b"timed out" in resp.content


def test_query_stream_passes_timeout_seconds_to_server(tmp_wiki):
    """timeout_seconds URL param is accepted and non-default values reach the stream."""
    from fastapi.testclient import TestClient

    app = _make_app(tmp_wiki)

    async def _ok_stream(question, session_id=None, session_mode="POWER_USER",
                         history=None):
        yield {"event": "token", "data": {"text": "ok"}}
        yield {"event": "done", "data": {"cacheable": False}}

    with patch("synthadoc.storage.log.AuditDB.get_summary",
               new=AsyncMock(return_value=(None, 0))):
        with patch("synthadoc.storage.log.AuditDB.get_all_messages",
                   new=AsyncMock(return_value=[])):
            with TestClient(app) as client:
                app.state.orch.query_stream = _ok_stream
                resp = client.get("/query/stream?q=hello&timeout_seconds=120")

    assert resp.status_code == 200
    assert b"event: done" in resp.content


# ---------------------------------------------------------------------------
# _install_shutdown_noise_filter — log filter behaviour
# ---------------------------------------------------------------------------

def _make_filter():
    """Return a fresh instance of the shutdown noise filter."""
    from synthadoc.integration.http_server import _install_shutdown_noise_filter
    logger = logging.getLogger("uvicorn.error.test_" + str(id(_make_filter)))
    _install_shutdown_noise_filter.__wrapped__ = None  # reset any cached state
    # Call the private installer and extract the filter it installs
    _install_shutdown_noise_filter()
    filters = logging.getLogger("uvicorn.error").filters
    return filters[-1]  # the most recently installed _Filter instance


def _make_record(exc_type=None, exc_val=None, msg="Exception in ASGI application", level=logging.ERROR):
    record = logging.LogRecord(
        name="uvicorn.error", level=level, pathname="", lineno=0,
        msg=msg, args=(), exc_info=None,
    )
    if exc_type is not None:
        record.exc_info = (exc_type, exc_val or exc_type(), None)
    return record


class TestShutdownNoiseFilter:
    def setup_method(self):
        from synthadoc.integration.http_server import _install_shutdown_noise_filter
        _install_shutdown_noise_filter()
        self.f = logging.getLogger("uvicorn.error").filters[-1]

    def test_passes_unrelated_error(self):
        record = _make_record(exc_type=ValueError, exc_val=ValueError("boom"))
        assert self.f.filter(record) is True

    def test_suppresses_cancelled_error(self):
        record = _make_record(exc_type=asyncio.CancelledError)
        assert self.f.filter(record) is False

    def test_suppresses_keyboard_interrupt(self):
        record = _make_record(exc_type=KeyboardInterrupt)
        assert self.f.filter(record) is False

    def test_suppresses_asgi_runtime_error_with_exc_info(self):
        exc = RuntimeError("Expected ASGI message 'http.response.body', but got 'http.response.start'.")
        record = _make_record(exc_type=RuntimeError, exc_val=exc)
        assert self.f.filter(record) is False

    def test_passes_unrelated_runtime_error(self):
        exc = RuntimeError("something else went wrong")
        record = _make_record(exc_type=RuntimeError, exc_val=exc)
        assert self.f.filter(record) is True

    def test_suppresses_asgi_error_in_message_text(self):
        record = _make_record(msg="Expected ASGI message 'http.response.body' http.response")
        assert self.f.filter(record) is False

    def test_suppresses_cancelled_error_in_message_text(self):
        record = _make_record(msg="some traceback ending in asyncio.CancelledError")
        assert self.f.filter(record) is False

    def test_passes_info_level(self):
        record = _make_record(
            exc_type=asyncio.CancelledError, level=logging.INFO,
            msg="asyncio.CancelledError",
        )
        record.exc_info = None  # no exc_info, info level — should pass
        assert self.f.filter(record) is True


# ---------------------------------------------------------------------------
# New code path tests for v1.0 code quality fixes
# ---------------------------------------------------------------------------

def test_ingest_request_rejects_empty_source(tmp_wiki):
    """POST /ingest with empty source must return 422 (Pydantic validation error)."""
    from fastapi.testclient import TestClient
    app = _make_app(tmp_wiki)
    with TestClient(app) as client:
        resp = client.post("/jobs/ingest", json={"source": ""})
    assert resp.status_code == 422


def test_ingest_request_rejects_whitespace_source(tmp_wiki):
    """POST /ingest with whitespace-only source must return 422."""
    from fastapi.testclient import TestClient
    app = _make_app(tmp_wiki)
    with TestClient(app) as client:
        resp = client.post("/jobs/ingest", json={"source": "   "})
    assert resp.status_code == 422


def test_jobs_rejects_invalid_sort(tmp_wiki):
    """GET /jobs with an invalid sort param must return 400."""
    from fastapi.testclient import TestClient
    app = _make_app(tmp_wiki)
    with TestClient(app) as client:
        resp = client.get("/jobs?sort=injected_column")
    assert resp.status_code == 400
    assert "sort" in resp.json()["detail"].lower()


def test_jobs_rejects_invalid_order(tmp_wiki):
    """GET /jobs with an invalid order param must return 400."""
    from fastapi.testclient import TestClient
    app = _make_app(tmp_wiki)
    with TestClient(app) as client:
        resp = client.get("/jobs?order=injected")
    assert resp.status_code == 400
    assert "order" in resp.json()["detail"].lower()


def _fake_query_result():
    from unittest.mock import MagicMock
    r = MagicMock()
    r.answer = "ok"
    r.citations = []
    r.knowledge_gap = False
    r.suggested_searches = []
    r.cacheable = False
    return r


def test_get_query_returns_no_store_header(tmp_wiki):
    """GET /query must include Cache-Control: no-store in the response headers."""
    from fastapi.testclient import TestClient
    app = _make_app(tmp_wiki)
    with TestClient(app) as client:
        app.state.orch.query = AsyncMock(return_value=_fake_query_result())
        resp = client.get("/query?q=test&no_cache=true")
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == "no-store"


def test_post_query_returns_no_store_header(tmp_wiki):
    """POST /query must include Cache-Control: no-store in the response headers."""
    from fastapi.testclient import TestClient
    app = _make_app(tmp_wiki)
    with TestClient(app) as client:
        app.state.orch.query = AsyncMock(return_value=_fake_query_result())
        resp = client.post("/query", json={"question": "test", "no_cache": True})
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == "no-store"


def test_content_size_middleware_blocks_large_body(tmp_wiki):
    """POST with body exceeding the configured limit must return 413."""
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    app = create_app(wiki_root=tmp_wiki, max_body_bytes=10)
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post("/jobs/ingest", json={"source": "x" * 50})
    assert resp.status_code == 413


# ---------------------------------------------------------------------------
# Task 4: max_source_chars field on IngestRequest
# ---------------------------------------------------------------------------

def test_ingest_request_accepts_max_source_chars():
    """IngestRequest must accept max_source_chars and store it."""
    from synthadoc.integration.http_server import IngestRequest
    req = IngestRequest(source="file.txt", max_source_chars=128000)
    assert req.max_source_chars == 128000


def test_ingest_request_max_source_chars_defaults_none():
    """IngestRequest must default max_source_chars to None."""
    from synthadoc.integration.http_server import IngestRequest
    req = IngestRequest(source="file.txt")
    assert req.max_source_chars is None


# ---------------------------------------------------------------------------
# Task 12: GET /graph — lazy hydration
# ---------------------------------------------------------------------------

_SAMPLE_GRAPH = {
    "nodes": [
        {"slug": "alpha", "cluster_id": 0},
        {"slug": "beta", "cluster_id": 0},
        {"slug": "gamma", "cluster_id": 1},
    ],
    "edges": [
        {"from_slug": "alpha", "to_slug": "beta", "weight": 2},
        {"from_slug": "beta", "to_slug": "gamma", "weight": 1},
    ],
}


@pytest.fixture(autouse=False)
def reset_graph_flag():
    """Reset the module-level _graph_computing flag before and after each test."""
    import synthadoc.integration.http_server as _hs
    _hs._graph_computing = False
    yield
    _hs._graph_computing = False


@pytest.fixture
def seeded_graph():
    """Patch AuditDB.read_graph to return sample graph data."""
    with patch(
        "synthadoc.storage.log.AuditDB.read_graph",
        new=AsyncMock(return_value=_SAMPLE_GRAPH),
    ):
        yield


def test_get_graph_returns_computing_when_empty(tmp_wiki, reset_graph_flag):
    """When graph tables are empty, GET /graph returns HTTP 200 with status == computing."""
    from fastapi.testclient import TestClient
    app = _make_app(tmp_wiki)

    # Patch read_graph to return None (empty tables).
    # The background build task is created but fails silently (no provider in test env)
    # — the response is already sent before the task runs.
    with patch("synthadoc.storage.log.AuditDB.read_graph", new=AsyncMock(return_value=None)):
        with TestClient(app) as client:
            resp = client.get("/graph")

    assert resp.status_code == 200
    assert resp.json()["status"] == "computing"


def test_get_graph_returns_ready_with_data(tmp_wiki, seeded_graph, reset_graph_flag):
    """When graph is seeded, GET /graph returns status == ready with nodes and edges."""
    from fastapi.testclient import TestClient

    fake_page = MagicMock()
    fake_page.title = "Alpha Page"
    fake_page.type = "concept"
    fake_page.status = "active"

    app = _make_app(tmp_wiki)
    with TestClient(app) as client:
        with patch("synthadoc.storage.wiki.WikiStorage.read_page", return_value=fake_page):
            resp = client.get("/graph")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert "nodes" in data
    assert "edges" in data
    assert isinstance(data["node_count"], int)
    assert isinstance(data["cluster_count"], int)


def test_get_graph_node_fields(tmp_wiki, seeded_graph, reset_graph_flag):
    """Each node returned by GET /graph has slug, title, type, state, cluster_id."""
    from fastapi.testclient import TestClient

    fake_page = MagicMock()
    fake_page.title = "Test Page"
    fake_page.type = "concept"
    fake_page.status = "active"

    app = _make_app(tmp_wiki)
    with TestClient(app) as client:
        with patch("synthadoc.storage.wiki.WikiStorage.read_page", return_value=fake_page):
            resp = client.get("/graph")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["nodes"]) > 0
    node = data["nodes"][0]
    assert "slug" in node
    assert "title" in node
    assert "type" in node
    assert "state" in node
    assert isinstance(node["cluster_id"], int)


def test_get_graph_returns_no_store_header(tmp_wiki, seeded_graph, reset_graph_flag):
    """GET /graph must include Cache-Control: no-store in the response headers."""
    from fastapi.testclient import TestClient

    fake_page = MagicMock()
    fake_page.title = "Page"
    fake_page.type = "concept"
    fake_page.status = "active"

    app = _make_app(tmp_wiki)
    with TestClient(app) as client:
        with patch("synthadoc.storage.wiki.WikiStorage.read_page", return_value=fake_page):
            resp = client.get("/graph")

    assert resp.headers.get("cache-control") == "no-store"


def test_get_graph_computing_returns_no_store_header(tmp_wiki, reset_graph_flag):
    """GET /graph computing response must also include Cache-Control: no-store."""
    from fastapi.testclient import TestClient

    app = _make_app(tmp_wiki)
    with patch("synthadoc.storage.log.AuditDB.read_graph", new=AsyncMock(return_value=None)):
        with TestClient(app) as client:
            resp = client.get("/graph")

    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == "no-store"
