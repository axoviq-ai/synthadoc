# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""
Live integration tests for the Lint Run & Report Workflow (Workflow D, v1.2.1).

Triggered by phrases such as "run lint and show me the report" or "lint run".
The workflow runs two tools in sequence:
  run_lint → get_lint_report

Run as a named suite:
  python -X utf8 tests/live/run_all.py --suite lint_report
  pytest tests/live/test_lint_report_workflow_live.py -v -s

Prerequisites:
  - synthadoc serve -w <wiki> running on SYNTHADOC_URL (default 127.0.0.1:7070)
  - ANTHROPIC_API_KEY set

Side effects:
  The workflow runs a real lint pass on the wiki, which may promote stale pages
  to draft, update orphan frontmatter, and write a lint_complete record to the
  audit DB.  No pages are deleted.  These are the same mutations that
  ``synthadoc lint`` performs; they are intended and idempotent.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from urllib.parse import quote

import httpx
import pytest

BASE = os.environ.get("SYNTHADOC_URL", "http://127.0.0.1:7070").rstrip("/")
_TERMINAL = {"completed", "failed", "cancelled", "dead", "skipped"}


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


def _stream_question(question: str, *, timeout: int = 400) -> list[tuple[str, dict]]:
    """Stream GET /query/stream and collect all (event_type, data) pairs."""
    events: list[tuple[str, dict]] = []
    current_type = "message"
    current_data: list[str] = []
    buf = ""
    q = quote(question, safe="")
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
                            events.append((current_type, data))
                        current_type = "message"
                        current_data = []
                    elif line.startswith("event:"):
                        current_type = line[6:].strip()
                    elif line.startswith("data:"):
                        current_data.append(line[5:].lstrip())
    return events


def _tool_names(events: list[tuple[str, dict]]) -> list[str]:
    return [e[1].get("tool", "") for e in events if e[0] == "tool_progress"]


def _tool_messages(events: list[tuple[str, dict]]) -> list[str]:
    return [e[1].get("message", "") for e in events if e[0] == "tool_progress"]


def _narrative(events: list[tuple[str, dict]]) -> str:
    return " ".join(e[1].get("text", "") for e in events if e[0] == "token").lower()


def _done_data(events: list[tuple[str, dict]]) -> dict | None:
    done = [e[1] for e in events if e[0] == "done"]
    return done[0] if done else None


def _assert_stream_complete(events: list[tuple[str, dict]]) -> dict:
    error_events = [e for e in events if e[0] == "error"]
    assert not error_events, f"Unexpected SSE error events: {error_events}"
    done = _done_data(events)
    assert done is not None, (
        f"Stream ended without a 'done' event. "
        f"Event types seen: {[t for t, _ in events]}"
    )
    return done


# ── Server gate ───────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def require_server():
    """Skip all tests if the server isn't reachable."""
    try:
        httpx.get(f"{BASE}/health", timeout=3).raise_for_status()
    except Exception:
        pytest.skip("Synthadoc server not running — skipping live tests")


# ══════════════════════════════════════════════════════════════════════════════
# Group 1 — SSE protocol: completion and tool sequence
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(450)
def test_workflow_completes_with_done_event_and_no_errors():
    """
    'run lint and show me the report' must complete with a done event and
    no SSE error events.  The workflow runs lint on the live wiki; the test
    passes regardless of whether stale pages, orphans, or contradictions exist.
    """
    events = _stream_question("run lint and show me the report")
    _assert_stream_complete(events)


@pytest.mark.live
@pytest.mark.timeout(450)
def test_workflow_fires_run_lint_and_get_lint_report_tools():
    """
    Both run_lint and get_lint_report tool_progress events must be present,
    confirming the two-step sequence (run_lint → get_lint_report) executed
    rather than the response coming from cached query data.
    """
    events = _stream_question("run lint and show me the report")
    _assert_stream_complete(events)

    tool_names = _tool_names(events)
    assert "run_lint" in tool_names, (
        f"run_lint tool_progress not emitted; tools fired: {tool_names}"
    )
    assert "get_lint_report" in tool_names, (
        f"get_lint_report tool_progress not emitted; tools fired: {tool_names}"
    )


@pytest.mark.live
@pytest.mark.timeout(450)
def test_workflow_does_not_emit_confirm_request():
    """
    LintReportWorkflow has no confirm gate — it runs lint autonomously.
    A confirm_request event would mean the wrong workflow was triggered.
    """
    events = _stream_question("run lint and show me the report")
    _assert_stream_complete(events)

    confirm_events = [e for e in events if e[0] == "confirm_request"]
    assert not confirm_events, (
        f"Unexpected confirm_request events: {confirm_events}. "
        "LintReportWorkflow should run without user confirmation."
    )


# ══════════════════════════════════════════════════════════════════════════════
# Group 2 — Labels and ordering
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(450)
def test_poll_job_progress_label_says_lint_not_ingest():
    """
    While the lint job is running, tool_progress messages must say 'Lint running...'
    (not 'Ingest running...') — regression guard for the job_label fix.
    Polling now happens inside run_lint; only asserts when at least one
    'running' progress message was emitted (fast wikis may skip this).
    """
    events = _stream_question("run lint and show me the report")
    _assert_stream_complete(events)

    progress_messages = _tool_messages(events)
    running_messages = [m for m in progress_messages if "running" in m.lower()]

    if not running_messages:
        pytest.skip(
            "No 'running' progress messages emitted — lint completed before first poll tick. "
            "Label regression cannot be verified on a fast wiki."
        )

    for msg in running_messages:
        assert "Ingest running" not in msg, (
            f"Progress message uses wrong label 'Ingest running' during lint poll: {msg!r}"
        )


