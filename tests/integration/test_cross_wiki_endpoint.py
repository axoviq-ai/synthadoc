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
