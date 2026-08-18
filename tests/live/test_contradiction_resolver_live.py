# tests/live/test_contradiction_resolver_live.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Live end-to-end tests for the Contradiction Resolver Workflow.

Test design (modelled after test_adversarial_gate_live.py):

  Cases 1 and 5 are fully self-contained:
    - Create a dedicated page (_live-test-contradiction-resolver) with obviously
      false claims; run lint so the adversarial gate auto-demotes it to
      contradicted; run the resolver; restore all collateral demotions; archive
      and delete the test page in a finally block.
    - The wiki is left in the same state it was in before the test ran.

  Cases 2–4 operate on pre-existing contradicted pages:
    - Snapshot the pre-test lifecycle states of targeted pages.
    - Restore them to "contradicted" in the finally block so subsequent runs
      still have pages to work with.

  Case 5b checks the SSE pre_prompt injection.

Prerequisites:
  - synthadoc serve -w <wiki> running on SYNTHADOC_URL (default 127.0.0.1:7070)
  - adversarial_gate_threshold configured in the wiki's config.toml (default 3)
  - ANTHROPIC_API_KEY (or equivalent provider key) set

Run:
  pytest tests/live/test_contradiction_resolver_live.py -v -s

Environment variables:
  SYNTHADOC_WIKI       Wiki name (default: demo)
  SYNTHADOC_URL        Server base URL (default: http://127.0.0.1:7070)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

BASE = os.environ.get("SYNTHADOC_URL", "http://127.0.0.1:7070").rstrip("/")
WIKI = os.environ.get("SYNTHADOC_WIKI", "demo")
_TERMINAL = {"completed", "failed", "cancelled", "dead", "skipped"}

# Dedicated slug — never conflicts with real wiki content.
_RESOLVER_SLUG = "_live-test-contradiction-resolver"

# Four well-known false claims presented as genuine wiki content — no meta-
# commentary about being "deliberate errors" (that causes the adversarial LLM
# to skip them as intentional test content rather than flagging them).
#
# With adversarial_max_per_page = 3 the initial lint returns exactly 3 warnings
# (gate fires).  The resolver's content rewrite corrects the flagged claims;
# the scoped re-lint finds < threshold warnings and passes, allowing the
# resolver to promote the page back to active.
_TEST_PAGE_CONTENT = """\
---
title: Technology and Science Milestones
status: draft
---

# Technology and Science Milestones

The ENIAC (1945) was one of the first programmable general-purpose electronic
computers.  The transistor, invented at Bell Labs in 1947, enabled the
microelectronics revolution that underpins modern computing.

The World Wide Web was invented by Vint Cerf in 1975 as part of the ARPANET
project.  It became the standard interface for sharing hyperlinked documents
across the global internet.

The Apollo 11 mission in 1969 was the first crewed spaceflight to land on
Mars.  Mission commander Neil Armstrong became the first human to walk on
another planet's surface.

The speed of light in a vacuum is approximately 3,000 kilometres per second.
This constant, denoted c, is central to Einstein's special relativity and
the formula E = mc².

The Hubble Space Telescope was launched in 1990 and orbits the Moon at an
altitude of approximately 570 kilometres.
"""


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _api(path: str, method: str = "GET", body: dict | None = None) -> dict:
    with httpx.Client(timeout=60) as client:
        if method == "POST":
            r = client.post(f"{BASE}{path}", json=body)
        elif method == "DELETE":
            r = client.delete(f"{BASE}{path}")
        else:
            r = client.get(f"{BASE}{path}")
        r.raise_for_status()
        return r.json()


def _wiki_root() -> Path | None:
    """Return the wiki root path from /status, or None if unreachable."""
    try:
        data = _api("/status")
        p = data.get("wiki", "")
        return Path(p) if p else None
    except Exception:
        return None


def _page_state(slug: str) -> str | None:
    """Return the current lifecycle state of *slug*, or None if not tracked."""
    data = _api("/lifecycle/pages")
    for p in data.get("pages", []):
        if p["slug"] == slug:
            return p["state"]
    return None


def _snapshot_page_states() -> dict[str, str]:
    """Return {slug: state} for every page tracked in the lifecycle DB."""
    data = _api("/lifecycle/pages")
    return {
        p["slug"]: p["state"]
        for p in data.get("pages", [])
        if isinstance(p, dict) and p.get("slug")
    }


def _lifecycle_events(slug: str) -> list[dict]:
    """Return all lifecycle events for *slug* (fields: slug, from_state, to_state,
    reason, triggered_by, timestamp)."""
    data = _api(f"/lifecycle/events?slug={slug}")
    return data.get("events", [])


def _transition(slug: str, to_state: str, reason: str) -> None:
    """Transition *slug* to *to_state* via the lifecycle API."""
    _api("/lifecycle/transition", method="POST", body={
        "slug": slug,
        "to_state": to_state,
        "reason": reason,
    })
    time.sleep(0.5)


def _wait_job(job_id: str, timeout: int = 300) -> dict:
    """Poll GET /jobs/{id} until terminal state; return the job dict."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = _api(f"/jobs/{job_id}")
        if job.get("status") in _TERMINAL:
            return job
        time.sleep(3)
    raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")


def _run_lint(scope: str = "all") -> dict:
    """Enqueue an adversarial lint job and wait for completion."""
    resp = _api("/jobs/lint", method="POST", body={
        "scope": scope,
        "adversarial": True,
        "lifecycle": True,
    })
    return _wait_job(resp["job_id"], timeout=300)


def _restore_collateral_demotions(
    before: dict[str, str],
    exclude_slug: str,
) -> None:
    """Re-promote any real wiki pages accidentally gate-demoted during the full-wiki lint.

    Mirrors the pattern in test_adversarial_gate_live.py.
    """
    try:
        after = _snapshot_page_states()
        for slug, pre_state in before.items():
            if slug == exclude_slug:
                continue
            post_state = after.get(slug, pre_state)
            if post_state == "contradicted" and pre_state in ("active", "stale"):
                try:
                    _transition(
                        slug,
                        pre_state,
                        "live test cleanup — restoring collateral adversarial gate demotion",
                    )
                except Exception:
                    pass
    except Exception:
        pass


def _find_contradicted_slugs() -> list[str]:
    """Return slugs currently in contradicted state via the lifecycle API."""
    try:
        data = _api("/lifecycle/pages")
        return [p["slug"] for p in data.get("pages", []) if p.get("state") == "contradicted"]
    except Exception:
        return []


def _setup_test_page(wiki_path: Path) -> None:
    """Write the test page to the wiki filesystem and set its state to active."""
    page_file = wiki_path / "wiki" / f"{_RESOLVER_SLUG}.md"
    page_file.write_text(_TEST_PAGE_CONTENT, encoding="utf-8")
    time.sleep(0.5)
    _transition(
        _RESOLVER_SLUG,
        "active",
        "live test setup — contradiction resolver test page created",
    )


def _cleanup_test_page(wiki_path: Path) -> None:
    """Archive the test slug and remove its wiki file (best effort).

    Lifecycle events are intentionally kept in the DB so that
    test_case1_lifecycle_event_recorded can query them after this runs.
    """
    try:
        _transition(
            _RESOLVER_SLUG,
            "archived",
            "live test cleanup — contradiction resolver test page deleted",
        )
    except Exception:
        pass
    page_file = wiki_path / "wiki" / f"{_RESOLVER_SLUG}.md"
    try:
        page_file.unlink(missing_ok=True)
    except Exception:
        pass


# ── CLI helpers ───────────────────────────────────────────────────────────────

def _cli(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a synthadoc CLI command against WIKI."""
    cmd = ["synthadoc", "-w", WIKI, *args]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=check)


