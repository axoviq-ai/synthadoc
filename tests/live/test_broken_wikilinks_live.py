# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""
Live integration tests for the Broken Wikilinks workflow (v1.2.1).

Prerequisites:
  - synthadoc serve -w <wiki> is running on SYNTHADOC_URL (default 127.0.0.1:7070)
  - ANTHROPIC_API_KEY (or equivalent provider key) is set

Run with:
  pytest tests/live/test_broken_wikilinks_live.py -v -s

Cleanup guarantee:
  Every test that creates wiki pages (via _create_active_test_page) records them
  in a `created` list and deletes all of them in a `finally` block, regardless of
  test outcome.  The wiki is left in the same state as before the test ran.

  Pages are created by writing .md files directly to the wiki directory and then
  transitioning them to active via POST /lifecycle/transition — no ingest is
  required, which makes the tests deterministic and independent of LLM output.
"""
from __future__ import annotations

import json
import os
import textwrap
import threading
import time
import uuid
from pathlib import Path

import httpx
import pytest

BASE = os.environ.get("SYNTHADOC_URL", "http://127.0.0.1:7070").rstrip("/")
_TERMINAL = {"completed", "failed", "cancelled", "dead", "skipped"}

# Prefixes all test-created slugs so cleanup is unambiguous.
_TEST_PREFIX = "bwl-test-"


# ── Low-level helpers ─────────────────────────────────────────────────────────

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


def _raw(path: str, method: str = "GET", body: dict | None = None) -> httpx.Response:
    with httpx.Client(timeout=30) as client:
        if method == "POST":
            return client.post(f"{BASE}{path}", json=body)
        elif method == "DELETE":
            return client.delete(f"{BASE}{path}")
        return client.get(f"{BASE}{path}")


def _wiki_root() -> Path:
    status = _api("/status")
    return Path(status["wiki"])


def _wiki_dir(wiki_root: Path) -> Path:
    return wiki_root / "wiki"


def _sse_events(path: str, *, timeout: int = 180) -> list[tuple[str, dict]]:
    """Stream a GET SSE endpoint and collect all (event_type, data) pairs."""
    events: list[tuple[str, dict]] = []
    current_type = "message"
    current_data: list[str] = []
    buf = ""
    with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
        with client.stream("GET", f"{BASE}{path}") as r:
            r.raise_for_status()
            for chunk in r.iter_text():
                buf += chunk
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.rstrip("\r")
                    if not line:
                        if current_data:
                            raw = "\n".join(current_data)
                            try:
                                data = json.loads(raw)
                            except json.JSONDecodeError:
                                data = {"raw": raw}
                            events.append((current_type, data))
                        current_type = "message"
                        current_data = []
                    elif line.startswith("event:"):
                        current_type = line[6:].strip()
                    elif line.startswith("data:"):
                        current_data.append(line[5:].lstrip())
    return events


def _post_action_stream(question: str, session_id: str, *, timeout: int = 180) -> list[tuple[str, dict]]:
    """POST /action and stream the SSE response."""
    path = f"/action?session_id={session_id}"
    events: list[tuple[str, dict]] = []
    current_type = "message"
    current_data: list[str] = []
    buf = ""
    with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
        with client.stream("POST", f"{BASE}{path}", json={"question": question}) as r:
            r.raise_for_status()
            for chunk in r.iter_text():
                buf += chunk
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.rstrip("\r")
                    if not line:
                        if current_data:
                            raw = "\n".join(current_data)
                            try:
                                data = json.loads(raw)
                            except json.JSONDecodeError:
                                data = {"raw": raw}
                            events.append((current_type, data))
                        current_type = "message"
                        current_data = []
                    elif line.startswith("event:"):
                        current_type = line[6:].strip()
                    elif line.startswith("data:"):
                        current_data.append(line[5:].lstrip())
    return events


def _confirm_after_delay(session_id: str, confirmed: bool, delay: float = 1.5) -> None:
    """Send a confirm response in a background thread after *delay* seconds."""
    def _send():
        time.sleep(delay)
        try:
            _raw("/action/confirm", "POST", {"session_id": session_id, "confirmed": confirmed})
        except Exception:
            pass
    threading.Thread(target=_send, daemon=True).start()


# ── Wiki page management helpers ──────────────────────────────────────────────

def _page_content(slug: str, broken_refs: list[str], real_refs: list[str] | None = None) -> str:
    """Build a minimal wiki .md file body with known broken and (optional) real wikilinks."""
    broken_links = " ".join(f"[[{r}]]" for r in broken_refs)
    real_links = " ".join(f"[[{r}]]" for r in (real_refs or []))
    return textwrap.dedent(f"""\
        ---
        title: "{slug}"
        status: draft
        sources: []
        ---
        Test page for broken wikilinks live test.

        Broken references: {broken_links}
        {"Real references: " + real_links if real_links else ""}
    """)


def _create_active_test_page(wiki_root: Path, slug: str, broken_refs: list[str],
                              real_refs: list[str] | None = None) -> None:
    """Write a wiki page .md file and transition it to active via the API.

    The page is written directly to the wiki directory — no ingest is needed.
    This guarantees the broken_refs appear verbatim in page content, independent
    of LLM output.
    """
    wiki_dir = _wiki_dir(wiki_root)
    page_path = wiki_dir / f"{slug}.md"
    page_path.write_text(_page_content(slug, broken_refs, real_refs), encoding="utf-8")
    # Transition draft → active (the API records a lifecycle_events row in audit.db)
    _api("/lifecycle/transition", "POST", {"slug": slug, "to": "active"})


def _delete_test_page(wiki_root: Path, slug: str) -> None:
    """Remove the wiki .md file and audit history for a test page.

    Uses unlink(missing_ok=True) so partial cleanup never raises.
    """
    page_path = _wiki_dir(wiki_root) / f"{slug}.md"
    page_path.unlink(missing_ok=True)
    # Remove audit DB entries so the slug is fully gone from lifecycle views
    try:
        _raw(f"/pages/{slug}/history", "DELETE")
    except Exception:
        pass


def _unique_slug(suffix: str = "") -> str:
    uid = uuid.uuid4().hex[:8]
    return f"{_TEST_PREFIX}{uid}{('-' + suffix) if suffix else ''}"


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.live
def test_broken_wikilinks_workflow_detects_broken_links():
    """Workflow scans active pages, finds broken [[wikilinks]], emits tool_progress events."""
    wiki_root = _wiki_root()
    created: list[str] = []
    slug = _unique_slug("scan")
    broken_ref = _unique_slug("dead")   # guaranteed non-existent slug

    try:
        _create_active_test_page(wiki_root, slug, broken_refs=[broken_ref])
        created.append(slug)

        session_id = str(uuid.uuid4())
        events = _post_action_stream("scan for broken wikilinks", session_id)

        event_types = [e[0] for e in events]
        assert "tool_progress" in event_types, "No tool_progress events emitted"

        progress_msgs = [
            e[1].get("message", "") for e in events if e[0] == "tool_progress"
        ]
        # The scan step must report finding the broken link
        scan_msgs = " ".join(progress_msgs).lower()
        assert any(
            kw in scan_msgs for kw in ("broken", "found", "scanning")
        ), f"Expected scan progress message, got: {progress_msgs}"

        # The confirm_request must appear (workflow paused for approval)
        assert "confirm_request" in event_types, "No confirm_request event emitted"

    finally:
        for s in created:
            _delete_test_page(wiki_root, s)


@pytest.mark.live
def test_broken_wikilinks_workflow_fixes_link_with_suggestion():
    """Workflow fixes a typo wikilink when a fuzzy suggestion exists; page content updated."""
    wiki_root = _wiki_root()
    created: list[str] = []

    # Create a real target page and a page that references a typo version of it
    target_slug = _unique_slug("target")
    source_slug = _unique_slug("source")
    # The broken ref is the target slug with one character changed — within fuzzy threshold
    broken_ref = target_slug[:-1] + "x"

    try:
        # Real target page must exist so it appears in all_slugs
        _create_active_test_page(wiki_root, target_slug, broken_refs=[])
        created.append(target_slug)

        # Source page has the typo reference
        _create_active_test_page(wiki_root, source_slug, broken_refs=[broken_ref])
        created.append(source_slug)

        session_id = str(uuid.uuid4())
        _confirm_after_delay(session_id, confirmed=True, delay=2.0)
        events = _post_action_stream("scan and fix broken wikilinks", session_id)

        event_types = [e[0] for e in events]
        progress_msgs = [
            e[1].get("message", "")
            for e in events if e[0] == "tool_progress"
        ]
        combined = " ".join(progress_msgs).lower()

        # fix applied → apply_link_fixes must have emitted a progress event
        assert any("fix" in m.lower() or "✓" in m for m in progress_msgs), (
            f"Expected fix progress message, got: {progress_msgs}"
        )

        # Page content must no longer contain the broken ref
        page_path = _wiki_dir(wiki_root) / f"{source_slug}.md"
        updated = page_path.read_text(encoding="utf-8")
        assert f"[[{broken_ref}]]" not in updated, (
            f"Broken ref [[{broken_ref}]] still present after fix"
        )
        # The corrected slug or display text must be present
        assert target_slug in updated or broken_ref.replace("-", " ") in updated, (
            f"Neither corrected slug nor display text found in updated page"
        )

    finally:
        for s in created:
            _delete_test_page(wiki_root, s)


@pytest.mark.live
def test_broken_wikilinks_workflow_removes_link_with_no_suggestion():
    """Broken link with no fuzzy match is removed from page content (new_ref=null path)."""
    wiki_root = _wiki_root()
    created: list[str] = []

    slug = _unique_slug("nosuggest")
    # Completely random broken ref — no close match exists in the wiki
    broken_ref = f"zzz-absolutely-nonexistent-{uuid.uuid4().hex[:6]}"

    try:
        _create_active_test_page(wiki_root, slug, broken_refs=[broken_ref])
        created.append(slug)

        session_id = str(uuid.uuid4())
        _confirm_after_delay(session_id, confirmed=True, delay=2.0)
        events = _post_action_stream("find and fix broken wiki links", session_id)

        progress_msgs = [
            e[1].get("message", "")
            for e in events if e[0] == "tool_progress"
        ]

        # Wikilink markup must be gone from page after removal
        page_path = _wiki_dir(wiki_root) / f"{slug}.md"
        updated = page_path.read_text(encoding="utf-8")
        assert f"[[{broken_ref}]]" not in updated, (
            f"Dead link [[{broken_ref}]] still present after removal"
        )

    finally:
        for s in created:
            _delete_test_page(wiki_root, s)


@pytest.mark.live
def test_broken_wikilinks_workflow_declined_makes_no_changes():
    """Workflow makes no content changes when the user declines the confirmation."""
    wiki_root = _wiki_root()
    created: list[str] = []
    slug = _unique_slug("decline")
    broken_ref = _unique_slug("dead")

    try:
        _create_active_test_page(wiki_root, slug, broken_refs=[broken_ref])
        created.append(slug)

        # Read original content before the workflow runs
        page_path = _wiki_dir(wiki_root) / f"{slug}.md"
        original_content = page_path.read_text(encoding="utf-8")

        session_id = str(uuid.uuid4())
        _confirm_after_delay(session_id, confirmed=False, delay=1.5)
        events = _post_action_stream("scan for broken wikilinks", session_id)

        # Content must be unchanged after decline
        updated_content = page_path.read_text(encoding="utf-8")
        assert updated_content == original_content, (
            "Page content changed despite user declining the workflow"
        )

        # No apply_link_fixes progress events should have fired
        fix_events = [
            e for e in events
            if e[0] == "tool_progress" and "fix" in e[1].get("message", "").lower()
        ]
        assert not fix_events, f"Unexpected fix events after decline: {fix_events}"

    finally:
        for s in created:
            _delete_test_page(wiki_root, s)


@pytest.mark.live
def test_broken_wikilinks_workflow_clean_wiki_reports_no_issues():
    """When the active page has only valid wikilinks, the workflow reports a clean wiki."""
    wiki_root = _wiki_root()
    created: list[str] = []

    target_slug = _unique_slug("real")
    source_slug = _unique_slug("clean")

    try:
        _create_active_test_page(wiki_root, target_slug, broken_refs=[])
        created.append(target_slug)
        # source page links only to the real target — no broken refs
        _create_active_test_page(wiki_root, source_slug, broken_refs=[], real_refs=[target_slug])
        created.append(source_slug)

        session_id = str(uuid.uuid4())
        events = _post_action_stream("check wikilink integrity", session_id)

        final_text = " ".join(
            e[1].get("text", "") for e in events if e[0] == "token"
        ).lower()

        assert any(
            kw in final_text for kw in ("no broken", "clean", "integrity")
        ), f"Expected clean-wiki summary, got: {final_text!r}"

        # No confirm_request should have appeared — nothing to fix
        assert "confirm_request" not in [e[0] for e in events], (
            "confirm_request emitted on a clean wiki — unexpected"
        )

    finally:
        for s in created:
            _delete_test_page(wiki_root, s)


@pytest.mark.live
def test_broken_wikilinks_workflow_skips_stale_pages():
    """Broken links inside stale pages are not reported — only active pages are scanned."""
    wiki_root = _wiki_root()
    created: list[str] = []
    stale_slug = _unique_slug("stale")
    broken_ref = _unique_slug("dead")

    try:
        # Create an active page first so there is at least one active page in the wiki
        active_slug = _unique_slug("active-anchor")
        _create_active_test_page(wiki_root, active_slug, broken_refs=[])
        created.append(active_slug)

        # Create a stale page: write it, activate it, then transition to stale
        _create_active_test_page(wiki_root, stale_slug, broken_refs=[broken_ref])
        created.append(stale_slug)
        _api("/lifecycle/transition", "POST", {"slug": stale_slug, "to": "stale"})

        session_id = str(uuid.uuid4())
        events = _post_action_stream("scan for broken wikilinks", session_id)

        # If broken_ref was reported we would see a confirm_request; we should NOT
        confirm_events = [e for e in events if e[0] == "confirm_request"]
        if confirm_events:
            # Confirm card appeared — check it does NOT mention the stale page's broken ref
            msg = confirm_events[0][1].get("message", "")
            assert broken_ref not in msg, (
                f"Stale page's broken ref {broken_ref!r} appeared in confirm message"
            )

        # Progress messages must not mention the stale_slug's broken ref
        progress_msgs = " ".join(
            e[1].get("message", "") for e in events if e[0] == "tool_progress"
        )
        assert broken_ref not in progress_msgs, (
            f"Stale page broken ref {broken_ref!r} leaked into progress messages"
        )

    finally:
        for s in created:
            _delete_test_page(wiki_root, s)
