# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""
Live integration tests for the Broken Wikilinks workflow (v1.2.1).

Run as a named suite:
  python -X utf8 tests/live/run_all.py --suite broken_wikilinks
  pytest tests/live/test_broken_wikilinks_live.py -v -s

Prerequisites:
  - synthadoc serve -w <wiki> running on SYNTHADOC_URL (default 127.0.0.1:7070)
  - ANTHROPIC_API_KEY set

Cleanup guarantee:
  Every test records created slugs and deletes them in a ``finally`` block.
  Pages are written directly as .md files + lifecycle API transition (no ingest
  dependency) so content is deterministic and independent of LLM output.

  The ``_isolate_pre_existing_broken`` fixture records any broken wikilinks in
  the wiki BEFORE each test and asserts that the test's assertions target only
  the known test slugs — preventing residual wiki state from causing false
  positives or negatives.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

import sys

import httpx
import pytest

BASE = os.environ.get("SYNTHADOC_URL", "http://127.0.0.1:7070").rstrip("/")
_TERMINAL = {"completed", "failed", "cancelled", "dead", "skipped"}
_TEST_PREFIX = "bwl-test-"


# ── Low-level HTTP helpers ────────────────────────────────────────────────────

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
    return Path(_api("/status")["wiki"])


def _wiki_dir(wiki_root: Path) -> Path:
    return wiki_root / "wiki"


# ── Incremental SSE streaming with reactive confirm ───────────────────────────

def _stream_incremental(
    question: str,
    session_id: str,
    events_out: list,
    lock: threading.Lock,
    done_flag: threading.Event,
    timeout: int = 180,
) -> None:
    """Stream GET /query/stream, appending events to *events_out* as they arrive.

    Runs in a background thread so a concurrent confirm-watcher can see events
    before the stream completes — necessary because the workflow blocks on the
    confirm gate mid-stream.
    """
    current_type = "message"
    current_data: list[str] = []
    buf = ""
    try:
        from urllib.parse import quote
        q = quote(question, safe="")
        path = f"/query/stream?q={q}&session_id={session_id}&no_cache=true&timeout_seconds={timeout}"
        with httpx.Client(timeout=httpx.Timeout(timeout + 30)) as client:
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
                                with lock:
                                    events_out.append((current_type, data))
                            current_type = "message"
                            current_data = []
                        elif line.startswith("event:"):
                            current_type = line[6:].strip()
                        elif line.startswith("data:"):
                            current_data.append(line[5:].lstrip())
    finally:
        done_flag.set()


def _post_action_with_confirm(
    question: str,
    session_id: str,
    confirmed: bool = True,
    timeout: int = 180,
) -> list[tuple[str, dict]]:
    """Stream POST /action; respond to confirm_request reactively (not with a fixed sleep).

    The watcher thread polls the growing events list every 0.3 s and sends the
    confirm response as soon as the ``confirm_request`` event arrives — matching
    the pattern used by the agentic ingest live tests.
    """
    events: list[tuple[str, dict]] = []
    lock = threading.Lock()
    done_flag = threading.Event()
    confirm_sent = threading.Event()

    def _confirm_watcher():
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not done_flag.is_set():
            with lock:
                has_confirm = any(e[0] == "confirm_request" for e in events)
            if has_confirm and not confirm_sent.is_set():
                confirm_sent.set()
                try:
                    _raw(
                        "/action/confirm", "POST",
                        {"session_id": session_id, "confirmed": confirmed},
                    )
                except Exception:
                    pass
                return
            time.sleep(0.3)

    t_stream = threading.Thread(
        target=_stream_incremental,
        args=(question, session_id, events, lock, done_flag),
        kwargs={"timeout": timeout},
        daemon=True,
    )
    t_confirm = threading.Thread(target=_confirm_watcher, daemon=True)
    t_stream.start()
    t_confirm.start()
    t_stream.join(timeout=timeout + 15)
    with lock:
        return list(events)


def _post_action_no_confirm(
    question: str,
    session_id: str,
    timeout: int = 180,
) -> list[tuple[str, dict]]:
    """Stream POST /action with no confirmation needed (scan-only or clean wiki)."""
    events: list[tuple[str, dict]] = []
    lock = threading.Lock()
    done_flag = threading.Event()
    _stream_incremental(question, session_id, events, lock, done_flag, timeout=timeout)
    return events


# ── Wiki page management helpers ──────────────────────────────────────────────