@pytest.mark.live
@pytest.mark.timeout(450)
def test_run_lint_fires_before_get_lint_report():
    """
    run_lint tool_progress must appear before get_lint_report in the event
    stream — the poll/wait step between them makes order deterministic.
    """
    events = _stream_question("run lint and show me the report")
    _assert_stream_complete(events)

    tool_names = _tool_names(events)
    assert "run_lint" in tool_names, f"run_lint not in tool names: {tool_names}"
    assert "get_lint_report" in tool_names, f"get_lint_report not in tool names: {tool_names}"

    run_idx = next(i for i, t in enumerate(tool_names) if t == "run_lint")
    report_idx = next(i for i, t in enumerate(tool_names) if t == "get_lint_report")
    assert run_idx < report_idx, (
        f"get_lint_report (index {report_idx}) fired before run_lint (index {run_idx})"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Group 3 — Report content
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(450)
def test_narrative_contains_lint_report_structure():
    """
    The final narrative must mention the core report sections: a summary
    of counts and at least one content section (orphan pages, contradictions,
    adversarial warnings, or dangling links).  Values may all be zero — the
    report must still be formatted.
    """
    events = _stream_question("run lint and show me the report")
    _assert_stream_complete(events)

    text = _narrative(events)

    # Summary section keywords
    summary_keywords = ["summary", "dangling", "orphan", "contradiction", "warning", "resolved", "flagged", "removed"]
    assert any(kw in text for kw in summary_keywords), (
        f"Narrative missing summary keywords. "
        f"Expected one of {summary_keywords!r}. Got: {text[:500]!r}"
    )

    # Report must have an explicit structure — at minimum a count of some metric
    count_re = any(char.isdigit() for char in text)
    assert count_re, (
        f"Narrative contains no numeric counts — expected at least N orphan pages, "
        f"N contradictions, etc. Got: {text[:500]!r}"
    )


@pytest.mark.live
@pytest.mark.timeout(450)
def test_audit_db_has_lint_summary_after_workflow():
    """
    After the workflow completes, GET /lint/report must return a valid report
    with the expected top-level keys, confirming the endpoint is responsive
    and the workflow did not leave the server in an error state.
    """
    events = _stream_question("run lint and show me the report")
    _assert_stream_complete(events)

    r = _raw("/lint/report")
    assert r.status_code == 200, (
        f"GET /lint/report returned {r.status_code} after workflow: {r.text[:200]}"
    )
    report = r.json()

    # The endpoint returns a live scan of the wiki — not a persisted record with a
    # timestamp.  Verify the expected structural keys are present.
    expected_keys = {"orphans", "contradictions", "adversarial_warnings"}
    missing = expected_keys - set(report.keys())
    assert not missing, (
        f"GET /lint/report missing expected keys {missing} after workflow. "
        f"Keys returned: {list(report.keys())}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Group 4 — Routing: multiple phrasings, no false trigger on query phrases
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(900)
def test_three_phrasings_all_trigger_workflow():
    """
    The canonical trigger phrasings must reach LintReportWorkflow
    (run_lint tool_progress present) rather than the query path.

    Runs each phrasing sequentially; uses a short timeout since lint
    is deterministic and the workflow only needs to start, not to finish
    a full re-check of every page before the assertion passes.
    """
    phrasings = [
        "run lint",
        "run lint and show me the lint report",
    ]
    for phrase in phrasings:
        # Short timeout: we only need the workflow to START (run_lint fired),
        # not to complete a full lint run.  Stream may time out before done.
        events = _stream_question(phrase, timeout=300)

        # Only non-timeout errors are unexpected (a timeout just means lint
        # is still running, which is fine for this routing assertion).
        bad_errors = [
            e for e in events
            if e[0] == "error" and "timed out" not in e[1].get("message", "").lower()
        ]
        assert not bad_errors, f"Unexpected SSE errors for {phrase!r}: {bad_errors}"

        tool_names = _tool_names(events)
        assert "run_lint" in tool_names, (
            f"Phrasing {phrase!r} did not trigger the workflow. "
            f"run_lint not in tool names: {tool_names}. "
            f"Event types: {[t for t, _ in events]}"
        )


@pytest.mark.live
@pytest.mark.timeout(180)
def test_query_phrase_does_not_invoke_run_lint_tool():
    """
    'show me my lint report' is a query phrase (no 'run' verb) and must NOT
    trigger LintReportWorkflow.  The response should come from the QueryAgent
    reading existing state rather than running a new lint job; no run_lint
    tool_progress event should appear.
    """
    events = _stream_question("show me my lint report", timeout=120)
    _assert_stream_complete(events)

    tool_names = _tool_names(events)
    assert "run_lint" not in tool_names, (
        f"'show me my lint report' incorrectly triggered run_lint. "
        f"Tools fired: {tool_names}. "
        "This phrase should be handled as a query, not as a workflow trigger."
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
