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
  - test_post_ingest_queues_job_for_valid_source: creates a temp source file and
    wiki page; both are deleted in the finally block.
  - test_agentic_full_reingest_workflow: may manufacture a stale page (temp source
    + wiki page); both are deleted in the finally block. Stale pages that existed
    before the test will be re-ingested (reset to draft) — this is the point of
    the test.
  All other tests are read-only or make no persistent state changes.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx
import pytest

BASE = os.environ.get("SYNTHADOC_URL", "http://127.0.0.1:7070").rstrip("/")
_TERMINAL = {"completed", "failed", "cancelled", "dead", "skipped"}


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


def _make_stale_page(wiki_root: Path, *, seed: str = "") -> tuple[str, Path] | None:
    """
    Manufacture a stale page for tests that need one:
      1. Write a temp source to raw_sources/
      2. Ingest it (hash recorded in DB)
      3. Modify the source (hash changes)
      4. Run lint (detects hash mismatch → marks page stale)

    Returns (slug, source_path) on success, None on failure (test should skip).
    Pass `seed` to embed a unique phrase in the content so two calls produce
    distinct slugs even when the LLM uses content-derived titles.
    """
    raw_dir = wiki_root / "raw_sources"
    raw_dir.mkdir(exist_ok=True)
    wiki_dir = wiki_root / "wiki"

    stamp = int(time.time())
    tag = f"{seed}-{stamp}" if seed else str(stamp)
    tmp = raw_dir / f"_live-agentic-stale-{tag}.txt"
    unique_label = f"[live-test-{tag}]"
    tmp.write_text(
        f"The Antikythera mechanism {unique_label} is an ancient analogue computer "
        f"from Greece.\n",
        encoding="utf-8",
    )

    before = {f.stem for f in wiki_dir.glob("*.md")}

    # Ingest via existing endpoint (not the new /ingest endpoint under test)
    try:
        r = _api("/jobs/ingest", "POST", {"source": str(tmp)})
        status = _wait_job(r["job_id"], max_wait=300)
    except Exception:
        tmp.unlink(missing_ok=True)
        return None

    if status != "completed":
        tmp.unlink(missing_ok=True)
        return None

    slug = _new_slug_in(wiki_dir, before)
    if not slug:
        tmp.unlink(missing_ok=True)
        return None

    # Modify source → hash mismatch
    tmp.write_text(
        f"The Antikythera mechanism {unique_label} is an ancient analogue computer "
        f"from Greece. It dates to approximately 100 BCE.\n",
        encoding="utf-8",
    )

    # Run lint to detect staleness
    try:
        r = _api("/jobs/lint", "POST", {"scope": "all", "auto_resolve": False, "adversarial": False})
        _wait_job(r["job_id"], max_wait=300)
    except Exception:
        _cleanup_page(wiki_root, slug, tmp)
        return None

    if slug not in _find_stale_slugs():
        _cleanup_page(wiki_root, slug, tmp)
        return None

    return slug, tmp


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
def test_post_ingest_queues_job_for_valid_source():
    """POST /ingest with a valid source path inside wiki root → job_id; job completes."""
    wiki_root = _wiki_root()
    raw_dir = wiki_root / "raw_sources"
    raw_dir.mkdir(exist_ok=True)

    stamp = int(time.time())
    tmp = raw_dir / f"_live-ingest-ep-{stamp}.txt"
    tmp.write_text(
        f"The Turing machine [{stamp}] is a theoretical model of computation.\n",
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
        assert status == "completed", f"Ingest job ended with status: {status!r}"

        slug = _new_slug_in(wiki_dir, before)
        assert slug is not None, "No new wiki page created after ingest job completed"
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
def test_action_confirm_duplicate_session_returns_409():
    """A second /action/confirm while the first is still pending returns 409."""
    stale_slugs = _find_stale_slugs()
    if not stale_slugs:
        pytest.skip("No stale pages — cannot trigger a pending confirm gate")

    session_id = str(uuid.uuid4())
    first_confirm_done = threading.Event()
    second_status: list[int] = []

    def _stream_until_confirm():
        # Run SSE in background just long enough to trigger the confirm gate;
        # we do not need the full response here.
        try:
            _sse_events(
                f"/query/stream?q=re-ingest+stale+pages"
                f"&session_id={session_id}&no_cache=true",
                timeout=120,
            )
        except Exception:
            pass

    stream_thread = threading.Thread(target=_stream_until_confirm, daemon=True)
    stream_thread.start()

    # Give the agent time to reach the confirm gate
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        r1 = _raw("/action/confirm", "POST", {"session_id": session_id, "confirmed": True})
        if r1.status_code == 200:
            # First confirm accepted — immediately fire a duplicate
            r2 = _raw("/action/confirm", "POST", {"session_id": session_id, "confirmed": True})
            second_status.append(r2.status_code)
            first_confirm_done.set()
            break
        time.sleep(1)

    stream_thread.join(timeout=10)

    if not first_confirm_done.is_set():
        pytest.skip("Confirm gate did not become pending within 45s — cannot test duplicate")

    assert second_status and second_status[0] == 409, (
        f"Expected 409 for duplicate confirm, got {second_status}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Group 3: pre_prompt in the SSE done event
# New done field added in v1.2.0; absent until the feature ships.
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
def test_query_done_pre_prompt_present_when_stale_pages_exist():
    """
    A wiki-status query's done SSE event includes pre_prompt mentioning the
    stale slug(s) when the wiki has stale pages.
    """
    stale_slugs = _find_stale_slugs()
    if not stale_slugs:
        pytest.skip("No stale pages in this wiki — cannot verify pre_prompt trigger")

    events = _sse_events("/query/stream?q=show+me+the+wiki+status&no_cache=true", timeout=90)
    done_events = [(t, d) for t, d in events if t == "done"]
    assert done_events, f"SSE stream ended without a done event. Events: {[t for t,_ in events]}"

    _, done_data = done_events[-1]
    pre_prompt = done_data.get("pre_prompt")
    assert pre_prompt, (
        f"done event missing pre_prompt despite {len(stale_slugs)} stale page(s). "
        f"done payload: {done_data}"
    )
    # Either slugs are named directly OR the suggestion is a generic re-ingest prompt.
    # LLM output format is non-deterministic so we only require that the pre_prompt
    # contains a re-ingest keyword or one of the known stale slugs.
    assert (
        any(slug in pre_prompt for slug in stale_slugs)
        or "ingest" in pre_prompt.lower()
        or "stale" in pre_prompt.lower()
    ), (
        f"pre_prompt {pre_prompt!r} does not suggest re-ingest of stale pages: {stale_slugs}"
    )


@pytest.mark.live
def test_query_done_pre_prompt_absent_when_no_stale_pages():
    """
    When no stale pages are present, the done SSE event has no pre_prompt
    (so the textarea is not pre-filled with a stale-reingest suggestion).
    """
    stale_slugs = _find_stale_slugs()
    if stale_slugs:
        pytest.skip("Wiki has stale pages — cannot verify pre_prompt is absent")

    events = _sse_events("/query/stream?q=show+me+the+wiki+status&no_cache=true", timeout=90)
    done_events = [(t, d) for t, d in events if t == "done"]
    assert done_events, "SSE stream ended without a done event"

    _, done_data = done_events[-1]
    pre_prompt = done_data.get("pre_prompt")
    assert not pre_prompt, (
        f"done event carries pre_prompt={pre_prompt!r} but no stale pages exist"
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
    confirmed_sessions: set[str] = set()
    lock = threading.Lock()

    def _monitor_and_confirm():
        while True:
            time.sleep(0.3)
            with lock:
                snapshot = list(collected)
            for evt_type, data in snapshot:
                if evt_type == "confirm_request":
                    sid = data.get("session_id", session_id)
                    if sid not in confirmed_sessions:
                        confirmed_sessions.add(sid)
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

    path = f"/query/stream?q={q}&session_id={session_id}&no_cache=true"
    with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
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
def test_agentic_reingest_emits_tool_progress_events():
    """
    Sending 're-ingest stale pages' when stale pages exist produces at least
    one tool_progress SSE event and completes with a done event (no error).

    Auto-confirms the confirm gate so tool_progress events are reachable.
    """
    stale_slugs = _find_stale_slugs()
    if not stale_slugs:
        pytest.skip("No stale pages — cannot test agentic reingest workflow")

    session_id = str(uuid.uuid4())
    events = _stream_with_autoconfirm(
        "re-ingest+stale+pages",
        session_id,
        timeout=300,
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


@pytest.mark.live
def test_agentic_reingest_stale_pages_become_draft():
    """
    After the agentic re-ingest workflow completes, the stale pages that were
    targeted are no longer in stale state — they reset to draft (awaiting lint
    promotion to active).

    Manufactures a stale page if none exists; cleans up the manufactured page
    after the test regardless of outcome.
    """
    wiki_root = _wiki_root()
    manufactured: tuple[str, Path] | None = None

    stale_before = _find_stale_slugs()
    if not stale_before:
        manufactured = _make_stale_page(wiki_root)
        if manufactured is None:
            pytest.skip("Could not manufacture a stale page — skipping e2e test")
        stale_before = _find_stale_slugs()

    target_slugs = list(stale_before)

    try:
        session_id = str(uuid.uuid4())
        events = _stream_with_autoconfirm(
            "re-ingest+stale+pages",
            session_id,
            timeout=300,
        )

        error_events = [(t, d) for t, d in events if t == "error"]
        assert not error_events, f"Agentic workflow emitted error events: {error_events}"

        done_events = [(t, d) for t, d in events if t == "done"]
        assert done_events, "SSE stream ended without a done event"

        stale_after = _find_stale_slugs()
        still_stale = [s for s in target_slugs if s in stale_after]
        assert not still_stale, (
            f"Pages still stale after agentic re-ingest: {still_stale}. "
            f"All stale before: {target_slugs}"
        )
    finally:
        if manufactured:
            slug, source_path = manufactured
            _cleanup_page(wiki_root, slug, source_path)


@pytest.mark.live
def test_agentic_confirm_decline_cancels_workflow():
    """
    When the user declines the confirm gate (confirmed=False), the agentic
    workflow narrates cancellation and stops — no pages are re-ingested and
    stale pages remain stale.
    """
    stale_slugs = _find_stale_slugs()
    if not stale_slugs:
        pytest.skip("No stale pages — cannot test confirm-decline path")

    session_id = str(uuid.uuid4())
    collected: list[tuple[str, dict]] = []
    declined = threading.Event()

    def _decline_monitor():
        deadline = time.monotonic() + 60
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

    path = f"/query/stream?q=re-ingest+stale+pages&session_id={session_id}&no_cache=true"
    with httpx.Client(timeout=httpx.Timeout(120)) as client:
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

    # Stale pages must remain stale (nothing was re-ingested)
    stale_after = _find_stale_slugs()
    still_stale = [s for s in stale_slugs if s in stale_after]
    assert still_stale, (
        "Expected stale pages to remain stale after confirm decline, "
        f"but none of {stale_slugs} are stale any more"
    )

    # The done event's narrative must mention cancellation (not a success message)
    _, done_data = done_events[-1]
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


@pytest.mark.live
def test_agentic_partial_completion_continues_after_one_failure():
    """
    If one of N ingest jobs fails (e.g. source file deleted between find and
    ingest), the agent continues with the remaining pages and reports all
    outcomes — the SSE stream still completes with a done event.

    Manufactures two stale pages, then deletes one source file just before
    the ingest phase runs so the agent encounters a file-not-found error
    mid-workflow.
    """
    wiki_root = _wiki_root()

    page_a = _make_stale_page(wiki_root, seed="a")
    if page_a is None:
        pytest.skip("Could not manufacture stale page A — skipping partial-completion test")
    slug_a, src_a = page_a

    page_b = _make_stale_page(wiki_root, seed="b")
    if page_b is None:
        _cleanup_page(wiki_root, slug_a, src_a)
        pytest.skip("Could not manufacture stale page B — skipping partial-completion test")
    slug_b, src_b = page_b

    try:
        # Sabotage page B's source just before ingest would pick it up.
        # We delete src_b immediately so the agent's ingest_source call for B
        # receives a file-not-found error, while A proceeds normally.
        src_b.unlink(missing_ok=True)

        session_id = str(uuid.uuid4())
        events = _stream_with_autoconfirm(
            "re-ingest+stale+pages",
            session_id,
            timeout=300,
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
            kw in full_text.lower() for kw in ("fail", "error", "not found", "could not")
        ), (
            "Expected failure narrative for the page whose source was deleted"
        )
    finally:
        _cleanup_page(wiki_root, slug_a, src_a)
        _cleanup_page(wiki_root, slug_b, src_b)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