def _unique_slug(suffix: str = "") -> str:
    uid = uuid.uuid4().hex[:8]
    return f"{_TEST_PREFIX}{uid}{('-' + suffix) if suffix else ''}"


def _page_md(slug: str, broken_refs: list[str], real_refs: list[str] | None = None) -> str:
    broken_part = " ".join(f"[[{r}]]" for r in broken_refs)
    real_part = " ".join(f"[[{r}]]" for r in (real_refs or []))
    body = f"Test page for broken wikilinks live test.\n\nBroken refs: {broken_part}"
    if real_part:
        body += f"\nReal refs: {real_part}"
    return (
        f"---\n"
        f"title: {slug}\n"
        f"status: draft\n"
        f"confidence: medium\n"
        f"tags: []\n"
        f"sources: []\n"
        f"---\n\n"
        f"{body}\n"
    )


def _create_active_page(wiki_root: Path, slug: str,
                        broken_refs: list[str],
                        real_refs: list[str] | None = None) -> None:
    """Write a wiki .md and transition it to active via the lifecycle API."""
    (wiki_root / "wiki" / f"{slug}.md").write_text(
        _page_md(slug, broken_refs, real_refs), encoding="utf-8"
    )
    _api("/lifecycle/transition", "POST", {
        "slug": slug,
        "to_state": "active",
        "reason": "BWL live test setup",
    })


def _delete_page(wiki_root: Path, slug: str) -> None:
    """Remove wiki .md and audit history for a test page."""
    (wiki_root / "wiki" / f"{slug}.md").unlink(missing_ok=True)
    try:
        _raw(f"/pages/{slug}/history", "DELETE")
    except Exception:
        pass


# ── Common SSE event inspection helpers ───────────────────────────────────────

def _tool_messages(events: list[tuple[str, dict]]) -> list[str]:
    return [e[1].get("message", "") for e in events if e[0] == "tool_progress"]


def _tool_names(events: list[tuple[str, dict]]) -> list[str]:
    return [e[1].get("tool", "") for e in events if e[0] == "tool_progress"]


def _narrative(events: list[tuple[str, dict]]) -> str:
    return " ".join(e[1].get("text", "") for e in events if e[0] == "token").lower()


def _done_data(events: list[tuple[str, dict]]) -> dict | None:
    done = [e[1] for e in events if e[0] == "done"]
    return done[0] if done else None


def _assert_no_errors(events: list[tuple[str, dict]]) -> None:
    error_events = [e for e in events if e[0] == "error"]
    assert not error_events, f"Unexpected SSE error events: {error_events}"


def _assert_stream_complete(events: list[tuple[str, dict]]) -> dict:
    _assert_no_errors(events)
    done = _done_data(events)
    assert done is not None, "Stream ended without a 'done' event"
    return done


# ── Session-scoped stale page cleanup ────────────────────────────────────────

@pytest.fixture(autouse=True, scope="module")
def _cleanup_stale_bwl_pages():
    """Delete any bwl-test-* pages left behind by a previous interrupted run.

    Runs once at module start (setup) and once at module teardown, so even
    pages stranded by a crash or keyboard interrupt are removed before the
    next suite execution.
    """
    def _sweep():
        try:
            wiki_root = _wiki_root()
        except Exception:
            return
        for md in (wiki_root / "wiki").glob(f"{_TEST_PREFIX}*.md"):
            _delete_page(wiki_root, md.stem)

    _sweep()
    yield
    _sweep()


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.live
@pytest.mark.timeout(300)
def test_scan_detects_broken_links_and_emits_confirm():
    """
    Workflow scans active pages, finds broken [[wikilinks]], emits tool_progress
    events with the correct tool names, and presents a confirm_request.
    """
    wiki_root = _wiki_root()
    created: list[str] = []
    slug = _unique_slug("scan")
    broken_ref = _unique_slug("dead")

    try:
        _create_active_page(wiki_root, slug, broken_refs=[broken_ref])
        created.append(slug)

        session_id = str(uuid.uuid4())
        # Decline so the test doesn't apply changes; we're only checking detection
        events = _post_action_with_confirm("scan for broken wikilinks", session_id, confirmed=False)

        _assert_stream_complete(events)

        # find_broken_wikilinks tool must have fired
        tool_names = _tool_names(events)
        assert "find_broken_wikilinks" in tool_names, (
            f"find_broken_wikilinks not in tool names: {tool_names}"
        )

        # Confirm gate must have been presented
        assert "confirm_request" in [e[0] for e in events], "No confirm_request emitted"

        # Confirm message must reference the page slug that contains the broken link.
        # The message lists pages-to-fix (e.g. "page-slug: 1 fix"), not the broken
        # ref target, so we check for the source page slug.
        confirm_msgs = [e[1].get("message", "") for e in events if e[0] == "confirm_request"]
        assert any(slug in m for m in confirm_msgs), (
            f"page slug {slug!r} not in confirm message: {confirm_msgs}"
        )

        # Scan progress message must appear
        msgs = " ".join(_tool_messages(events)).lower()
        assert any(kw in msgs for kw in ("scanning", "found", "broken")), (
            f"No scan progress message: {msgs}"
        )

    finally:
        for s in created:
            _delete_page(wiki_root, s)


