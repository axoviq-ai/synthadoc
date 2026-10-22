# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
from unittest.mock import AsyncMock, MagicMock

import pytest

from synthadoc.agents.workflows._base import WorkflowContext
from synthadoc.agents.workflows._rollback import restore_page_snapshot, parse_rollback_intent
from synthadoc.storage.wiki import LifecycleState, WikiPage, WikiStorage


def _make_ctx(store):
    ctx = MagicMock(spec=WorkflowContext)
    ctx.store = store
    ctx.audit_db = MagicMock()
    ctx.audit_db.list_page_snapshots = AsyncMock(return_value=[{"index": 1, "id": 42}])
    ctx.audit_db.get_snapshot_by_index = AsyncMock(return_value=None)
    ctx.bump_epoch = MagicMock()
    return ctx


def _make_page(slug: str, **kwargs) -> WikiPage:
    defaults = dict(title=slug.title(), tags=[], content="# Page\n\nContent.",
                    status=LifecycleState.ACTIVE, confidence="", sources=[])
    return WikiPage(**{**defaults, **kwargs})


class TestParseRollbackIntent:
    def test_bare_roll_back_returns_true_none(self):
        assert parse_rollback_intent("roll back") == (True, None)

    def test_roll_back_with_slug_returns_true_slug(self):
        assert parse_rollback_intent("roll back alan-turing") == (True, "alan-turing")

    def test_rollback_one_word_also_matches(self):
        assert parse_rollback_intent("please rollback this page") == (True, None)

    def test_unrelated_text_returns_false_none(self):
        assert parse_rollback_intent("fix the broken citations") == (False, None)

    def test_substring_match_is_a_known_limitation(self):
        # Documents existing behavior inherited from content_health_resolver's own
        # matcher — "roll back" as a literal substring of unrelated prose still
        # matches. Not fixed here; just pinned so a future change notices.
        assert parse_rollback_intent("we need to roll back our expectations") == (True, None)


class TestRestorePageSnapshot:
    @pytest.mark.asyncio
    async def test_restores_content_from_resolved_snapshot(self, tmp_path):
        original_content = "# Turing\n\nOriginal body.\n"
        store = WikiStorage(tmp_path / "wiki")
        store.write_page("turing", _make_page("turing", content="# Turing\n\nChanged body.\n"))
        ctx = _make_ctx(store)
        ctx.audit_db.get_snapshot_by_index = AsyncMock(return_value={
            "index": 1, "id": 42, "content_snapshot": original_content,
        })
        result = await restore_page_snapshot(ctx, "turing", 42, fallback_index=1)
        assert result["status"] == "success"
        assert store.read_page("turing").content == original_content

    @pytest.mark.asyncio
    async def test_resolves_snapshot_id_robust_to_later_snapshots(self, tmp_path):
        store = WikiStorage(tmp_path / "wiki")
        store.write_page("turing", _make_page("turing"))
        ctx = _make_ctx(store)
        # Two snapshots exist now (id 42 at index 2, a newer id 99 at index 1) —
        # restoring by id=42 must resolve to index 2, not the stale fallback_index=1.
        ctx.audit_db.list_page_snapshots = AsyncMock(
            return_value=[{"index": 1, "id": 99}, {"index": 2, "id": 42}]
        )
        ctx.audit_db.get_snapshot_by_index = AsyncMock(return_value={
            "index": 2, "id": 42, "content_snapshot": "# Turing\n\nOld body.\n",
        })
        result = await restore_page_snapshot(ctx, "turing", 42, fallback_index=1)
        assert result["status"] == "success"
        assert result["resolved_index"] == 2
        ctx.audit_db.get_snapshot_by_index.assert_awaited_with("turing", 2)

    @pytest.mark.asyncio
    async def test_falls_back_to_index_when_snapshot_id_none(self, tmp_path):
        store = WikiStorage(tmp_path / "wiki")
        store.write_page("turing", _make_page("turing"))
        ctx = _make_ctx(store)
        ctx.audit_db.get_snapshot_by_index = AsyncMock(return_value={
            "index": 1, "id": 42, "content_snapshot": "# Turing\n\nFallback body.\n",
        })
        result = await restore_page_snapshot(ctx, "turing", None, fallback_index=1)
        assert result["status"] == "success"
        ctx.audit_db.list_page_snapshots.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_error_for_missing_page(self, tmp_path):
        store = WikiStorage(tmp_path / "wiki")
        ctx = _make_ctx(store)
        result = await restore_page_snapshot(ctx, "no-such-page", None, fallback_index=1)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_returns_error_when_snapshot_pruned_from_audit_log(self, tmp_path):
        store = WikiStorage(tmp_path / "wiki")
        store.write_page("turing", _make_page("turing"))
        ctx = _make_ctx(store)
        ctx.audit_db.list_page_snapshots = AsyncMock(return_value=[])
        ctx.audit_db.get_snapshot_by_index = AsyncMock(return_value=None)
        result = await restore_page_snapshot(ctx, "turing", "nonexistent-id", fallback_index=999)
        assert result["status"] == "error"
