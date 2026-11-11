# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
import aiosqlite
from synthadoc.core.cache import CacheManager, make_cache_key, CACHE_VERSION


@pytest.mark.asyncio
async def test_miss_returns_none(tmp_wiki):
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    try:
        assert await cache.get("missing") is None
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_set_and_get(tmp_wiki):
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    try:
        await cache.set("k1", {"result": "Paris"})
        result = await cache.get("k1")
        assert result["result"] == "Paris"
    finally:
        await cache.close()


def test_cache_key_deterministic():
    k1 = make_cache_key("op", {"text": "hello"})
    k2 = make_cache_key("op", {"text": "hello"})
    k3 = make_cache_key("op", {"text": "world"})
    assert k1 == k2
    assert k1 != k3


def test_cache_version_changes_key():
    """Keys must differ across cache versions so stale entries are never served."""
    k1 = make_cache_key("op", {"text": "hello"}, version="4")
    k2 = make_cache_key("op", {"text": "hello"}, version="5")
    assert k1 != k2


@pytest.mark.asyncio
async def test_clear_deletes_all_entries(tmp_wiki):
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    try:
        await cache.set("a", {"v": 1})
        await cache.set("b", {"v": 2})
        await cache.set("c", {"v": 3})

        removed = await cache.clear()
        assert removed == 3
        assert await cache.get("a") is None
        assert await cache.get("b") is None
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_clear_on_empty_cache_returns_zero(tmp_wiki):
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    try:
        assert await cache.clear() == 0
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_clear_also_wipes_query_cache(tmp_wiki):
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    try:
        await cache.set("r1", {"v": 1})
        await cache.set_query("q1", epoch=1, result={"answer": "x"})
        await cache.set_query("q2", epoch=1, result={"answer": "y"})
        removed = await cache.clear()
        assert removed == 3
        assert await cache.get("r1") is None
        assert await cache.get_query("q1") is None
        assert await cache.get_query("q2") is None
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_clear_preserves_epoch_row(tmp_path):
    """clear() must delete regular entries but keep the epoch row.

    Without this, 'synthadoc cache clear' would reset the saved epoch to 0
    so the restart-bump could re-use old epoch numbers, defeating
    cross-wiki cache invalidation.
    """
    cm = CacheManager(tmp_path / "cache.db")
    await cm.init()
    try:
        await cm.save_epoch(42)
        await cm.set("some-key", {"v": 1})
        await cm.set_query("q1", epoch=42, result={"answer": "x"})

        removed = await cm.clear()
        # 2 non-epoch rows: "some-key" (response_cache) + "q1" (query_cache)
        assert removed == 2
        # Epoch row survived clear
        assert await cm.get_saved_epoch() == 42
        # Other entries are gone
        assert await cm.get("some-key") is None
        assert await cm.get_query("q1") is None
    finally:
        await cm.close()


@pytest.mark.asyncio
async def test_get_query_returns_none_on_miss(tmp_path):
    """get_query returns None when no matching entry exists."""
    from synthadoc.core.cache import CacheManager
    cm = CacheManager(tmp_path / "cache.db")
    await cm.init()
    try:
        result = await cm.get_query("nonexistent-key")
        assert result is None
    finally:
        await cm.close()


@pytest.mark.asyncio
async def test_set_and_get_query_round_trip(tmp_path):
    """set_query then get_query must return the stored dict."""
    from synthadoc.core.cache import CacheManager
    cm = CacheManager(tmp_path / "cache.db")
    await cm.init()
    try:
        payload = {"answer": "42", "citations": ["page-a"], "knowledge_gap": False}
        await cm.set_query("abc123", epoch=1, result=payload)
        stored = await cm.get_query("abc123")
        assert stored == payload
    finally:
        await cm.close()


@pytest.mark.asyncio
async def test_query_cache_cleanup_removes_old_epochs(tmp_path):
    """cleanup_query_cache removes entries with epoch < current_epoch - 5."""
    from synthadoc.core.cache import CacheManager
    cm = CacheManager(tmp_path / "cache.db")
    await cm.init()
    try:
        await cm.set_query("old-key", epoch=1, result={"answer": "old"})
        await cm.set_query("new-key", epoch=10, result={"answer": "new"})
        await cm.cleanup_query_cache(current_epoch=10)
        assert await cm.get_query("old-key") is None
        assert await cm.get_query("new-key") is not None
    finally:
        await cm.close()


