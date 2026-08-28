# tests/live/test_orphan_resolver_live.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
"""Live end-to-end tests for the Orphan Resolver Workflow.

Each test creates dedicated pages (prefixed with _live-test-orphan-resolver-)
so they never conflict with real wiki content.  A finally block deletes all
created pages so the wiki is left in its original state.

Pages are written directly to the wiki filesystem (WikiStorage is file-backed,
and GET /lint/report reads from the same directory) rather than via a REST
endpoint — there is no POST /pages or DELETE /pages API.

Prerequisites:
  - synthadoc serve -w <wiki> running on SYNTHADOC_URL (default 127.0.0.1:7070)
  - ANTHROPIC_API_KEY (or equivalent provider key) set

Run:
  pytest tests/live/test_orphan_resolver_live.py -v -s -m live

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

_ORPHAN_SLUG   = "_live-test-orphan-resolver-orphan"
_RELATED_SLUG1 = "_live-test-orphan-resolver-related-a"
_RELATED_SLUG2 = "_live-test-orphan-resolver-related-b"
_ISOLATED_SLUG = "_live-test-orphan-resolver-isolated"


# ── Low-level helpers ─────────────────────────────────────────────────────────

def _get_wiki_root() -> Path:
    """Return the absolute wiki root directory from GET /status."""
    with httpx.Client(timeout=10) as client:
        resp = client.get(f"{BASE}/status")
        resp.raise_for_status()
        return Path(resp.json()["wiki"])


def _ingest_page(wiki_root: Path, slug: str, title: str, content: str) -> None:
    """Write a page directly to the wiki filesystem with active status.

    WikiStorage (used by the workflow tools) and GET /lint/report both read
    markdown files from ``<wiki_root>/wiki/``, so writing the file here is
    the only setup step needed — no REST call is required.
    """
    page_path = wiki_root / "wiki" / f"{slug}.md"
    fm: dict = {
        "title": title,
        "status": "active",
        "tags": [],
        "confidence": "high",
        "sources": [],
        "orphan": False,
        "aliases": [],
    }
    yaml_str = yaml.dump(fm, default_flow_style=False, allow_unicode=True)
    page_path.write_text(f"---\n{yaml_str}---\n\n{content}\n", encoding="utf-8")


def _delete_page(wiki_root: Path, slug: str) -> None:
    """Remove a test page from the wiki filesystem if it exists."""
    page_path = wiki_root / "wiki" / f"{slug}.md"
    if page_path.exists():
        page_path.unlink()


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


def _find_orphan_slugs_via_api() -> list[str]:
    """Call GET /lint/report and return the list of orphan slugs.

    GET /lint/report reads directly from the wiki filesystem, so pages written
    by _ingest_page() are visible immediately without any additional setup.
    """
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{BASE}/lint/report")
        resp.raise_for_status()
        return resp.json().get("orphans", [])


def _accept_estimate_decline_proposals(data: dict) -> bool:
    """Accept the cost-estimate confirm; decline all link-proposal confirms.

    tool_estimate_and_confirm uses yes_label="Proceed".
    tool_propose_and_apply uses yes_label="Apply".
    Inter-orphan tool_confirm uses yes_label="Continue".

    Declining proposals forces the workflow to exhaust all 4 strategies and
    emit the tool_notify escalation notice without writing to any real pages.
    """
    return data.get("yes_label") == "Proceed"


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
def test_resolves_single_orphan():
    """Workflow inserts a wikilink so the orphan is no longer orphaned."""
    wiki_root = _get_wiki_root()
    try:
        # Create orphan (no page links to it)
        _ingest_page(wiki_root, _ORPHAN_SLUG, "Orphan Topic",
                     "This page covers orphan topic details.")
        # Create two related pages (neither references the orphan yet)
        _ingest_page(wiki_root, _RELATED_SLUG1, "Related Alpha",
                     "Information about orphan topic background.")
        _ingest_page(wiki_root, _RELATED_SLUG2, "Related Beta",
                     "Further context on orphan topic usage.")

        # Confirm the orphan exists in the lint report
        orphans_before = _find_orphan_slugs_via_api()
        assert _ORPHAN_SLUG in orphans_before, (
            f"{_ORPHAN_SLUG} not in orphans: {orphans_before}"
        )

        # Run the workflow targeting just this slug; accept all confirm gates
        events = _run_workflow(
            f"run orphan resolver --slug {_ORPHAN_SLUG}",
            confirm_response=True,
        )

        # At least one event should have fired
        assert events, "No SSE events received from workflow"

        # After the workflow, the orphan should be resolved
        orphans_after = _find_orphan_slugs_via_api()
        assert _ORPHAN_SLUG not in orphans_after, (
            f"{_ORPHAN_SLUG} still orphaned after workflow run.\n"
            f"Events: {events}"
        )

    finally:
        for slug in [_ORPHAN_SLUG, _RELATED_SLUG1, _RELATED_SLUG2]:
            _delete_page(wiki_root, slug)


@pytest.mark.live
@pytest.mark.timeout(300)
def test_escalation_on_isolated_orphan():
    """Orphan with all link proposals declined leaves the orphan unresolved.

    The confirm handler accepts the cost estimate ("Proceed") but declines
    every link proposal ("Apply").  The workflow must not write any link to a
    real wiki page — the orphan must still be orphaned after the run.

    The agent may emit a tool_notify escalation notice (preferred path), or it
    may exhaust strategies without proposing when no candidate is a plausible
    match (acceptable path).  Either way the invariant is the same: no pages
    were modified.

    Note: requiring a specific ``notice`` event is too strict — the LLM can
    legitimately skip a proposal when it judges no candidate is a good fit,
    which bypasses the decline→escalate path without violating the guarantee.
    """
    wiki_root = _get_wiki_root()
    try:
        # Create a page about an extremely niche topic unlikely to match any other page
        _ingest_page(
            wiki_root, _ISOLATED_SLUG, "Zzyzx Niche Topic XQ9",
            "This page covers an extremely specific concept with no related pages."
        )

        events = _run_workflow(
            f"run orphan resolver --slug {_ISOLATED_SLUG}",
            confirm_response=_accept_estimate_decline_proposals,
        )

        # Workflow must have produced at least some events
        assert events, "No SSE events received from workflow"

        # Core guarantee: no pages were written — the orphan must still be orphaned.
        orphans_after = _find_orphan_slugs_via_api()
        assert _ISOLATED_SLUG in orphans_after, (
            f"{_ISOLATED_SLUG!r} is no longer an orphan after declining all proposals "
            f"— the workflow must have written a link without user approval.\n"
            f"Events: {events}"
        )

    finally:
        _delete_page(wiki_root, _ISOLATED_SLUG)


@pytest.mark.live
@pytest.mark.timeout(300)
def test_slug_filter_targets_single():
    """--slug flag limits workflow to just the specified orphan."""
    wiki_root = _get_wiki_root()
    try:
        _ingest_page(wiki_root, _ORPHAN_SLUG, "Target Orphan",
                     "Target page for single-slug test.")
        _ingest_page(wiki_root, _ISOLATED_SLUG, "Other Orphan",
                     "Should not be processed in this run.")

        # Decline proposals to avoid writing to real pages; only check filtering.
        events = _run_workflow(
            f"run orphan resolver --slug {_ORPHAN_SLUG}",
            confirm_response=_accept_estimate_decline_proposals,
        )

        # _ORPHAN_SLUG must appear somewhere in the event stream (targeted).
        event_text = json.dumps(events)
        assert _ORPHAN_SLUG in event_text, (
            f"Targeted slug {_ORPHAN_SLUG!r} not found in events"
        )

        # _ISOLATED_SLUG must NOT appear in the final summary (token events).
        # It may legitimately appear as a *candidate host* in notice / confirm_request
        # events (when the LLM proposes to add [[_ORPHAN_SLUG]] inside _ISOLATED_SLUG),
        # but it must never be listed as an orphan subject in Resolved / Unresolved /
        # Skipped sections.  BM25 slug-similarity between the two test pages makes
        # _ISOLATED_SLUG a plausible link-candidate host — that is expected and correct;
        # the test only checks it was not *processed as an orphan*.
        final_text = "".join(
            e["data"].get("text", "") for e in events if e["event"] == "token"
        )
        assert _ISOLATED_SLUG not in final_text, (
            f"Non-targeted slug {_ISOLATED_SLUG!r} appeared in the final summary — "
            "slug filter did not constrain which orphan was processed"
        )
    finally:
        for slug in [_ORPHAN_SLUG, _ISOLATED_SLUG]:
            _delete_page(wiki_root, slug)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
