# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Live end-to-end tests for the Content Health Resolver Workflow.

Each test writes dedicated wiki pages (prefixed with _live-test-chr-) directly
to the wiki filesystem so they never conflict with real wiki content.  A finally
block removes all created pages, leaving the wiki in its original state.

Pages are written to the wiki filesystem with ``content_health_issues`` already
embedded in the frontmatter — this simulates the post-ingest scanner state
(the scanner normally runs inside ingest_agent._write_or_stage).

Prerequisites:
  - synthadoc serve -w <wiki> running on SYNTHADOC_URL (default: http://127.0.0.1:7070)
  - ANTHROPIC_API_KEY (or equivalent provider key) set

Run:
  pytest tests/live/test_content_health_resolver_live.py -v -s -m live

Environment variables:
  SYNTHADOC_URL     Server base URL (default: http://127.0.0.1:7070)
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Callable, Union
from urllib.parse import quote

import httpx
import pytest
import yaml

BASE = os.environ.get("SYNTHADOC_URL", "http://127.0.0.1:7070").rstrip("/")

_DUP_SLUG   = "_live-test-chr-duplicate-sections"
_CLEAN_SLUG = "_live-test-chr-clean-page"


# ── Low-level helpers ─────────────────────────────────────────────────────────

def _get_wiki_root() -> Path:
    """Return the absolute wiki root directory from GET /status."""
    with httpx.Client(timeout=10) as client:
        resp = client.get(f"{BASE}/status")
        resp.raise_for_status()
        return Path(resp.json()["wiki"])


def _ingest_page(
    wiki_root: Path,
    slug: str,
    title: str,
    content: str,
    content_health_issues: list[dict] | None = None,
) -> None:
    """Write a page directly to the wiki filesystem.

    ``content_health_issues`` mirrors what the post-ingest scanner stores.
    Writing it here avoids needing to trigger a real ingest cycle.
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
    if content_health_issues:
        fm["content_health_issues"] = content_health_issues
    yaml_str = yaml.dump(fm, default_flow_style=False, allow_unicode=True)
    page_path.write_text(f"---\n{yaml_str}---\n\n{content}\n", encoding="utf-8")


def _delete_page(wiki_root: Path, slug: str) -> None:
    """Remove a test page from the wiki filesystem and its audit history."""
    page_path = wiki_root / "wiki" / f"{slug}.md"
    if page_path.exists():
        page_path.unlink()
    try:
        with httpx.Client(timeout=10) as client:
            client.delete(f"{BASE}/pages/{slug}/history")
    except Exception:
        pass


def _read_page_frontmatter(wiki_root: Path, slug: str) -> dict:
    """Read and parse a page's YAML frontmatter from the wiki filesystem."""
    page_path = wiki_root / "wiki" / f"{slug}.md"
    text = page_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.index("---", 3)
    return yaml.safe_load(text[3:end]) or {}


def _run_workflow(
    query: str,
    *,
    confirm_response: Union[bool, Callable[[dict], bool]] = True,
    timeout: int = 240,
) -> list[dict]:
    """Stream GET /query/stream and auto-respond to all confirm gates.

    *confirm_response* controls how each ``confirm_request`` SSE event is
    answered.  Pass ``True`` to accept all gates, ``False`` to decline all,
    or a callable ``fn(data) -> bool`` to decide per-event.

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

_DUPLICATE_CONTENT = """\
## Background

This section describes the background of the topic in detail.

## Key Contributions

Important contributions include work on computation, algorithms, and logic.

## Background

This section describes the background of the topic in detail.
This duplicate should be merged with the first Background section.
"""

_DUPLICATE_ISSUES = [
    {
        "type": "duplicate_section",
        "severity": "critical",
        "location": "## Background",
        "description": "Heading '## Background' appears 2 times",
    }
]


@pytest.mark.live
@pytest.mark.timeout(300)
def test_fixes_duplicate_section():
    """Workflow rewrites a page with a duplicate section and stores a fix_record."""
    wiki_root = _get_wiki_root()
    try:
        _ingest_page(
            wiki_root, _DUP_SLUG,
            "Duplicate Section Test",
            _DUPLICATE_CONTENT,
            content_health_issues=_DUPLICATE_ISSUES,
        )

        # Confirm the issue is visible before running
        fm_before = _read_page_frontmatter(wiki_root, _DUP_SLUG)
        assert fm_before.get("content_health_issues"), (
            "content_health_issues not written to frontmatter"
        )

        # Run the workflow targeting just this page; accept all confirms
        events = _run_workflow(
            f"run content health resolver --slug {_DUP_SLUG}",
            confirm_response=True,
        )

        assert events, "No SSE events received from workflow"

        # After the workflow the page must have a fix_record
        fm_after = _read_page_frontmatter(wiki_root, _DUP_SLUG)
        assert fm_after.get("content_health_fix_record") is not None, (
            f"fix_record not stored after workflow run.\nEvents: {events}"
        )

        # Issues should be cleared (or reduced) in the stored page
        remaining = fm_after.get("content_health_issues", [])
        assert not any(i.get("type") == "duplicate_section" for i in remaining), (
            f"duplicate_section issue still present after fix.\nEvents: {events}"
        )

    finally:
        _delete_page(wiki_root, _DUP_SLUG)


@pytest.mark.live
@pytest.mark.timeout(120)
def test_skips_page_with_no_issues():
    """Workflow exits cleanly when no active pages have content issues."""
    wiki_root = _get_wiki_root()
    try:
        _ingest_page(
            wiki_root, _CLEAN_SLUG,
            "Clean Page",
            "## Overview\n\n" + " ".join(["word"] * 60) + "\n",
            content_health_issues=[],
        )

        events = _run_workflow("run content health resolver", confirm_response=False)

        assert events, "No SSE events received from workflow"
        # At least one final_text event should mention no issues
        final_texts = [
            e["data"].get("text", "")
            for e in events
            if e.get("event") == "final_text"
        ]
        combined = " ".join(final_texts).lower()
        assert "no" in combined or "0" in combined, (
            f"Expected no-issues message in final_text.\nfinal_texts: {final_texts}"
        )

    finally:
        _delete_page(wiki_root, _CLEAN_SLUG)
