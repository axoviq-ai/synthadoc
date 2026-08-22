# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Live integration tests for the citation faithfulness audit.

Tests verify that:
  1. POST /audit/citations/faithfulness with dry_run=true returns a cost
     estimate without making any LLM calls.
  2. POST /audit/citations/faithfulness scoped to a test page returns
     per-citation verdicts in the expected set.
  3. GET /audit/citations/faithfulness/cache reflects results after a run
     and does not list the audited page as stale.

Self-contained: the faith_test_page fixture creates a dedicated test page
(_live-test-faith-audit) and extracted source file in the live wiki
filesystem, then archives and removes both in its teardown.  Real wiki
content is never modified.

Prerequisites:
  - synthadoc serve -w <wiki> running on SYNTHADOC_URL
    (default http://127.0.0.1:7070)
  - ANTHROPIC_API_KEY set in the *server's* environment (not this process)

Run:
  pytest tests/live/test_citation_faithfulness_live.py -v -s
  python -X utf8 tests/live/test_citation_faithfulness_live.py
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import httpx
import pytest

BASE = os.environ.get("SYNTHADOC_URL", "http://127.0.0.1:7070").rstrip("/")

# Dedicated test slug — never conflicts with real wiki content.
_FAITH_SLUG = "_live-test-faith-audit"

# Extracted source text.  Line 1 supports the first claim (faithful).
# Line 2 contradicts the second claim (hallucination/drift).
_SOURCE_FILENAME = "_live-test-faith-source.txt"
_SOURCE_CONTENT = (
    "Line 1: The Internet evolved from the ARPANET project, which began in the late 1960s.\n"
    "Line 2: The World Wide Web was invented by Tim Berners-Lee in 1989, not the 1960s.\n"
)

# Page body: one faithful citation and one that contradicts its source.
# IMPORTANT: no meta-commentary ("this is a test") in the body — the LLM
# must evaluate claims as written, not as acknowledged test fixtures.
_PAGE_CONTENT = (
    "---\n"
    "title: Internet History Test\n"
    "status: draft\n"
    "---\n\n"
    "ARPANET laid the groundwork for the modern Internet starting in the late 1960s."
    f"^[{_SOURCE_FILENAME}:1-1]\n\n"
    "Tim Berners-Lee invented ARPANET in 1969, predating the Internet itself."
    f"^[{_SOURCE_FILENAME}:2-2]\n"
)

_VALID_VERDICTS = {"supported", "drift", "hallucination", "skipped"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _api(path: str, method: str = "GET", body: dict | None = None) -> dict:
    with httpx.Client(timeout=120) as client:
        if method == "POST":
            r = client.post(f"{BASE}{path}", json=body)
        else:
            r = client.get(f"{BASE}{path}")
        r.raise_for_status()
        return r.json()


def _get_wiki_path() -> Path | None:
    """Return the wiki root path reported by /status, or None if unreachable."""
    try:
        data = _api("/status")
        p = data.get("wiki", "")
        return Path(p) if p else None
    except Exception:
        return None


def _transition(slug: str, to_state: str, reason: str) -> None:
    _api("/lifecycle/transition", method="POST", body={
        "slug": slug,
        "to_state": to_state,
        "reason": reason,
    })
    time.sleep(0.5)


def _setup_test_page(wiki_path: Path) -> None:
    """Write the test page and extracted source to the wiki filesystem."""
    extracted_dir = wiki_path / ".synthadoc" / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    (extracted_dir / _SOURCE_FILENAME).write_text(_SOURCE_CONTENT, encoding="utf-8")

    page_file = wiki_path / "wiki" / f"{_FAITH_SLUG}.md"
    page_file.write_text(_PAGE_CONTENT, encoding="utf-8")
    time.sleep(0.5)  # let filesystem settle before lifecycle call
    _transition(
        _FAITH_SLUG,
        "active",
        "live test setup — faithfulness audit test page created",
    )


def _cleanup_test_page(wiki_path: Path) -> None:
    """Archive the test slug and remove the wiki file + source (best effort).

    Each step is wrapped individually so a failure in one doesn't skip the
    rest.  The lifecycle transition may legitimately fail if setup didn't
    complete — that is expected and ignored.
    """
    try:
        _transition(
            _FAITH_SLUG,
            "archived",
            "live test cleanup — faithfulness audit test page deleted",
        )
    except Exception:
        pass
    try:
        (wiki_path / "wiki" / f"{_FAITH_SLUG}.md").unlink(missing_ok=True)
    except Exception:
        pass
    try:
        (wiki_path / ".synthadoc" / "extracted" / _SOURCE_FILENAME).unlink(
            missing_ok=True
        )
    except Exception:
        pass


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def require_server():
    """Skip all tests if the server isn't reachable."""
    try:
        httpx.get(f"{BASE}/health", timeout=3).raise_for_status()
    except Exception:
        pytest.skip("Synthadoc server not running — skipping live tests")


@pytest.fixture
def faith_test_page():
    """Create the test page + source; guarantee teardown after every test.

    The try/finally wraps both setup and yield so _cleanup_test_page runs
    even when:
      - setup fails partway through (file written but transition errored)
      - the test body raises an assertion error
      - the test is timed out
      - the test is interrupted with Ctrl-C (KeyboardInterrupt)

    Yields the wiki root Path so tests can inspect the filesystem if needed.
    """
    wiki_path = _get_wiki_path()
    if wiki_path is None:
        pytest.skip("Cannot determine wiki path from /status — skipping")

    try:
        _setup_test_page(wiki_path)
        yield wiki_path
    finally:
        _cleanup_test_page(wiki_path)


# ══════════════════════════════════════════════════════════════════════════════
# Test 1 — dry_run returns a cost estimate without LLM calls
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(60)
def test_faithfulness_dry_run(faith_test_page):
    """dry_run=true returns pages/citations/cost without making LLM calls.

    This test does not require ANTHROPIC_API_KEY in the server (no LLM
    call is made), so it is the fastest signal that the endpoint is wired up.
    """
    resp = _api("/audit/citations/faithfulness", method="POST", body={
        "page_slug": _FAITH_SLUG,
        "dry_run": True,
    })
    assert "pages" in resp, f"Expected 'pages' key in dry-run response: {resp}"
    assert "citations" in resp, f"Expected 'citations' key in dry-run response: {resp}"
    assert "estimated_cost_usd" in resp, (
        f"Expected 'estimated_cost_usd' in dry-run response: {resp}"
    )
    assert resp["pages"] >= 1, f"Expected pages >= 1, got: {resp['pages']}"
    assert resp["citations"] >= 1, f"Expected citations >= 1, got: {resp['citations']}"
    assert isinstance(resp["estimated_cost_usd"], (int, float)), (
        f"Expected numeric cost, got: {resp['estimated_cost_usd']!r}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Test 2 — per-page audit returns verdicts in the expected set
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(120)
def test_faithfulness_per_page_audit(faith_test_page):
    """Per-page audit returns per-citation verdicts in {supported, drift, hallucination, skipped}.

    The test page has one citation whose claim is faithful to its source and
    one that directly contradicts it.  The contradicted citation must not be
    rated 'supported'; xfail is used rather than a hard fail so a single
    conservative LLM response doesn't block CI.
    """
    resp = _api("/audit/citations/faithfulness", method="POST", body={
        "page_slug": _FAITH_SLUG,
    })
    assert "results" in resp, f"Expected 'results' key in response: {resp}"
    assert resp.get("pages_checked", 0) >= 1, f"Expected pages_checked >= 1: {resp}"
    assert resp.get("citations_checked", 0) >= 1, f"Expected citations_checked >= 1: {resp}"

    for r in resp["results"]:
        assert r.get("verdict") in _VALID_VERDICTS, (
            f"Unexpected verdict '{r.get('verdict')}' for "
            f"citation {r.get('citation_marker')!r}"
        )

    # The second citation misrepresents its source — should not be supported.
    # xfail rather than hard-fail: conservative LLM runs occasionally miss
    # even clear contradictions.
    contradicted_marker = f"^[{_SOURCE_FILENAME}:2-2]"
    verdicts = {r["citation_marker"]: r["verdict"] for r in resp["results"]}
    if verdicts.get(contradicted_marker) == "supported":
        pytest.xfail(
            f"LLM rated the contradicted citation as 'supported' on this run. "
            f"Full verdicts: {verdicts}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Test 3 — cache endpoint reflects the audit result
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(120)
def test_faithfulness_cache_reflects_audit(faith_test_page):
    """GET /audit/citations/faithfulness/cache reflects results after a full run.

    After POST (full run), the cache must contain an entry for the test slug
    and must NOT list that slug in stale_slugs.
    """
    # Run the audit to populate the cache.
    _api("/audit/citations/faithfulness", method="POST", body={
        "page_slug": _FAITH_SLUG,
    })

    cache = _api("/audit/citations/faithfulness/cache")
    assert "results" in cache, f"Expected 'results' in cache response: {cache}"
    assert "stale_slugs" in cache, f"Expected 'stale_slugs' in cache response: {cache}"
    assert "total_slugs_cached" in cache, (
        f"Expected 'total_slugs_cached' in cache response: {cache}"
    )

    # The test slug must not appear as stale — it was just audited.
    assert _FAITH_SLUG not in cache["stale_slugs"], (
        f"Expected {_FAITH_SLUG!r} to be cached (not stale) after audit. "
        f"stale_slugs: {cache['stale_slugs']}"
    )
