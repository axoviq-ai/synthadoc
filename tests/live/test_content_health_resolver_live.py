# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Live end-to-end tests for the Content Health Resolver Workflow.

Tests connect through the CLI (``synthadoc workflow run``) and HTTP
(``GET /query/stream``).  No API key is required in the test code — the
server handles LLM authentication via whichever provider is configured
(anthropic, claude-code, opencode, …).

Each test writes dedicated wiki pages (prefixed with _live-test-chr-) directly
to the wiki filesystem, runs the workflow, then removes the pages in a finally
block, leaving the wiki in its original state.

Prerequisites:
  - synthadoc serve -w <wiki> running on SYNTHADOC_URL (default 127.0.0.1:7070)
  - LLM provider configured in the wiki's config.toml (any supported provider)

Run:
  pytest tests/live/test_content_health_resolver_live.py -v -s -m live
  python -X utf8 tests/live/run_all.py --suite content_health_resolver

Environment variables:
  SYNTHADOC_URL     Server base URL (default: http://127.0.0.1:7070)
  SYNTHADOC_WIKI    Wiki name to use (default: inferred from server /status)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
import yaml

BASE = os.environ.get("SYNTHADOC_URL", "http://127.0.0.1:7070").rstrip("/")
PY = sys.executable

_DUP_SLUG   = "_live-test-chr-duplicate-sections"
_CLEAN_SLUG = "_live-test-chr-clean-page"


# ── Low-level helpers ─────────────────────────────────────────────────────────

def _get_wiki_root() -> Path:
    """Return the absolute wiki root directory from GET /status."""
    with httpx.Client(timeout=10) as client:
        resp = client.get(f"{BASE}/status")
        resp.raise_for_status()
        return Path(resp.json()["wiki"])


def _get_wiki_name() -> str:
    """Return the wiki name from SYNTHADOC_WIKI env or GET /status."""
    if name := os.environ.get("SYNTHADOC_WIKI"):
        return name
    with httpx.Client(timeout=10) as client:
        resp = client.get(f"{BASE}/status")
        resp.raise_for_status()
        data = resp.json()
        return data.get("wiki_name") or Path(data.get("wiki", "")).name


def _ingest_page(
    wiki_root: Path,
    slug: str,
    title: str,
    content: str,
    content_health_issues: list[dict] | None = None,
) -> None:
    """Write a page directly to the wiki filesystem.

    ``content_health_issues`` is written to the frontmatter to simulate the
    post-ingest scanner state without requiring a real ingest cycle.
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


def _run_workflow_cli(
    wiki_name: str,
    slug: str,
    *,
    confirm_input: str = "y\ny\ny\ny\n",
    timeout: int = 240,
) -> subprocess.CompletedProcess:
    """Run ``synthadoc workflow run --name content-health`` via subprocess.

    Pipes *confirm_input* to stdin so the CLI's interactive confirm prompts
    are answered automatically.  No API key is referenced in the test code.
    """
    return subprocess.run(
        [PY, "-m", "synthadoc", "workflow", "run",
         "--name", "content-health",
         "--slug", slug,
         "--wiki", wiki_name,
         "--timeout", str(timeout)],
        input=confirm_input,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout + 30,
    )


def _run_workflow_http(
    query: str,
    *,
    confirm_response: bool = True,
    timeout: int = 240,
) -> list[dict]:
    """Stream GET /query/stream and auto-respond to confirm gates via HTTP POST.

    Returns a list of SSE event dicts: [{"event": str, "data": dict}, ...]
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

                                def _respond(sid: str = session_id) -> None:
                                    time.sleep(0.3)
                                    with httpx.Client(timeout=10) as c:
                                        try:
                                            c.post(
                                                f"{BASE}/action/confirm",
                                                json={"session_id": sid,
                                                      "confirmed": confirm_response},
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

This section describes the background of the topic in detail for the reader.

## Key Contributions

Important contributions include work on computation, algorithms, and logic.

## Background

This section describes the background of the topic in detail for the reader.
This duplicate should be merged with the first Background section above.
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
def test_fixes_duplicate_section_via_http(tmp_path):
    """Workflow fixes a duplicate section via HTTP SSE streaming."""
    wiki_root = _get_wiki_root()
    try:
        _ingest_page(
            wiki_root, _DUP_SLUG,
            "Duplicate Section Test",
            _DUPLICATE_CONTENT,
            content_health_issues=_DUPLICATE_ISSUES,
        )

        fm_before = _read_page_frontmatter(wiki_root, _DUP_SLUG)
        assert fm_before.get("content_health_issues"), (
            "content_health_issues not written to frontmatter"
        )

        events = _run_workflow_http(
            f"run content health resolver --slug {_DUP_SLUG}",
            confirm_response=True,
        )

        assert events, "No SSE events received from workflow"

        fm_after = _read_page_frontmatter(wiki_root, _DUP_SLUG)
        assert fm_after.get("content_health_fix_record") is not None, (
            f"fix_record not stored after workflow run.\nEvents: {events}"
        )

        remaining = fm_after.get("content_health_issues", [])
        assert not any(i.get("type") == "duplicate_section" for i in remaining), (
            f"duplicate_section issue still present after fix.\nEvents: {events}"
        )

    finally:
        _delete_page(wiki_root, _DUP_SLUG)


@pytest.mark.live
@pytest.mark.timeout(300)
def test_fixes_duplicate_section_via_cli(tmp_path):
    """Workflow fixes a duplicate section via CLI subprocess (no API key in test)."""
    wiki_root = _get_wiki_root()
    wiki_name = _get_wiki_name()
    if not wiki_name:
        pytest.skip("Cannot determine wiki name from server /status")

    try:
        _ingest_page(
            wiki_root, _DUP_SLUG,
            "Duplicate Section Test",
            _DUPLICATE_CONTENT,
            content_health_issues=_DUPLICATE_ISSUES,
        )

        result = _run_workflow_cli(wiki_name, _DUP_SLUG)
        combined = result.stdout + result.stderr

        assert result.returncode == 0 or "fixed" in combined.lower() or "snapshot" in combined.lower(), (
            f"CLI workflow run failed.\nstdout: {result.stdout[:600]}\nstderr: {result.stderr[:200]}"
        )

        fm_after = _read_page_frontmatter(wiki_root, _DUP_SLUG)
        assert fm_after.get("content_health_fix_record") is not None, (
            f"fix_record not stored after CLI run.\nCLI output: {combined[:600]}"
        )

    finally:
        _delete_page(wiki_root, _DUP_SLUG)


@pytest.mark.live
@pytest.mark.timeout(60)
def test_workflow_list_includes_content_health():
    """``synthadoc workflow list`` shows content-health without hitting the LLM."""
    result = subprocess.run(
        [PY, "-m", "synthadoc", "workflow", "list"],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, f"workflow list failed: {result.stderr}"
    assert "content-health" in result.stdout, (
        f"content-health not in workflow list.\nOutput: {result.stdout}"
    )