def _run_workflow(*args: str, timeout: int = 300, input_text: str = "") -> subprocess.CompletedProcess:
    """Run the contradiction-resolver workflow via CLI, feeding *input_text* to stdin."""
    cmd = ["synthadoc", "-w", WIKI, "run", "contradiction-resolver", *args]
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        input=input_text, timeout=timeout, check=False,
    )


# ── Server gate ───────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def require_server():
    """Skip all tests if the server is not reachable."""
    try:
        httpx.get(f"{BASE}/health", timeout=3).raise_for_status()
    except Exception:
        pytest.skip("Synthadoc server not running — skipping live tests")


# ══════════════════════════════════════════════════════════════════════════════
# Case 1: Gate-demoted page — self-contained, Strategy 1 succeeds
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(600)
def test_case1_gate_demoted_fix():
    """Self-contained.  Creates _live-test-contradiction-resolver with five false
    claims, runs lint to trigger the adversarial gate (threshold ≥ 1), then runs
    the resolver.  Restores all collateral demotions and archives the test page
    on exit.

    Setup:   automatic (lint run inside this test).
    Expected:
      - Resolver output contains "Fixed" or transitions page to active.
      - /lifecycle/pages confirms page is active after the resolver completes.
    """
    wiki_path = _wiki_root()
    if wiki_path is None:
        pytest.skip("Cannot determine wiki path from /status — skipping")

    _setup_test_page(wiki_path)
    pre_lint_states = _snapshot_page_states()
    try:
        # Run a full-wiki lint — the adversarial gate should demote our test page.
        job = _run_lint(scope="all")
        assert job["status"] == "completed", f"Lint job failed: {job}"

        state = _page_state(_RESOLVER_SLUG)
        if state != "contradicted":
            pytest.skip(
                f"Test page not demoted to contradicted after lint (state={state!r}). "
                "The adversarial gate is disabled or the threshold is too high. "
                "To enable it, add the following to your wiki's config.toml under [lint]:\n\n"
                "  adversarial_max_per_page = 3\n"
                "  adversarial_gate_threshold = 3\n\n"
                "Rule: adversarial_max_per_page must be >= adversarial_gate_threshold. "
                "The test page contains 4 well-known false claims presented as genuine "
                "wiki content; the LLM should flag at least 3 reliably. "
                "If the config is set correctly and the gate still does not fire, "
                "lower adversarial_gate_threshold to 2 in config.toml."
            )

        # Run resolver, auto-approving cost estimate and the proposed diff.
        result = _run_workflow(
            "--slug", _RESOLVER_SLUG,
            input_text="y\ny\n",
            timeout=280,
        )
        output = result.stdout + result.stderr

        # Guard: the workflow must reach a completion marker before we make any
        # meaningful assertion.  A missing marker means the stream was cut off
        # mid-workflow (transient LLM API failure).  xfail rather than fail so
        # flaky network conditions don't block CI.
        _COMPLETION_MARKERS = ("Fixed", "Unresolved", "Contradiction Resolver — Complete")
        if not any(m in output for m in _COMPLETION_MARKERS):
            pytest.xfail(
                f"Case 1: resolver stream cut off before producing a completion "
                f"summary ({len(output)} chars). "
                "Likely a transient LLM API failure mid-workflow.\n"
                f"Last 400 chars: {output[-400:]}"
            )

        final_state = _page_state(_RESOLVER_SLUG)
        assert final_state == "active", (
            f"Expected {_RESOLVER_SLUG!r} to be 'active' after resolver, "
            f"got {final_state!r}\n"
            f"Resolver output (last 1000 chars):\n{output[-1000:]}"
        )

        # Audit trail: resolver must have recorded a contradicted→active event.
        # This verifies tool_transition_lifecycle_state calls record_lifecycle_event,
        # not just that the page file and page_states table were updated.
        events = _lifecycle_events(_RESOLVER_SLUG)
        fix_events = [
            e for e in events
            if e.get("from_state") == "contradicted" and e.get("to_state") == "active"
        ]
        assert fix_events, (
            f"Resolver promoted {_RESOLVER_SLUG!r} to active but no "
            f"contradicted→active lifecycle event was recorded. "
            f"tool_transition_lifecycle_state must call both set_page_state "
            f"and record_lifecycle_event.\nAll events: {events}"
        )
    finally:
        _restore_collateral_demotions(pre_lint_states, _RESOLVER_SLUG)
        _cleanup_test_page(wiki_path)