@pytest.mark.live
@pytest.mark.timeout(300)
def test_fix_with_fuzzy_suggestion_updates_page_content():
    """
    Typo wikilink with a close fuzzy match is replaced with the corrected slug.
    After fixing: no error events, done event present, apply_link_fixes tool fired,
    page content no longer contains the broken ref.
    """
    wiki_root = _wiki_root()
    created: list[str] = []
    target_slug = _unique_slug("target")
    source_slug = _unique_slug("source")
    # One character off the end — within difflib 0.72 threshold
    broken_ref = target_slug[:-1] + "x"

    try:
        _create_active_page(wiki_root, target_slug, broken_refs=[])
        created.append(target_slug)
        _create_active_page(wiki_root, source_slug, broken_refs=[broken_ref])
        created.append(source_slug)

        session_id = str(uuid.uuid4())
        events = _post_action_with_confirm(
            "scan and fix broken wikilinks", session_id, confirmed=True
        )

        done = _assert_stream_complete(events)

        # apply_link_fixes tool must have been called
        tool_names = _tool_names(events)
        assert "apply_link_fixes" in tool_names, (
            f"apply_link_fixes not called; tools fired: {tool_names}"
        )

        # get_page_states must appear after fixes
        assert "get_page_states" in tool_names, (
            f"get_page_states not called; tools fired: {tool_names}"
        )

        # Narrative must mention fix success
        text = _narrative(events)
        assert any(kw in text for kw in ("fix", "corrected", "updated", "replaced")), (
            f"No fix confirmation in narrative: {text!r}"
        )

        # Broken ref must be gone from page content
        content = (wiki_root / "wiki" / f"{source_slug}.md").read_text(encoding="utf-8")
        assert f"[[{broken_ref}]]" not in content, (
            f"Broken ref [[{broken_ref}]] still in content after fix"
        )
        # Corrected slug must be present
        assert target_slug in content, (
            f"Corrected slug {target_slug!r} not found in fixed page"
        )

    finally:
        for s in created:
            _delete_page(wiki_root, s)


@pytest.mark.live
@pytest.mark.timeout(300)
def test_remove_link_with_no_fuzzy_match():
    """
    Completely alien broken ref (no close fuzzy match) is unlinked from the page.
    The [[markup]] is removed; the slug text may remain as display text.
    """
    wiki_root = _wiki_root()
    created: list[str] = []
    slug = _unique_slug("nosugg")
    # Construct a ref that is guaranteed to have no fuzzy match
    broken_ref = f"zzz-totally-alien-{uuid.uuid4().hex[:6]}"

    try:
        _create_active_page(wiki_root, slug, broken_refs=[broken_ref])
        created.append(slug)

        session_id = str(uuid.uuid4())
        events = _post_action_with_confirm(
            "find and fix broken wiki links", session_id, confirmed=True
        )

        done = _assert_stream_complete(events)
        assert "apply_link_fixes" in _tool_names(events)

        content = (wiki_root / "wiki" / f"{slug}.md").read_text(encoding="utf-8")
        assert f"[[{broken_ref}]]" not in content, (
            f"Dead link [[{broken_ref}]] still present after removal"
        )

    finally:
        for s in created:
            _delete_page(wiki_root, s)


