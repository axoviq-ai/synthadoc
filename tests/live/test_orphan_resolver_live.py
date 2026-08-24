# tests/live/test_orphan_resolver_live.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
"""Live end-to-end tests for the Orphan Resolver Workflow.

Modelled after test_contradiction_resolver_live.py.

Each test creates dedicated pages (prefixed with _live-test-orphan-resolver-)
so they never conflict with real wiki content. A finally block archives and
deletes all created pages so the wiki is left in its original state.

Prerequisites:
  - synthadoc serve -w <wiki> running on SYNTHADOC_URL (default 127.0.0.1:7070)
  - ANTHROPIC_API_KEY (or equivalent provider key) set

Run:
  pytest tests/live/test_orphan_resolver_live.py -v -s -m live

Environment variables:
  SYNTHADOC_WIKI    Wiki name (default: demo)
  SYNTHADOC_URL     Server base URL (default: http://127.0.0.1:7070)
"""
from __future__ import annotations

import json
import os
import sys
import time

import httpx
import pytest

BASE = os.environ.get("SYNTHADOC_URL", "http://127.0.0.1:7070").rstrip("/")
WIKI = os.environ.get("SYNTHADOC_WIKI", "demo")

_ORPHAN_SLUG   = "_live-test-orphan-resolver-orphan"
_RELATED_SLUG1 = "_live-test-orphan-resolver-related-a"
_RELATED_SLUG2 = "_live-test-orphan-resolver-related-b"
_ISOLATED_SLUG = "_live-test-orphan-resolver-isolated"

def _api(path: str) -> str:
    return f"{BASE}/wiki/{WIKI}{path}"


def _ingest_page(client: httpx.Client, slug: str, title: str, content: str) -> None:
    """Write a page directly via the ingest API and activate it."""
    # Use the raw write endpoint if available, or ingest a temp markdown file
    resp = client.post(
        _api("/pages"),
        json={
            "slug": slug,
            "title": title,
            "content": content,
            "status": "active",
        },
        timeout=30,
    )
    assert resp.status_code in (200, 201), f"Failed to create {slug}: {resp.text}"


def _delete_page(client: httpx.Client, slug: str) -> None:
    resp = client.delete(_api(f"/pages/{slug}"), timeout=10)
    # 404 is acceptable — page may not have been created
    assert resp.status_code in (200, 204, 404), f"Failed to delete {slug}: {resp.text}"


def _run_workflow(client: httpx.Client, query: str, timeout: int = 180) -> list[dict]:
    """Open a session, run a workflow query, collect all SSE events."""
    sess_resp = client.post(_api("/session"), timeout=10)
    sess_resp.raise_for_status()
    session_id = sess_resp.json()["session_id"]

    events: list[dict] = []
    deadline = time.time() + timeout
    with client.stream(
        "POST",
        _api("/query"),
        json={"session_id": session_id, "question": query},
        timeout=timeout,
    ) as resp:
        for line in resp.iter_lines():
            if time.time() > deadline:
                break
            if line.startswith("data:"):
                try:
                    events.append(json.loads(line[5:].strip()))
                except json.JSONDecodeError:
                    pass
            if any(e.get("event") == "done" for e in events):
                break
    return events


def _find_orphan_slugs_via_api(client: httpx.Client) -> list[str]:
    """Call the lint report endpoint and return orphan slugs."""
    resp = client.get(_api("/lint/report"), timeout=30)
    resp.raise_for_status()
    return resp.json().get("orphans", [])


@pytest.mark.live
def test_resolves_single_orphan():
    """Workflow inserts a wikilink so the orphan is no longer orphaned."""
    with httpx.Client() as client:
        try:
            # Create orphan (no page links to it)
            _ingest_page(client, _ORPHAN_SLUG, "Orphan Topic",
                         "This page covers orphan topic details.")
            # Create two related pages (neither references the orphan yet)
            _ingest_page(client, _RELATED_SLUG1, "Related Alpha",
                         "Information about orphan topic background.")
            _ingest_page(client, _RELATED_SLUG2, "Related Beta",
                         "Further context on orphan topic usage.")

            # Confirm the orphan exists in the lint report
            orphans_before = _find_orphan_slugs_via_api(client)
            assert _ORPHAN_SLUG in orphans_before, (
                f"{_ORPHAN_SLUG} not in orphans: {orphans_before}"
            )

            # Run the workflow targeting just this slug
            events = _run_workflow(
                client,
                f"run orphan resolver --slug {_ORPHAN_SLUG}",
            )

            # At least one event should have fired
            assert events, "No SSE events received from workflow"

            # After the workflow, the orphan should be resolved
            orphans_after = _find_orphan_slugs_via_api(client)
            assert _ORPHAN_SLUG not in orphans_after, (
                f"{_ORPHAN_SLUG} still orphaned after workflow run.\n"
                f"Events: {events}"
            )

        finally:
            for slug in [_ORPHAN_SLUG, _RELATED_SLUG1, _RELATED_SLUG2]:
                _delete_page(client, slug)


@pytest.mark.live
def test_escalation_on_isolated_orphan():
    """Orphan with no topically related pages triggers tool_notify escalation."""
    with httpx.Client() as client:
        try:
            # Create a page about an extremely niche topic unlikely to match any other page
            _ingest_page(
                client, _ISOLATED_SLUG, "Zzyzx Niche Topic XQ9",
                "This page covers an extremely specific concept with no related pages."
            )

            events = _run_workflow(
                client,
                f"run orphan resolver --slug {_ISOLATED_SLUG}",
            )

            # Should have received a notice event (tool_notify escalation)
            notice_events = [e for e in events if e.get("event") == "notice"]
            assert notice_events, (
                "Expected a notice event (escalation) but none received.\n"
                f"Events: {events}"
            )
            # Escalation message should include the re-run suggestion
            notice_texts = " ".join(
                e.get("data", {}).get("text", "") for e in notice_events
            )
            assert "Re-run" in notice_texts or "re-run" in notice_texts, (
                f"Escalation message missing re-run hint. Notice: {notice_texts}"
            )

        finally:
            _delete_page(client, _ISOLATED_SLUG)


@pytest.mark.live
def test_slug_filter_targets_single():
    """--slug flag limits workflow to just the specified orphan."""
    with httpx.Client() as client:
        try:
            _ingest_page(client, _ORPHAN_SLUG, "Target Orphan",
                         "Target page for single-slug test.")
            _ingest_page(client, _ISOLATED_SLUG, "Other Orphan",
                         "Should not be processed in this run.")

            events = _run_workflow(
                client,
                f"run orphan resolver --slug {_ORPHAN_SLUG}",
            )

            # Only the targeted slug should appear in workflow events; the other
            # orphan should not have been processed by the workflow.
            event_text = json.dumps(events)
            assert _ORPHAN_SLUG in event_text, (
                f"Targeted slug {_ORPHAN_SLUG!r} not found in events"
            )
            assert _ISOLATED_SLUG not in event_text, (
                f"Non-targeted slug {_ISOLATED_SLUG!r} appeared in events — "
                "slug filter did not constrain the run"
            )
        finally:
            for slug in [_ORPHAN_SLUG, _ISOLATED_SLUG]:
                _delete_page(client, slug)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
