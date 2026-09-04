# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""
Live integration tests for the Agentic Ingest & Lint Workflow.

IMPORTANT: Groups 1–4 require the v1.2.0 Agentic Ingest & Lint Workflow
to be shipped. Tests for new HTTP endpoints (POST /ingest, POST /action/confirm)
and SSE protocol extensions (tool_progress, pre_prompt) will fail with 404 or
assertion errors until the feature is implemented.

Prerequisites:
  - synthadoc serve -w <wiki> is running on SYNTHADOC_URL (default 127.0.0.1:7070)
  - A wiki with pages is registered and the server is healthy
  - ANTHROPIC_API_KEY (or equivalent provider key) is set

Run with:
  python -X utf8 tests/live/run_all.py --suite agentic
  pytest tests/live/test_agentic_ingest_lint_live.py -v -s

Side effects and rollback:
  All tests that modify wiki state are self-contained: they manufacture temporary
  stale pages (via _make_stale_page), isolate any pre-existing stale pages to avoid
  interference, and restore everything in finally blocks via _restore_stale_page /
  _restore_isolated_pages regardless of test outcome.  The wiki should be left in
  the same state it was in before the suite ran.
  - test_post_ingest_queues_job_for_valid_source: creates a temp source file and
    wiki page; both are deleted in the finally block.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx
import pytest

from synthadoc.core.queue import JobStatus

BASE = os.environ.get("SYNTHADOC_URL", "http://127.0.0.1:7070").rstrip("/")
_TERMINAL = {s for s in JobStatus if s.is_terminal}


# ── Low-level helpers ─────────────────────────────────────────────────────────

def _api(path: str, method: str = "GET", body: dict | None = None) -> dict:
    """Make an HTTP request and return the parsed JSON body.

    Does NOT raise on 4xx — callers that care about the status code
    should use _raw() instead.
    """
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
    """Make an HTTP request and return the raw response (never raise)."""
    with httpx.Client(timeout=30) as client:
        if method == "POST":
            return client.post(f"{BASE}{path}", json=body)
        elif method == "DELETE":
            return client.delete(f"{BASE}{path}")
        return client.get(f"{BASE}{path}")


def _wait_job(job_id: str, max_wait: int = 240) -> str:
    """Poll /jobs/{job_id} until terminal; return final status string."""
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        try:
            body = _api(f"/jobs/{job_id}")
            status = body.get("status", "")
            if status in _TERMINAL:
                return status
        except Exception:
            pass
        time.sleep(3)
    return "timeout"


def _wait_for_queue_idle(max_wait: int = 300) -> None:
    """Block until the job queue has no pending or running jobs.

    Polls ``GET /jobs`` every 5 seconds.  Returns as soon as all known
    jobs are in a terminal state, or after *max_wait* seconds (best-effort).
    Used before starting a workflow to ensure residual jobs from earlier
    tests do not delay the ingest job beyond ``tool_poll_job``'s timeout.
    """
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        try:
            r = _raw("/jobs")
            if r.status_code == 200:
                active = [
                    j for j in r.json()
                    if isinstance(j, dict) and j.get("status") not in _TERMINAL
                ]
                if not active:
                    return
        except Exception:
            pass
        time.sleep(5)


def _sse_events(path: str, *, timeout: int = 90) -> list[tuple[str, dict]]:
    """Stream a GET SSE endpoint and collect all (event_type, data) pairs.

    Handles the server's `event: type\\ndata: json\\n\\n` framing correctly,
    including blank-line event separators that httpx iter_lines() would skip.
    """
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
                        # Blank line → dispatch accumulated event
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


def _wiki_root() -> Path:
    """Return the wiki root path from the running server's /status endpoint."""
    status = _api("/status")
    return Path(status["wiki"])


def _find_stale_slugs() -> list[str]:
    """Return slugs currently in stale state according to /lifecycle/pages."""
    result = _api("/lifecycle/pages")
    return [p["slug"] for p in result.get("pages", []) if p.get("state") == "stale"]


def _find_contradicted_slugs() -> list[str]:
    """Return slugs currently in contradicted state according to /lifecycle/pages."""
    result = _api("/lifecycle/pages")
    return [p["slug"] for p in result.get("pages", []) if p.get("state") == "contradicted"]


def _new_slug_in(wiki_dir: Path, before: set[str]) -> str | None:
    """Return the first new slug that appeared in wiki_dir since before was snapped."""
    now = {f.stem for f in wiki_dir.glob("*.md")}
    new = now - before
    return next(iter(new), None)


def _cleanup_page(wiki_root: Path, slug: str, source_path: Path | None = None) -> None:
    """Delete a test-created wiki page and its source file; remove DB history."""
    (wiki_root / "wiki" / f"{slug}.md").unlink(missing_ok=True)
    if source_path:
        source_path.unlink(missing_ok=True)
    try:
        _raw(f"/pages/{slug}/history", "DELETE")
    except Exception:
        pass


