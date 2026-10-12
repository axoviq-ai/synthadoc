# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests: ingest_agent calls content_health_scanner and stores issues in WikiPage."""
import tempfile
from dataclasses import asdict
from pathlib import Path

import pytest

from synthadoc.agents.content_health_scanner import scan_page
from synthadoc.storage.wiki import LifecycleState, WikiPage, WikiStorage


def _make_page(content: str, status: str = LifecycleState.ACTIVE, **kwargs) -> WikiPage:
    return WikiPage(
        title="Test", tags=[], content=content,
        status=status, confidence="", sources=[],
        **kwargs,
    )


def test_scan_page_stores_issues_on_write(tmp_path):
    """Simulates what ingest_agent._write_or_stage does: scan then write."""
    store = WikiStorage(tmp_path / "wiki")
    dup_content = "# Test\n\n## Intro\nHello.\n\n## Intro\nDuplicate.\n"
    page = _make_page(dup_content)

    # Simulate what the ingest hook does
    issues = scan_page("test-page", page.content)
    page.content_health_issues = [asdict(i) for i in issues]
    store.write_page("test-page", page)

    loaded = store.read_page("test-page")
    assert loaded.content_health_issues
    assert loaded.content_health_issues[0]["type"] == "duplicate_section"
    assert loaded.content_health_issues[0]["severity"] == "critical"


def test_clean_page_stores_empty_issues(tmp_path):
    """A page with no issues gets an empty content_health_issues list."""
    store = WikiStorage(tmp_path / "wiki")
    clean_content = "# Test\n\n## Section\n" + " ".join(["word"] * 60) + "\n"
    page = _make_page(clean_content)

    issues = scan_page("clean-page", page.content)
    page.content_health_issues = [asdict(i) for i in issues]
    store.write_page("clean-page", page)

    loaded = store.read_page("clean-page")
    assert loaded.content_health_issues == []
    assert store.count_content_health_issues() == 0


def test_fix_record_not_touched_by_ingest(tmp_path):
    """Ingest scan only sets content_health_issues; fix_record must survive re-ingest."""
    store = WikiStorage(tmp_path / "wiki")
    fix_record = {"slug": "test-page", "snapshot_index_before": 2,
                  "timestamp": "2026-10-11T10:00:00Z", "issues_fixed": ["dup x1"]}
    dup_content = "# Test\n\n## Intro\nHello.\n\n## Intro\nDuplicate.\n"
    page = _make_page(dup_content, content_health_fix_record=fix_record)
    store.write_page("test-page", page)

    # Re-ingest: only update content_health_issues, not fix_record
    loaded = store.read_page("test-page")
    new_issues = scan_page("test-page", loaded.content)
    loaded.content_health_issues = [asdict(i) for i in new_issues]
    store.write_page("test-page", loaded)

    final = store.read_page("test-page")
    assert final.content_health_fix_record == fix_record  # unchanged
    assert final.content_health_issues  # re-set from scan
