# tests/test_http_lifecycle.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import asyncio
import pytest
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from synthadoc.storage.wiki import WikiStorage, WikiPage, LifecycleState
from synthadoc.storage.log import AuditDB


def _make_test_app(wiki_root: Path, store: WikiStorage, db: AuditDB) -> FastAPI:
    """Minimal FastAPI app with only lifecycle endpoints for testing."""
    from fastapi import HTTPException
    from pydantic import BaseModel
    from synthadoc.storage.wiki import TriggerSource

    app = FastAPI()

    _ALLOWED_TRANSITIONS = {
        (LifecycleState.DRAFT,        LifecycleState.ACTIVE),
        (LifecycleState.DRAFT,        LifecycleState.ARCHIVED),
        (LifecycleState.ACTIVE,       LifecycleState.ARCHIVED),
        (LifecycleState.ACTIVE,       LifecycleState.STALE),
        (LifecycleState.CONTRADICTED, LifecycleState.ARCHIVED),
        (LifecycleState.STALE,        LifecycleState.DRAFT),
        (LifecycleState.STALE,        LifecycleState.ARCHIVED),
        (LifecycleState.ARCHIVED,     LifecycleState.DRAFT),
    }

    class LifecycleTransitionRequest(BaseModel):
        slug: str
        to_state: str
        reason: str

    @app.get("/lifecycle/status")
    async def lifecycle_status():
        counts = await db.get_lifecycle_summary()
        return {"counts": counts}

    @app.get("/lifecycle/events")
    async def lifecycle_events(slug: str = "", to_state: str = "",
                                limit: int = 50, offset: int = 0):
        events = await db.get_lifecycle_events(
            slug=slug or None, to_state=to_state or None,
            limit=limit, offset=offset
        )
        return {"events": events, "total": len(events)}

    @app.post("/lifecycle/transition")
    async def lifecycle_transition(req: LifecycleTransitionRequest):
        page = store.read_page(req.slug)
        if not page:
            raise HTTPException(status_code=404, detail=f"Page not found: {req.slug}")
        from_state = page.status
        if (from_state, req.to_state) not in _ALLOWED_TRANSITIONS:
            raise HTTPException(
                status_code=422,
                detail=f"Transition {from_state!r} -> {req.to_state!r} is not allowed.",
            )
        page.status = req.to_state
        store.write_page(req.slug, page)
        await db.set_page_state(req.slug, req.to_state, TriggerSource.USER)
        await db.record_lifecycle_event(req.slug, from_state, req.to_state,
                                         req.reason, TriggerSource.USER)
        return {"ok": True, "slug": req.slug, "from_state": from_state, "to_state": req.to_state}

    return app


@pytest.fixture
def client(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    store = WikiStorage(wiki_dir)
    db = AuditDB(tmp_path / ".synthadoc" / "audit.db")
    asyncio.run(db.init())
    asyncio.run(
        db.set_page_state("alan-turing", LifecycleState.DRAFT, "ingest")
    )
    # Write a draft page for transition tests
    page = WikiPage(title="Alan Turing", tags=[], content="# Alan Turing",
                    status=LifecycleState.DRAFT, confidence="medium", sources=[])
    store.write_page("alan-turing", page)
    app = _make_test_app(tmp_path, store, db)
    return TestClient(app)


def test_lifecycle_status_returns_counts(client):
    resp = client.get("/lifecycle/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "counts" in data
    assert data["counts"].get(LifecycleState.DRAFT, 0) >= 1


def test_lifecycle_events_returns_paginated(client):
    resp = client.get("/lifecycle/events?limit=10&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert "total" in data


def test_lifecycle_transition_valid(client):
    resp = client.post("/lifecycle/transition", json={
        "slug": "alan-turing",
        "to_state": LifecycleState.ACTIVE,
        "reason": "reviewed",
    })
    assert resp.status_code == 200
    assert resp.json()["to_state"] == LifecycleState.ACTIVE


def test_lifecycle_transition_invalid_rejected(client):
    resp = client.post("/lifecycle/transition", json={
        "slug": "alan-turing",
        "to_state": LifecycleState.CONTRADICTED,
        "reason": "test",
    })
    assert resp.status_code == 422