def _get_source_path_from_page(wiki_dir: Path, slug: str) -> Path | None:
    """Return the first local text-file source path from a wiki page's frontmatter.

    Parses the YAML frontmatter for `sources[*].file`, skips URL sources and
    binary formats (pdf, docx, etc.), and returns a Path only if the file
    exists on disk and is safe to append a text line to.
    """
    page_file = wiki_dir / f"{slug}.md"
    try:
        text = page_file.read_text(encoding="utf-8")
    except Exception:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("\n---\n", 3)
    if end == -1:
        return None
    fm_text = text[3:end]
    # Match file entries. The lint lifecycle check uses the AUDIT DB hash (not the
    # frontmatter hash) to detect staleness — so pages with hash="placeholder" in the
    # frontmatter can still be made stale if they have a real audit DB entry.
    for m in re.finditer(r'file:\s*(?P<file>[^\n]+)', fm_text):
        val = m.group("file").strip().strip('"\'')
        if val.startswith("http://") or val.startswith("https://"):
            continue
        p = Path(val)
        if not p.is_absolute():
            # Legacy pages store paths relative to raw_sources/ (e.g. "public-domain/foo.txt").
            # Try wiki_root first, then wiki_root/raw_sources as fallback.
            wiki_root = wiki_dir.parent
            candidate = wiki_root / p
            if not candidate.exists():
                candidate = wiki_root / "raw_sources" / p
            p = candidate
        if not (p.exists() and p.is_file()):
            continue
        if p.suffix.lower() not in {".txt", ".md"}:
            continue
        return p
    return None


def _make_stale_page(
    wiki_root: Path,
    *,
    seed: str = "",
    exclude_slugs: set | None = None,
) -> tuple[str, Path, str, str] | None:
    """
    Manufacture a stale page by borrowing an existing active or draft page.

    Finds a page whose source is a local text file, reads the current source
    content, then uses POST /lifecycle/transition to set the page to STALE in
    both the frontmatter and audit DB.  Active pages go directly ACTIVE→STALE.
    Draft pages are first promoted DRAFT→ACTIVE, then transitioned ACTIVE→STALE.

    The source file is NOT modified, so the agentic workflow's own lint run sees
    H_orig == H_orig in the ingests table (no false-positive hash-mismatch on
    other pages).

    Returns (slug, source_path, original_content, original_state) on success
    where original_state is "active" or "draft".  Returns None if no suitable
    page is found.  Use _restore_stale_page() for cleanup — NOT
    _cleanup_page(), which would delete real user data.

    `exclude_slugs`: skip these slugs (use when borrowing a second page).
    `seed`: accepted for API compatibility but unused.
    """
    wiki_dir = wiki_root / "wiki"
    exclude = set(exclude_slugs or [])

    try:
        pages = _api("/lifecycle/pages").get("pages", [])
    except Exception:
        return None

    def _find_candidate(target_state: str) -> tuple[str, Path, str] | None:
        for page_info in pages:
            if page_info.get("state") != target_state:
                continue
            candidate = page_info["slug"]
            if candidate in exclude:
                continue
            sp = _get_source_path_from_page(wiki_dir, candidate)
            if sp is None:
                continue
            try:
                orig = sp.read_text(encoding="utf-8")
            except Exception:
                continue
            return candidate, sp, orig
        return None

    # Prefer active pages (no extra transition needed)
    found = _find_candidate("active")
    original_state = "active"

    # Fall back to draft pages: promote DRAFT→ACTIVE first, then ACTIVE→STALE
    if found is None:
        found = _find_candidate("draft")
        if found is None:
            return None
        original_state = "draft"
        slug_tmp = found[0]
        try:
            r = _raw("/lifecycle/transition", "POST", {
                "slug": slug_tmp,
                "to_state": "active",
                "reason": "live-test: promote draft before manufacturing stale page",
            })
            if r.status_code != 200:
                return None
        except Exception:
            return None

    slug, source_path, original_content = found

    # Transition ACTIVE→STALE via the lifecycle API — fast (< 1 s) and
    # surgical: only this page is affected.  The source hash in the ingests
    # table still matches the current source file (H_orig == H_orig), so the
    # agentic workflow's lint won't re-detect a mismatch and won't touch any
    # other page.  The ingest LLM sees real, in-scope content and chooses
    # action=update (not action=skip), triggering the STALE→DRAFT transition.
    try:
        r = _raw("/lifecycle/transition", "POST", {
            "slug": slug,
            "to_state": "stale",
            "reason": "live-test: manufacture stale page",
        })
        if r.status_code != 200:
            return None
    except Exception:
        return None

    if slug not in _find_stale_slugs():
        return None

    return slug, source_path, original_content, original_state


def _restore_stale_page(
    wiki_root: Path,
    slug: str,
    source_path: Path,
    original_content: str,
    *,
    original_state: str = "active",
) -> None:
    """Restore a page borrowed by _make_stale_page to its pre-test state.

    Writes the original content back, then force-re-ingests so the DB hash
    is updated and the page leaves stale/draft state.  If original_state is
    "active", promotes the page from DRAFT→ACTIVE after the ingest completes.
    """
    try:
        source_path.write_text(original_content, encoding="utf-8")
    except Exception:
        pass
    try:
        r = _api("/jobs/ingest", "POST", {"source": str(source_path), "force": True})
        _wait_job(r["job_id"], max_wait=180)
    except Exception:
        pass
    if original_state == "active":
        try:
            _raw("/lifecycle/transition", "POST", {
                "slug": slug,
                "to_state": "active",
                "reason": "live-test: restore to original active state",
            })
        except Exception:
            pass