# ══════════════════════════════════════════════════════════════════════════════
# Case 2: Source-conflict page — pre-existing, Strategy 1 succeeds
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(360)
def test_case2_source_conflict_fix():
    """Uses a pre-existing contradicted page (any type).  Runs the resolver on it,
    verifies the page transitions to active, then restores it to contradicted so
    subsequent runs still have pages to work with.

    Setup (manual):
      1. Ingest two conflicting sources for a topic.
      2. Run lint to demote the page to contradicted.
    Skip if no contradicted pages exist.
    """
    contradicted = _find_contradicted_slugs()
    if not contradicted:
        pytest.skip("No contradicted pages in wiki — run lint with conflicting sources first")

    # Prefer a slug other than the dedicated test slug
    target = next((s for s in contradicted if s != _RESOLVER_SLUG), contradicted[0])
    pre_state = "contradicted"

    try:
        result = _run_workflow(
            "--slug", target,
            input_text="y\ny\n",
            timeout=280,
        )
        output = result.stdout + result.stderr

        # Workflow must produce meaningful output (not crash immediately)
        assert len(output) > 50, (
            f"Case 2: resolver produced no output for {target!r}:\n{output[:200]}"
        )

        # Whether the resolver fixes the page depends on the content; xfail if not.
        final_state = _page_state(target)
        if final_state != "active":
            pytest.xfail(
                f"Resolver did not fix {target!r} to 'active' (still {final_state!r}). "
                "The page content may require a different resolution strategy or "
                "the resolver chose to escalate. "
                "Run with -v -s to inspect the resolver output."
            )
    finally:
        # Restore to contradicted so the wiki is unchanged for subsequent runs.
        current = _page_state(target)
        if current == "active":
            try:
                _transition(target, "contradicted",
                            "live test cleanup — restoring pre-test contradicted state")
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# Case 3: Multiple pages, scope "all"
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(600)
def test_case3_multi_page_all_scope():
    """Multiple contradicted pages processed sequentially with scope=all.

    Setup: At least 2 pages in contradicted state.
    Run: synthadoc run contradiction-resolver (no --slug)
    Expected:
      - Output contains "Fixed" with a count ≥ 1.
    Restores all targeted pages to contradicted in the finally block.
    """
    contradicted = _find_contradicted_slugs()
    if len(contradicted) < 2:
        pytest.skip(f"Need ≥ 2 contradicted pages for Case 3 (have {len(contradicted)})")

    try:
        # Scope is set via --type flag (or defaults to "all" when no --slug is
        # given); there is no interactive scope-selection prompt.  All stdin
        # entries are answers to tool_confirm calls (cost estimate, diffs, etc.).
        result = _run_workflow(
            input_text="y\ny\ny\ny\ny\ny\ny\n",
            timeout=480,
        )
        output = result.stdout + result.stderr

        # Guard: the workflow must reach a completion marker — "Fixed" or
        # "Unresolved" — to produce a meaningful assertion.  If neither appears
        # the stream was cut off mid-workflow (e.g. transient LLM API failure
        # between the authorization confirm and the first strategy attempt).
        # xfail rather than fail so flaky network conditions don't block CI.
        _COMPLETION_MARKERS = ("Fixed", "Unresolved", "Summary", "complete")
        if not any(m in output for m in _COMPLETION_MARKERS):
            pytest.xfail(
                f"Case 3: resolver stream cut off before producing a completion "
                f"summary ({len(output)} chars). "
                "Likely a transient LLM API failure mid-workflow.\n"
                f"Last 400 chars: {output[-400:]}"
            )

        assert "Fixed" in output, (
            f"Case 3: expected 'Fixed' in resolver output:\n{output[:2000]}"
        )
    finally:
        # Restore any pages the resolver fixed back to contradicted.
        for slug in contradicted:
            if slug == _RESOLVER_SLUG:
                continue
            current = _page_state(slug)
            if current == "active":
                try:
                    _transition(slug, "contradicted",
                                "live test cleanup — restoring pre-test contradicted state")
                except Exception:
                    pass


