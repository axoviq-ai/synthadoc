# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Integration tests for GET /registry endpoint."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch


def _make_app(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    return create_app(wiki_root=tmp_wiki)


def test_registry_returns_dict(tmp_wiki):
    """GET /registry returns a dict of wikis with port and running fields."""
    app = _make_app(tmp_wiki)
    fake_reg = {"wiki-a": {"path": "/x", "port": 7070, "purpose_summary": "finance"}}
    with patch("synthadoc.cli._wiki.read_registry_all", return_value=fake_reg):
        with patch("synthadoc.cli._wiki.probe_port", return_value=False):
            with TestClient(app) as client:
                resp = client.get("/registry")
    assert resp.status_code == 200
    data = resp.json()
    assert "wiki-a" in data["wikis"]
    assert data["wikis"]["wiki-a"]["running"] is False
    assert data["wikis"]["wiki-a"]["port"] == 7070


def test_registry_no_store_header(tmp_wiki):
    """GET /registry returns Cache-Control: no-store header."""
    app = _make_app(tmp_wiki)
    with patch("synthadoc.cli._wiki.read_registry_all", return_value={}):
        with TestClient(app) as client:
            resp = client.get("/registry")
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == "no-store"


def test_registry_empty_when_no_wikis(tmp_wiki):
    """GET /registry returns empty wikis dict when registry is empty."""
    app = _make_app(tmp_wiki)
    with patch("synthadoc.cli._wiki.read_registry_all", return_value={}):
        with TestClient(app) as client:
            resp = client.get("/registry")
    assert resp.status_code == 200
    assert resp.json() == {"wikis": {}}
