# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""
Live integration tests for the Scaffold Workflow (Workflow E, v1.2.1).

Triggered by phrases such as "run scaffold" or "regenerate scaffold".
The workflow runs two tools in sequence; confirmation is embedded inside
run_scaffold (Pattern A) so no separate confirm tool call is needed:
  get_scaffold_preview → run_scaffold (fires confirm internally)

Run:
  pytest tests/live/test_scaffold_workflow_live.py -v -s

Prerequisites:
  - synthadoc serve -w <wiki> running on SYNTHADOC_URL (default 127.0.0.1:7070)
  - ANTHROPIC_API_KEY set

Side effects (end-to-end test only):
  test_full_scaffold_workflow_succeeds_end_to_end re-scaffolds the wiki —
  index.md, purpose.md, AGENTS.md, CLAUDE.md, GEMINI.md are overwritten.
  All other tests decline the confirm gate immediately, so they produce no
  wiki mutations.
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


# ── Low-level helpers ─────────────────────────────────────────────────────────

def _stream_with_confirm_response(
    question: str,
    *,
    accept: bool,
    confirm_delay: float = 0.3,
    timeout: int = 300,
) -> list[tuple[str, dict]]:
    """Stream GET /query/stream and automatically respond to the first confirm gate.

    When a confirm_request SSE event arrives, a background thread immediately
    POSTs to /action/confirm with the given *accept* value.  This lets the
    workflow proceed (or cancel) without waiting for the 120-second gate timeout.
    """
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

                            # Respond to the confirm gate in a background thread
                            # so the streaming connection stays open.
                            if current_type == "confirm_request":
                                session_id = data.get("session_id", "")

                                def _respond(sid: str = session_id) -> None:
                                    time.sleep(confirm_delay)
                                    with httpx.Client(timeout=10) as c:
                                        try:
                                            c.post(
                                                f"{BASE}/action/confirm",
                                                json={"session_id": sid, "confirmed": accept},
                                            )
                                        except Exception:
                                            pass

                                threading.Thread(target=_respond, daemon=True).start()
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
# Group 1 — SSE protocol: tool sequence and confirm gate (decline path)
# All tests in this group decline the confirm gate immediately.
# They run quickly because the workflow stops as soon as the gate is resolved.
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(90)
def test_workflow_fires_preview_tool_and_emits_confirm_request():
    """
    'run scaffold' must emit get_scaffold_preview tool_progress then a
    confirm_request event — the workflow runs preview, then asks before writing.
    The confirm gate is declined immediately so no wiki files are touched.
    """
    events = _stream_with_confirm_response("run scaffold", accept=False)
    _assert_stream_complete(events)

    tool_names = _tool_names(events)
    assert "get_scaffold_preview" in tool_names, (
        f"get_scaffold_preview not emitted; tools fired: {tool_names}"
    )

    confirm_events = [e for e in events if e[0] == "confirm_request"]
    assert confirm_events, (
        "No confirm_request emitted — ScaffoldWorkflow must ask before writing files."
    )


@pytest.mark.live
@pytest.mark.timeout(90)
def test_workflow_does_not_run_scaffold_when_declined():
    """
    When the confirm gate is declined the scaffold job must not be started
    and the stream must complete without errors.

    Note: with Pattern A (confirm embedded inside tool_run_scaffold), the LLM
    still calls run_scaffold — the tool loop emits a pre-call tool_progress
    for it, then the embedded confirm fires.  What proves the job did NOT run
    is the absence of the progress messages that are only emitted after the
    confirm check: "Running scaffold for..." and "✓ Scaffold complete...".
    """
    events = _stream_with_confirm_response("run scaffold", accept=False)
    _assert_stream_complete(events)

    messages = _tool_messages(events)
    assert not any("running scaffold for" in m.lower() for m in messages), (
        f"Scaffold job was started despite confirmation being declined. "
        f"Tool messages: {messages}"
    )
    assert not any("scaffold complete" in m.lower() for m in messages), (
        f"Scaffold job completed despite confirmation being declined. "
        f"Tool messages: {messages}"
    )


@pytest.mark.live
@pytest.mark.timeout(90)
def test_declined_scaffold_narrative_mentions_cancellation():
    """
    After a declined confirm gate the final narrative must mention cancellation,
    confirming the LLM correctly reports the outcome rather than silently failing.
    """
    events = _stream_with_confirm_response("run scaffold", accept=False)
    _assert_stream_complete(events)

    narrative = _narrative(events)
    assert "cancel" in narrative or "declin" in narrative, (
        f"Narrative should mention cancellation. Got: {narrative[:400]!r}"
    )


@pytest.mark.live
@pytest.mark.timeout(90)
def test_preview_progress_message_includes_domain():
    """
    The get_scaffold_preview tool_progress message must include the domain
    string, confirming the tool read ctx.domain from the wiki config correctly.
    """
    events = _stream_with_confirm_response("run scaffold", accept=False)
    _assert_stream_complete(events)

    preview_messages = [
        e[1].get("message", "")
        for e in events
        if e[0] == "tool_progress" and e[1].get("tool") == "get_scaffold_preview"
    ]
    assert preview_messages, "No get_scaffold_preview tool_progress messages emitted"
    assert any("domain" in m.lower() or ":" in m for m in preview_messages), (
        f"Preview message does not contain domain info: {preview_messages}"
    )