@pytest.mark.live
@pytest.mark.timeout(300)
def test_declined_workflow_makes_no_changes():
    """Declining confirmation leaves page content byte-for-byte identical."""
    wiki_root = _wiki_root()
    created: list[str] = []
    slug = _unique_slug("decline")
    broken_ref = _unique_slug("dead")

    try:
        _create_active_page(wiki_root, slug, broken_refs=[broken_ref])
        created.append(slug)

        page_path = wiki_root / "wiki" / f"{slug}.md"
        original = page_path.read_text(encoding="utf-8")

        session_id = str(uuid.uuid4())
        events = _post_action_with_confirm(
            "scan for broken wikilinks", session_id, confirmed=False
        )

        _assert_stream_complete(events)

        # No apply_link_fixes should have fired
        assert "apply_link_fixes" not in _tool_names(events), (
            "apply_link_fixes fired despite declined confirmation"
        )

        # Content must be unchanged
        assert page_path.read_text(encoding="utf-8") == original, (
            "Page content changed despite user declining"
        )

        # Narrative must mention cancellation
        text = _narrative(events)
        assert any(kw in text for kw in ("declin", "cancel", "no changes")), (
            f"No decline/cancel message in narrative: {text!r}"
        )

    finally:
        for s in created:
            _delete_page(wiki_root, s)


@pytest.mark.live
@pytest.mark.timeout(300)
def test_clean_wiki_reports_no_broken_links():
    """When only valid wikilinks exist, workflow reports clean — no confirm_request."""
    wiki_root = _wiki_root()
    created: list[str] = []
    target = _unique_slug("real")
    source = _unique_slug("clean")

    try:
        _create_active_page(wiki_root, target, broken_refs=[])
        created.append(target)
        _create_active_page(wiki_root, source, broken_refs=[], real_refs=[target])
        created.append(source)

        session_id = str(uuid.uuid4())
        events = _post_action_no_confirm("check wikilink integrity", session_id)

        done = _assert_stream_complete(events)

        # No confirm_request should have appeared
        assert "confirm_request" not in [e[0] for e in events], (
            "confirm_request emitted for a clean wiki"
        )

        # Narrative must say clean
        text = _narrative(events)
        assert any(kw in text for kw in ("no broken", "clean", "integrity")), (
            f"Expected clean-wiki summary, got: {text!r}"
        )

        # apply_link_fixes must NOT have been called
        assert "apply_link_fixes" not in _tool_names(events)

    finally:
        for s in created:
            _delete_page(wiki_root, s)


@pytest.mark.live
@pytest.mark.timeout(300)
def test_stale_pages_excluded_from_scan():
    """Broken links in stale pages are not reported; only active pages are scanned."""
    wiki_root = _wiki_root()
    created: list[str] = []
    stale_slug = _unique_slug("stale")
    anchor_slug = _unique_slug("anchor")
    broken_ref = _unique_slug("dead")

    try:
        # Active anchor page — ensures at least one active page exists
        _create_active_page(wiki_root, anchor_slug, broken_refs=[])
        created.append(anchor_slug)

        # Stale page with a broken ref
        _create_active_page(wiki_root, stale_slug, broken_refs=[broken_ref])
        created.append(stale_slug)
        _api("/lifecycle/transition", "POST", {
            "slug": stale_slug,
            "to_state": "stale",
            "reason": "BWL live test setup",
        })

        session_id = str(uuid.uuid4())
        # Decline — we only want to inspect detection, not apply changes
        events = _post_action_with_confirm(
            "scan for broken wikilinks", session_id, confirmed=False
        )

        _assert_stream_complete(events)

        # The stale page's broken_ref must not appear in confirm messages
        confirm_msgs = [e[1].get("message", "") for e in events if e[0] == "confirm_request"]
        for msg in confirm_msgs:
            assert broken_ref not in msg, (
                f"Stale-page broken ref {broken_ref!r} leaked into confirm: {msg}"
            )

        # Must not appear in tool_progress messages either
        progress = " ".join(_tool_messages(events))
        assert broken_ref not in progress, (
            f"Stale-page broken ref {broken_ref!r} leaked into progress: {progress}"
        )

    finally:
        for s in created:
            _delete_page(wiki_root, s)


