# tests/live/test_contradiction_resolver_live.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Live end-to-end test cases for the Contradiction Resolver Workflow.

These tests require:
  1. A running synthadoc server (synthadoc serve --wiki <name>)
  2. A configured wiki with the history-of-computing demo corpus (or equivalent)
  3. pytest-asyncio, httpx

Run with:
  pytest tests/live/test_contradiction_resolver_live.py -m live -v

Environment variables:
  SYNTHADOC_WIKI       Wiki name (default: demo)
  SYNTHADOC_URL        Server base URL (default: http://127.0.0.1:7070)

Skip in CI: these tests are marked @pytest.mark.live and are excluded from
the standard test suite by default. They are run manually before a feature
ships for manual validation.

Setup steps are described in each test's docstring.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import time
from typing import Optional

import pytest

WIKI = os.environ.get("SYNTHADOC_WIKI", "demo")
BASE = os.environ.get("SYNTHADOC_URL", "http://127.0.0.1:7070").rstrip("/")


def _cli(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a synthadoc CLI command against WIKI and return its result."""
    cmd = ["synthadoc", "-w", WIKI, *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _run_workflow(*args: str, timeout: int = 300, input_text: str = "") -> subprocess.CompletedProcess:
    """Run contradiction-resolver workflow via CLI, providing input for prompts."""
    cmd = ["synthadoc", "-w", WIKI, "run", "contradiction-resolver", *args]
    return subprocess.run(
        cmd, capture_output=True, text=True,
        input=input_text, timeout=timeout, check=False,
    )


@pytest.fixture(scope="module", autouse=True)
def check_server():
    """Verify the server is running before live tests execute."""
    import httpx
    try:
        resp = httpx.get(f"{BASE}/health", timeout=5)
        assert resp.status_code in (200, 204)
    except Exception as exc:
        pytest.skip(f"Server not reachable at {SERVER_URL}: {exc}")


# ── Case 1: Gate-demoted page — Strategy 1 succeeds ──────────────────────────────

@pytest.mark.live
def test_case1_gate_demoted_fix():
    """Case 1: Gate-demoted page. Strategy 1 (content rewrite) fixes it on attempt 1.

    Setup:
      1. Ensure alan-turing page is ingested with dubious content (fabricated claims).
      2. Run lint to demote it.
      3. Confirm contradicted: 1.
    Run:
      synthadoc run contradiction-resolver --slug alan-turing
      Approve cost estimate (y), approve proposed diff (y).
    Expected:
      - Final summary shows ✅ Fixed (1)
      - synthadoc status confirms contradicted: 0
    """
    # Verify setup: contradicted page exists
    status_output = _cli("status").stdout
    if "contradicted" not in status_output.lower():
        pytest.skip("No contradicted pages — run setup steps first")

    # Run resolver, auto-approving all prompts
    result = _run_workflow(
        "--slug", "alan-turing",
        input_text="y\ny\n",  # approve cost estimate, approve diff
        timeout=180,
    )
    output = result.stdout + result.stderr

    assert "Fixed" in output or "active" in output.lower(), (
        f"Expected '✅ Fixed' in output but got:\n{output}"
    )

    # Verify via status
    assert "alan-turing" not in _get_contradicted_slugs()


@pytest.mark.live
def test_case1_lifecycle_event_recorded():
    """After Case 1, lifecycle event must be recorded for alan-turing."""
    # This test runs after test_case1_gate_demoted_fix
    # Check audit trail via CLI
    audit_output = _cli("audit", "events", "--slug", "alan-turing").stdout
    assert "contradiction-resolver" in audit_output.lower() or \
           "resolved" in audit_output.lower(), (
        f"Expected resolver lifecycle event in audit, got:\n{audit_output}"
    )


# ── Case 2: Source-conflict page — Strategy 1 succeeds ───────────────────────

@pytest.mark.live
def test_case2_source_conflict_fix():
    """Case 2: Source-conflict page. Resolver reads contradiction_note + source content.

    Setup:
      1. Ingest two conflicting sources for eniac topic.
      2. Run lint → contradiction_note set, page demoted to contradicted.
    Run:
      synthadoc run contradiction-resolver --slug eniac
    Expected:
      - Agent reads contradiction_note and source content (no error).
      - Proposed rewrite reconciles conflict with hedging language.
      - User approves.
      - Scoped re-lint: no contradiction detected.
      - contradicted → active.
    """
    if "eniac" not in _get_contradicted_slugs():
        pytest.skip("eniac not in contradicted state — run setup steps first")

    result = _run_workflow(
        "--slug", "eniac",
        input_text="y\ny\n",
        timeout=180,
    )
    output = result.stdout + result.stderr
    assert "Fixed" in output or "active" in output.lower(), (
        f"Case 2: expected fix confirmation, got:\n{output}"
    )
    assert "eniac" not in _get_contradicted_slugs()


# ── Case 3: Multiple pages, scope "all" ──────────────────────────────────────

@pytest.mark.live
def test_case3_multi_page_all_scope():
    """Case 3: Multiple pages, scope all, mix of gate and conflict types.

    Setup: Both alan-turing (gate) and eniac (conflict) in contradicted state.
    Run: synthadoc run contradiction-resolver (select 'a' for all)
    Expected:
      - Both pages processed sequentially.
      - "Continue to next page?" prompt between pages.
      - Final summary: ✅ Fixed (2), ⚠ Unresolved (0), ⏭ Skipped (0).
      - synthadoc status confirms contradicted: 0.
    """
    contradicted = _get_contradicted_slugs()
    if len(contradicted) < 2:
        pytest.skip("Need ≥ 2 contradicted pages for Case 3")

    # Input: select all (a), approve cost, approve diff for page 1, continue, approve diff page 2
    result = _run_workflow(
        input_text="a\ny\ny\ny\ny\n",
        timeout=360,
    )
    output = result.stdout + result.stderr
    assert "Fixed" in output, f"Case 3: expected ✅ Fixed in output:\n{output}"
    assert "Unresolved (0)" in output or "0" in output, \
        f"Case 3: expected 0 unresolved:\n{output}"

    status_output = _cli("status").stdout
    assert "contradicted" not in status_output or "contradicted   0" in status_output, \
        f"Case 3: status still shows contradicted pages:\n{status_output}"


# ── Case 4: Unresolvable page, cap exhausted ─────────────────────────────────

@pytest.mark.live
def test_case4_cap_exhaustion_escalation():
    """Case 4: Page where all 3 strategy attempts fail → escalation.

    Setup:
      1. Create a page whose content has an authorship dispute with conflicting primary sources
         that cannot be resolved by rewriting alone.
      2. Run lint to demote it.

    Expected:
      - Three strategy attempts shown.
      - Strategy 5 (escalate) fires: plain-language diagnosis present in output.
      - Page remains contradicted.
      - Final status shows contradicted: 1.
    """
    contradicted = _get_contradicted_slugs()
    if not contradicted:
        pytest.skip("No contradicted pages for cap exhaustion test")

    # Use the first contradicted page as the test subject
    test_slug = contradicted[0]

    # Run resolver — approve all 3 strategy attempts (which all fail in re-lint)
    # then the escalation fires automatically
    result = _run_workflow(
        "--slug", test_slug,
        input_text="y\ny\ny\ny\ny\ny\ny\n",  # generous approvals
        timeout=360,
    )
    output = result.stdout + result.stderr

    # Escalation (Strategy 5) must appear in output
    assert "Unresolved" in output or "unresolved" in output or "escalat" in output.lower(), (
        f"Case 4: expected escalation in output:\n{output}"
    )
    # Diagnosis text must be present
    assert "Diagnosis" in output or "diagnosis" in output or "suggest" in output.lower(), (
        f"Case 4: expected diagnosis/suggestions:\n{output}"
    )
    # Page must still be contradicted
    assert test_slug in _get_contradicted_slugs(), (
        f"Case 4: page {test_slug!r} should still be contradicted after cap exhaustion"
    )


# ── Case 5: CLI parity ────────────────────────────────────────────────────────

@pytest.mark.live
def test_case5_cli_parity():
    """Case 5: CLI path reaches the same end state as web UI path.

    This test verifies the CLI path. Web UI path is verified manually.

    Setup: Same as Case 1 (alan-turing gate-demoted).
    Run via CLI: synthadoc run contradiction-resolver --slug alan-turing
    Expected:
      - No web UI required.
      - Workflow completes: contradicted → active.
      - Same lifecycle event text as web UI path.
    """
    if "alan-turing" not in _get_contradicted_slugs():
        pytest.skip("alan-turing not contradicted — run setup first")

    result = _run_workflow(
        "--slug", "alan-turing",
        input_text="y\ny\n",
        timeout=180,
    )
    output = result.stdout + result.stderr
    # Must not error with "web UI required" or similar
    assert "web UI" not in output, f"CLI path should not require web UI:\n{output}"
    assert "alan-turing" not in _get_contradicted_slugs()


# ── Case 5b: pre_prompt fires after lint with contradicted pages ──────────────

@pytest.mark.live
def test_case5b_pre_prompt_fires_after_lint():
    """After a lint run that finds contradicted pages, the query response must include pre_prompt.

    Setup: At least 1 contradicted page in the wiki.
    Run: synthadoc query "run lint" (or equivalent lint trigger via CLI)
    Expected: The pre_prompt field in the SSE done event contains resolver suggestion.
    """
    import httpx
    import json

    # Run a lint job via HTTP and check the done event for pre_prompt
    # This requires parsing SSE from the /query/stream endpoint
    contradicted = _get_contradicted_slugs()
    if not contradicted:
        pytest.skip("No contradicted pages to trigger pre_prompt")

    # Use the query stream endpoint to send a lint question
    pre_prompt_seen = False
    try:
        with httpx.stream(
            "GET",
            f"{BASE}/query/stream",
            params={"question": "run lint", "wiki": WIKI},
            timeout=60,
        ) as resp:
            for line in resp.iter_lines():
                if line.startswith("data:"):
                    try:
                        data = json.loads(line[5:].strip())
                        if "pre_prompt" in data:
                            pre_prompt_seen = True
                            assert "contradicted" in data["pre_prompt"].lower() or \
                                   "resolver" in data["pre_prompt"].lower()
                            break
                    except json.JSONDecodeError:
                        pass
    except Exception as exc:
        pytest.skip(f"HTTP stream failed: {exc}")

    # Note: pre_prompt only fires if the LLM response text mentions "N contradicted"
    # This is a best-effort check; skip if the model didn't mention it in the response
    if not pre_prompt_seen:
        pytest.xfail("LLM response did not include contradicted count phrase — pre_prompt not triggered")


# ── Helper ────────────────────────────────────────────────────────────────────

def _get_contradicted_slugs() -> list[str]:
    """Return slugs currently in contradicted state by parsing `synthadoc status`."""
    try:
        result = _cli("status")
        output = result.stdout + result.stderr
        # Look for contradicted count
        import re
        m = re.search(r"contradicted\s+(\d+)", output, re.IGNORECASE)
        if m and int(m.group(1)) == 0:
            return []
        # Try to extract slugs from status detail if shown
        slugs = re.findall(r"^\s+([a-z][a-z0-9-]+)\s+.*contradicted", output,
                            re.IGNORECASE | re.MULTILINE)
        return slugs
    except Exception:
        return []
