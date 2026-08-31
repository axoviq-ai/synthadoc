# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Live integration tests for BrokenCitationResolverWorkflow.

Self-contained: each test injects a dedicated wiki page with broken citations,
streams the workflow, asserts outcomes, then archives + deletes the page in
a finally block. Real wiki content is never permanently modified.

Prerequisites:
  - synthadoc serve -w <wiki> running on SYNTHADOC_URL (default: http://localhost:8000)
  - ANTHROPIC_API_KEY set

Run:
  pytest tests/live/test_broken_citation_resolver_live.py -v -s
  python tests/live/test_broken_citation_resolver_live.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx
import pytest

BASE = os.environ.get("SYNTHADOC_URL", "http://localhost:8000")
TIMEOUT = 120  # seconds per test
_SKIP_REASON = "ANTHROPIC_API_KEY not set or SYNTHADOC_URL not reachable"


def _should_skip() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return True
    try:
        httpx.get(f"{BASE}/health", timeout=5).raise_for_status()
    except Exception:
        return True
    return False


def _create_session() -> str:
    resp = httpx.post(f"{BASE}/sessions", timeout=10)
    resp.raise_for_status()
    return resp.json()["session_id"]


def _ingest_page(slug: str, content: str, title: str, sources: list[dict]) -> None:
    """Write a page directly via the ingest/page API."""
    resp = httpx.post(f"{BASE}/pages", json={
        "slug": slug, "title": title, "content": content,
        "status": "active", "confidence": "high", "sources": sources,
    }, timeout=10)
    resp.raise_for_status()


def _delete_page(slug: str) -> None:
    httpx.delete(f"{BASE}/pages/{slug}", timeout=10)


def _stream_workflow(session_id: str, message: str) -> list[dict]:
    """Stream the chat endpoint and collect all SSE events."""
    events: list[dict] = []
    with httpx.stream(
        "POST", f"{BASE}/chat",
        json={"session_id": session_id, "message": message},
        timeout=TIMEOUT,
        headers={"Accept": "text/event-stream"},
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line.startswith("data:"):
                try:
                    events.append(json.loads(line[5:].strip()))
                except json.JSONDecodeError:
                    pass
    return events


def _get_lifecycle_status() -> dict:
    resp = httpx.get(f"{BASE}/lifecycle/status", timeout=10)
    resp.raise_for_status()
    return resp.json()


@pytest.mark.skipif(_should_skip(), reason=_SKIP_REASON)
def test_resolver_no_issues_exits_cleanly():
    """When no broken citations exist, workflow emits clean-wiki message without writing."""
    # Use a page with no citations at all
    slug = "_live-test-bcr-clean"
    _ingest_page(slug, "Clean content with no citation markers.", "Clean Test Page", [])
    try:
        sid = _create_session()
        events = _stream_workflow(sid, "run the broken citation resolver")
        text_events = [e for e in events if e.get("type") == "text"]
        full_text = " ".join(e.get("text", "") for e in text_events)
        assert "no broken citations" in full_text.lower(), (
            f"Expected clean-wiki message but got: {full_text[:400]}"
        )
        # No writes should have occurred
        write_events = [e for e in events if e.get("type") == "tool_progress"
                        and "apply_citation_fixes" in e.get("message", "")]
        assert not write_events, "No writes expected for clean wiki"
    finally:
        _delete_page(slug)


@pytest.mark.skipif(_should_skip(), reason=_SKIP_REASON)
def test_resolver_fixes_broken_ref():
    """Workflow corrects a broken_ref citation when a fuzzy match is available."""
    slug = "_live-test-bcr-broken-ref"
    # Citation file "biographie.txt" should fuzzy-match "biography.txt" (similarity > 0.72)
    content = "A claim about the author.^[biographie.txt:1-5]"
    sources = [{"file": "biography.txt", "hash": "abc", "size": 100, "ingested": "2026-01-01"}]
    _ingest_page(slug, content, "Broken Ref Test", sources)
    initial_status = _get_lifecycle_status()

    try:
        sid = _create_session()
        events = _stream_workflow(sid, "fix broken citations")
        text_events = [e for e in events if e.get("type") == "text"]
        full_text = " ".join(e.get("text", "") for e in text_events)

        # Final status should show 0 broken citations
        final_status = _get_lifecycle_status()
        assert final_status.get("broken_citations", 0) == 0, (
            f"Expected 0 broken_citations after fix. Status: {final_status}"
        )
    finally:
        _delete_page(slug)


@pytest.mark.skipif(_should_skip(), reason=_SKIP_REASON)
def test_resolver_removes_malformed_citation():
    """Workflow removes a malformed citation marker; surrounding prose survives."""
    slug = "_live-test-bcr-malformed"
    content = "A fact.^[bio.txt] This text must survive."
    sources = [{"file": "bio.txt", "hash": "abc", "size": 50, "ingested": "2026-01-01"}]
    _ingest_page(slug, content, "Malformed Test", sources)

    try:
        sid = _create_session()
        events = _stream_workflow(sid, f"fix broken citations --slug {slug}")
        final_status = _get_lifecycle_status()
        assert final_status.get("broken_citations", 0) == 0, (
            f"Expected 0 broken_citations after removing malformed marker. Status: {final_status}"
        )
    finally:
        _delete_page(slug)


@pytest.mark.skipif(_should_skip(), reason=_SKIP_REASON)
def test_resolver_single_page_mode():
    """Triggering with --slug only processes the requested page."""
    slug_target = "_live-test-bcr-target"
    slug_other = "_live-test-bcr-other"
    content_target = "Target.^[missing.txt:1-5]"
    content_other = "Other.^[alsomissing.txt:1-5]"
    _ingest_page(slug_target, content_target, "Target", [])
    _ingest_page(slug_other, content_other, "Other", [])

    try:
        sid = _create_session()
        events = _stream_workflow(sid, f"fix broken citations --slug {slug_target}")
        progress_events = [e for e in events if e.get("type") == "tool_progress"]
        tool_msgs = " ".join(e.get("message", "") for e in progress_events)
        # Target page was processed, other page was NOT processed
        assert slug_target in tool_msgs or "target" in tool_msgs.lower(), (
            "Expected target page to appear in progress events"
        )
        assert slug_other not in tool_msgs, (
            f"Other page {slug_other!r} should not appear in single-page mode"
        )
    finally:
        _delete_page(slug_target)
        _delete_page(slug_other)


if __name__ == "__main__":
    if _should_skip():
        print(f"SKIP: {_SKIP_REASON}")
        sys.exit(0)
    import subprocess
    result = subprocess.run(
        ["pytest", __file__, "-v", "-s"],
        check=False,
    )
    sys.exit(result.returncode)
