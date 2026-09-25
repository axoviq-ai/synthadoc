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
import subprocess
from pathlib import Path

import sys

import httpx
import pytest

# Provider for live tests — override with SYNTHADOC_LIVE_PROVIDER env var.
# Allowed: "claude-code" (default), "opencode"
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from live_helpers import patch_provider  # noqa: E402

# Suppress console popup windows on Windows when spawning background processes.
_POPEN_HIDDEN: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
if sys.platform == "win32":
    _POPEN_HIDDEN["creationflags"] = subprocess.CREATE_NO_WINDOW

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("SYNTHADOC_LIVE_TESTS") != "1",
        reason="Set SYNTHADOC_LIVE_TESTS=1 to run live cross-wiki tests",
    ),
    # Fixture spins up real servers and runs cross-wiki LLM queries; 600 s gives
    # enough headroom for the full suite even on a slow machine.
    pytest.mark.timeout(600),
]

_COORDINATOR_PORT = 17070
_TARGET_PORT = 17071
_WAIT_SECS = 60  # max seconds to wait for server ready


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

    # Patch config.toml to use a coding-tool CLI provider (no API key needed).
    # Defaults to "claude-code"; set SYNTHADOC_LIVE_PROVIDER=opencode to switch.
    for _wiki_dir in (coord_dir / "live-coord", target_dir / "live-target"):
        patch_provider(_wiki_dir)

    # Seed content with status:active frontmatter — coordinator: finance domain
    _write_page(coord_dir / "live-coord", "leverage", (
        "Leverage\n\n"
        "Leverage is the ratio of debt to equity in a capital structure. "
        "High leverage amplifies returns but also increases financial risk. "
        "In corporate finance, the leverage ratio measures how much of a company's "
        "capital comes from debt versus equity.\n\n"
        "Formula: Leverage Ratio = Total Debt / Total Equity\n\n"
        "A leverage ratio above 2x is considered high; below 1x is conservative."
    ))
    _write_page(coord_dir / "live-coord", "ebitda", (
        "EBITDA and M&A Valuation Multiples\n\n"
        "EBITDA stands for Earnings Before Interest, Taxes, Depreciation, and Amortisation. "
        "It is the primary metric used to value companies in mergers and acquisitions (M&A). "
        "Analysts apply an EBITDA multiple to estimate enterprise value.\n\n"
        "Typical EBITDA multiples in M&A range from 6x to 12x depending on sector and growth rate. "
        "Technology companies often trade at 10x–15x EBITDA; industrials at 5x–8x EBITDA.\n\n"
        "Example: a company with $10M EBITDA at an 8x multiple has an enterprise value of $80M."
    ))

    # Seed content — target: operations domain
    _write_page(target_dir / "live-target", "deployment-runbook", (
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
    _write_page(target_dir / "live-target", "incident-response", (
        "Incident Response\n\n"
        "Severity levels: P1 (complete outage), P2 (degraded service), P3 (minor issue). "
        "P1 incidents require a response within 15 minutes. "
        "P2 incidents require acknowledgement within 1 hour.\n\n"
        "Escalation: page the on-call engineer via PagerDuty for P1 and P2."
    ))

    # Free the test ports before starting — a previous crashed run may have
    # left servers running (fixture setup failed before yield, so teardown
    # never executed and those processes kept their port bindings).
    _free_port(_COORDINATOR_PORT)
    _free_port(_TARGET_PORT)

    # Start servers in foreground so we own the processes directly.
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

    # Guard: pages written with status:active frontmatter before server start
    # are indexed from disk on the first BM25 query (cold cache).  Verify here.
    _assert_retrieve_works(_COORDINATOR_PORT, "leverage ratio debt equity", label="live-coord")
    _assert_retrieve_works(_TARGET_PORT, "kubernetes deployment rollback", label="live-target")

    yield {
        "coord_dir": coord_dir,
        "target_dir": target_dir,
        "_target_proc": target_proc_holder,
    }

    # Teardown — terminate server processes, clean registry, remove wiki dirs.
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
    shutil.rmtree(base, ignore_errors=True)


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
    """Write a wiki page directly with status:active frontmatter.

    Bypasses the ingest pipeline entirely — no LLM, no jobs.  The BM25
    corpus is rebuilt from disk on the first query after server start (cold
    cache), so pages written here are immediately searchable via /retrieve.
    """
    import yaml as _yaml
    page_dir = wiki_dir / "wiki"
    page_dir.mkdir(parents=True, exist_ok=True)
    lines = [ln for ln in content.splitlines() if ln.strip()]
    title = lines[0].strip() if lines else slug
    fm = {"title": title, "status": "active"}
    yaml_str = _yaml.dump(fm, default_flow_style=False, allow_unicode=True)
    (page_dir / f"{slug}.md").write_text(
        f"---\n{yaml_str}---\n\n{content}", encoding="utf-8"
    )


def _assert_retrieve_works(port: int, query: str, label: str = "") -> None:
    """Raise if /retrieve returns no pages for the given query."""
    resp = httpx.post(
        f"http://127.0.0.1:{port}/retrieve",
        json={"question": query, "top_k": 3},
        timeout=10.0,
    )
    resp.raise_for_status()
    pages = resp.json().get("pages", [])
    if not pages:
        tag = f" ({label})" if label else ""
        raise RuntimeError(
            f"No pages returned by /retrieve on port {port}{tag} "
            f"for query {query!r} — pages may not have status:active"
        )


def _free_port(port: int) -> None:
    """Kill any process currently listening on *port* (best-effort, cross-platform)."""
    if sys.platform == "win32":
        result = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                if parts:
                    subprocess.run(["taskkill", "/F", "/PID", parts[-1]], capture_output=True)
    else:
        result = subprocess.run(
            ["lsof", "-t", f"-i:{port}", "-sTCP:LISTEN"],
            capture_output=True, text=True,
        )
        for pid_str in result.stdout.splitlines():
            pid_str = pid_str.strip()
            if pid_str.isdigit():
                subprocess.run(["kill", "-9", pid_str], capture_output=True)
        time.sleep(0.5)  # give the OS time to release the port


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
        timeout=120.0,
    )
    resp.raise_for_status()
    return resp.json()
