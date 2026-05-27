# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from pathlib import Path
from fastapi import FastAPI, HTTPException, Response
from fastapi.testclient import TestClient
from pydantic import BaseModel
from typing import Optional
from synthadoc.storage.wiki import WikiStorage, WikiPage, LifecycleState
from synthadoc.agents.export_agent import EXPORT_FORMATS


def _make_export_app(wiki_root: Path, store: WikiStorage) -> FastAPI:
    from synthadoc.agents.export_agent import ExportAgent, ExportOptions

    app = FastAPI()

    class ExportRequest(BaseModel):
        format: str
        status_filter: str = "all"
        context_pack: Optional[str] = None

    @app.post("/export")
    async def export_wiki(req: ExportRequest):
        if req.format not in EXPORT_FORMATS:
            raise HTTPException(status_code=422, detail=f"Unknown format: {req.format!r}")
        agent = ExportAgent(
            store=store,
            wiki_name=wiki_root.name,
            audit_db_path=wiki_root / ".synthadoc" / "audit.db",
            routing_path=wiki_root / "ROUTING.md",
        )
        opts = ExportOptions(
            format=req.format,
            status_filter=req.status_filter,
            context_pack=req.context_pack,
        )
        content = await agent.export(opts)
        _CONTENT_TYPES = {
            "llms.txt":      "text/plain; charset=utf-8",
            "llms-full.txt": "text/plain; charset=utf-8",
            "graphml":       "application/xml",
            "json":          "application/json",
        }
        return Response(content=content, media_type=_CONTENT_TYPES[req.format])

    return app


def _write_page(store, slug, status=LifecycleState.ACTIVE):
    page = WikiPage(
        title=slug.replace("-", " ").title(), tags=[], content="Content.",
        status=status, confidence="high", sources=[], created="2026-05-26T00:00:00",
    )
    store.write_page(slug, page)


def test_export_llms_txt_returns_text_plain(tmp_path):
    store = WikiStorage(tmp_path / "wiki")
    _write_page(store, "babbage")
    app = _make_export_app(tmp_path, store)
    client = TestClient(app)
    resp = client.post("/export", json={"format": "llms.txt"})
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert "## Pages" in resp.text


def test_export_graphml_returns_application_xml(tmp_path):
    store = WikiStorage(tmp_path / "wiki")
    _write_page(store, "babbage")
    app = _make_export_app(tmp_path, store)
    client = TestClient(app)
    resp = client.post("/export", json={"format": "graphml"})
    assert resp.status_code == 200
    assert "application/xml" in resp.headers["content-type"]
    assert "<graphml" in resp.text


def test_export_json_returns_application_json(tmp_path):
    store = WikiStorage(tmp_path / "wiki")
    _write_page(store, "babbage")
    app = _make_export_app(tmp_path, store)
    client = TestClient(app)
    resp = client.post("/export", json={"format": "json"})
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    data = resp.json()
    assert "pages" in data


def test_export_llms_full_txt_returns_text_plain(tmp_path):
    store = WikiStorage(tmp_path / "wiki")
    _write_page(store, "babbage")
    app = _make_export_app(tmp_path, store)
    client = TestClient(app)
    resp = client.post("/export", json={"format": "llms-full.txt"})
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]


def test_export_unknown_format_returns_422(tmp_path):
    store = WikiStorage(tmp_path / "wiki")
    app = _make_export_app(tmp_path, store)
    client = TestClient(app)
    resp = client.post("/export", json={"format": "bogus"})
    assert resp.status_code == 422


def test_export_status_filter_forwarded(tmp_path):
    store = WikiStorage(tmp_path / "wiki")
    _write_page(store, "active-page", LifecycleState.ACTIVE)
    _write_page(store, "stale-page", LifecycleState.STALE)
    app = _make_export_app(tmp_path, store)
    client = TestClient(app)
    resp = client.post("/export", json={"format": "llms.txt", "status_filter": "active"})
    assert resp.status_code == 200
    assert "active-page" in resp.text
    assert "stale-page" not in resp.text
