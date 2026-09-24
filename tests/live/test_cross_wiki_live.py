# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""
Cross-wiki live integration tests.

Run with:
    pytest tests/live/test_cross_wiki_live.py -v -s --timeout=120

Requires: synthadoc installed in PATH and an LLM provider configured.
Creates two real wikis, starts servers, queries across them, tears down.

Skipped automatically in CI unless SYNTHADOC_LIVE_TESTS=1 is set.
"""
from __future__ import annotations

import os
import time
import shutil
import tempfile
import subprocess
from pathlib import Path

import sys

import httpx
import pytest

# Suppress console popup windows on Windows when spawning background processes.
_POPEN_HIDDEN: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
if sys.platform == "win32":
    _POPEN_HIDDEN["creationflags"] = subprocess.CREATE_NO_WINDOW

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("SYNTHADOC_LIVE_TESTS") != "1",
        reason="Set SYNTHADOC_LIVE_TESTS=1 to run live cross-wiki tests",
    ),
    # Fixture spins up real servers and waits for async LLM ingest; 600 s gives
    # enough headroom for the full setup even on a slow machine.
    pytest.mark.timeout(600),
]

_COORDINATOR_PORT = 17070
_TARGET_PORT = 17071
_WAIT_SECS = 30  # max seconds to wait for server ready


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def live_wikis(tmp_path_factory):
    """Create two wikis, seed content, start servers, yield, tear down."""
    base = tmp_path_factory.mktemp("live_cross_wiki")
    coord_dir = base / "coordinator-wiki"
    target_dir = base / "target-wiki"

    # Pre-flight: remove any stale registrations from a previous crashed run.
    # `synthadoc uninstall` requires interactive confirmation so we edit the
    # registry JSON directly instead.
    import json as _json
    _registry_path = Path.home() / ".synthadoc" / "wikis.json"
    for _name in ("live-coord", "live-target"):
        subprocess.run(["synthadoc", "stop", "-w", _name], capture_output=True)
    if _registry_path.exists():
        _reg = _json.loads(_registry_path.read_text(encoding="utf-8"))
        changed = False
        for _name in ("live-coord", "live-target"):
            if _name in _reg:
                del _reg[_name]
                changed = True
        if changed:
            _registry_path.write_text(_json.dumps(_reg, indent=2), encoding="utf-8")

    _run(["synthadoc", "install", "live-coord", "--target", str(coord_dir),
          "--port", str(_COORDINATOR_PORT), "--domain", "Finance and Corporate Strategy"])
    _run(["synthadoc", "install", "live-target", "--target", str(target_dir),
          "--port", str(_TARGET_PORT), "--domain", "Software Engineering and DevOps"])

    # Clear purpose.md on both wikis so the ingest agent skips the LLM scope
    # check entirely.  This test is about cross-wiki query routing, not scope
    # filtering; an LLM scope check on controlled test pages introduces
    # non-deterministic failures where all pages are silently rejected, leaving
    # no ACTIVE pages for queries to find.
    for _wiki_dir, _name in (
        (coord_dir / "live-coord", "live-coord"),
        (target_dir / "live-target", "live-target"),
    ):
        (_wiki_dir / "wiki" / "purpose.md").write_text("", encoding="utf-8")

    # Patch config.toml to use opencode — the install default is gemini which
    # requires GEMINI_API_KEY; opencode needs no separate key.
    for _wiki_dir in (coord_dir / "live-coord", target_dir / "live-target"):
        _cfg_path = _wiki_dir / ".synthadoc" / "config.toml"
        _cfg_text = _cfg_path.read_text(encoding="utf-8")
        _cfg_text = _cfg_text.replace(
            'default = { provider = "gemini", model = "gemini-2.5-flash-lite" }',
            'default = { provider = "opencode", model = "opencode/big-pickle" }',
        )
        _cfg_path.write_text(_cfg_text, encoding="utf-8")

    # Seed content — coordinator: finance domain
    _write_page(coord_dir, "leverage", (
        "Leverage\n\n"
        "Leverage is the ratio of debt to equity in a capital structure. "
        "High leverage amplifies returns but also increases financial risk. "
        "In corporate finance, the leverage ratio measures how much of a company's "
        "capital comes from debt versus equity.\n\n"
        "Formula: Leverage Ratio = Total Debt / Total Equity\n\n"
        "A leverage ratio above 2x is considered high; below 1x is conservative."
    ))
    _write_page(coord_dir, "ebitda", (
        "EBITDA and M&A Valuation Multiples\n\n"
        "EBITDA stands for Earnings Before Interest, Taxes, Depreciation, and Amortisation. "
        "It is the primary metric used to value companies in mergers and acquisitions (M&A). "
        "Analysts apply an EBITDA multiple to estimate enterprise value.\n\n"
        "Typical EBITDA multiples in M&A range from 6x to 12x depending on sector and growth rate. "
        "Technology companies often trade at 10x–15x EBITDA; industrials at 5x–8x EBITDA.\n\n"
        "Example: a company with $10M EBITDA at an 8x multiple has an enterprise value of $80M."
    ))

    # Seed content — target: operations domain
    _write_page(target_dir, "deployment-runbook", (
        "Kubernetes Deployment Runbook\n\n"
        "This runbook covers deploying and rolling back applications on Kubernetes.\n\n"
        "## Deploy\n"
        "To deploy the application to Kubernetes: (1) run `make build` to build the Docker image, "
        "(2) push the Docker image to the registry, (3) run `kubectl apply -f k8s/` to apply the "
        "Kubernetes manifests.\n\n"
        "## Rollback a Kubernetes Deployment\n"
        "To roll back a Kubernetes deployment to the previous revision:\n"
        "  kubectl rollout undo deployment/app\n\n"
        "To roll back to a specific Kubernetes revision:\n"
        "  kubectl rollout undo deployment/app --to-revision=2\n\n"
        "To check Kubernetes rollout status: kubectl rollout status deployment/app"
    ))
    _write_page(target_dir, "incident-response", (
        "Incident Response\n\n"
        "Severity levels: P1 (complete outage), P2 (degraded service), P3 (minor issue). "
        "P1 incidents require a response within 15 minutes. "
        "P2 incidents require acknowledgement within 1 hour.\n\n"
        "Escalation: page the on-call engineer via PagerDuty for P1 and P2."
    ))

    # Start servers in foreground (no --background) so we own the process
    # directly — no grandchild pythonw.exe chain, no cmd.exe popup windows.
    # Same pattern as live_template_install_test.py.
    coord_proc = subprocess.Popen(
        [sys.executable, "-m", "synthadoc", "serve", "-w", "live-coord"],
        **_POPEN_HIDDEN,
    )
    # Use a mutable list so test_cross_wiki_offline_degradation can swap the
    # reference when it terminates and restarts the target server.
    target_proc_holder = [subprocess.Popen(
        [sys.executable, "-m", "synthadoc", "serve", "-w", "live-target"],
        **_POPEN_HIDDEN,
    )]

    _wait_for_server(_COORDINATOR_PORT)
    _wait_for_server(_TARGET_PORT)

    # Ingest pages now that servers are up.  Capture job IDs so we can poll
    # each job to terminal state rather than blindly polling /retrieve (which
    # stays empty if jobs fail and never tells us why).
    coord_job_ids = _ingest_directory(coord_dir / "wiki", "live-coord")
    target_job_ids = _ingest_directory(target_dir / "wiki", "live-target")

    # Block until every ingest job reaches a terminal state.  A FAILED or DEAD
    # job raises immediately with the server-side error message so the test
    # output shows the root cause instead of a 300s timeout.
    _wait_for_jobs(_COORDINATOR_PORT, coord_job_ids, timeout=300)
    _wait_for_jobs(_TARGET_PORT, target_job_ids, timeout=300)

    # Ingest agent creates pages as DRAFT; /retrieve only returns ACTIVE pages.
    # Promote every DRAFT page on both wikis so cross-wiki queries can find them.
    _activate_draft_pages(_COORDINATOR_PORT)
    _activate_draft_pages(_TARGET_PORT)

    # Guard: if no ACTIVE pages exist after activation, the ingest silently
    # produced nothing (e.g. scope-rejected despite cleared purpose.md).
    # Fail now with a clear message rather than getting knowledge_gap failures.
    _assert_active_pages(_COORDINATOR_PORT, min_count=1, label="live-coord")
    _assert_active_pages(_TARGET_PORT, min_count=1, label="live-target")

    yield {
        "coord_dir": coord_dir,
        "target_dir": target_dir,
        "_target_proc": target_proc_holder,
    }

    # Teardown — terminate server processes then clean registry.
    for proc in (coord_proc, target_proc_holder[0]):
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    if _registry_path.exists():
        _reg = _json.loads(_registry_path.read_text(encoding="utf-8"))
        for _name in ("live-coord", "live-target"):
            _reg.pop(_name, None)
        _registry_path.write_text(_json.dumps(_reg, indent=2), encoding="utf-8")


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_cross_wiki_both_domains_answered(live_wikis):
    """Query requiring both finance and ops domains → both wikis cited."""
    result = _query_cross_wiki("What is the leverage ratio and how do I deploy the application?")
    assert result["knowledge_gap"] is False
    citations = result["citations"]
    wiki_names = {c.split("::")[0] for c in citations if "::" in c}
    assert "live-coord" in wiki_names or "leverage" in result["answer"].lower()
    assert "live-target" in wiki_names or "deploy" in result["answer"].lower()

def test_cross_wiki_target_only_found(live_wikis):
    """Query whose answer only exists in target wiki → still found via cross-wiki."""
    result = _query_cross_wiki("How do I roll back a Kubernetes deployment?")
    assert result["knowledge_gap"] is False
    assert "rollback" in result["answer"].lower() or "kubectl" in result["answer"].lower()

def test_cross_wiki_coordinator_only_found(live_wikis):
    """Query whose answer only exists in coordinator wiki → still found."""
    result = _query_cross_wiki("What are typical EBITDA multiples in M&A?")
    assert result["knowledge_gap"] is False
    assert "ebitda" in result["answer"].lower() or "multiple" in result["answer"].lower()

def test_cross_wiki_offline_degradation(live_wikis):
    """Stop target wiki → query returns degradation response, offline list non-empty."""
    target_proc_holder = live_wikis["_target_proc"]
    target_proc_holder[0].terminate()
    try:
        target_proc_holder[0].wait(timeout=5)
    except subprocess.TimeoutExpired:
        target_proc_holder[0].kill()
    try:
        result = _query_cross_wiki("How do I deploy?")
        assert "live-target" in result.get("cross_wiki_offline", [])
    finally:
        # Restart target for subsequent tests; update holder so teardown
        # terminates the new process.
        new_proc = subprocess.Popen(
            [sys.executable, "-m", "synthadoc", "serve", "-w", "live-target"],
            **_POPEN_HIDDEN,
        )
        target_proc_holder[0] = new_proc
        _wait_for_server(_TARGET_PORT)

def test_serve_all_and_status_all(live_wikis, tmp_path_factory):
    """synthadoc status --all shows both wikis running."""
    out = subprocess.check_output(
        ["synthadoc", "status", "--all"], text=True
    )
    assert "live-coord" in out
    assert "live-target" in out
    assert "running" in out.lower()

def test_operation_cross_wiki_skipped(live_wikis):
    """Running an operation with --cross-wiki returns cross_wiki_skipped=True."""
    result = _query_cross_wiki("run lint")
    # May or may not be skipped depending on ActionAgent, but should not error
    assert "answer" in result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _write_page(wiki_dir: Path, slug: str, content: str) -> None:
    page_dir = wiki_dir / "wiki"
    page_dir.mkdir(parents=True, exist_ok=True)
    (page_dir / f"{slug}.md").write_text(content, encoding="utf-8")


def _ingest_directory(wiki_dir: Path, wiki_name: str) -> list[str]:
    """Enqueue batch ingest for a directory; return the list of job IDs."""
    result = subprocess.run(
        ["synthadoc", "ingest", str(wiki_dir), "-w", wiki_name, "--batch"],
        capture_output=True, text=True, check=True, encoding="utf-8",
    )
    job_ids = []
    for line in result.stdout.splitlines():
        if "-> job " in line:
            job_id = line.split("-> job ")[-1].strip()
            if job_id:
                job_ids.append(job_id)
    return job_ids


def _wait_for_jobs(port: int, job_ids: list[str], timeout: int = 300) -> None:
    """Poll /jobs/<id> for each job until all reach a terminal state.

    Raises RuntimeError immediately if any job is FAILED or DEAD (surfaces the
    server-side error message).  Raises TimeoutError if the deadline expires
    before all jobs complete.
    """
    if not job_ids:
        return
    from synthadoc.core.queue import JobStatus
    deadline = time.time() + timeout
    pending = list(job_ids)
    while pending and time.time() < deadline:
        still_pending = []
        for job_id in pending:
            try:
                resp = httpx.get(
                    f"http://127.0.0.1:{port}/jobs/{job_id}",
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    try:
                        status = JobStatus(data.get("status", ""))
                    except ValueError:
                        status = None
                    if status is not None and status.is_terminal:
                        if status in (JobStatus.FAILED, JobStatus.DEAD):
                            err = data.get("error") or ""
                            raise RuntimeError(
                                f"Ingest job {job_id[:8]} on port {port} "
                                f"reached {status.value}: {err[:400]}"
                            )
                        continue  # COMPLETED, SKIPPED, or CANCELLED
                still_pending.append(job_id)
            except RuntimeError:
                raise
            except Exception:
                still_pending.append(job_id)
        pending = still_pending
        if pending:
            time.sleep(3)
    if pending:
        raise TimeoutError(
            f"{len(pending)} ingest job(s) on port {port} did not reach "
            f"terminal state within {timeout}s"
        )


def _assert_active_pages(port: int, min_count: int = 1, label: str = "") -> None:
    """Raise if fewer than min_count ACTIVE pages exist on the wiki at port."""
    resp = httpx.get(f"http://127.0.0.1:{port}/lifecycle/pages", timeout=10.0)
    resp.raise_for_status()
    active = [p for p in resp.json().get("pages", []) if p.get("state") == "active"]
    if len(active) < min_count:
        tag = f" ({label})" if label else ""
        raise RuntimeError(
            f"Expected at least {min_count} active page(s) on port {port}{tag}, "
            f"got {len(active)} — ingest may have scope-rejected all pages"
        )


def _activate_draft_pages(port: int) -> None:
    """Promote every DRAFT page on the wiki at *port* to ACTIVE.

    The ingest agent creates pages as LifecycleState.DRAFT, but /retrieve
    only serves LifecycleState.ACTIVE pages.  Calling this after all ingest
    jobs complete makes the freshly created pages visible to cross-wiki queries.
    """
    resp = httpx.get(f"http://127.0.0.1:{port}/lifecycle/pages", timeout=10.0)
    resp.raise_for_status()
    draft_slugs = [
        p["slug"] for p in resp.json().get("pages", []) if p.get("state") == "draft"
    ]
    for slug in draft_slugs:
        r = httpx.post(
            f"http://127.0.0.1:{port}/lifecycle/transition",
            json={"slug": slug, "to_state": "active", "reason": "live-test activation"},
            timeout=10.0,
        )
        r.raise_for_status()


def _wait_for_server(port: int, timeout: int = _WAIT_SECS) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            httpx.get(f"http://127.0.0.1:{port}/health", timeout=1.0)
            return
        except Exception:
            time.sleep(1)
    raise TimeoutError(f"Server on port {port} did not start within {timeout}s")


def _query_cross_wiki(question: str) -> dict:
    resp = httpx.post(
        f"http://127.0.0.1:{_COORDINATOR_PORT}/cross-wiki/query",
        json={"question": question},
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()