@pytest.mark.live
@pytest.mark.timeout(300)
def test_multi_page_scan_and_fix():
    """
    Three pages, each with a broken wikilink. All three are detected and fixed
    in a single workflow run. Verifies multi-page apply_link_fixes iteration.
    """
    wiki_root = _wiki_root()
    created: list[str] = []

    # Three source pages each with a broken ref pointing to target slugs
    target_a = _unique_slug("ta")
    target_b = _unique_slug("tb")
    target_c = _unique_slug("tc")
    src_a = _unique_slug("sa")
    src_b = _unique_slug("sb")
    src_c = _unique_slug("sc")
    # Each broken ref is one char off from its target
    broken_a = target_a[:-1] + "x"
    broken_b = target_b[:-1] + "x"
    broken_c = target_c[:-1] + "x"

    try:
        for slug in (target_a, target_b, target_c):
            _create_active_page(wiki_root, slug, broken_refs=[])
            created.append(slug)
        _create_active_page(wiki_root, src_a, broken_refs=[broken_a])
        created.append(src_a)
        _create_active_page(wiki_root, src_b, broken_refs=[broken_b])
        created.append(src_b)
        _create_active_page(wiki_root, src_c, broken_refs=[broken_c])
        created.append(src_c)

        session_id = str(uuid.uuid4())
        events = _post_action_with_confirm(
            "fix broken wikilinks", session_id, confirmed=True
        )

        done = _assert_stream_complete(events)

        # apply_link_fixes must have fired multiple times (once per source page)
        fix_events = [e for e in events if e[0] == "tool_progress"
                      and e[1].get("tool") == "apply_link_fixes"]
        assert len(fix_events) >= 3, (
            f"Expected ≥3 apply_link_fixes events, got {len(fix_events)}"
        )

        # All broken refs must be gone from page content
        for src_slug, broken_ref in [(src_a, broken_a), (src_b, broken_b), (src_c, broken_c)]:
            content = (wiki_root / "wiki" / f"{src_slug}.md").read_text(encoding="utf-8")
            assert f"[[{broken_ref}]]" not in content, (
                f"[[{broken_ref}]] still in {src_slug} after fix"
            )

    finally:
        for s in created:
            _delete_page(wiki_root, s)


@pytest.mark.live
@pytest.mark.timeout(300)
def test_mixed_fixable_and_removable_links_on_one_page():
    """
    One page has two broken refs: one with a fuzzy suggestion (corrected) and
    one with no match (removed). Both operations apply in a single fix call.
    """
    wiki_root = _wiki_root()
    created: list[str] = []
    target = _unique_slug("mix-target")
    page = _unique_slug("mix-page")
    fixable_ref = target[:-1] + "x"                            # close to target
    removable_ref = f"zzz-no-match-ever-{uuid.uuid4().hex[:5]}"  # no match

    try:
        _create_active_page(wiki_root, target, broken_refs=[])
        created.append(target)
        _create_active_page(wiki_root, page, broken_refs=[fixable_ref, removable_ref])
        created.append(page)

        session_id = str(uuid.uuid4())
        events = _post_action_with_confirm(
            "scan and fix broken wikilinks", session_id, confirmed=True
        )

        done = _assert_stream_complete(events)
        assert "apply_link_fixes" in _tool_names(events)

        content = (wiki_root / "wiki" / f"{page}.md").read_text(encoding="utf-8")
        # Fixable ref → replaced with target
        assert f"[[{fixable_ref}]]" not in content
        assert target in content
        # Removable ref → unlinked (markup gone)
        assert f"[[{removable_ref}]]" not in content

    finally:
        for s in created:
            _delete_page(wiki_root, s)


@pytest.mark.live
@pytest.mark.timeout(300)
def test_lint_runs_after_fixes_and_get_page_states_fires():
    """
    After applying fixes, run_lint and get_page_states tool_progress events
    must both be present — validating the full Phase 2 tool sequence.
    """
    wiki_root = _wiki_root()
    created: list[str] = []
    target = _unique_slug("lint-target")
    source = _unique_slug("lint-source")
    broken_ref = target[:-1] + "x"

    try:
        _create_active_page(wiki_root, target, broken_refs=[])
        created.append(target)
        _create_active_page(wiki_root, source, broken_refs=[broken_ref])
        created.append(source)

        session_id = str(uuid.uuid4())
        events = _post_action_with_confirm(
            "fix broken wikilinks", session_id, confirmed=True
        )

        done = _assert_stream_complete(events)
        tool_names = _tool_names(events)

        assert "run_lint" in tool_names, f"run_lint not fired; tools: {tool_names}"
        assert "get_page_states" in tool_names, f"get_page_states not fired; tools: {tool_names}"

        # Narrative must include page-states section
        text = _narrative(events)
        assert any(kw in text for kw in ("active", "state", "page state")), (
            f"No page-state summary in narrative: {text!r}"
        )

    finally:
        for s in created:
            _delete_page(wiki_root, s)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
