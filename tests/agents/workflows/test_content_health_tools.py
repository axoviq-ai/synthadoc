# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for content health workflow tool functions."""
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from synthadoc.agents.workflows._base import WorkflowContext
from synthadoc.agents.workflows.tools.content_health_tools import (
    tool_get_page_content,
    tool_list_content_health_fixes,
    tool_rollback_content_health_fix,
    tool_write_content_health_fix,
)
from synthadoc.storage.wiki import LifecycleState, WikiPage, WikiStorage


def _make_ctx(store):
    ctx = MagicMock(spec=WorkflowContext)
    ctx.store = store
    ctx.audit_db = MagicMock()
    # snapshot_if_changed returns True (new snapshot taken)
    ctx.audit_db.snapshot_if_changed = AsyncMock(return_value=True)
    # list_page_snapshots returns a list with one entry whose id is 42
    ctx.audit_db.list_page_snapshots = AsyncMock(return_value=[{"index": 1, "id": 42}])
    ctx.bump_epoch = MagicMock()
    return ctx


def _make_page(slug: str, **kwargs) -> WikiPage:
    defaults = dict(title=slug.title(), tags=[], content="# Page\n\nContent.",
                    status=LifecycleState.ACTIVE, confidence="", sources=[])
    return WikiPage(**{**defaults, **kwargs})


@pytest.mark.asyncio
async def test_get_page_content(tmp_path):
    store = WikiStorage(tmp_path / "wiki")
    store.write_page("turing", _make_page("turing", content="# Turing\n\nBio content."))
    ctx = _make_ctx(store)
    result = await tool_get_page_content(ctx, slug="turing")
    assert result["status"] == "success"
    assert result["slug"] == "turing"
    assert "Bio content." in result["content"]


@pytest.mark.asyncio
async def test_get_page_content_not_found(tmp_path):
    store = WikiStorage(tmp_path / "wiki")
    ctx = _make_ctx(store)
    result = await tool_get_page_content(ctx, slug="missing")
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_write_fix_stores_fix_record(tmp_path):
    store = WikiStorage(tmp_path / "wiki")
    issues = [{"type": "duplicate_section", "severity": "critical",
               "location": "## Intro", "description": "x2"}]
    store.write_page("turing", _make_page("turing", content_health_issues=issues))
    ctx = _make_ctx(store)
    fixed_content = "# Turing\n\n## Intro\n" + " ".join(["word"] * 60) + "\n"
    result = await tool_write_content_health_fix(
        ctx, slug="turing", content=fixed_content,
        issues_fixed=["duplicate_section x1"],
    )
    assert result["status"] == "success"
    loaded = store.read_page("turing")
    assert loaded.content_health_fix_record is not None
    assert loaded.content_health_fix_record["slug"] == "turing"
    assert loaded.content_health_fix_record["snapshot_id"] == 42


@pytest.mark.asyncio
async def test_write_fix_clears_issues_when_clean(tmp_path):
    store = WikiStorage(tmp_path / "wiki")
    issues = [{"type": "duplicate_section", "severity": "critical",
               "location": "## Intro", "description": "x2"}]
    dup_content = "# Turing\n\n## Intro\nHello.\n\n## Intro\nDup.\n"
    store.write_page("turing", _make_page("turing", content=dup_content,
                                          content_health_issues=issues))
    ctx = _make_ctx(store)
    clean_content = "# Turing\n\n## Intro\n" + " ".join(["word"] * 60) + "\n"
    result = await tool_write_content_health_fix(
        ctx, slug="turing", content=clean_content, issues_fixed=["dup x1"],
    )
    assert result["status"] == "success"
    assert result["remaining_issues"] == 0
    loaded = store.read_page("turing")
    assert loaded.content_health_issues == []


@pytest.mark.asyncio
async def test_list_fixes_empty(tmp_path):
    store = WikiStorage(tmp_path / "wiki")
    store.write_page("turing", _make_page("turing"))
    ctx = _make_ctx(store)
    result = await tool_list_content_health_fixes(ctx)
    assert result["fixes"] == []


@pytest.mark.asyncio
async def test_list_fixes_returns_fix_record(tmp_path):
    store = WikiStorage(tmp_path / "wiki")
    fix_record = {"slug": "turing", "snapshot_id": 42, "snapshot_index_before": 1,
                  "timestamp": "2026-10-11T14:00:00Z", "issues_fixed": ["dup x2"]}
    store.write_page("turing", _make_page("turing", content_health_fix_record=fix_record))
    ctx = _make_ctx(store)
    result = await tool_list_content_health_fixes(ctx)
    assert len(result["fixes"]) == 1
    assert result["fixes"][0]["slug"] == "turing"


@pytest.mark.asyncio
async def test_rollback_no_fix_record_returns_error(tmp_path):
    store = WikiStorage(tmp_path / "wiki")
    store.write_page("turing", _make_page("turing"))
    ctx = _make_ctx(store)
    result = await tool_rollback_content_health_fix(ctx, slug="turing")
    assert result["status"] == "error"
    assert "No content health fix recorded" in result["message"]


