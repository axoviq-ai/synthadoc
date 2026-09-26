# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Integration tests for POST /cross-wiki/query and GET /cross-wiki/query/stream endpoints."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from synthadoc.agents.query_agent import QueryResult


def _mock_result(**kwargs):
    defaults = dict(
        question="q", answer="Answer [[wiki-a::Page1]]",
        citations=["wiki-a::Page1"], knowledge_gap=False,
        tokens_used=100, input_tokens=80, output_tokens=20,
        suggested_searches=[], routing_warning="",
        cross_wiki_offline=[], cross_wiki_searched=["wiki-a", "wiki-b"],
        cross_wiki_skipped=False, cross_wiki_skip_reason="",
        cacheable=True, sub_questions_count=1,
    )
    defaults.update(kwargs)
    return QueryResult(**defaults)


def _make_app(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    return create_app(wiki_root=tmp_wiki)


def test_cross_wiki_query_returns_json(tmp_wiki):
    """POST /cross-wiki/query returns expected JSON fields."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=_mock_result())
    with patch("synthadoc.integration.http_server._make_cross_wiki_agent", return_value=mock_agent):
        app = _make_app(tmp_wiki)
        with TestClient(app) as client:
            resp = client.post("/cross-wiki/query", json={"question": "what is leverage?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "Answer [[wiki-a::Page1]]"
    assert "cross_wiki_searched" in data
    assert data["cross_wiki_skipped"] is False
    assert data["cross_wiki_searched"] == ["wiki-a", "wiki-b"]
    assert data["citations"] == ["wiki-a::Page1"]


def test_cross_wiki_query_skipped_response(tmp_wiki):
    """POST /cross-wiki/query returns skipped fields when agent skips cross-wiki search."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=_mock_result(
        cross_wiki_skipped=True, cross_wiki_skip_reason="operation detected"
    ))
    with patch("synthadoc.integration.http_server._make_cross_wiki_agent", return_value=mock_agent):
        app = _make_app(tmp_wiki)
        with TestClient(app) as client:
            resp = client.post("/cross-wiki/query", json={"question": "run lint"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["cross_wiki_skipped"] is True
    assert data["cross_wiki_skip_reason"] == "operation detected"


def test_cross_wiki_empty_question_rejected(tmp_wiki):
    """POST /cross-wiki/query with whitespace-only question returns 400."""
    app = _make_app(tmp_wiki)
    with TestClient(app) as client:
        resp = client.post("/cross-wiki/query", json={"question": "  "})
    assert resp.status_code == 400


def test_cross_wiki_query_no_store_header(tmp_wiki):
    """POST /cross-wiki/query response includes Cache-Control: no-store."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=_mock_result())
    with patch("synthadoc.integration.http_server._make_cross_wiki_agent", return_value=mock_agent):
        app = _make_app(tmp_wiki)
        with TestClient(app) as client:
            resp = client.post("/cross-wiki/query", json={"question": "what is leverage?"})
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == "no-store"


def test_cross_wiki_stream_returns_sse(tmp_wiki):
    """GET /cross-wiki/query/stream returns text/event-stream with expected events."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=_mock_result())
    with patch("synthadoc.integration.http_server._make_cross_wiki_agent", return_value=mock_agent):
        with patch("synthadoc.cli._wiki.read_registry_all", return_value={"wiki-a": {}, "wiki-b": {}}):
            app = _make_app(tmp_wiki)
            with TestClient(app) as client:
                resp = client.get("/cross-wiki/query/stream", params={"q": "what is leverage?"})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    body = resp.text
    assert "event: wikis_querying" in body
    assert "event: token" in body
    assert "event: done" in body


def test_cross_wiki_stream_empty_q_rejected(tmp_wiki):
    """GET /cross-wiki/query/stream with empty q returns 400."""
    app = _make_app(tmp_wiki)
    with TestClient(app) as client:
        resp = client.get("/cross-wiki/query/stream", params={"q": "  "})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /epoch
# ---------------------------------------------------------------------------

def test_epoch_endpoint_returns_epoch_and_wiki_name(tmp_wiki):
    """GET /epoch returns the wiki's current epoch and wiki_name."""
    app = _make_app(tmp_wiki)
    with TestClient(app) as client:
        resp = client.get("/epoch")
    assert resp.status_code == 200
    data = resp.json()
    assert "epoch" in data
    assert "wiki_name" in data
    assert isinstance(data["epoch"], int)
    assert data["wiki_name"] == tmp_wiki.name


def test_epoch_endpoint_epoch_is_non_negative(tmp_wiki):
    """GET /epoch epoch value is a non-negative integer at server startup."""
    app = _make_app(tmp_wiki)
    with TestClient(app) as client:
        resp = client.get("/epoch")
    assert resp.json()["epoch"] >= 0


# ---------------------------------------------------------------------------
# _cw_cache_key pure-function unit tests
# ---------------------------------------------------------------------------

def test_cw_cache_key_deterministic():
    """_cw_cache_key returns the same 32-char hex key for identical inputs."""
    from synthadoc.integration.http_server import _cw_cache_key
    peer_epochs = {"wiki-a": 1, "wiki-b": 2}
    key1 = _cw_cache_key("what is turing?", peer_epochs, "provider/model")
    key2 = _cw_cache_key("what is turing?", peer_epochs, "provider/model")
    assert key1 == key2
    assert len(key1) == 32
    assert all(c in "0123456789abcdef" for c in key1)


def test_cw_cache_key_differs_on_question_change():
    """_cw_cache_key changes when the question changes."""
    from synthadoc.integration.http_server import _cw_cache_key
    epochs = {"wiki-a": 1}
    assert _cw_cache_key("q1", epochs, "m") != _cw_cache_key("q2", epochs, "m")


def test_cw_cache_key_differs_on_epoch_change():
    """_cw_cache_key changes when any peer epoch changes."""
    from synthadoc.integration.http_server import _cw_cache_key
    assert (
        _cw_cache_key("q", {"wiki-a": 1}, "m")
        != _cw_cache_key("q", {"wiki-a": 2}, "m")
    )


def test_cw_cache_key_differs_on_model_change():
    """_cw_cache_key changes when the model string changes."""
    from synthadoc.integration.http_server import _cw_cache_key
    epochs = {"wiki-a": 1}
    assert (
        _cw_cache_key("q", epochs, "provider/model-a")
        != _cw_cache_key("q", epochs, "provider/model-b")
    )


def test_cw_cache_key_offline_peer_distinct():
    """_cw_cache_key with an offline peer (epoch -1) differs from the online state."""
    from synthadoc.integration.http_server import _cw_cache_key
    key_online = _cw_cache_key("q", {"wiki-a": 1, "wiki-b": 5}, "m")
    key_offline = _cw_cache_key("q", {"wiki-a": 1, "wiki-b": -1}, "m")
    assert key_online != key_offline


def test_cw_cache_key_normalizes_whitespace():
    """_cw_cache_key treats extra internal whitespace as equivalent to a single space."""
    from synthadoc.integration.http_server import _cw_cache_key
    key1 = _cw_cache_key("what  is  turing?", {"wiki-a": 1}, "m")
    key2 = _cw_cache_key("what is turing?", {"wiki-a": 1}, "m")
    assert key1 == key2


def test_cw_cache_key_epoch_dict_order_independent():
    """_cw_cache_key is stable regardless of insertion order in peer_epochs."""
    from synthadoc.integration.http_server import _cw_cache_key
    key1 = _cw_cache_key("q", {"wiki-a": 1, "wiki-b": 2}, "m")
    key2 = _cw_cache_key("q", {"wiki-b": 2, "wiki-a": 1}, "m")
    assert key1 == key2


# ---------------------------------------------------------------------------
# _cw_fetch_peer_epochs async unit tests
# ---------------------------------------------------------------------------

async def test_cw_fetch_peer_epochs_returns_own_epoch_directly():
    """_cw_fetch_peer_epochs includes the coordinator's epoch without any HTTP call."""
    from synthadoc.integration.http_server import _cw_fetch_peer_epochs
    # Empty registry — no peers, only coordinator
    registry = {"own-wiki": {"port": 7070}}
    epochs = await _cw_fetch_peer_epochs(registry, "own-wiki", own_epoch=42)
    assert epochs == {"own-wiki": 42}


async def test_cw_fetch_peer_epochs_offline_peer_returns_minus_one():
    """_cw_fetch_peer_epochs gives epoch -1 for a peer that refuses the connection."""
    from synthadoc.integration.http_server import _cw_fetch_peer_epochs
    # Port 1 is always closed / refused on modern systems
    registry = {
        "own-wiki": {"port": 7070},
        "offline-wiki": {"port": 1},
    }
    epochs = await _cw_fetch_peer_epochs(
        registry, "own-wiki", own_epoch=5, http_timeout=0.5
    )
    assert epochs["own-wiki"] == 5
    assert epochs["offline-wiki"] == -1


# ---------------------------------------------------------------------------
# Cache integration tests — /cross-wiki/query/stream
# ---------------------------------------------------------------------------

def test_cross_wiki_stream_cache_hit_skips_agent(tmp_wiki):
    """Stream endpoint replays cached events and does not call the agent on a cache hit."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=_mock_result())

    cached = {
        "answer": "Cached cross-wiki answer",
        "citations": ["wiki-a::Page1"],
        "knowledge_gap": False,
        "cross_wiki_searched": ["wiki-a", "wiki-b"],
        "cross_wiki_offline": [],
        "cross_wiki_skipped": False,
        "cross_wiki_skip_reason": "",
    }

    with patch("synthadoc.integration.http_server._make_cross_wiki_agent", return_value=mock_agent):
        with patch("synthadoc.cli._wiki.read_registry_all", return_value={"wiki-a": {"port": 7070}}):
            with patch("synthadoc.integration.http_server._cw_fetch_peer_epochs",
                       new=AsyncMock(return_value={"wiki-a": 1})):
                with patch("synthadoc.integration.http_server._cw_cache_read",
                           new=AsyncMock(return_value=cached)):
                    app = _make_app(tmp_wiki)
                    with TestClient(app) as client:
                        resp = client.get(
                            "/cross-wiki/query/stream",
                            params={"q": "what is turing?"},
                        )

    assert resp.status_code == 200
    body = resp.text
    assert "event: done" in body
    assert "Cached cross-wiki answer" in body
    mock_agent.run.assert_not_called()


def test_cross_wiki_stream_cache_hit_emits_sse_events(tmp_wiki):
    """Stream cache hit emits wikis_querying, wikis_result, token, and done events."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=_mock_result())

    cached = {
        "answer": "Cached answer",
        "citations": ["wiki-a::Page1"],
        "knowledge_gap": False,
        "cross_wiki_searched": ["wiki-a", "wiki-b"],
        "cross_wiki_offline": [],
        "cross_wiki_skipped": False,
        "cross_wiki_skip_reason": "",
    }

    with patch("synthadoc.integration.http_server._make_cross_wiki_agent", return_value=mock_agent):
        with patch("synthadoc.cli._wiki.read_registry_all", return_value={"wiki-a": {"port": 7070}}):
            with patch("synthadoc.integration.http_server._cw_fetch_peer_epochs",
                       new=AsyncMock(return_value={"wiki-a": 1})):
                with patch("synthadoc.integration.http_server._cw_cache_read",
                           new=AsyncMock(return_value=cached)):
                    app = _make_app(tmp_wiki)
                    with TestClient(app) as client:
                        resp = client.get(
                            "/cross-wiki/query/stream",
                            params={"q": "what is turing?"},
                        )

    body = resp.text
    assert "event: wikis_querying" in body
    assert "event: wikis_result" in body
    assert "event: token" in body
    assert "event: citations" in body
    assert "event: done" in body


def test_cross_wiki_stream_multi_turn_reads_cache_but_skips_write(tmp_wiki):
    """In a multi-turn session the cache is still checked (read), but not written to."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=_mock_result(cacheable=True))

    mock_cache_read = AsyncMock(return_value=None)   # cache miss → falls through to agent
    mock_cache_write = AsyncMock()

    prior_history = [
        {"role": "user", "content": "prior question"},
        {"role": "assistant", "content": "prior answer"},
    ]

    with patch("synthadoc.integration.http_server._make_cross_wiki_agent", return_value=mock_agent):
        with patch("synthadoc.cli._wiki.read_registry_all", return_value={"wiki-a": {"port": 7070}}):
            with patch("synthadoc.integration.http_server._cw_fetch_peer_epochs",
                       new=AsyncMock(return_value={"wiki-a": 1})):
                with patch("synthadoc.integration.http_server._cw_cache_read", new=mock_cache_read):
                    with patch("synthadoc.integration.http_server._cw_cache_write", new=mock_cache_write):
                        app = _make_app(tmp_wiki)
                        with TestClient(app) as client:
                            app.state.orch._audit.get_all_messages = AsyncMock(return_value=prior_history)
                            resp = client.get(
                                "/cross-wiki/query/stream",
                                params={"q": "follow-up question", "session_id": "sess-123"},
                            )

    assert resp.status_code == 200
    # Cache read IS called — same standalone question in multi-turn still benefits from cache
    mock_cache_read.assert_called_once()
    # Agent runs (cache was a miss)
    mock_agent.run.assert_called_once()
    # Cache write is NOT called — context-dependent answers must not be cached
    mock_cache_write.assert_not_called()


def test_cross_wiki_stream_writes_cache_after_live_query(tmp_wiki):
    """Stream endpoint calls _cw_cache_write after a cacheable live query completes."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=_mock_result(cacheable=True))

    mock_cache_write = AsyncMock()

    with patch("synthadoc.integration.http_server._make_cross_wiki_agent", return_value=mock_agent):
        with patch("synthadoc.cli._wiki.read_registry_all", return_value={"wiki-a": {"port": 7070}}):
            with patch("synthadoc.integration.http_server._cw_fetch_peer_epochs",
                       new=AsyncMock(return_value={"wiki-a": 1})):
                with patch("synthadoc.integration.http_server._cw_cache_read",
                           new=AsyncMock(return_value=None)):
                    with patch("synthadoc.integration.http_server._cw_cache_write",
                               new=mock_cache_write):
                        app = _make_app(tmp_wiki)
                        with TestClient(app) as client:
                            resp = client.get(
                                "/cross-wiki/query/stream",
                                params={"q": "what is turing?"},
                            )

    assert resp.status_code == 200
    mock_cache_write.assert_called_once()


def test_cross_wiki_stream_non_cacheable_result_skips_write(tmp_wiki):
    """Stream endpoint does NOT call _cw_cache_write when result is not cacheable."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=_mock_result(cacheable=False))

    mock_cache_write = AsyncMock()

    with patch("synthadoc.integration.http_server._make_cross_wiki_agent", return_value=mock_agent):
        with patch("synthadoc.cli._wiki.read_registry_all", return_value={"wiki-a": {"port": 7070}}):
            with patch("synthadoc.integration.http_server._cw_fetch_peer_epochs",
                       new=AsyncMock(return_value={"wiki-a": 1})):
                with patch("synthadoc.integration.http_server._cw_cache_read",
                           new=AsyncMock(return_value=None)):
                    with patch("synthadoc.integration.http_server._cw_cache_write",
                               new=mock_cache_write):
                        app = _make_app(tmp_wiki)
                        with TestClient(app) as client:
                            resp = client.get(
                                "/cross-wiki/query/stream",
                                params={"q": "what is turing?"},
                            )

    assert resp.status_code == 200
    mock_cache_write.assert_not_called()
