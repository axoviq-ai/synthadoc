# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Live end-to-end tests for the Broken Citation Resolver Workflow.

Each test writes dedicated wiki pages (prefixed with _live-test-bcr-) directly
to the wiki filesystem so they never conflict with real wiki content.  A finally
block removes all created pages, leaving the wiki in its original state.

Pages are written directly to the wiki filesystem (WikiStorage is file-backed).
Each page is also registered in the audit DB via POST /lifecycle/transition so
that tool_find_broken_citations (which filters by audit-DB active state) can see
it.  Cleanup calls DELETE /pages/{slug}/history to remove the audit trail.

Prerequisites:
  - synthadoc serve -w <wiki> running on SYNTHADOC_URL (default: http://127.0.0.1:7070)
  - ANTHROPIC_API_KEY (or equivalent provider key) set

Run:
  pytest tests/live/test_broken_citation_resolver_live.py -v -s -m live

Environment variables:
  SYNTHADOC_URL     Server base URL (default: http://127.0.0.1:7070)
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Union
from urllib.parse import quote

import httpx
import pytest
import yaml

BASE = os.environ.get("SYNTHADOC_URL", "http://127.0.0.1:7070").rstrip("/")

_CLEAN_SLUG      = "_live-test-bcr-clean"
_BROKEN_REF_SLUG = "_live-test-bcr-broken-ref"
_TARGET_SLUG     = "_live-test-bcr-target"
_OTHER_SLUG      = "_live-test-bcr-other"


# ── Low-level helpers ─────────────────────────────────────────────────────────

def _get_wiki_root() -> Path:
    """Return the absolute wiki root directory from GET /status."""
    with httpx.Client(timeout=10) as client:
        resp = client.get(f"{BASE}/status")
        resp.raise_for_status()
        return Path(resp.json()["wiki"])


def _api(path: str, method: str = "GET", body: dict | None = None) -> dict:
    """Make a simple JSON API call and return the parsed response."""
    with httpx.Client(timeout=30) as client:
        if method == "POST":
            r = client.post(f"{BASE}{path}", json=body)
        elif method == "DELETE":
            r = client.delete(f"{BASE}{path}")
        else:
            r = client.get(f"{BASE}{path}")
        r.raise_for_status()
        return r.json()


def _ingest_page(
    wiki_root: Path,
    slug: str,
    title: str,
    content: str,
    sources: list[str] | None = None,
) -> None:
    """Write a page to the wiki filesystem so it is visible to the BCR workflow.

    ``tool_find_broken_citations`` uses ``store.read_page()`` directly to check
    whether a page is active — it does NOT filter through the audit DB.  Writing
    the page file with ``status: active`` in its frontmatter is therefore
    sufficient to make it visible to the workflow.

    *sources* is a list of source filenames.  They are serialised as full
    SourceRef dicts so that ``_sources_from_dicts`` (called by WikiStorage) can
    parse them; plain strings are silently dropped by that function.
    """
    page_path = wiki_root / "wiki" / f"{slug}.md"
    source_entries = [
        {"file": s, "hash": "", "size": 0, "ingested": ""}
        for s in (sources or [])
    ]
    fm: dict = {
        "title": title,
        "status": "active",   # tool_find_broken_citations reads page.status directly
        "tags": [],
        "confidence": "high",
        "sources": source_entries,
        "orphan": False,
        "aliases": [],
    }
    yaml_str = yaml.dump(fm, default_flow_style=False, allow_unicode=True)
    page_path.write_text(f"---\n{yaml_str}---\n\n{content}\n", encoding="utf-8")


def _delete_page(wiki_root: Path, slug: str) -> None:
    """Remove a test page from the wiki filesystem and its audit history."""
    page_path = wiki_root / "wiki" / f"{slug}.md"
    if page_path.exists():
        page_path.unlink()
    try:
        _api(f"/pages/{slug}/history", "DELETE")
    except Exception:
        pass


def _run_workflow(
    query: str,
    *,
    confirm_response: Union[bool, Callable[[dict], bool]] = True,
    timeout: int = 180,
) -> list[dict]:
    """Stream GET /query/stream and auto-respond to all confirm gates.

    *confirm_response* controls how each ``confirm_request`` SSE event is
    answered.  Pass ``True`` to accept all gates, ``False`` to decline all,
    or a callable ``fn(data) -> bool`` to decide per-event (``data`` is the
    parsed SSE payload including ``yes_label``, ``no_label``, ``message``).

    Returns a list of event dicts: [{"event": str, "data": dict}, ...]
    """
    events: list[dict] = []
    current_type = "message"
    current_data: list[str] = []
    buf = ""

    q = quote(query, safe="")
    path = f"/query/stream?q={q}&no_cache=true&timeout_seconds={timeout}"

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
                            events.append({"event": current_type, "data": data})

                            # Auto-respond to confirm gates in a background thread
                            # so the streaming connection stays open.
                            if current_type == "confirm_request":
                                session_id = data.get("session_id", "")
                                if callable(confirm_response):
                                    accepted = confirm_response(data)
                                else:
                                    accepted = bool(confirm_response)

                                def _respond(
                                    sid: str = session_id, acc: bool = accepted
                                ) -> None:
                                    time.sleep(0.3)
                                    with httpx.Client(timeout=10) as c:
                                        try:
                                            c.post(
                                                f"{BASE}/action/confirm",
                                                json={"session_id": sid, "confirmed": acc},
                                            )
                                        except Exception:
                                            pass

                                threading.Thread(target=_respond, daemon=True).start()

                            if current_type == "done":
                                return events

                        current_type = "message"
                        current_data = []
                    elif line.startswith("event:"):
                        current_type = line[6:].strip()
                    elif line.startswith("data:"):
                        current_data.append(line[5:].lstrip())

    return events


# ── Server gate ───────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def require_server():
    """Skip all tests if the server isn't reachable."""
    try:
        httpx.get(f"{BASE}/health", timeout=3).raise_for_status()
    except Exception:
        pytest.skip("Synthadoc server not running — skipping live tests")


# ══════════════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(300)
def test_clean_slug_no_broken_citations():
    """Workflow reports clean and never invokes apply_citation_fixes for a citation-free page."""
    wiki_root = _get_wiki_root()
    try:
        _ingest_page(
            wiki_root, _CLEAN_SLUG, "Clean Test Page",
            "Clean content with no citation markers.",
        )

        # Decline any gate that fires — the gate should not fire at all for
        # a clean page, but we also decline to avoid blocking if the LLM
        # strays to a real wiki page.
        events = _run_workflow(
            f"fix broken citations --slug {_CLEAN_SLUG}",
            confirm_response=False,
        )

        assert events, "No SSE events received from workflow"

        # The confirm gate must not have fired about the clean test page.
        # If a gate fires about a real pre-existing wiki issue (workflow went
        # off-script in single-page mode) that is also a failure — the
        # single-page mode section of the system prompt must constrain the scan.
        confirm_events = [e for e in events if e["event"] == "confirm_request"]
        assert not confirm_events, (
            f"apply_citation_fixes was gated in single-page mode for a citation-free page — "
            f"the workflow must not run a full-wiki scan when --slug is given.\n"
            f"Events: {events}"
        )

    finally:
        _delete_page(wiki_root, _CLEAN_SLUG)


@pytest.mark.live
@pytest.mark.timeout(300)
def test_fixes_broken_ref():
    """Workflow detects a broken_ref citation and proposes a fix via the confirm gate.

    The page has ``^[biographie.txt:1-5]`` in its body but declares
    ``biography.txt`` in sources — a fuzzy-matchable broken_ref.  The test
    accepts the confirm gate and verifies that the workflow engaged with the
    broken citation (either the gate fired or the summary mentions the filenames).
    """
    wiki_root = _get_wiki_root()
    try:
        content = "A claim about the author.^[biographie.txt:1-5]"
        _ingest_page(
            wiki_root, _BROKEN_REF_SLUG, "Broken Ref Test",
            content, sources=["biography.txt"],
        )

        # Accept the gate so apply_citation_fixes can proceed.
        events = _run_workflow(
            f"fix broken citations --slug {_BROKEN_REF_SLUG}",
            confirm_response=True,
        )

        assert events, "No SSE events received from workflow"

        # The workflow must have detected the broken citation.  Evidence: either
        # the confirm gate fired (apply_citation_fixes was gated), or the final
        # summary text mentions one of the citation filenames.
        confirm_events = [e for e in events if e["event"] == "confirm_request"]
        token_text = "".join(
            e["data"].get("text", "") for e in events if e["event"] == "token"
        )
        detected = (
            bool(confirm_events)
            or "biographie" in token_text.lower()
            or "biography" in token_text.lower()
        )
        assert detected, (
            f"Expected workflow to detect broken citation "
            f"(^[biographie.txt:1-5] vs sources=[biography.txt]) but got:\n"
            f"{token_text[:400]}\n"
            f"Events: {events}"
        )

    finally:
        _delete_page(wiki_root, _BROKEN_REF_SLUG)


@pytest.mark.live
@pytest.mark.timeout(300)
def test_single_page_mode():
    """--slug flag limits the scan to only the specified page.

    Two pages are created, both with broken citations.  The workflow is invoked
    with ``--slug _TARGET_SLUG`` and the confirm gate is declined so that no
    content is actually modified.  The target slug must appear in the event
    stream; the other slug must not appear in the final token summary.
    """
    wiki_root = _get_wiki_root()
    try:
        _ingest_page(
            wiki_root, _TARGET_SLUG, "Target Page",
            "Target claim.^[missing.txt:1-5]",
        )
        _ingest_page(
            wiki_root, _OTHER_SLUG, "Other Page",
            "Other claim.^[alsomissing.txt:1-5]",
        )

        # Decline the gate — we only care about slug filtering, not the fix itself.
        events = _run_workflow(
            f"fix broken citations --slug {_TARGET_SLUG}",
            confirm_response=False,
        )

        assert events, "No SSE events received from workflow"

        # Target slug must appear somewhere in the event stream (it was targeted).
        event_text = json.dumps(events)
        assert _TARGET_SLUG in event_text, (
            f"Targeted slug {_TARGET_SLUG!r} not found in events"
        )

        # Other slug must not appear in the final summary (token events).
        # It may legitimately appear as a *candidate* in intermediate tool events,
        # but the LLM summary must not list it as a scanned subject.
        final_text = "".join(
            e["data"].get("text", "") for e in events if e["event"] == "token"
        )
        assert _OTHER_SLUG not in final_text, (
            f"Non-targeted slug {_OTHER_SLUG!r} appeared in the final summary — "
            "slug filter did not constrain which page was scanned.\n"
            f"Final text: {final_text[:400]}"
        )

    finally:
        for slug in [_TARGET_SLUG, _OTHER_SLUG]:
            _delete_page(wiki_root, slug)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