@pytest.mark.asyncio
async def test_rollback_restores_content(tmp_path):
    original_content = "# Turing\n\n## Intro\nHello.\n\n## Intro\nDup.\n"
    fixed_content = "# Turing\n\n## Intro\n" + " ".join(["word"] * 60) + "\n"
    store = WikiStorage(tmp_path / "wiki")
    fix_record = {"slug": "turing", "snapshot_id": 42, "snapshot_index_before": 1,
                  "timestamp": "2026-10-11T14:00:00Z", "issues_fixed": ["dup x2"]}
    store.write_page("turing", _make_page("turing", content=fixed_content,
                                          content_health_fix_record=fix_record))
    ctx = _make_ctx(store)
    # Mock: list returns snapshot with id=42 at index 1
    ctx.audit_db.list_page_snapshots = AsyncMock(return_value=[{"index": 1, "id": 42}])
    ctx.audit_db.get_snapshot_by_index = AsyncMock(return_value={
        "index": 1, "id": 42, "content_snapshot": original_content
    })
    result = await tool_rollback_content_health_fix(ctx, slug="turing")
    assert result["status"] == "success"
    loaded = store.read_page("turing")
    assert loaded.content_health_fix_record is None
    # Issues restored from original (duplicate content)
    assert loaded.content_health_issues


_DISMISSAL = {"slug": "zuse", "timestamp": "2026-10-17T01:01:36Z", "issues_fixed": [],
              "dismissed_at": "2026-10-17T01:01:36Z", "dismissed_count": 2,
              "dismissed_types": ["thin_section"],
              "dismissed_reason": "all issues are thin_section requiring human editing"}


@pytest.mark.asyncio
async def test_list_fixes_labels_fixed_dismissed_and_both(tmp_path):
    store = WikiStorage(tmp_path / "wiki")
    store.write_page("turing", _make_page("turing", content_health_fix_record={
        "slug": "turing", "snapshot_id": 42, "snapshot_index_before": 1,
        "timestamp": "2026-10-17T01:01:03Z", "issues_fixed": ["empty_section x1"]}))
    store.write_page("zuse", _make_page("zuse", content_health_fix_record=dict(_DISMISSAL)))
    store.write_page("hopper", _make_page("hopper", content_health_fix_record={
        **_DISMISSAL, "slug": "hopper", "snapshot_id": 29, "snapshot_index_before": 1,
        "timestamp": "2026-10-17T01:01:20Z", "issues_fixed": ["orphaned_heading x1"]}))
    fixes = {f["slug"]: f for f in (await tool_list_content_health_fixes(_make_ctx(store)))["fixes"]}

    assert fixes["turing"]["action"] == "fixed" and "dismissed_count" not in fixes["turing"]
    assert fixes["zuse"]["action"] == "dismissed"
    assert fixes["zuse"]["snapshot_id"] is None
    assert fixes["zuse"]["dismissed_types"] == ["thin_section"]
    assert fixes["zuse"]["dismissed_reason"].startswith("all issues are thin_section")
    assert fixes["hopper"]["action"] == "fixed+dismissed"


@pytest.mark.asyncio
async def test_rollback_dismissal_restores_issues_without_touching_content(tmp_path):
    """A dismissal has no snapshot; rollback must not restore some unrelated snapshot."""
    thin = "# Zuse\n\n## Early life\nShort.\n\n## Z3\nAlso short.\n"
    store = WikiStorage(tmp_path / "wiki")
    store.write_page("zuse", _make_page("zuse", content=thin,
                                        content_health_fix_record=dict(_DISMISSAL)))
    ctx = _make_ctx(store)
    ctx.audit_db.get_snapshot_by_index = AsyncMock(return_value={
        "index": 1, "id": 7, "content_snapshot": "UNRELATED OLDER VERSION"})

    result = await tool_rollback_content_health_fix(ctx, slug="zuse")

    assert result["status"] == "success"
    assert "Dismissal undone" in result["message"]
    ctx.audit_db.get_snapshot_by_index.assert_not_called()
    loaded = store.read_page("zuse")
    assert loaded.content.strip() == thin.strip()
    assert loaded.content_health_fix_record is None
    assert result["restored_issues"] == len(loaded.content_health_issues) == 2


def test_format_fix_list_shows_dismissals_as_dismissals():
    from synthadoc.agents.workflows.content_health_resolver import _format_fix_list
    text = _format_fix_list([
        {"slug": "zuse", "action": "dismissed", "fixed_at": "t2",
         "dismissed_count": 2, "dismissed_types": ["thin_section"]},
        {"slug": "turing", "action": "fixed", "fixed_at": "t1",
         "issues_fixed": ["empty_section x1"], "snapshot_index_before": 1},
    ])
    assert "zuse — t2 — dismissed 2 thin_section — needs human editing (no snapshot: content unchanged)" in text
    assert "turing — t1 — fixed: empty_section x1 (pre-fix snapshot #1)" in text
