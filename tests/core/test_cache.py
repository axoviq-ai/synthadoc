# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from synthadoc.core.cache import CacheManager, make_cache_key, CACHE_VERSION


@pytest.mark.asyncio
async def test_miss_returns_none(tmp_wiki):
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    assert await cache.get("missing") is None


@pytest.mark.asyncio
async def test_set_and_get(tmp_wiki):
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    await cache.set("k1", {"result": "Paris"})
    result = await cache.get("k1")
    assert result["result"] == "Paris"


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
    await cache.set("a", {"v": 1})
    await cache.set("b", {"v": 2})
    await cache.set("c", {"v": 3})

    removed = await cache.clear()
    assert removed == 3
    assert await cache.get("a") is None
    assert await cache.get("b") is None


@pytest.mark.asyncio
async def test_clear_on_empty_cache_returns_zero(tmp_wiki):
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    assert await cache.clear() == 0


@pytest.mark.asyncio
async def test_clear_also_wipes_query_cache(tmp_wiki):
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    await cache.set("r1", {"v": 1})
    await cache.set_query("q1", epoch=1, result={"answer": "x"})
    await cache.set_query("q2", epoch=1, result={"answer": "y"})
    removed = await cache.clear()
    assert removed == 3
    assert await cache.get("r1") is None
    assert await cache.get_query("q1") is None
    assert await cache.get_query("q2") is None


@pytest.mark.asyncio
async def test_get_query_returns_none_on_miss(tmp_path):
    """get_query returns None when no matching entry exists."""
    from synthadoc.core.cache import CacheManager
    cm = CacheManager(tmp_path / "cache.db")
    await cm.init()
    result = await cm.get_query("nonexistent-key")
    assert result is None


@pytest.mark.asyncio
async def test_set_and_get_query_round_trip(tmp_path):
    """set_query then get_query must return the stored dict."""
    from synthadoc.core.cache import CacheManager
    cm = CacheManager(tmp_path / "cache.db")
    await cm.init()
    payload = {"answer": "42", "citations": ["page-a"], "knowledge_gap": False}
    await cm.set_query("abc123", epoch=1, result=payload)
    stored = await cm.get_query("abc123")
    assert stored == payload


@pytest.mark.asyncio
async def test_query_cache_cleanup_removes_old_epochs(tmp_path):
    """cleanup_query_cache removes entries with epoch < current_epoch - 5."""
    from synthadoc.core.cache import CacheManager
    cm = CacheManager(tmp_path / "cache.db")
    await cm.init()
    await cm.set_query("old-key", epoch=1, result={"answer": "old"})
    await cm.set_query("new-key", epoch=10, result={"answer": "new"})
    await cm.cleanup_query_cache(current_epoch=10)
    assert await cm.get_query("old-key") is None
    assert await cm.get_query("new-key") is not None


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
    # At current_epoch=10, threshold is 5. epoch=5 is NOT < 5, so it should be kept.
    await cm.set_query("boundary-key", epoch=5, result={"answer": "boundary"})
    await cm.cleanup_query_cache(current_epoch=10)
    assert await cm.get_query("boundary-key") is not None


@pytest.mark.asyncio
async def test_query_cache_cleanup_removes_below_boundary(tmp_path):
    """Entry at epoch = current_epoch - 6 must be REMOVED."""
    from synthadoc.core.cache import CacheManager
    cm = CacheManager(tmp_path / "cache.db")
    await cm.init()
    # At current_epoch=10, threshold is 5. epoch=4 IS < 5, so it should be removed.
    await cm.set_query("below-key", epoch=4, result={"answer": "below"})
    await cm.cleanup_query_cache(current_epoch=10)
    assert await cm.get_query("below-key") is None


@pytest.mark.asyncio
async def test_set_query_overwrites_existing_entry(tmp_path):
    """Calling set_query twice for the same key must return the second value."""
    from synthadoc.core.cache import CacheManager
    cm = CacheManager(tmp_path / "cache.db")
    await cm.init()
    await cm.set_query("key-x", epoch=1, result={"answer": "first"})
    await cm.set_query("key-x", epoch=2, result={"answer": "second"})
    stored = await cm.get_query("key-x")
    assert stored == {"answer": "second"}