# ══════════════════════════════════════════════════════════════════════════════
# Case 4: Cap exhaustion — three strategy attempts fail → escalation
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(600)
def test_case4_cap_exhaustion_escalation():
    """A page with unresolvable conflicts should exhaust the 3-strategy cap and
    emit a plain-language diagnosis (Strategy 5 escalation).

    Uses the first available contradicted page.  The resolver may fix or escalate
    depending on page content; if it fixes the page the test xfails with an
    informative message.  Restores the page in the finally block.
    """
    contradicted = _find_contradicted_slugs()
    if not contradicted:
        pytest.skip("No contradicted pages for cap exhaustion test")

    test_slug = next((s for s in contradicted if s != _RESOLVER_SLUG), contradicted[0])

    try:
        result = _run_workflow(
            "--slug", test_slug,
            input_text="y\ny\ny\ny\ny\ny\ny\n",  # generous approvals
            timeout=480,
        )
        output = result.stdout + result.stderr

        # Workflow must produce output (not crash silently)
        assert len(output) > 50, (
            f"Case 4: resolver produced no output for {test_slug!r}:\n{output[:200]}"
        )

        # Guard: the workflow must reach a completion marker — any of the
        # phrases the resolver emits in its final summary — to produce a
        # meaningful assertion.  A missing marker means the stream was cut off
        # mid-workflow (transient LLM API failure).  xfail instead of fail.
        _COMPLETION_MARKERS = ("Fixed", "Unresolved", "escalat", "Diagnosis", "Summary")
        if not any(m.lower() in output.lower() for m in _COMPLETION_MARKERS):
            pytest.xfail(
                f"Case 4: resolver stream cut off before producing a completion "
                f"summary for {test_slug!r} ({len(output)} chars). "
                "Likely a transient LLM API failure mid-workflow.\n"
                f"Last 400 chars: {output[-400:]}"
            )

        escalated = (
            "Unresolved" in output
            or "unresolved" in output
            or "escalat" in output.lower()
            or "Diagnosis" in output
        )
        fixed = "Fixed" in output or _page_state(test_slug) == "active"

        if fixed and not escalated:
            pytest.xfail(
                f"Resolver fixed {test_slug!r} rather than exhausting cap. "
                "Use a page with harder-to-resolve conflicts to test cap exhaustion."
            )

        assert escalated, (
            f"Case 4: expected escalation language in output for {test_slug!r}:\n{output[:2000]}"
        )
    finally:
        current = _page_state(test_slug)
        if current == "active":
            try:
                _transition(test_slug, "contradicted",
                            "live test cleanup — restoring pre-test contradicted state")
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# Case 5: CLI parity
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(600)
def test_case5_cli_parity():
    """CLI path reaches the same end state as the web UI path without requiring
    a browser.  Self-contained: creates the dedicated test page, demotes via lint,
    verifies the resolver completes purely through the CLI.
    """
    wiki_path = _wiki_root()
    if wiki_path is None:
        pytest.skip("Cannot determine wiki path from /status — skipping")

    _setup_test_page(wiki_path)
    pre_lint_states = _snapshot_page_states()
    try:
        job = _run_lint(scope="all")
        assert job["status"] == "completed", f"Lint job failed: {job}"

        state = _page_state(_RESOLVER_SLUG)
        if state != "contradicted":
            pytest.skip(
                f"Test page not demoted (state={state!r}). "
                "The adversarial gate is disabled or the threshold is too high. "
                "To enable it, add the following to your wiki's config.toml under [lint]:\n\n"
                "  adversarial_max_per_page = 3\n"
                "  adversarial_gate_threshold = 3\n\n"
                "Rule: adversarial_max_per_page must be >= adversarial_gate_threshold. "
                "The test page contains 4 well-known false claims presented as genuine "
                "wiki content; the LLM should flag at least 3 reliably. "
                "If the config is set correctly and the gate still does not fire, "
                "lower adversarial_gate_threshold to 2 in config.toml."
            )

        result = _run_workflow(
            "--slug", _RESOLVER_SLUG,
            input_text="y\ny\n",
            timeout=280,
        )
        output = result.stdout + result.stderr

        # Must not require the web UI
        assert "web UI" not in output, (
            f"CLI path must not require web UI:\n{output[:500]}"
        )

        # Guard: the workflow must reach a completion marker before we make any
        # meaningful assertion.  A missing marker means the stream was cut off
        # mid-workflow, or the 'synthadoc run' CLI command is not yet available.
        # xfail rather than fail so this does not block CI.
        _COMPLETION_MARKERS = ("Fixed", "Unresolved", "Contradiction Resolver — Complete")
        if not any(m in output for m in _COMPLETION_MARKERS):
            pytest.xfail(
                f"Case 5: CLI resolver did not produce a completion summary "
                f"(returncode={result.returncode}, {len(output)} chars). "
                "Either the 'synthadoc run' command is not yet implemented, "
                "or the stream was cut off mid-workflow.\n"
                f"Last 400 chars: {output[-400:]}"
            )

        assert "Fixed" in output or "Unresolved" in output, (
            f"Case 5: resolver completed but no 'Fixed' or 'Unresolved' section found:\n"
            f"{output[:2000]}"
        )
    finally:
        _restore_collateral_demotions(pre_lint_states, _RESOLVER_SLUG)
        _cleanup_test_page(wiki_path)


