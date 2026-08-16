# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""
Live integration tests for the Adversarial Lint Gate (v1.3.0).

Tests verify that:
  1. A lint run auto-demotes pages with ≥ adversarial_gate_threshold warnings to
     `contradicted` and records the reason in the lifecycle audit trail.
  2. A subsequent `lint run --auto-resolve` does NOT re-promote a gate-demoted
     page (cycling prevention), and records the skip in the lifecycle audit trail.

Prerequisites:
  - synthadoc serve -w history-of-computing running on SYNTHADOC_URL
  - ANTHROPIC_API_KEY set in environment
  - adversarial_gate_threshold = 3 in the wiki's config.toml (new-wiki default)
  - alan-turing page has 3 deliberate adversarial warning triggers

Run:
  pytest tests/live/test_adversarial_gate_live.py -v -s
  python -X utf8 tests/live/test_adversarial_gate_live.py
"""
from __future__ import annotations

import os
import time

import httpx
import pytest

BASE = os.environ.get("SYNTHADOC_URL", "http://127.0.0.1:7070").rstrip("/")
_TERMINAL = {"completed", "failed", "cancelled", "dead", "skipped"}
_GATE_SLUG = "alan-turing"   # has 3 deliberate adversarial triggers in the demo wiki


# ── Helpers ───────────────────────────────────────────────────────────────────

def _api(path: str, method: str = "GET", body: dict | None = None) -> dict:
    with httpx.Client(timeout=60) as client:
        if method == "POST":
            r = client.post(f"{BASE}{path}", json=body)
        else:
            r = client.get(f"{BASE}{path}")
        r.raise_for_status()
        return r.json()


def _wait_job(job_id: str, timeout: int = 300) -> dict:
    """Poll GET /jobs/{id} until the job reaches a terminal state."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = _api(f"/jobs/{job_id}")
        if job.get("status") in _TERMINAL:
            return job
        time.sleep(3)
    raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")


def _page_state(slug: str) -> str:
    """Return the current lifecycle state of a page from GET /lifecycle/pages."""
    data = _api("/lifecycle/pages")
    for p in data.get("pages", []):
        if p["slug"] == slug:
            return p["state"]
    raise KeyError(f"Slug '{slug}' not found in /lifecycle/pages")


def _lifecycle_events(slug: str) -> list[dict]:
    """Return lifecycle events for a slug from GET /lifecycle/events."""
    data = _api(f"/lifecycle/events?slug={slug}")
    return data.get("events", [])


def _ensure_active(slug: str) -> None:
    """Transition slug to active if it is not already active."""
    state = _page_state(slug)
    if state != "active":
        _api("/lifecycle/transition", method="POST", body={
            "slug": slug,
            "to_state": "active",
            "reason": "live test setup — restoring to active",
        })
        time.sleep(1)


def _run_lint(scope: str = "all", auto_resolve: bool = False) -> dict:
    """Enqueue a lint job and wait for completion. Returns the job dict."""
    resp = _api("/jobs/lint", method="POST", body={
        "scope": scope,
        "auto_resolve": auto_resolve,
        "adversarial": True,
        "lifecycle": True,
    })
    job_id = resp["job_id"]
    return _wait_job(job_id, timeout=300)


# ── Server gate ───────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def require_server():
    """Skip all tests if the server isn't reachable."""
    try:
        httpx.get(f"{BASE}/health", timeout=3).raise_for_status()
    except Exception:
        pytest.skip("Synthadoc server not running — skipping live tests")


# ══════════════════════════════════════════════════════════════════════════════
# Test 1 — Gate demotion: lint demotes alan-turing to contradicted
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(360)
def test_gate_demotes_alan_turing_on_lint_run():
    """
    A full lint run with adversarial_gate_threshold=3 must auto-demote alan-turing
    (which has 3 deliberate adversarial triggers) to contradicted and record the
    reason in the lifecycle audit trail.
    """
    # Setup: ensure alan-turing starts active
    _ensure_active(_GATE_SLUG)

    try:
        # Run a full lint pass (adversarial + lifecycle)
        job = _run_lint(scope="all")
        assert job["status"] == "completed", f"Lint job failed: {job}"

        # alan-turing must now be contradicted
        state = _page_state(_GATE_SLUG)
        assert state == "contradicted", (
            f"Expected alan-turing to be 'contradicted' after gate lint, got '{state}'"
        )

        # Lifecycle audit trail must contain the auto-demotion entry
        events = _lifecycle_events(_GATE_SLUG)
        gate_events = [
            e for e in events
            if "auto-demoted" in (e.get("reason") or "")
            and "adversarial gate" in (e.get("reason") or "")
        ]
        assert gate_events, (
            f"Expected an 'auto-demoted: adversarial gate' lifecycle event for {_GATE_SLUG}. "
            f"Events found: {[e.get('reason') for e in events]}"
        )

    finally:
        # Rollback: restore alan-turing to active
        _ensure_active(_GATE_SLUG)


# ══════════════════════════════════════════════════════════════════════════════
# Test 2 — Cycle prevention: lint --auto-resolve does NOT re-promote gate pages
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(600)
def test_auto_resolve_does_not_re_promote_gate_demoted_page():
    """
    After the gate demotes alan-turing to contradicted, running lint with
    auto_resolve=True must NOT re-promote it to active (which would cycle).
    The lifecycle audit trail must record the auto-resolve skip with reason.
    """
    # Setup: ensure alan-turing starts active
    _ensure_active(_GATE_SLUG)

    try:
        # Step 1: run full lint to trigger the gate demotion
        job1 = _run_lint(scope="all")
        assert job1["status"] == "completed", f"Lint job 1 failed: {job1}"

        state_after_gate = _page_state(_GATE_SLUG)
        assert state_after_gate == "contradicted", (
            f"Gate did not fire — alan-turing is '{state_after_gate}', not 'contradicted'. "
            f"Check that adversarial_gate_threshold=3 is set in config.toml and that "
            f"the alan-turing page has 3 adversarial triggers."
        )

        # Step 2: run lint with auto_resolve — this should NOT promote the page
        job2 = _run_lint(scope="contradictions", auto_resolve=True)
        assert job2["status"] == "completed", f"Lint job 2 failed: {job2}"

        # Page must still be contradicted — cycling prevented
        state_after_resolve = _page_state(_GATE_SLUG)
        assert state_after_resolve == "contradicted", (
            f"Cycling problem: alan-turing was re-promoted to '{state_after_resolve}' "
            f"by auto-resolve even though it still has adversarial warnings ≥ threshold. "
            f"The adversarial_gate_skipped_resolve guard is not working."
        )

        # Lifecycle audit trail must record the skip
        events = _lifecycle_events(_GATE_SLUG)
        skip_events = [
            e for e in events
            if "auto-resolve skipped" in (e.get("reason") or "")
            and "adversarial gate" in (e.get("reason") or "")
        ]
        assert skip_events, (
            f"Expected an 'auto-resolve skipped: adversarial gate' lifecycle event for "
            f"{_GATE_SLUG}. Events found: {[e.get('reason') for e in events]}"
        )

    finally:
        # Rollback: restore alan-turing to active
        _ensure_active(_GATE_SLUG)
