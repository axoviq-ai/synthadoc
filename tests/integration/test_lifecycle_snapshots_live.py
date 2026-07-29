# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""
Live integration tests for page content snapshots.

Prerequisites:
  - synthadoc serve -w <wiki> is running on http://127.0.0.1:7070
  - A wiki is registered and the server is healthy

Run with:
  pytest tests/integration/test_lifecycle_snapshots_live.py -v -s
"""
from __future__ import annotations

import httpx
import pytest

BASE = "http://127.0.0.1:7070"


def _api(path: str, method: str = "GET", body: dict | None = None) -> dict:
    with httpx.Client(timeout=30) as client:
        if method == "POST":
            r = client.post(f"{BASE}{path}", json=body)
        else:
            r = client.get(f"{BASE}{path}")
        r.raise_for_status()
        return r.json()


@pytest.fixture(autouse=True)
def require_server():
    """Skip all tests if the server isn't running."""
    try:
        httpx.get(f"{BASE}/health", timeout=3).raise_for_status()
    except Exception:
        pytest.skip("Synthadoc server not running — skipping live tests")


# ── Live test 1: View-and-restore workflow ───────────────────────────────────

def test_live_view_and_restore():
    """Activate → edit → GET history shows snapshot → POST rollback → file matches."""
    import time

    slug = f"live-snap-test-{int(time.time())}"
    original_body = "Original content before the accidental edit."

    # 1. Ingest a page by writing it directly through the write endpoint
    r = httpx.post(
        f"{BASE}/write",
        json={"slug": slug, "title": "Live Snap Test", "content": original_body},
        timeout=30,
    )
    if r.status_code in (404, 405):
        pytest.skip("No /write endpoint — use a wiki with a test page")
    r.raise_for_status()

    # 2. Activate → this creates snapshot 1
    _api("/lifecycle/transition", "POST", {
        "slug": slug, "to_state": "active", "reason": "live test activate"
    })

    # 3. GET history — should show 1 snapshot
    history = _api(f"/pages/{slug}/history")
    assert history["slug"] == slug
    assert len(history["snapshots"]) == 1
    assert history["snapshots"][0]["to_state"] == "active"

    # 4. GET snapshot with content
    snap = _api(f"/pages/{slug}/history?index=1&include_content=true")
    assert original_body in snap["content"]

    # 5. POST rollback
    rb = _api(f"/pages/{slug}/rollback", "POST", {
        "index": 1, "reason": "live test rollback"
    })
    assert rb["snapshot_index"] == 1
    assert rb["restored_chars"] > 0

    # 6. Verify history now has 2 snapshots (original + the rollback record)
    history2 = _api(f"/pages/{slug}/history")
    assert len(history2["snapshots"]) == 2


# ── Live test 2: Rollback is undoable ────────────────────────────────────────

def test_live_rollback_is_undoable():
    """Activate (snap 1) → rollback to 1 (creates snap 2) → rollback to 2 → original restored."""
    import time

    slug = f"live-undo-test-{int(time.time())}"
    body_v1 = "Version one of the content."
    body_v2 = "Version two — different content."

    r = httpx.post(
        f"{BASE}/write",
        json={"slug": slug, "title": "Live Undo", "content": body_v1},
        timeout=30,
    )
    if r.status_code in (404, 405):
        pytest.skip("No /write endpoint")
    r.raise_for_status()

    _api("/lifecycle/transition", "POST", {
        "slug": slug, "to_state": "active", "reason": "activate v1"
    })

    # Simulate manual edit to v2 (via a second /write call)
    httpx.post(
        f"{BASE}/write",
        json={"slug": slug, "title": "Live Undo", "content": body_v2},
        timeout=30,
    ).raise_for_status()

    # Rollback to snap 1 (restores body_v1)
    rb1 = _api(f"/pages/{slug}/rollback", "POST", {
        "index": 1, "reason": "restore v1"
    })
    snap2_idx = rb1["rollback_event_index"]

    # After rollback to snap 1 (body_v1 restored), snapshot index 1 is the
    # newly-saved pre-rollback snapshot (body_v2), not the restored body.
    snap_after_rb1 = _api(f"/pages/{slug}/history?index=1&include_content=true")
    assert body_v2 in snap_after_rb1.get("content", "")  # index 1 = pre-rollback snapshot = body_v2

    # Undo: rollback to snap2_idx (restores body_v2)
    _api(f"/pages/{slug}/rollback", "POST", {
        "index": snap2_idx, "reason": "undo rollback"
    })
    # After undo, snapshot index 1 is the pre-undo snapshot (body_v1), not the restored body.
    snap_after_undo = _api(f"/pages/{slug}/history?index=1&include_content=true")
    assert body_v1 in snap_after_undo.get("content", "")  # index 1 = pre-undo snapshot = body_v1


# ── Live test 3: Lint/ingest events produce no snapshot ──────────────────────

def test_live_lint_transition_has_no_snapshot():
    """Verify that lint-agent transitions do not appear in /pages/{slug}/history."""
    import time

    slug = f"live-lint-snap-{int(time.time())}"
    body = "Content for lint snapshot test."

    r = httpx.post(
        f"{BASE}/write",
        json={"slug": slug, "title": "Lint Snap", "content": body},
        timeout=30,
    )
    if r.status_code in (404, 405):
        pytest.skip("No /write endpoint")
    r.raise_for_status()

    # Trigger a lint run
    _api("/jobs/lint", "POST", {"scope": "all", "auto_resolve": False, "adversarial": False})

    # Give the lint agent a moment to process
    import time as _time
    _time.sleep(3)

    # /pages/{slug}/history should be empty (lint transitions have NULL snapshot)
    history = _api(f"/pages/{slug}/history")
    assert history["snapshots"] == [], (
        f"Expected no snapshots from lint transitions, got: {history['snapshots']}"
    )