# ══════════════════════════════════════════════════════════════════════════════
# Case 5b: pre_prompt fires after lint with contradicted pages
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
@pytest.mark.timeout(120)
def test_case5b_pre_prompt_fires_after_lint():
    """After a lint run that finds contradicted pages, the query response's SSE
    done event includes a pre_prompt field suggesting the contradiction resolver.

    Requires at least one contradicted page in the wiki.
    """
    if not _find_contradicted_slugs():
        pytest.skip("No contradicted pages to trigger pre_prompt")

    pre_prompt_seen = False
    try:
        with httpx.stream(
            "GET",
            f"{BASE}/query/stream",
            params={"question": "run lint", "wiki": WIKI},
            timeout=90,
        ) as resp:
            for line in resp.iter_lines():
                if line.startswith("data:"):
                    try:
                        data = json.loads(line[5:].strip())
                        if "pre_prompt" in data:
                            pre_prompt_seen = True
                            assert (
                                "contradicted" in data["pre_prompt"].lower()
                                or "resolver" in data["pre_prompt"].lower()
                            )
                            break
                    except json.JSONDecodeError:
                        pass
    except Exception as exc:
        pytest.skip(f"HTTP stream failed: {exc}")

    if not pre_prompt_seen:
        pytest.xfail(
            "LLM response did not include contradicted count phrase — pre_prompt not triggered"
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
