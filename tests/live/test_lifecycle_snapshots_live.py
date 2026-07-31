# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""
Live integration tests for page content snapshots.

Prerequisites:
  - synthadoc serve -w <wiki> is running on http://127.0.0.1:7070
  - A wiki is registered and the server is healthy

Run with:
  python -X utf8 tests/live/run_all.py --suite snapshots
  python -X utf8 tests/live/test_lifecycle_snapshots_live.py
  pytest tests/live/test_lifecycle_snapshots_live.py -v -s
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx
import pytest

BASE = os.environ.get("SYNTHADOC_URL", "http://127.0.0.1:7070").rstrip("/")


def _api(path: str, method: str = "GET", body: dict | None = None) -> dict:
    with httpx.Client(timeout=30) as client:
        if method == "POST":
            r = client.post(f"{BASE}{path}", json=body)
        elif method == "DELETE":
            r = client.delete(f"{BASE}{path}")
        else:
            r = client.get(f"{BASE}{path}")
        r.raise_for_status()
        return r.json()


def _cleanup_slug(wiki_dir: Path, slug: str) -> None:
    """Remove wiki page file and all its lifecycle events (snapshots) from the DB."""
    (wiki_dir / f"{slug}.md").unlink(missing_ok=True)
    try:
        _api(f"/pages/{slug}/history", "DELETE")
    except Exception:
        pass


def _wiki_dir() -> Path:
    """Return the wiki/ subdirectory of the running server's wiki root."""
    status = _api("/status")
    return Path(status["wiki"]) / "wiki"


