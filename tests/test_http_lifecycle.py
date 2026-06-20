# tests/test_http_lifecycle.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import asyncio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from synthadoc.storage.wiki import WikiStorage, WikiPage, LifecycleState
from synthadoc.storage.log import AuditDB


def _make_test_app(store: WikiStorage, db: AuditDB) -> FastAPI:
    """Minimal FastAPI app with only lifecycle endpoints for testing."""
    from datetime import datetime, timezone
    from fastapi import HTTPException
    from pydantic import BaseModel
    from synthadoc.storage.wiki import TriggerSource

    app = FastAPI()

    class LifecycleTransitionRequest(BaseModel):
        slug: str
        to_state: str
        reason: str

    @app.get("/lifecycle/status")
    async def lifecycle_status():
        return await db.get_lifecycle_summary()

    @app.get("/lifecycle/events")
    async def lifecycle_events(slug: str = "", to_state: str = "",
                                limit: int = 50, offset: int = 0):
        events, total = await db.get_lifecycle_events(
            slug=slug or None, to_state=to_state or None,
            limit=limit, offset=offset
        )
        return {"events": events, "total": total}

    @app.post("/lifecycle/transition")
    async def lifecycle_transition(req: LifecycleTransitionRequest):
        from synthadoc.storage.wiki import validate_lifecycle_transition
        page = store.read_page(req.slug)
        if not page:
            raise HTTPException(status_code=404, detail=f"Page not found: {req.slug}")
        from_state = page.status
        err = validate_lifecycle_transition(from_state, req.to_state)
        if err:
            raise HTTPException(status_code=422, detail=err)
        page.status = req.to_state
        store.write_page(req.slug, page)
        ts = datetime.now(timezone.utc).isoformat()
        await db.set_page_state(req.slug, req.to_state, TriggerSource.USER)
        await db.record_lifecycle_event(req.slug, from_state, req.to_state,
                                         req.reason, TriggerSource.USER)
        return {"slug": req.slug, "from_state": from_state, "to_state": req.to_state, "timestamp": ts}

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
    page = WikiPage(title="Alan Turing", tags=[], content="# Alan Turing",
                    status=LifecycleState.DRAFT, confidence="medium", sources=[])
    store.write_page("alan-turing", page)
    app = _make_test_app(store, db)
    return TestClient(app)


def test_lifecycle_status_returns_flat_counts_for_all_states(client):
    resp = client.get("/lifecycle/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "counts" not in data
    for state in ("draft", "active", "contradicted", "stale", "archived"):
        assert state in data
    assert data[LifecycleState.DRAFT] >= 1


def test_lifecycle_events_total_reflects_db_count(client):
    resp = client.get("/lifecycle/events?limit=1&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert "total" in data
    # total must be >= number of events on this page
    assert data["total"] >= len(data["events"])


def test_lifecycle_transition_valid_returns_slug_states_timestamp(client):
    resp = client.post("/lifecycle/transition", json={
        "slug": "alan-turing",
        "to_state": LifecycleState.ACTIVE,
        "reason": "reviewed",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["slug"] == "alan-turing"
    assert data["from_state"] == LifecycleState.DRAFT
    assert data["to_state"] == LifecycleState.ACTIVE
    assert "timestamp" in data
    assert "ok" not in data


def test_lifecycle_transition_same_state_returns_422(client):
    resp = client.post("/lifecycle/transition", json={
        "slug": "alan-turing",
        "to_state": LifecycleState.DRAFT,
        "reason": "no-op test",
    })
    assert resp.status_code == 422
    assert "already in state" in resp.json()["detail"]


def test_lifecycle_transition_valid_cross_state_allowed(client):
    """A valid non-trivial cross-state transition must succeed."""
    # draft → archived: abandon a draft without publishing
    resp = client.post("/lifecycle/transition", json={
        "slug": "alan-turing",
        "to_state": LifecycleState.ARCHIVED,
        "reason": "abandoned draft",
    })
    assert resp.status_code == 200, resp.json()
    assert resp.json()["to_state"] == LifecycleState.ARCHIVED


def test_lifecycle_transition_blocked_returns_422(client):
    """Transitions not in the allowed graph must return 422."""
    # draft → contradicted: a draft page cannot be contradicted (not published yet)
    resp = client.post("/lifecycle/transition", json={
        "slug": "alan-turing",
        "to_state": LifecycleState.CONTRADICTED,
        "reason": "should be blocked",
    })
    assert resp.status_code == 422
    assert "not permitted" in resp.json()["detail"]


def test_lifecycle_transition_stale_to_active_allowed(client):
    """stale → active must be permitted (re-validate without revision)."""
    # First advance to active, then stale
    client.post("/lifecycle/transition", json={
        "slug": "alan-turing", "to_state": LifecycleState.ACTIVE, "reason": "publish"
    })
    client.post("/lifecycle/transition", json={
        "slug": "alan-turing", "to_state": LifecycleState.STALE, "reason": "source changed"
    })
    resp = client.post("/lifecycle/transition", json={
        "slug": "alan-turing",
        "to_state": LifecycleState.ACTIVE,
        "reason": "re-validated, still accurate",
    })
    assert resp.status_code == 200, resp.json()
    assert resp.json()["from_state"] == LifecycleState.STALE
    assert resp.json()["to_state"] == LifecycleState.ACTIVE