def _isolate_stale_pages_with_sources(wiki_root: Path) -> list[str]:
    """Temporarily move all currently-stale pages with local text sources to ACTIVE.

    This prevents the agentic workflow from picking up residual stale pages
    during the test, ensuring only the manufactured page appears as stale.
    Returns the slugs that were moved; pass them to _restore_isolated_pages()
    in a finally block to restore their state after the test.
    """
    wiki_dir = wiki_root / "wiki"
    moved: list[str] = []
    try:
        pages = _api("/lifecycle/pages").get("pages", [])
    except Exception:
        return []
    for page_info in pages:
        if page_info.get("state") != "stale":
            continue
        slug = page_info["slug"]
        if _get_source_path_from_page(wiki_dir, slug) is None:
            continue
        try:
            r = _raw("/lifecycle/transition", "POST", {
                "slug": slug,
                "to_state": "active",
                "reason": "live-test: isolate pre-existing stale page",
            })
            if r.status_code == 200:
                moved.append(slug)
        except Exception:
            pass
    return moved


def _restore_isolated_pages(slugs: list[str]) -> None:
    """Move slugs previously isolated by _isolate_stale_pages_with_sources back to STALE."""
    for slug in slugs:
        try:
            _raw("/lifecycle/transition", "POST", {
                "slug": slug,
                "to_state": "stale",
                "reason": "live-test: restore isolated page",
            })
        except Exception:
            pass


def _wait_for_slug_not_stale(slug: str, timeout: int = 120) -> bool:
    """Poll /lifecycle/pages until slug is no longer stale or timeout expires.

    Returns True if the slug left stale state within the timeout.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if slug not in _find_stale_slugs():
                return True
        except Exception:
            pass
        time.sleep(5)
    try:
        return slug not in _find_stale_slugs()
    except Exception:
        return False


# ── Server gate ───────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def require_server():
    """Skip all tests if the server isn't reachable."""
    try:
        httpx.get(f"{BASE}/health", timeout=3).raise_for_status()
    except Exception:
        pytest.skip("Synthadoc server not running — skipping live tests")


# ══════════════════════════════════════════════════════════════════════════════
# Group 1: POST /ingest endpoint
# New endpoint added in v1.2.0: file-path ingest with wiki-root validation.
# Will return 404 (route not found) until the feature ships.
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(300)
def test_post_ingest_queues_job_for_valid_source():
    """POST /ingest with a valid source path inside wiki root → job_id; job completes."""
    wiki_root = _wiki_root()
    raw_dir = wiki_root / "raw_sources"
    raw_dir.mkdir(exist_ok=True)

    stamp = int(time.time())
    tmp = raw_dir / f"_live-ingest-ep-{stamp}.txt"
    tmp.write_text(
        f"The Antikythera mechanism [{stamp}] is an ancient analogue computer "
        f"from Greece, dating to approximately 100 BCE.\n",
        encoding="utf-8",
    )

    wiki_dir = wiki_root / "wiki"
    before = {f.stem for f in wiki_dir.glob("*.md")}
    slug = None
    try:
        r = _raw("/ingest", "POST", {"source_path": str(tmp)})
        assert r.status_code == 200, (
            f"POST /ingest → {r.status_code} (expected 200)\n{r.text[:300]}"
        )
        body = r.json()
        assert "job_id" in body, f"No job_id in response: {body}"

        status = _wait_job(body["job_id"])
        # The endpoint contract is: valid path → 200 + queued job. Whether the
        # worker skips (out-of-scope for this wiki's purpose) or completes both
        # indicate the endpoint wired correctly. Unexpected statuses (failed,
        # dead, timeout) signal a real problem.
        # Accept "completed" (page created or updated) and "skipped" (content
        # out-of-scope for this wiki's purpose, or already ingested).
        # Both indicate the endpoint correctly queued and ran the job.
        assert status in {JobStatus.COMPLETED, JobStatus.SKIPPED}, (
            f"POST /ingest job ended with unexpected status: {status!r}"
        )
        # Only check for a new slug when completed AND a new page would be
        # expected — if the wiki already has an Antikythera page the job
        # updates it in place, which is equally correct behaviour.
        if status == JobStatus.COMPLETED:
            slug = _new_slug_in(wiki_dir, before)
    finally:
        if slug:
            _cleanup_page(wiki_root, slug, tmp)
        else:
            tmp.unlink(missing_ok=True)


@pytest.mark.live
def test_post_ingest_rejects_path_outside_wiki_root():
    """POST /ingest with a path outside wiki root returns 403."""
    r = _raw("/ingest", "POST", {"source_path": "/etc/passwd"})
    assert r.status_code == 403, (
        f"Expected 403 for outside-root path, got {r.status_code}\n{r.text[:200]}"
    )


