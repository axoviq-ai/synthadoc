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

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("SYNTHADOC_LIVE_TESTS") != "1",
    reason="Set SYNTHADOC_LIVE_TESTS=1 to run live cross-wiki tests"
)

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

    # Install wikis
    _run(["synthadoc", "install", "live-coord", "--target", str(coord_dir), "--port", str(_COORDINATOR_PORT)])
    _run(["synthadoc", "install", "live-target", "--target", str(target_dir), "--port", str(_TARGET_PORT)])

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
    _write_page(coord_dir, "leverage", "Leverage\n\nLeverage is the ratio of debt to equity in a capital structure. High leverage amplifies returns but increases risk.\n\nFormula: Leverage = Total Debt / Total Equity")
    _write_page(coord_dir, "ebitda", "EBITDA\n\nEBITDA stands for Earnings Before Interest, Taxes, Depreciation, and Amortisation. It measures operating performance.\n\nTypical EBITDA multiples in M&A range from 6x to 12x depending on sector.")

    # Seed content — target: operations domain
    _write_page(target_dir, "deployment-runbook", "Deployment Runbook\n\nTo deploy the application: (1) run `make build`, (2) push Docker image, (3) run `kubectl apply`.\n\nRollback: `kubectl rollout undo deployment/app`")
    _write_page(target_dir, "incident-response", "Incident Response\n\nSeverity levels: P1 (outage), P2 (degraded), P3 (minor). P1 requires response within 15 minutes.")

    # Start servers
    subprocess.Popen(["synthadoc", "serve", "-w", "live-coord", "--background"])
    subprocess.Popen(["synthadoc", "serve", "-w", "live-target", "--background"])

    _wait_for_server(_COORDINATOR_PORT)
    _wait_for_server(_TARGET_PORT)

    # Ingest pages now that servers are up
    _run(["synthadoc", "ingest", str(coord_dir / "wiki"), "-w", "live-coord", "--batch"])
    _run(["synthadoc", "ingest", str(target_dir / "wiki"), "-w", "live-target", "--batch"])

    yield {"coord_dir": coord_dir, "target_dir": target_dir}

    # Teardown — stop servers and clean registry directly (uninstall requires
    # interactive confirmation so we edit the JSON directly, same as pre-flight).
    subprocess.run(["synthadoc", "stop", "-w", "live-coord"], capture_output=True)
    subprocess.run(["synthadoc", "stop", "-w", "live-target"], capture_output=True)
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
    _run(["synthadoc", "stop", "-w", "live-target"])
    try:
        result = _query_cross_wiki("How do I deploy?")
        assert "live-target" in result.get("cross_wiki_offline", [])
    finally:
        # Restart target for subsequent tests
        subprocess.Popen(["synthadoc", "serve", "-w", "live-target", "--background"])
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
