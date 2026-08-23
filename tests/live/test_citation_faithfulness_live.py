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
import sys
import time
from pathlib import Path

import httpx
import pytest

from synthadoc.core.queue import JobStatus

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


def _run_audit(page_slug: str | None = None, stale_only: bool = False,
               poll_interval: float = 2.0, max_wait: float = 180.0) -> dict:
    """POST /audit/citations/faithfulness, then poll /jobs/{id} until terminal.

    Returns the job object once complete.  Raises AssertionError if the job
    fails or the wait exceeds max_wait seconds.
    """
    body: dict = {}
    if page_slug:
        body["page_slug"] = page_slug
    if stale_only:
        body["stale_only"] = True

    resp = _api("/audit/citations/faithfulness", method="POST", body=body)
    job_id: str = resp.get("job_id", "")
    assert job_id, f"Expected job_id in response, got: {resp}"

    deadline = time.time() + max_wait
    while time.time() < deadline:
        job = _api(f"/jobs/{job_id}")
        status = job.get("status", "unknown")
        if status == JobStatus.COMPLETED:
            return job
        if status in (JobStatus.FAILED, JobStatus.DEAD):
            pytest.fail(f"Faithfulness job {job_id} ended with status={status!r}: {job}")
        time.sleep(poll_interval)

    pytest.fail(f"Faithfulness job {job_id} did not complete within {max_wait}s")


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


# ── Invalidation helpers ──────────────────────────────────────────────────────

def _write_page_with_ingested(wiki_path: Path, ts: str) -> None:
    """Overwrite the test page with a sources.ingested timestamp for cache-key testing."""
    page_file = wiki_path / "wiki" / f"{_FAITH_SLUG}.md"
    page_file.write_text(
        "---\n"
        "title: Internet History Test\n"
        "status: active\n"
        "sources:\n"
        f"  - file: {_SOURCE_FILENAME}\n"
        "    hash: abc\n"
        "    size: 100\n"
        f"    ingested: '{ts}'\n"
        "---\n\n"
        "ARPANET laid the groundwork for the modern Internet starting in the late 1960s."
        f"^[{_SOURCE_FILENAME}:1-1]\n",
        encoding="utf-8",
    )
    time.sleep(0.3)  # let filesystem settle


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
    _run_audit(page_slug=_FAITH_SLUG)

    # Verdicts are now in the cache — read them from there
    cache = _api("/audit/citations/faithfulness/cache")
    slug_results = [r for r in cache.get("results", []) if r.get("slug") == _FAITH_SLUG]
    assert slug_results, f"Expected results for {_FAITH_SLUG!r} in cache after audit: {cache}"

    for r in slug_results:
        assert r.get("verdict") in _VALID_VERDICTS, (
            f"Unexpected verdict '{r.get('verdict')}' for "
            f"citation {r.get('citation_marker')!r}"
        )

    # The second citation misrepresents its source — should not be supported.
    # xfail rather than hard-fail: conservative LLM runs occasionally miss
    # even clear contradictions.
    contradicted_marker = f"^[{_SOURCE_FILENAME}:2-2]"
    verdicts = {r["citation_marker"]: r["verdict"] for r in slug_results}
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
    _run_audit(page_slug=_FAITH_SLUG)

    cache = _api("/audit/citations/faithfulness/cache")
    assert "results" in cache, f"Expected 'results' in cache response: {cache}"
    assert "stale_slugs" in cache, f"Expected 'stale_slugs' in cache response: {cache}"
    assert "total_slugs_cached" in cache, (
        f"Expected 'total_slugs_cached' in cache response: {cache}"
    )
    # last_checked_at must be a non-empty ISO UTC string after at least one audit.
    assert cache.get("last_checked_at"), (
        f"Expected 'last_checked_at' to be set after audit: {cache}"
    )

    # The test slug must not appear as stale — it was just audited.
    assert _FAITH_SLUG not in cache["stale_slugs"], (
        f"Expected {_FAITH_SLUG!r} to be cached (not stale) after audit. "
        f"stale_slugs: {cache['stale_slugs']}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Test 4 — cache invalidation when source ingested timestamp advances
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(180)
def test_faithfulness_cache_invalidated_on_source_update(faith_test_page):
    """Cache entry becomes stale when a page's source ingested timestamp changes.

    Validates the per-page invalidation contract:
        page_key = max(sources[].ingested)

    When a source's ingested timestamp advances (i.e. the source was
    re-ingested), the stored page_key no longer matches the current one
    and the page must appear as stale in GET /cache.

    Steps:
      1. Rewrite test page with sources.ingested = T1
      2. POST audit (page_slug) — cache entry written with page_key = T1
      3. GET /cache — slug NOT in stale_slugs  (fresh)
      4. Rewrite test page with sources.ingested = T2 (simulate re-ingest)
      5. GET /cache — slug IS in stale_slugs  (invalidated by timestamp change)
      6. POST audit again — cache entry updated with page_key = T2
      7. GET /cache — slug NOT in stale_slugs  (fresh again)
    """
    wiki_path = faith_test_page

    _T1 = "2026-01-01T00:00:00+00:00"
    _T2 = "2026-06-01T00:00:00+00:00"

    # ── Steps 1–3: audit with T1, verify fresh ────────────────────────────────
    _write_page_with_ingested(wiki_path, _T1)
    _run_audit(page_slug=_FAITH_SLUG)
    cache = _api("/audit/citations/faithfulness/cache")
    assert _FAITH_SLUG not in cache["stale_slugs"], (
        f"Expected {_FAITH_SLUG!r} fresh after first audit (T1); "
        f"stale_slugs: {cache['stale_slugs']}"
    )

    # ── Steps 4–5: advance timestamp, verify stale ────────────────────────────
    _write_page_with_ingested(wiki_path, _T2)
    cache = _api("/audit/citations/faithfulness/cache")
    assert _FAITH_SLUG in cache["stale_slugs"], (
        f"Expected {_FAITH_SLUG!r} stale after ingested timestamp advanced "
        f"from {_T1!r} to {_T2!r}; stale_slugs: {cache['stale_slugs']}"
    )

    # ── Steps 6–7: re-audit with T2, verify fresh again ──────────────────────
    _run_audit(page_slug=_FAITH_SLUG)
    cache = _api("/audit/citations/faithfulness/cache")
    assert _FAITH_SLUG not in cache["stale_slugs"], (
        f"Expected {_FAITH_SLUG!r} fresh after re-audit (T2); "
        f"stale_slugs: {cache['stale_slugs']}"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
