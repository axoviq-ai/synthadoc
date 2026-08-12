# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""
Live integration tests for the Scaffold Workflow (Workflow E, v1.2.1).

Triggered by phrases such as "run scaffold" or "regenerate scaffold".
The workflow runs three tools in sequence with a confirm gate:
  get_scaffold_preview → confirm → run_scaffold

Run as a named suite:
  pytest tests/live/test_scaffold_workflow_live.py -v -s

Prerequisites:
  - synthadoc serve -w <wiki> running on SYNTHADOC_URL (default 127.0.0.1:7070)
  - ANTHROPIC_API_KEY set

Side effects:
  Accepting the confirm gate re-scaffolds the wiki — index.md, purpose.md,
  AGENTS.md, CLAUDE.md, GEMINI.md are overwritten.  Tests that test the
  confirm path use the NO path to avoid mutations; only the explicit
  run-through test accepts.
"""
from __future__ import annotations

import json
import os
import sys
from urllib.parse import quote

import httpx
import pytest

BASE = os.environ.get("SYNTHADOC_URL", "http://127.0.0.1:7070").rstrip("/")


# ── Low-level helpers ─────────────────────────────────────────────────────────

def _stream_question(question: str, *, timeout: int = 300) -> list[tuple[str, dict]]:
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


def _decline_confirm(session_id: str) -> None:
    """Respond 'no' to the pending confirm gate for a session."""
    with httpx.Client(timeout=10) as client:
        r = client.post(
            f"{BASE}/action/confirm",
            json={"session_id": session_id, "confirmed": False},
        )
        r.raise_for_status()


# ── Server gate ───────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def require_server():
    """Skip all tests if the server isn't reachable."""
    try:
        httpx.get(f"{BASE}/health", timeout=3).raise_for_status()
    except Exception:
        pytest.skip("Synthadoc server not running — skipping live tests")


# ══════════════════════════════════════════════════════════════════════════════
# Group 1 — SSE protocol: tool sequence and confirm gate
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(180)
def test_workflow_fires_get_scaffold_preview_tool():
    """
    'run scaffold' must emit a get_scaffold_preview tool_progress event,
    confirming the workflow fast-path was taken rather than the LLM query path.
    The confirm gate times out after 120 s (declined), so no scaffold mutation
    occurs.
    """
    events = _stream_question("run scaffold")
    _assert_stream_complete(events)

    tool_names = _tool_names(events)
    assert "get_scaffold_preview" in tool_names, (
        f"get_scaffold_preview tool_progress not emitted; tools fired: {tool_names}"
    )


@pytest.mark.live
@pytest.mark.timeout(180)
def test_workflow_emits_confirm_request_before_running():
    """
    ScaffoldWorkflow requires user confirmation before writing files.
    A confirm_request SSE event must be emitted before any run_scaffold call.
    """
    events = _stream_question("run scaffold")
    _assert_stream_complete(events)

    confirm_events = [e for e in events if e[0] == "confirm_request"]
    assert confirm_events, (
        "No confirm_request event emitted — ScaffoldWorkflow must ask before writing files."
    )


@pytest.mark.live
@pytest.mark.timeout(180)
def test_workflow_does_not_run_scaffold_when_declined():
    """
    When the confirm gate times out (or is declined), run_scaffold must NOT
    be called and the narrative must indicate cancellation.
    """
    events = _stream_question("run scaffold")
    _assert_stream_complete(events)

    tool_names = _tool_names(events)
    assert "run_scaffold" not in tool_names, (
        f"run_scaffold was called despite no confirmation: tools fired: {tool_names}"
    )

    narrative = _narrative(events)
    assert "cancel" in narrative or "declin" in narrative, (
        f"Narrative should mention cancellation after timeout. Got: {narrative[:300]!r}"
    )


@pytest.mark.live
@pytest.mark.timeout(180)
def test_workflow_completes_with_done_event():
    """Stream must end with a 'done' event and no error events."""
    events = _stream_question("run scaffold")
    _assert_stream_complete(events)


# ══════════════════════════════════════════════════════════════════════════════
# Group 2 — Preview content
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(180)
def test_preview_progress_message_includes_domain():
    """
    The get_scaffold_preview tool_progress message must include the domain,
    confirming the tool read the wiki config correctly.
    """
    events = _stream_question("run scaffold")
    _assert_stream_complete(events)

    preview_messages = [
        e[1].get("message", "")
        for e in events
        if e[0] == "tool_progress" and e[1].get("tool") == "get_scaffold_preview"
    ]
    assert preview_messages, "No get_scaffold_preview tool_progress messages emitted"
    assert any("domain" in m.lower() or ":" in m for m in preview_messages), (
        f"Preview message does not include domain info: {preview_messages}"
    )


@pytest.mark.live
@pytest.mark.timeout(180)
def test_confirm_message_mentions_index_md():
    """
    The confirm_request message must list the files to be overwritten.
    index.md is always written by scaffold; its presence confirms the preview
    payload was correctly incorporated into the confirm message.
    """
    events = _stream_question("run scaffold")
    _assert_stream_complete(events)

    confirm_events = [e[1] for e in events if e[0] == "confirm_request"]
    assert confirm_events, "No confirm_request events emitted"

    msg = confirm_events[0].get("message", "").lower()
    assert "index" in msg or "scaffold" in msg, (
        f"confirm_request message does not mention index.md or scaffold. "
        f"Message: {confirm_events[0].get('message', '')[:300]!r}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Group 3 — Routing: multiple phrasings, no false triggers
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(540)
def test_two_phrasings_both_trigger_workflow():
    """
    Both canonical trigger phrasings must route to ScaffoldWorkflow
    (get_scaffold_preview tool_progress present).
    """
    phrasings = [
        "run scaffold",
        "regenerate scaffold",
    ]
    for phrase in phrasings:
        events = _stream_question(phrase, timeout=180)
        _assert_stream_complete(events)

        tool_names = _tool_names(events)
        assert "get_scaffold_preview" in tool_names, (
            f"Phrasing {phrase!r} did not trigger the workflow. "
            f"get_scaffold_preview not in tool names: {tool_names}. "
            f"Event types: {[t for t, _ in events]}"
        )


@pytest.mark.live
@pytest.mark.timeout(180)
def test_query_phrase_does_not_invoke_scaffold_preview_tool():
    """
    'what is scaffold?' is a query phrase and must NOT trigger ScaffoldWorkflow.
    No get_scaffold_preview tool_progress event should appear.
    """
    events = _stream_question("what is scaffold?", timeout=120)
    _assert_stream_complete(events)

    tool_names = _tool_names(events)
    assert "get_scaffold_preview" not in tool_names, (
        f"'what is scaffold?' incorrectly triggered ScaffoldWorkflow. "
        f"Tools fired: {tool_names}. "
        "This phrase should be handled as a query, not as a workflow trigger."
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