def test_make_query_cache_key_normalises_whitespace():
    """make_query_cache_key treats different whitespace as the same question."""
    from synthadoc.core.cache import make_query_cache_key
    k1 = make_query_cache_key("  What   is AI?  ", epoch=3)
    k2 = make_query_cache_key("What is AI?", epoch=3)
    assert k1 == k2


def test_make_query_cache_key_is_epoch_sensitive():
    """Different epochs produce different keys."""
    from synthadoc.core.cache import make_query_cache_key
    k1 = make_query_cache_key("What is AI?", epoch=1)
    k2 = make_query_cache_key("What is AI?", epoch=2)
    assert k1 != k2


def test_make_query_cache_key_is_model_sensitive():
    """Different provider/model strings produce different keys for the same question and epoch."""
    from synthadoc.core.cache import make_query_cache_key
    k1 = make_query_cache_key("What is AI?", epoch=1, model="gemini/gemini-2.5-flash-lite")
    k2 = make_query_cache_key("What is AI?", epoch=1, model="openai/gpt-4o-mini")
    k3 = make_query_cache_key("What is AI?", epoch=1, model="claude-code/")
    k4 = make_query_cache_key("What is AI?", epoch=1, model="opencode/")
    assert k1 != k2
    assert k3 != k4  # same empty model, different provider


def test_make_query_cache_key_empty_model_is_stable():
    """Omitting model (default '') is equivalent to passing model=''."""
    from synthadoc.core.cache import make_query_cache_key
    k1 = make_query_cache_key("What is AI?", epoch=1)
    k2 = make_query_cache_key("What is AI?", epoch=1, model="")
    assert k1 == k2


@pytest.mark.asyncio
async def test_query_cache_cleanup_keeps_boundary_entry(tmp_path):
    """Entry at exactly current_epoch - 5 must be KEPT (< not <=)."""
    from synthadoc.core.cache import CacheManager
    cm = CacheManager(tmp_path / "cache.db")
    await cm.init()
    try:
        # At current_epoch=10, threshold is 5. epoch=5 is NOT < 5, so it should be kept.
        await cm.set_query("boundary-key", epoch=5, result={"answer": "boundary"})
        await cm.cleanup_query_cache(current_epoch=10)
        assert await cm.get_query("boundary-key") is not None
    finally:
        await cm.close()


@pytest.mark.asyncio
async def test_query_cache_cleanup_removes_below_boundary(tmp_path):
    """Entry at epoch = current_epoch - 6 must be REMOVED."""
    from synthadoc.core.cache import CacheManager
    cm = CacheManager(tmp_path / "cache.db")
    await cm.init()
    try:
        # At current_epoch=10, threshold is 5. epoch=4 IS < 5, so it should be removed.
        await cm.set_query("below-key", epoch=4, result={"answer": "below"})
        await cm.cleanup_query_cache(current_epoch=10)
        assert await cm.get_query("below-key") is None
    finally:
        await cm.close()


@pytest.mark.asyncio
async def test_set_query_overwrites_existing_entry(tmp_path):
    """Calling set_query twice for the same key must return the second value."""
    from synthadoc.core.cache import CacheManager
    cm = CacheManager(tmp_path / "cache.db")
    await cm.init()
    try:
        await cm.set_query("key-x", epoch=1, result={"answer": "first"})
        await cm.set_query("key-x", epoch=2, result={"answer": "second"})
        stored = await cm.get_query("key-x")
        assert stored == {"answer": "second"}
    finally:
        await cm.close()


@pytest.mark.asyncio
async def test_cache_manager_uses_wal_journal_mode(tmp_wiki):
    cm = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cm.init()
    try:
        async with aiosqlite.connect(tmp_wiki / ".synthadoc" / "cache.db") as conn:
            async with conn.execute("PRAGMA journal_mode") as cur:
                row = await cur.fetchone()
        assert row[0] == "wal" # type: ignore
    finally:
        await cm.close()


