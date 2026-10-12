# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
import tempfile
from pathlib import Path

from synthadoc.storage.wiki import LifecycleState, WikiPage, WikiStorage


def _make_page(**kwargs):
    defaults = dict(title="T", tags=[], content="# T\n\nContent.", status=LifecycleState.ACTIVE,
                    confidence="", sources=[])
    return WikiPage(**{**defaults, **kwargs})


def test_content_health_issues_default_empty():
    p = _make_page()
    assert p.content_health_issues == []


def test_content_health_fix_record_default_none():
    p = _make_page()
    assert p.content_health_fix_record is None


def test_roundtrip_content_health_issues():
    with tempfile.TemporaryDirectory() as tmp:
        store = WikiStorage(Path(tmp))
        issues = [{"type": "duplicate_section", "severity": "critical",
                   "location": "## Intro", "description": "Appears 3 times"}]
        page = _make_page(content_health_issues=issues)
        store.write_page("test", page)
        loaded = store.read_page("test")
        assert loaded.content_health_issues == issues


def test_roundtrip_fix_record():
    with tempfile.TemporaryDirectory() as tmp:
        store = WikiStorage(Path(tmp))
        fix_record = {"slug": "test", "snapshot_index_before": 3,
                      "timestamp": "2026-10-11T14:00:00Z",
                      "issues_fixed": ["duplicate_section x2"]}
        page = _make_page(content_health_fix_record=fix_record)
        store.write_page("test", page)
        loaded = store.read_page("test")
        assert loaded.content_health_fix_record == fix_record


def test_clean_page_omits_issues_from_frontmatter():
    with tempfile.TemporaryDirectory() as tmp:
        store = WikiStorage(Path(tmp))
        store.write_page("test", _make_page())
        raw = (Path(tmp) / "test.md").read_text()
        assert "content_health_issues" not in raw
        assert "content_health_fix_record" not in raw


def test_count_content_health_issues():
    with tempfile.TemporaryDirectory() as tmp:
        store = WikiStorage(Path(tmp))
        store.write_page("clean", _make_page())
        issues = [{"type": "duplicate_section", "severity": "critical",
                   "location": "## Intro", "description": "x2"}]
        store.write_page("dirty", _make_page(content_health_issues=issues))
        store.write_page("stale-dirty", _make_page(status=LifecycleState.STALE,
                         content_health_issues=issues))
        assert store.count_content_health_issues() == 1  # only active pages


def test_fix_record_cleared_writes_correctly():
    with tempfile.TemporaryDirectory() as tmp:
        store = WikiStorage(Path(tmp))
        fix_record = {"slug": "test", "snapshot_index_before": 1,
                      "timestamp": "2026-10-11T14:00:00Z",
                      "issues_fixed": []}
        page = _make_page(content_health_fix_record=fix_record)
        store.write_page("test", page)
        # Clear and re-save
        page.content_health_fix_record = None
        store.write_page("test", page)
        loaded = store.read_page("test")
        assert loaded.content_health_fix_record is None
        raw = (Path(tmp) / "test.md").read_text()
        assert "content_health_fix_record" not in raw