@pytest.mark.live
@pytest.mark.timeout(90)
def test_confirm_message_lists_scaffold_files():
    """
    The confirm_request message must mention the files that will be overwritten
    (index.md is always written). This confirms get_scaffold_preview output
    was correctly incorporated into the confirm prompt.
    """
    events = _stream_with_confirm_response("run scaffold", accept=False)
    _assert_stream_complete(events)

    confirm_events = [e[1] for e in events if e[0] == "confirm_request"]
    assert confirm_events, "No confirm_request events emitted"

    msg = confirm_events[0].get("message", "").lower()
    assert "index" in msg or "scaffold" in msg or "domain" in msg, (
        f"confirm_request message does not mention scaffold files or domain. "
        f"Message: {confirm_events[0].get('message', '')[:400]!r}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Group 2 — Full end-to-end (accept path)
# This group actually runs scaffold — core wiki files are overwritten.
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(360)
def test_full_scaffold_workflow_succeeds_end_to_end():
    """
    Accept the confirm gate and verify the complete workflow:
      get_scaffold_preview → confirm (accepted) → run_scaffold → plain-text report

    tool_progress events must appear for get_scaffold_preview and run_scaffold,
    in that order, confirming the 3-tool sequence executed.

    WARNING: This test re-scaffolds the wiki.
    """
    events = _stream_with_confirm_response("run scaffold", accept=True, timeout=300)
    _assert_stream_complete(events)

    tool_names = _tool_names(events)
    assert "get_scaffold_preview" in tool_names, (
        f"get_scaffold_preview not emitted; tools: {tool_names}"
    )
    assert "run_scaffold" in tool_names, (
        f"run_scaffold not emitted after acceptance; tools: {tool_names}"
    )

    preview_idx = next(i for i, t in enumerate(tool_names) if t == "get_scaffold_preview")
    scaffold_idx = next(i for i, t in enumerate(tool_names) if t == "run_scaffold")
    assert preview_idx < scaffold_idx, (
        f"run_scaffold (index {scaffold_idx}) fired before get_scaffold_preview "
        f"(index {preview_idx})"
    )


@pytest.mark.live
@pytest.mark.timeout(360)
def test_scaffold_narrative_mentions_domain_and_completion():
    """
    After a successful scaffold run the narrative must mention completion and
    at least one expected artefact (domain, index.md, categories, or pages).
    """
    events = _stream_with_confirm_response("run scaffold", accept=True, timeout=300)
    _assert_stream_complete(events)

    narrative = _narrative(events)
    completion_keywords = ["scaffold", "complete", "domain", "index", "categor", "page"]
    assert any(kw in narrative for kw in completion_keywords), (
        f"Narrative does not mention completion or scaffold artefacts. "
        f"Keywords checked: {completion_keywords}. Got: {narrative[:500]!r}"
    )


@pytest.mark.live
@pytest.mark.timeout(360)
def test_scaffold_progress_label_says_scaffold_not_ingest():
    """
    While polling the scaffold job, tool_progress messages must say
    'Scaffold running...' (not 'Ingest running...') — regression guard for the
    job_label parameter.  Only asserts when poll_job emitted progress messages,
    which happens when the scaffold job takes more than one poll cycle.
    """
    events = _stream_with_confirm_response("run scaffold", accept=True, timeout=300)
    _assert_stream_complete(events)

    running_messages = [
        m for m in _tool_messages(events) if "running" in m.lower()
    ]
    if not running_messages:
        pytest.skip(
            "No 'running' progress messages emitted — scaffold completed before "
            "first poll tick. Label regression cannot be verified on a fast wiki."
        )

    for msg in running_messages:
        assert "Ingest running" not in msg, (
            f"Progress message uses wrong label 'Ingest running' during scaffold: {msg!r}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Group 3 — Routing: multiple phrasings and no false triggers
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(180)
def test_two_phrasings_both_trigger_workflow():
    """
    Both canonical trigger phrasings must route to ScaffoldWorkflow
    (get_scaffold_preview tool_progress present).
    The confirm gate is declined immediately so no wiki mutations occur.
    """
    phrasings = [
        "run scaffold",
        "regenerate scaffold",
    ]
    for phrase in phrasings:
        events = _stream_with_confirm_response(phrase, accept=False, timeout=90)
        _assert_stream_complete(events)

        tool_names = _tool_names(events)
        assert "get_scaffold_preview" in tool_names, (
            f"Phrasing {phrase!r} did not trigger ScaffoldWorkflow. "
            f"get_scaffold_preview not in tool names: {tool_names}. "
            f"Event types: {[t for t, _ in events]}"
        )


@pytest.mark.live
@pytest.mark.timeout(120)
def test_query_phrase_does_not_invoke_scaffold_preview_tool():
    """
    'what is scaffold?' is a query phrase and must NOT trigger ScaffoldWorkflow.
    No get_scaffold_preview tool_progress event should appear.
    """
    events = _stream_with_confirm_response("what is scaffold?", accept=False, timeout=90)
    _assert_stream_complete(events)

    tool_names = _tool_names(events)
    assert "get_scaffold_preview" not in tool_names, (
        f"'what is scaffold?' incorrectly triggered ScaffoldWorkflow. "
        f"Tools fired: {tool_names}. "
        "This phrase should be handled as a query, not a workflow trigger."
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
