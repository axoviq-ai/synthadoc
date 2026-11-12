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
    ctx.invalidate_search = MagicMock()
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

    def test_single_word_slug_is_recognized(self):
        assert parse_rollback_intent("roll back turing") == (True, "turing")

    def test_single_word_slug_in_cli_form_with_trailing_punctuation(self):
        assert parse_rollback_intent(
            "run contradiction resolver roll back python."
        ) == (True, "python")

    def test_slug_with_leading_underscore_is_recognized(self):
        # synthadoc's own live-test fixtures use a leading underscore to mark
        # test/system pages (e.g. "_live-test-contradiction-resolver"). Before
        # this fix, the slug-candidate class excluded "_", so the whole match
        # failed at that position and this fell through to (True, None) —
        # "roll back" with no page named — silently rolling back nothing.
        assert parse_rollback_intent(
            "roll back _live-test-contradiction-resolver"
        ) == (True, "_live-test-contradiction-resolver")

    def test_slug_with_embedded_underscore_is_recognized(self):
        assert parse_rollback_intent("roll back my_page_slug") == (True, "my_page_slug")

    @pytest.mark.parametrize("filler", [
        "this", "that", "our", "your", "my", "it", "them", "these", "those",
        "page", "pages", "This", "the",
    ])
    def test_filler_words_are_not_slugs(self, filler):
        assert parse_rollback_intent(f"roll back {filler} please") == (True, None)


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
    async def test_invalidates_search_index_on_success(self, tmp_path):
        """A rollback changes page content — search must be told to reindex,
        not just the query cache (bump_epoch alone doesn't touch BM25/vector
        indexes, so a page restored by rollback would stay unsearchable under
        its restored text until something unrelated happened to reindex)."""
        store = WikiStorage(tmp_path / "wiki")
        store.write_page("turing", _make_page("turing", content="# Turing\n\nChanged body.\n"))
        ctx = _make_ctx(store)
        ctx.audit_db.get_snapshot_by_index = AsyncMock(return_value={
            "index": 1, "id": 42, "content_snapshot": "# Turing\n\nOriginal body.\n",
        })
        result = await restore_page_snapshot(ctx, "turing", 42, fallback_index=1)
        assert result["status"] == "success"
        ctx.invalidate_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_invalidate_search_on_error(self, tmp_path):
        store = WikiStorage(tmp_path / "wiki")
        store.write_page("turing", _make_page("turing"))
        ctx = _make_ctx(store)
        ctx.audit_db.get_snapshot_by_index = AsyncMock(return_value=None)
        result = await restore_page_snapshot(ctx, "turing", 42, fallback_index=1)
        assert result["status"] == "error"
        ctx.invalidate_search.assert_not_called()

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

    @pytest.mark.asyncio
    async def test_errors_instead_of_silently_using_fallback_when_snapshot_id_pruned(
        self, tmp_path
    ):
        """GitHub #519: when the recorded snapshot_id has been pruned (e.g. by
        purge_lifecycle_events retention), the lookup must not silently fall
        through to fallback_index and restore an unrelated snapshot while
        still reporting success. A pruned, explicitly-requested snapshot_id is
        a genuine error — fallback_index is only for the snapshot_id=None case.
        """
        store = WikiStorage(tmp_path / "wiki")
        store.write_page("turing", _make_page("turing"))
        ctx = _make_ctx(store)
        # The requested snapshot (id=42) was pruned and no longer appears in
        # list_page_snapshots. A different, unrelated snapshot still exists at
        # fallback_index=1 — restoring it would silently substitute the wrong
        # content while reporting "success".
        ctx.audit_db.list_page_snapshots = AsyncMock(
            return_value=[{"index": 1, "id": 7}]
        )
        ctx.audit_db.get_snapshot_by_index = AsyncMock(return_value={
            "index": 1, "id": 7, "content_snapshot": "# Turing\n\nUnrelated body.\n",
        })
        result = await restore_page_snapshot(ctx, "turing", 42, fallback_index=1)
        assert result["status"] == "error"
        assert "42" in result["error"] or "pruned" in result["error"].lower() \
            or "no longer available" in result["error"].lower()
        ctx.audit_db.get_snapshot_by_index.assert_not_awaited()