# ── Epoch persistence tests ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_saved_epoch_returns_zero_on_fresh_db(tmp_path):
    """A brand-new cache has no saved epoch — get_saved_epoch must return 0."""
    cm = CacheManager(tmp_path / "cache.db")
    await cm.init()
    try:
        assert await cm.get_saved_epoch() == 0
    finally:
        await cm.close()


@pytest.mark.asyncio
async def test_save_and_get_epoch_round_trip(tmp_path):
    """save_epoch then get_saved_epoch must return the value that was saved."""
    cm = CacheManager(tmp_path / "cache.db")
    await cm.init()
    try:
        await cm.save_epoch(42)
        assert await cm.get_saved_epoch() == 42
    finally:
        await cm.close()


@pytest.mark.asyncio
async def test_epoch_persists_across_close_and_reopen(tmp_path):
    """An epoch saved before close must still be readable after a fresh init()."""
    db = tmp_path / "cache.db"
    cm = CacheManager(db)
    await cm.init()
    await cm.save_epoch(7)
    await cm.close()

    cm2 = CacheManager(db)
    await cm2.init()
    try:
        assert await cm2.get_saved_epoch() == 7
    finally:
        await cm2.close()


@pytest.mark.asyncio
async def test_restart_does_not_serve_stale_query_cache(tmp_path):
    """After a restart, a question cached under the old epoch must be a cache miss.

    Scenario: epoch 5 at shutdown, restart sets epoch to 6.  The entry stored
    at epoch 5 produces a different cache key at epoch 6, so get_query returns None.
    """
    from synthadoc.core.cache import CacheManager, make_query_cache_key

    db = tmp_path / "cache.db"
    cm = CacheManager(db)
    await cm.init()

    # Simulate server run: epoch 5, cache one answer.
    pre_restart_epoch = 5
    await cm.save_epoch(pre_restart_epoch)
    q = "What is the company revenue?"
    old_key = make_query_cache_key(q, epoch=pre_restart_epoch)
    await cm.set_query(old_key, epoch=pre_restart_epoch, result={"answer": "100M"})
    await cm.close()

    # Simulate restart: new instance reads saved epoch and adds 1.
    cm2 = CacheManager(db)
    await cm2.init()
    try:
        new_epoch = (await cm2.get_saved_epoch()) + 1  # mirrors orchestrator init()
        new_key = make_query_cache_key(q, epoch=new_epoch)
        assert new_epoch == pre_restart_epoch + 1
        assert new_key != old_key, "cache key must differ after epoch bump"
        assert await cm2.get_query(new_key) is None, "restarted wiki must not serve old answer"
    finally:
        await cm2.close()


@pytest.mark.asyncio
async def test_peer_wiki_restart_invalidates_cross_wiki_cache_key(tmp_path):
    """When a peer wiki restarts (its epoch increments), the cross-wiki cache key changes.

    Scenario: fernway-marketing cached a cross-wiki answer keyed on
    {product: 5, marketing: 7}.  fernway-product restarts (epoch → 6) and
    changes.  After 1 more ingest (epoch 7), product is at epoch 7 again but
    with *different* content.  However, because epoch numbers never decrease
    (saved + 1 on restart means product went 5→6→7, never back to 5), the
    cross-wiki key was {product: 7, marketing: 7} — which NEVER matches the
    stale key {product: 5, marketing: 7}.
    """
    import hashlib, json as _json
    from synthadoc.core.cache import make_query_cache_key

    def _cw_key(q: str, peer_epochs: dict, model: str = "") -> str:
        normalized = " ".join(q.lower().split())
        payload = f"cross-wiki|{normalized}|{_json.dumps(peer_epochs, sort_keys=True)}|{model}"
        return hashlib.sha256(payload.encode()).hexdigest()[:32]

    q = "What is total headcount across all teams?"

    # Pre-restart: product epoch=5, marketing epoch=7
    stale_key = _cw_key(q, {"fernway-product": 5, "fernway-marketing": 7})

    # Simulate product restart: epoch saved=5 → new epoch = 6, then one more ingest → 7.
    # The key with monotonically increasing epochs NEVER matches the old key.
    for product_epoch in [6, 7]:  # post-restart values
        fresh_key = _cw_key(q, {"fernway-product": product_epoch, "fernway-marketing": 7})
        assert fresh_key != stale_key, (
            f"product epoch={product_epoch} must not collide with pre-restart stale key"
        )