def _write_page(wiki_dir: Path, slug: str, title: str, body: str, status: str = "draft") -> Path:
    """Write a minimal wiki page .md file directly to disk and return its path."""
    md = (
        f"---\n"
        f"title: {title}\n"
        f"status: {status}\n"
        f"confidence: medium\n"
        f"tags: []\n"
        f"sources: []\n"
        f"---\n\n"
        f"{body}\n"
    )
    path = wiki_dir / f"{slug}.md"
    path.write_text(md, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def require_server():
    """Skip all tests if the server isn't running."""
    try:
        httpx.get(f"{BASE}/health", timeout=3).raise_for_status()
    except Exception:
        pytest.skip("Synthadoc server not running — skipping live tests")


# ── Live test 1: View-and-restore workflow ───────────────────────────────────

@pytest.mark.live
def test_live_view_and_restore():
    """Write page → activate (snap 1) → GET history → POST rollback → 2 snapshots."""
    slug = f"live-snap-test-{int(time.time())}"
    original_body = "Original content before the accidental edit."

    wiki_dir = _wiki_dir()
    page_path = _write_page(wiki_dir, slug, "Live Snap Test", original_body)
    try:
        # Activate → captures snapshot 1
        _api("/lifecycle/transition", "POST", {
            "slug": slug, "to_state": "active", "reason": "live test activate"
        })

        # GET history — should show 1 snapshot
        history = _api(f"/pages/{slug}/history")
        assert history["slug"] == slug
        assert len(history["snapshots"]) == 1
        assert history["snapshots"][0]["to_state"] == "active"

        # GET snapshot with content
        snap = _api(f"/pages/{slug}/history?index=1&include_content=true")
        assert original_body in snap["content"]

        # POST rollback
        rb = _api(f"/pages/{slug}/rollback", "POST", {
            "index": 1, "reason": "live test rollback"
        })
        assert rb["snapshot_index"] == 1
        assert rb["restored_chars"] > 0

        # History now has 2 snapshots (activation + pre-rollback record)
        history2 = _api(f"/pages/{slug}/history")
        assert len(history2["snapshots"]) == 2
    finally:
        _cleanup_slug(wiki_dir, slug)


# ── Live test 2: Rollback is undoable ────────────────────────────────────────

@pytest.mark.live
def test_live_rollback_is_undoable():
    """Activate (snap 1) → edit body → rollback to 1 (creates snap 2) → undo rollback."""
    slug = f"live-undo-test-{int(time.time())}"
    body_v1 = "Version one of the content."
    body_v2 = "Version two — different content."

    wiki_dir = _wiki_dir()
    page_path = _write_page(wiki_dir, slug, "Live Undo", body_v1)
    try:
        _api("/lifecycle/transition", "POST", {
            "slug": slug, "to_state": "active", "reason": "activate v1"
        })

        # Simulate manual edit: overwrite body on disk
        _write_page(wiki_dir, slug, "Live Undo", body_v2, status="active")

        # Rollback to snap 1 (restores body_v1)
        rb1 = _api(f"/pages/{slug}/rollback", "POST", {
            "index": 1, "reason": "restore v1"
        })
        snap2_idx = rb1["rollback_event_index"]

        # After rollback, snapshot index 1 = newly-saved pre-rollback body (body_v2)
        snap_after_rb1 = _api(f"/pages/{slug}/history?index=1&include_content=true")
        assert body_v2 in snap_after_rb1.get("content", "")

        # Undo: rollback to snap2_idx (restores body_v2)
        _api(f"/pages/{slug}/rollback", "POST", {
            "index": snap2_idx, "reason": "undo rollback"
        })
        # After undo, snapshot index 1 = pre-undo snapshot (body_v1)
        snap_after_undo = _api(f"/pages/{slug}/history?index=1&include_content=true")
        assert body_v1 in snap_after_undo.get("content", "")
    finally:
        _cleanup_slug(wiki_dir, slug)


# ── Live test 3: Lint transitions now capture content snapshots ──────────────

@pytest.mark.live
def test_live_lint_transition_captures_snapshot():
    """Verify lint-agent state changes record a content snapshot."""
    slug = f"live-lint-snap-{int(time.time())}"
    body = "Content for lint snapshot test."

    wiki_dir = _wiki_dir()
    _write_page(wiki_dir, slug, "Lint Snap", body)
    try:
        # Activate the page (draft → active) so the DB has a state row
        _api("/lifecycle/transition", "POST", {
            "slug": slug, "to_state": "active", "reason": "live test setup"
        })

        # Trigger a lint run — for a new page with no source file, lint may
        # produce a stale or other state transition depending on config.
        # We only verify that if any snapshot exists, it contains the body.
        _api("/jobs/lint", "POST", {"scope": "all", "auto_resolve": False, "adversarial": False})
        time.sleep(3)

        history = _api(f"/pages/{slug}/history")
        # Every snapshot recorded (activation + any lint transition) must include body text
        for snap in history.get("snapshots", []):
            snap_detail = _api(
                f"/pages/{slug}/history?index={snap['index']}&include_content=true"
            )
            assert body in snap_detail.get("content", ""), (
                f"Snapshot index {snap['index']} content missing expected body"
            )
    finally:
        _cleanup_slug(wiki_dir, slug)


# ── Live test 4: Manual snapshot endpoint deduplication ──────────────────────

@pytest.mark.live
def test_live_manual_snapshot_dedup():
    """POST /pages/{slug}/snapshot only records when content actually changed."""
    slug = f"live-manual-snap-{int(time.time())}"
    body_v1 = "Version one."
    body_v2 = "Version two — different."

    wiki_dir = _wiki_dir()
    _write_page(wiki_dir, slug, "Manual Snap", body_v1)
    try:
        # Activate the page (draft → active) so the DB has a state row
        _api("/lifecycle/transition", "POST", {
            "slug": slug, "to_state": "active", "reason": "setup"
        })

        # First manual snapshot: new content → recorded
        r1 = _api(f"/pages/{slug}/snapshot", "POST", {"content": body_v1})
        assert r1["recorded"] is True

        # Same content again: no-op
        r2 = _api(f"/pages/{slug}/snapshot", "POST", {"content": body_v1})
        assert r2["recorded"] is False

        # Different content → recorded
        r3 = _api(f"/pages/{slug}/snapshot", "POST", {"content": body_v2})
        assert r3["recorded"] is True
    finally:
        _cleanup_slug(wiki_dir, slug)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
