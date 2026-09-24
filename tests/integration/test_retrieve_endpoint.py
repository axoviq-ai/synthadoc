# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Integration tests for POST /retrieve endpoint."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _make_search_result(slug: str, score: float = 0.9):
    """Return a mock SearchResult-like object."""
    r = MagicMock()
    r.slug = slug
    r.score = score
    r.title = slug.replace("-", " ").title()
    r.snippet = f"Snippet for {slug}"
    return r


def _make_page(slug: str, status: str = "active"):
    """Return a mock WikiPage-like object."""
    page = MagicMock()
    page.slug = slug
    page.title = slug.replace("-", " ").title()
    page.content = f"Content of {slug}."
    page.status = status
    return page


def _make_app(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    return create_app(wiki_root=tmp_wiki)


def test_retrieve_returns_pages(tmp_wiki):
    """POST /retrieve returns BM25 results with wiki_name, pages, purpose_summary, routing_warning."""
    fake_result = _make_search_result("leverage-basics", score=0.9)
    fake_page = _make_page("leverage-basics", status="active")

    app = _make_app(tmp_wiki)
    with patch(
        "synthadoc.storage.search.HybridSearch.hybrid_search",
        new_callable=AsyncMock,
        return_value=[fake_result],
    ):
        with patch(
            "synthadoc.storage.wiki.WikiStorage.read_page",
            return_value=fake_page,
        ):
            with patch(
                "synthadoc.cli._wiki.extract_purpose_summary",
                return_value="A finance wiki.",
            ):
                with TestClient(app) as client:
                    resp = client.post(
                        "/retrieve",
                        json={
                            "question": "what is leverage",
                            "sub_questions": [
                                "what is leverage",
                                "how is leverage calculated",
                            ],
                            "top_k": 5,
                        },
                    )

    assert resp.status_code == 200
    data = resp.json()
    assert "wiki_name" in data
    assert isinstance(data["pages"], list)
    assert "purpose_summary" in data
    assert "routing_warning" in data
    assert data["routing_warning"] == ""
    assert data["purpose_summary"] == "A finance wiki."
    # wiki_name should be the name of the tmp_wiki directory
    assert data["wiki_name"] == tmp_wiki.name


def test_retrieve_top_k_clamped(tmp_wiki):
    """top_k > 20 is silently clamped to 20 — endpoint returns 200."""
    fake_result = _make_search_result("some-page", score=0.7)
    fake_page = _make_page("some-page", status="active")

    app = _make_app(tmp_wiki)
    with patch(
        "synthadoc.storage.search.HybridSearch.hybrid_search",
        new_callable=AsyncMock,
        return_value=[fake_result],
    ):
        with patch(
            "synthadoc.storage.wiki.WikiStorage.read_page",
            return_value=fake_page,
        ):
            with patch("synthadoc.cli._wiki.extract_purpose_summary", return_value=""):
                with TestClient(app) as client:
                    resp = client.post("/retrieve", json={"question": "x", "top_k": 99})

    assert resp.status_code == 200


def test_retrieve_empty_question_rejected(tmp_wiki):
    """POST /retrieve with whitespace-only question returns 400."""
    app = _make_app(tmp_wiki)
    with TestClient(app) as client:
        resp = client.post("/retrieve", json={"question": "  "})
    assert resp.status_code == 400


def test_retrieve_no_store_header(tmp_wiki):
    """POST /retrieve response includes Cache-Control: no-store."""
    fake_result = _make_search_result("page-a", score=0.8)
    fake_page = _make_page("page-a", status="active")

    app = _make_app(tmp_wiki)
    with patch(
        "synthadoc.storage.search.HybridSearch.hybrid_search",
        new_callable=AsyncMock,
        return_value=[fake_result],
    ):
        with patch(
            "synthadoc.storage.wiki.WikiStorage.read_page",
            return_value=fake_page,
        ):
            with patch("synthadoc.cli._wiki.extract_purpose_summary", return_value=""):
                with TestClient(app) as client:
                    resp = client.post(
                        "/retrieve",
                        json={"question": "some query"},
                    )

    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == "no-store"


def test_retrieve_inactive_pages_excluded(tmp_wiki):
    """Pages with non-ACTIVE status are excluded from results."""
    fake_result = _make_search_result("stale-page", score=0.85)
    stale_page = _make_page("stale-page", status="stale")

    app = _make_app(tmp_wiki)
    with patch(
        "synthadoc.storage.search.HybridSearch.hybrid_search",
        new_callable=AsyncMock,
        return_value=[fake_result],
    ):
        with patch(
            "synthadoc.storage.wiki.WikiStorage.read_page",
            return_value=stale_page,
        ):
            with patch("synthadoc.cli._wiki.extract_purpose_summary", return_value=""):
                with TestClient(app) as client:
                    resp = client.post(
                        "/retrieve",
                        json={"question": "stale content"},
                    )

    assert resp.status_code == 200
    data = resp.json()
    # stale page should not be included
    assert data["pages"] == []