@pytest.mark.live
def test_post_ingest_rejects_nonexistent_source():
    """POST /ingest with a path that doesn't exist (but is within wiki root) returns 404."""
    wiki_root = _wiki_root()
    ghost = str(wiki_root / "raw_sources" / "_does_not_exist_live_test.txt")
    r = _raw("/ingest", "POST", {"source_path": ghost})
    assert r.status_code == 404, (
        f"Expected 404 for non-existent source, got {r.status_code}\n{r.text[:200]}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Group 2: POST /action/confirm endpoint
# New endpoint added in v1.2.0: unblocks a waiting confirm tool call.
# Will return 404 (route not found) until the feature ships.
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
def test_action_confirm_unknown_session_returns_404():
    """POST /action/confirm with no pending session → 404."""
    r = _raw("/action/confirm", "POST", {
        "session_id": "00000000-0000-0000-0000-000000000000",
        "confirmed": True,
    })
    assert r.status_code == 404, (
        f"Expected 404 for unknown session, got {r.status_code}\n{r.text[:200]}"
    )


@pytest.mark.live
@pytest.mark.timeout(360)
def test_action_confirm_duplicate_session_returns_409():
    """A second /action/confirm while the first is still pending returns 409."""
    wiki_root = _wiki_root()
    isolated_slugs = _isolate_stale_pages_with_sources(wiki_root)
    manufactured = _make_stale_page(wiki_root)
    if manufactured is None:
        _restore_isolated_pages(isolated_slugs)
        pytest.skip("No suitable page to manufacture stale state — cannot trigger confirm gate")
    slug, source_path, orig_content, orig_state = manufactured
    isolated_slugs = [s for s in isolated_slugs if s != slug]

    session_id = str(uuid.uuid4())
    first_confirm_done = threading.Event()
    second_status: list[int] = []

    def _stream_until_confirm():
        # Run SSE in background just long enough to trigger the confirm gate;
        # we do not need the full response here.
        try:
            _sse_events(
                f"/query/stream?q=re-ingest+stale+pages"
                f"&session_id={session_id}&no_cache=true&timeout_seconds=300",
                timeout=320,
            )
        except Exception:
            pass

    stream_thread = threading.Thread(target=_stream_until_confirm, daemon=True)
    stream_thread.start()

    try:
        # Give the agent time to reach the confirm gate
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            r1 = _raw("/action/confirm", "POST", {"session_id": session_id, "confirmed": True})
            if r1.status_code == 200:
                # First confirm accepted — immediately fire a duplicate
                r2 = _raw("/action/confirm", "POST", {"session_id": session_id, "confirmed": True})
                second_status.append(r2.status_code)
                first_confirm_done.set()
                break
            time.sleep(1)

        stream_thread.join(timeout=30)

        if not first_confirm_done.is_set():
            pytest.skip("Confirm gate did not become pending within 60s — cannot test duplicate")

        # 409 = gate still pending (result set but agent hasn't cleaned up yet).
        # 404 = agent already consumed and cleaned up by the time the second
        #       confirm arrived. Both mean the session cannot be double-confirmed.
        assert second_status and second_status[0] in {404, 409}, (
            f"Expected 404 or 409 for duplicate confirm, got {second_status}"
        )
    finally:
        _restore_stale_page(wiki_root, slug, source_path, orig_content, original_state=orig_state)
        _restore_isolated_pages(isolated_slugs)


# ══════════════════════════════════════════════════════════════════════════════
# Group 3: pre_prompt in the SSE done event
# New done field added in v1.2.0; absent until the feature ships.
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(240)
def test_query_done_pre_prompt_present_when_stale_pages_exist():
    """
    A wiki-status query's done SSE event includes a non-null pre_prompt when
    the wiki has at least one actionable maintenance issue.

    Manufactures a stale page to guarantee at least one issue exists.  The
    actual pre_prompt content may reflect a higher-priority issue (e.g.
    contradictions) rather than the manufactured stale page — both are valid.
    """
    wiki_root = _wiki_root()
    isolated_slugs = _isolate_stale_pages_with_sources(wiki_root)
    manufactured = _make_stale_page(wiki_root)
    if manufactured is None:
        _restore_isolated_pages(isolated_slugs)
        pytest.skip("No suitable page found to manufacture stale state — skipping")
    slug, source_path, orig_content, orig_state = manufactured
    isolated_slugs = [s for s in isolated_slugs if s != slug]

    try:
        events = _sse_events("/query/stream?q=show+me+the+wiki+status&no_cache=true", timeout=90)
        done_events = [(t, d) for t, d in events if t == "done"]
        assert done_events, f"SSE stream ended without a done event. Events: {[t for t,_ in events]}"

        _, done_data = done_events[-1]
        pre_prompt = done_data.get("pre_prompt")
        assert pre_prompt, (
            f"done event missing pre_prompt despite stale page {slug!r}. "
            f"done payload: {done_data}"
        )
        # The pre_prompt must contain actionable maintenance language.
        # It may mention the manufactured stale slug, or it may surface a
        # higher-priority issue (contradictions, broken links, orphans) if one
        # exists in the wiki — all are valid pre_prompt payloads.
        _MAINTENANCE_KEYWORDS = (
            "ingest", "stale", "re-ingest",
            "contradicted", "contradiction",
            "broken", "wikilink",
            "orphan", "lint",
        )
        assert (
            slug in pre_prompt
            or any(kw in pre_prompt.lower() for kw in _MAINTENANCE_KEYWORDS)
        ), (
            f"pre_prompt {pre_prompt!r} contains no actionable maintenance language "
            f"and does not mention the manufactured slug {slug!r}"
        )
    finally:
        _restore_stale_page(wiki_root, slug, source_path, orig_content, original_state=orig_state)
        _restore_isolated_pages(isolated_slugs)


@pytest.mark.live
@pytest.mark.timeout(120)
def test_query_done_pre_prompt_absent_when_no_stale_pages():
    """
    When no actionable pages exist (no stale, no contradicted), the done SSE
    event has no pre_prompt (so the textarea is not pre-filled with a
    suggestion to run a workflow).

    Note: contradicted pages also trigger a pre_prompt (contradiction resolver
    hint), so the test must skip when either condition exists.
    """
    stale_slugs = _find_stale_slugs()
    if stale_slugs:
        pytest.skip("Wiki has stale pages — cannot verify pre_prompt is absent")

    contradicted_slugs = _find_contradicted_slugs()
    if contradicted_slugs:
        pytest.skip(
            f"Wiki has {len(contradicted_slugs)} contradicted page(s) — "
            "they also trigger a pre_prompt (contradiction resolver hint); "
            "cannot verify pre_prompt is absent"
        )

    events = _sse_events("/query/stream?q=show+me+the+wiki+status&no_cache=true", timeout=90)
    done_events = [(t, d) for t, d in events if t == "done"]
    assert done_events, "SSE stream ended without a done event"

    _, done_data = done_events[-1]
    pre_prompt = done_data.get("pre_prompt")
    assert not pre_prompt, (
        f"done event carries pre_prompt={pre_prompt!r} but no stale or contradicted pages exist"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Group 4: End-to-end agentic workflow
# Requires complete v1.2.0 implementation. Tests will fail until shipped.
# ══════════════════════════════════════════════════════════════════════════════

def _stream_with_autoconfirm(
    q: str,
    session_id: str,
    *,
    timeout: int = 300,
) -> list[tuple[str, dict]]:
    """
    Stream the query endpoint in a thread. Whenever a confirm_request SSE event
    arrives, immediately POST /action/confirm to unblock the agent.

    Returns the full collected event list.
    """
    collected: list[tuple[str, dict]] = []
    lock = threading.Lock()

    def _monitor_and_confirm():
        # Respond to every confirm_request seen in the snapshot.  The server
        # returns 404 if no gate is pending (already processed or popped) and
        # 409 if the gate is already set — both are swallowed by the except.
        # This allows the agent to call confirm multiple times: each new gate
        # registered by tool_confirm() will be caught on the next poll cycle.
        while True:
            time.sleep(0.3)
            with lock:
                snapshot = list(collected)
            for evt_type, data in snapshot:
                if evt_type == "confirm_request":
                    sid = data.get("session_id", session_id)
                    try:
                        _raw("/action/confirm", "POST", {
                            "session_id": sid,
                            "confirmed": True,
                        })
                    except Exception:
                        pass
                if evt_type == "done":
                    return

    monitor = threading.Thread(target=_monitor_and_confirm, daemon=True)
    monitor.start()

    path = f"/query/stream?q={q}&session_id={session_id}&no_cache=true&timeout_seconds={timeout}"
    with httpx.Client(timeout=httpx.Timeout(timeout + 30)) as client:
        with client.stream("GET", f"{BASE}{path}") as r:
            r.raise_for_status()
            current_type = "message"
            current_data: list[str] = []
            buf = ""
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
                                collected.append((current_type, data))
                        current_type = "message"
                        current_data = []
                    elif line.startswith("event:"):
                        current_type = line[6:].strip()
                    elif line.startswith("data:"):
                        current_data.append(line[5:].lstrip())

    monitor.join(timeout=5)
    return collected


@pytest.mark.live
@pytest.mark.timeout(900)
def test_agentic_reingest_emits_tool_progress_events():
    """
    Sending 're-ingest stale pages' when stale pages exist produces at least
    one tool_progress SSE event and completes with a done event (no error).

    Auto-confirms the confirm gate so tool_progress events are reachable.
    Manufactures a stale page if none exist so the test is self-contained.
    """
    wiki_root = _wiki_root()
    isolated_slugs = _isolate_stale_pages_with_sources(wiki_root)
    manufactured = _make_stale_page(wiki_root)
    if manufactured is None:
        _restore_isolated_pages(isolated_slugs)
        pytest.skip("No suitable page found to manufacture stale state — skipping")
    slug, source_path, orig_content, orig_state = manufactured
    isolated_slugs = [s for s in isolated_slugs if s != slug]

    _wait_for_queue_idle(max_wait=300)

    try:
        session_id = str(uuid.uuid4())
        events = _stream_with_autoconfirm(
            "re-ingest+stale+pages",
            session_id,
            timeout=600,
        )

        tool_progress = [(t, d) for t, d in events if t == "tool_progress"]
        assert tool_progress, (
            "Expected at least one tool_progress SSE event during agentic re-ingest. "
            f"Events received: {[t for t, _ in events]}"
        )

        done_events = [(t, d) for t, d in events if t == "done"]
        assert done_events, "SSE stream ended without a done event"

        error_events = [(t, d) for t, d in events if t == "error"]
        assert not error_events, f"Agentic workflow emitted error events: {error_events}"

        # Lint must have been queued AND polled to completion — not just queued.
        lint_progress = [d for t, d in events if t == "tool_progress" and d.get("tool") == "run_lint"]
        assert lint_progress, (
            "Expected a run_lint tool_progress event — lint was not called"
        )

        # get_page_states must be called after lint to confirm goal was achieved.
        states_progress = [d for t, d in events if t == "tool_progress" and d.get("tool") == "get_page_states"]
        assert states_progress, (
            "Expected a get_page_states tool_progress event — page states were not checked after lint"
        )

        full_text = "".join(d.get("text", "") for t, d in events if t == "token")
        assert any(
            kw in full_text.lower()
            for kw in ("lint", "check")
        ), f"Expected lint result mentioned in narrative. Got: {full_text[:300]!r}"
    finally:
        _restore_stale_page(wiki_root, slug, source_path, orig_content, original_state=orig_state)
        _restore_isolated_pages(isolated_slugs)


@pytest.mark.live
@pytest.mark.timeout(900)
def test_agentic_reingest_stale_pages_become_draft():
    """
    After the agentic re-ingest workflow completes, the stale pages that were
    targeted are no longer in stale state — they reset to draft (awaiting lint
    promotion to active).

    Manufactures a stale page if none exists; cleans up the manufactured page
    after the test regardless of outcome.  Isolates any pre-existing stale pages
    before running the workflow so queue congestion from residual jobs does not
    prevent the manufactured page from being processed.
    """
    wiki_root = _wiki_root()

    # Hide pre-existing stale pages so the workflow only sees the one we make.
    isolated_slugs = _isolate_stale_pages_with_sources(wiki_root)

    # Borrow an existing active or draft page — no source modification needed.
    manufactured = _make_stale_page(wiki_root)
    if manufactured is None:
        _restore_isolated_pages(isolated_slugs)
        pytest.skip("No active or draft page with a local text source found — skipping e2e test")
    slug, source_path, orig_content, orig_state = manufactured

    # The manufactured slug must not be in isolated_slugs — if it is,
    # _restore_isolated_pages would try to re-stale it after the workflow
    # sets it to draft, polluting subsequent test runs.
    isolated_slugs = [s for s in isolated_slugs if s != slug]

    # Drain any residual jobs from earlier tests (e.g. a long-running lint
    # job) so the workflow's ingest job reaches the front of the queue within
    # tool_poll_job's 120-second timeout window.
    _wait_for_queue_idle(max_wait=300)

    try:
        session_id = str(uuid.uuid4())
        events = _stream_with_autoconfirm(
            "re-ingest+stale+pages",
            session_id,
            timeout=600,
        )

        error_events = [(t, d) for t, d in events if t == "error"]
        assert not error_events, f"Agentic workflow emitted error events: {error_events}"

        done_events = [(t, d) for t, d in events if t == "done"]
        assert done_events, "SSE stream ended without a done event"

        # Safety net: give the ingest job a moment to write its final state even
        # if tool_poll_job returned just before the DB write completed.
        _wait_for_slug_not_stale(slug, timeout=120)

        stale_after = _find_stale_slugs()
        assert slug not in stale_after, (
            f"Borrowed page {slug!r} still stale after agentic re-ingest. "
            f"All stale slugs after: {stale_after}\n"
            f"SSE event types seen: {[t for t, _ in events]}"
        )

        # Lint must complete (not just be queued) — the narrative should say so.
        lint_progress = [d for t, d in events if t == "tool_progress" and d.get("tool") == "run_lint"]
        assert lint_progress, "Expected a run_lint tool_progress event — lint was not called"
        full_text = "".join(d.get("text", "") for t, d in events if t == "token")
        assert any(
            kw in full_text.lower()
            for kw in ("lint", "check")
        ), f"Expected lint result in narrative. Got: {full_text[:300]!r}"

        # get_page_states must follow lint and page states must appear in the narrative.
        states_progress = [d for t, d in events if t == "tool_progress" and d.get("tool") == "get_page_states"]
        assert states_progress, (
            "Expected a get_page_states tool_progress event — page states not checked after lint"
        )
        assert any(
            kw in full_text.lower()
            for kw in ("active", "stale", "page state", "✓", "✗")
        ), f"Expected page state in narrative. Got: {full_text[:300]!r}"
    finally:
        _restore_stale_page(wiki_root, slug, source_path, orig_content, original_state=orig_state)
        _restore_isolated_pages(isolated_slugs)


@pytest.mark.live
@pytest.mark.timeout(360)
def test_agentic_confirm_decline_cancels_workflow():
    """
    When the user declines the confirm gate (confirmed=False), the agentic
    workflow narrates cancellation and stops — no pages are re-ingested and
    stale pages remain stale.

    Manufactures a stale page if none exist so the test is self-contained.
    """
    wiki_root = _wiki_root()
    isolated_slugs = _isolate_stale_pages_with_sources(wiki_root)
    manufactured = _make_stale_page(wiki_root)
    if manufactured is None:
        _restore_isolated_pages(isolated_slugs)
        pytest.skip("No suitable page found to manufacture stale state — skipping")
    slug, source_path, orig_content, orig_state = manufactured
    isolated_slugs = [s for s in isolated_slugs if s != slug]

    try:
        session_id = str(uuid.uuid4())
        collected: list[tuple[str, dict]] = []
        declined = threading.Event()

        def _decline_monitor():
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                for evt_type, data in list(collected):
                    if evt_type == "confirm_request" and not declined.is_set():
                        sid = data.get("session_id", session_id)
                        try:
                            _raw("/action/confirm", "POST", {
                                "session_id": sid,
                                "confirmed": False,
                            })
                        except Exception:
                            pass
                        declined.set()
                        return
                time.sleep(0.3)

        monitor = threading.Thread(target=_decline_monitor, daemon=True)
        monitor.start()

        path = f"/query/stream?q=re-ingest+stale+pages&session_id={session_id}&no_cache=true&timeout_seconds=300"
        with httpx.Client(timeout=httpx.Timeout(320)) as client:
            with client.stream("GET", f"{BASE}{path}") as r:
                r.raise_for_status()
                current_type = "message"
                current_data: list[str] = []
                buf = ""
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
                                collected.append((current_type, data))
                            current_type = "message"
                            current_data = []
                        elif line.startswith("event:"):
                            current_type = line[6:].strip()
                        elif line.startswith("data:"):
                            current_data.append(line[5:].lstrip())

        monitor.join(timeout=5)

        if not declined.is_set():
            pytest.skip("No confirm_request event seen — cannot verify decline path")

        # Stream must still complete (done event — not hanging or erroring)
        done_events = [(t, d) for t, d in collected if t == "done"]
        assert done_events, "SSE stream did not produce a done event after confirm decline"

        # The manufactured stale page must remain stale (nothing was re-ingested)
        stale_after = _find_stale_slugs()
        assert slug in stale_after, (
            f"Expected manufactured page {slug!r} to remain stale after confirm decline, "
            f"but it is no longer stale. All stale slugs after: {stale_after}"
        )

        # The done event's narrative must mention cancellation (not a success message)
        full_text = "".join(
            d.get("text", "") for t, d in collected if t == "token"
        )
        assert any(
            kw in full_text.lower()
            for kw in ("cancel", "declined", "not confirmed", "operation cancelled")
        ), (
            f"Expected cancellation language in narrative after decline. "
            f"Got: {full_text[:300]!r}"
        )
    finally:
        _restore_stale_page(wiki_root, slug, source_path, orig_content, original_state=orig_state)
        _restore_isolated_pages(isolated_slugs)


@pytest.mark.live
@pytest.mark.timeout(900)
def test_agentic_partial_completion_continues_after_one_failure():
    """
    If one of N ingest jobs fails (e.g. source file deleted between find and
    ingest), the agent continues with the remaining pages and reports all
    outcomes — the SSE stream still completes with a done event.

    Manufactures two stale pages, then deletes one source file just before
    the ingest phase runs so the agent encounters a file-not-found error
    mid-workflow.  Isolates any pre-existing stale pages so the workflow only
    sees the two manufactured pages.
    """
    wiki_root = _wiki_root()

    # Hide pre-existing stale pages so the workflow only sees the two we make.
    isolated_slugs = _isolate_stale_pages_with_sources(wiki_root)

    page_a = _make_stale_page(wiki_root)
    if page_a is None:
        _restore_isolated_pages(isolated_slugs)
        pytest.skip("No active or draft page with a local text source found for page A — skipping")
    slug_a, src_a, orig_a, orig_state_a = page_a

    page_b = _make_stale_page(wiki_root, exclude_slugs={slug_a})
    if page_b is None:
        _restore_stale_page(wiki_root, slug_a, src_a, orig_a, original_state=orig_state_a)
        _restore_isolated_pages(isolated_slugs)
        pytest.skip("No second active or draft page with a local text source found for page B — skipping")
    slug_b, src_b, orig_b, orig_state_b = page_b

    # Guard: if both pages resolve to the same source file, renaming src_b would
    # also break src_a, making a partial-completion test impossible on this wiki.
    if src_a == src_b:
        _restore_stale_page(wiki_root, slug_a, src_a, orig_a, original_state=orig_state_a)
        _restore_stale_page(wiki_root, slug_b, src_b, orig_b, original_state=orig_state_b)
        _restore_isolated_pages(isolated_slugs)
        pytest.skip(
            f"Both manufactured pages share the same source file ({src_a.name!r}) — "
            "cannot sabotage one without breaking the other; skipping partial-failure test"
        )

    # Exclude manufactured slugs from isolated_slugs so _restore_isolated_pages
    # does not re-stale pages that the workflow just set to draft.
    isolated_slugs = [s for s in isolated_slugs if s not in {slug_a, slug_b}]

    # Drain any residual jobs (e.g. lint from the previous test's workflow) so
    # the ingest job for page A reaches the front of the queue within
    # tool_poll_job's timeout window.
    _wait_for_queue_idle(max_wait=300)

    # Sabotage: rename src_b so the agent's ingest call for B gets file-not-found
    # while page A still has a reachable source.
    src_b_bak = src_b.with_name(src_b.name + ".bak")

    try:
        src_b.rename(src_b_bak)

        session_id = str(uuid.uuid4())
        events = _stream_with_autoconfirm(
            "re-ingest+stale+pages",
            session_id,
            timeout=600,
        )

        # Stream must complete
        done_events = [(t, d) for t, d in events if t == "done"]
        assert done_events, "SSE stream ended without a done event"

        # Error event means the stream itself died — that's a bug; tool errors
        # are structured tool_result payloads and do not produce an SSE error event
        stream_error_events = [(t, d) for t, d in events if t == "error"]
        assert not stream_error_events, (
            f"Stream emitted error event (tool errors must stay in tool_result, "
            f"not surface as SSE errors): {stream_error_events}"
        )

        # The final narrative must mention both outcomes
        full_text = "".join(d.get("text", "") for t, d in events if t == "token")
        assert slug_a in full_text or "re-ingested" in full_text.lower(), (
            f"Expected successful re-ingest of {slug_a!r} mentioned in narrative"
        )
        assert any(
            kw in full_text.lower()
            for kw in (
                "fail", "error", "not found", "could not",
                "unable", "missing", "unavailable", "problem",
            )
        ), (
            "Expected failure narrative for the page whose source was missing"
        )
    finally:
        # Restore src_b from its backup before re-ingesting
        if src_b_bak.exists() and not src_b.exists():
            src_b_bak.rename(src_b)
        _restore_stale_page(wiki_root, slug_a, src_a, orig_a, original_state=orig_state_a)
        _restore_stale_page(wiki_root, slug_b, src_b, orig_b, original_state=orig_state_b)
        _restore_isolated_pages(isolated_slugs)


# ══════════════════════════════════════════════════════════════════════════════
# Group 5: Slug-based reingest (Workflow B)
# Re-ingesting a specific active or draft page by naming its slug.
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(900)
def test_agentic_reingest_by_slug_active_page_becomes_draft():
    """
    'Re-ingest the <slug> page' triggers Workflow B:
    find_page_source → confirm → ingest_source → run_lint.

    Manufactures a stale page, runs Workflow B by slug (not the stale-pages
    bulk workflow), and asserts the page is no longer stale (ingest transitions
    stale → draft).  This tests slug-based routing independently of Workflow A.
    """
    wiki_root = _wiki_root()
    isolated_slugs = _isolate_stale_pages_with_sources(wiki_root)
    manufactured = _make_stale_page(wiki_root)
    if manufactured is None:
        _restore_isolated_pages(isolated_slugs)
        pytest.skip("No suitable page for slug-based reingest test")
    slug, source_path, orig_content, orig_state = manufactured
    isolated_slugs = [s for s in isolated_slugs if s != slug]

    _wait_for_queue_idle(max_wait=300)

    try:
        session_id = str(uuid.uuid4())
        query = f"re-ingest+the+{slug}+page"
        events = _stream_with_autoconfirm(query, session_id, timeout=600)

        error_events = [(t, d) for t, d in events if t == "error"]
        assert not error_events, f"Agentic workflow emitted error events: {error_events}"

        done_events = [(t, d) for t, d in events if t == "done"]
        assert done_events, "SSE stream ended without a done event"

        # Workflow B must have run — tool_progress events from find_page_source, ingest, lint
        tool_progress = [(t, d) for t, d in events if t == "tool_progress"]
        assert tool_progress, "Expected tool_progress events during slug-based reingest"

        # The stale page must have transitioned to draft after re-ingest
        _wait_for_slug_not_stale(slug, timeout=120)
        stale_after = _find_stale_slugs()
        assert slug not in stale_after, (
            f"Expected {slug!r} to leave stale after slug-based reingest, still stale: {stale_after}"
        )

        full_text = "".join(d.get("text", "") for t, d in events if t == "token")
        assert (
            slug in full_text
            or "re-ingested" in full_text.lower()
            or "ingest" in full_text.lower()
        ), f"Expected {slug!r} or ingest language in narrative. Got: {full_text[:300]!r}"

        # Lint must complete (not just be queued) — run_lint tool_progress must be
        # present and the narrative must mention the lint result.
        lint_progress = [d for t, d in events if t == "tool_progress" and d.get("tool") == "run_lint"]
        assert lint_progress, "Expected a run_lint tool_progress event — lint was not called"
        assert any(
            kw in full_text.lower()
            for kw in ("lint", "check")
        ), f"Expected lint result in narrative. Got: {full_text[:300]!r}"

        # get_page_states must be called and the final state of the slug reported.
        states_progress = [d for t, d in events if t == "tool_progress" and d.get("tool") == "get_page_states"]
        assert states_progress, (
            "Expected a get_page_states tool_progress event — page state not checked after lint"
        )
        assert any(
            kw in full_text.lower()
            for kw in ("active", "stale", "page state", "✓", "✗")
        ), f"Expected page state in narrative. Got: {full_text[:300]!r}"
    finally:
        _restore_stale_page(wiki_root, slug, source_path, orig_content, original_state=orig_state)
        _restore_isolated_pages(isolated_slugs)


@pytest.mark.live
@pytest.mark.timeout(300)
def test_find_page_source_tool_rejects_unknown_slug():
    """
    Asking to re-ingest a slug that does not exist in the wiki produces
    a narrative that mentions the page was not found — the workflow does not
    hang or produce an SSE error event.
    """
    _wait_for_queue_idle(max_wait=60)

    session_id = str(uuid.uuid4())
    nonexistent = "this-slug-does-not-exist-xyz-live-test"
    query = f"re-ingest+the+{nonexistent}+page"
    events = _stream_with_autoconfirm(query, session_id, timeout=270)

    error_events = [(t, d) for t, d in events if t == "error"]
    assert not error_events, f"Stream emitted unexpected error events: {error_events}"

    done_events = [(t, d) for t, d in events if t == "done"]
    assert done_events, "SSE stream ended without a done event"

    full_text = "".join(d.get("text", "") for t, d in events if t == "token")
    assert any(
        kw in full_text.lower()
        for kw in (
            "not found",
            "does not exist",
            "doesn't exist",
            "no page",
            "no wiki page",
            "no source path",
            "no source file",
            "no source found",   # "No source found for page …" (tool_read_source_content)
            "unknown",
            "couldn't find",
            "could not find",
            "don't exist",
        )
    ), (
        f"Expected 'not found' language for unknown slug. Got: {full_text[:300]!r}"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
