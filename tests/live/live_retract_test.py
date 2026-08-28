# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Live tests for synthadoc retract — full end-to-end with real wiki storage.

Run with:
    pytest tests/live/live_retract_test.py -v

Tests create a temporary wiki directory, ingest pages, run retract scan/apply,
verify redactions, and clean up all artifacts on completion.
"""
from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from synthadoc.cli.retract import retract_app

runner = CliRunner()

SENSITIVE_CONTENT = """\
# API Config

This page documents our production API setup.

api_key = sk-abcdefghijklmnopqrstvwxyz01
Contact: admin@example.com for issues.
"""

CLEAN_CONTENT = """\
# Public Page

This page is safe to share. No secrets here.
"""


@pytest.fixture()
def live_wiki(tmp_path):
    """Create a minimal on-disk wiki with a .synthadoc directory."""
    wiki_root = tmp_path / "live-retract-wiki"
    wiki_root.mkdir()
    (wiki_root / ".synthadoc").mkdir()
    # Create a config.toml with sensitive scan enabled
    (wiki_root / ".synthadoc" / "config.toml").write_text(
        "[security]\nsensitive_scan_enabled = true\n",
        encoding="utf-8",
    )
    # Create test pages
    (wiki_root / "api-config.md").write_text(SENSITIVE_CONTENT, encoding="utf-8")
    (wiki_root / "public-page.md").write_text(CLEAN_CONTENT, encoding="utf-8")
    yield wiki_root
    # Cleanup
    shutil.rmtree(wiki_root, ignore_errors=True)


def _patch_resolve(wiki_root):
    """Context manager: patch CLI helpers to point at our test wiki."""
    from unittest.mock import patch
    return patch(
        "synthadoc.cli.retract._resolve_wiki_root", return_value=wiki_root
    )


def _patch_resolve_wiki():
    from unittest.mock import patch
    return patch("synthadoc.cli._wiki.resolve_wiki", side_effect=lambda w: w)


# ---------------------------------------------------------------------------
# Live test: scan dry-run
# ---------------------------------------------------------------------------

def test_live_scan_detects_api_key(live_wiki):
    """scan (dry-run) detects API key and email; prints slug and line number."""
    with _patch_resolve(live_wiki), _patch_resolve_wiki():
        result = runner.invoke(retract_app, ["scan", "-w", "live-retract-wiki"])
    assert result.exit_code == 0
    # Page slug and pattern types must appear
    assert "api-config" in result.output
    assert "api_key" in result.output or "email" in result.output
    # Sensitive value must NOT appear
    assert "sk-abcdefghijklmnopqrstvwxyz01" not in result.output
    assert "admin@example.com" not in result.output


def test_live_scan_clean_page_excluded(live_wiki):
    """scan on clean page reports 0 matches."""
    with _patch_resolve(live_wiki), _patch_resolve_wiki():
        result = runner.invoke(retract_app, ["scan", "-w", "live-retract-wiki",
                                              "--slug", "public-page"])
    assert result.exit_code == 0
    assert "0 matches" in result.output or "No sensitive" in result.output


# ---------------------------------------------------------------------------
# Live test: scan --apply
# ---------------------------------------------------------------------------

def test_live_apply_redacts_api_key(live_wiki):
    """scan --apply --yes writes [REDACTED] to file; original value gone."""
    with _patch_resolve(live_wiki), _patch_resolve_wiki():
        result = runner.invoke(retract_app, ["scan", "-w", "live-retract-wiki",
                                              "--apply", "--yes"])
    assert result.exit_code == 0
    content = (live_wiki / "api-config.md").read_text(encoding="utf-8")
    assert "sk-abcdefghijklmnopqrstvwxyz01" not in content
    assert "[REDACTED]" in content


def test_live_apply_clean_page_unchanged(live_wiki):
    """scan --apply does not modify pages without sensitive data."""
    original = (live_wiki / "public-page.md").read_text(encoding="utf-8")
    with _patch_resolve(live_wiki), _patch_resolve_wiki():
        runner.invoke(retract_app, ["scan", "-w", "live-retract-wiki",
                                    "--apply", "--yes"])
    content = (live_wiki / "public-page.md").read_text(encoding="utf-8")
    assert content == original


def test_live_apply_audit_log_written(live_wiki):
    """After apply, audit DB has a retract_scan event with correct metadata."""
    from synthadoc.storage.log import AuditDB
    db = AuditDB(live_wiki / ".synthadoc" / "audit.db")
    asyncio.run(db.init())
    with _patch_resolve(live_wiki), _patch_resolve_wiki():
        runner.invoke(retract_app, ["scan", "-w", "live-retract-wiki",
                                    "--apply", "--yes"])
    events, total = asyncio.run(db.list_events(limit=10))
    retract_events = [e for e in events if e.get("event") == "retract_scan"]
    assert len(retract_events) >= 1
    meta = json.loads(retract_events[0]["metadata"])
    assert meta["slug"] == "api-config"
    assert meta["applied"] is True
    assert meta["matches_count"] >= 1


def test_live_apply_idempotent(live_wiki):
    """Applying twice does not corrupt the file (already-redacted lines are stable)."""
    with _patch_resolve(live_wiki), _patch_resolve_wiki():
        runner.invoke(retract_app, ["scan", "-w", "live-retract-wiki", "--apply", "--yes"])
        result2 = runner.invoke(retract_app, ["scan", "-w", "live-retract-wiki", "--apply", "--yes"])
    assert result2.exit_code == 0
    content = (live_wiki / "api-config.md").read_text(encoding="utf-8")
    # After second run, [REDACTED] should still appear correctly
    assert "[REDACTED]" in content


# ---------------------------------------------------------------------------
# Live test: status command
# ---------------------------------------------------------------------------

def test_live_status_after_apply(live_wiki):
    """status shows the retract event written during apply."""
    from synthadoc.storage.log import AuditDB
    db = AuditDB(live_wiki / ".synthadoc" / "audit.db")
    asyncio.run(db.init())
    asyncio.run(db.record_retract_event(
        slug="api-config", matches_count=2, pattern_names=["api_key", "email"], applied=True
    ))
    with _patch_resolve(live_wiki), _patch_resolve_wiki():
        result = runner.invoke(retract_app, ["status", "-w", "live-retract-wiki"])
    assert result.exit_code == 0
    assert "api-config" in result.output


def test_live_status_json(live_wiki):
    """status --json returns parseable JSON with correct shape."""
    from synthadoc.storage.log import AuditDB
    db = AuditDB(live_wiki / ".synthadoc" / "audit.db")
    asyncio.run(db.init())
    asyncio.run(db.record_retract_event(
        slug="api-config", matches_count=1, pattern_names=["api_key"], applied=True
    ))
    with _patch_resolve(live_wiki), _patch_resolve_wiki():
        result = runner.invoke(retract_app, ["status", "-w", "live-retract-wiki", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert any(json.loads(e.get("metadata", "{}")).get("slug") == "api-config" for e in data)
