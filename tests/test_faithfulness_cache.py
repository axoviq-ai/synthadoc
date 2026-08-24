# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Unit tests for faithfulness_cache module."""
from __future__ import annotations
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from synthadoc.agents.faithfulness_cache import (
    _page_key,
    read_cache,
    write_cache,
    get_stale_slugs,
    merge_results_into_cache,
)
from synthadoc.agents.citation_faithfulness_agent import FaithfulnessResult
from synthadoc.storage.wiki import WikiPage, SourceRef, WikiStorage


def _make_source(ingested: str) -> SourceRef:
    return SourceRef(file="src.txt", hash="", size=0, ingested=ingested)


def _make_page(ingested_timestamps: list[str]) -> WikiPage:
    return WikiPage(
        title="T", tags=[], content="", status="active", confidence="high",
        sources=[_make_source(ts) for ts in ingested_timestamps],
    )


def _make_wiki_storage(tmp_path: Path, pages: dict[str, WikiPage]) -> WikiStorage:
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    store = WikiStorage(wiki_dir)
    for slug, page in pages.items():
        store.write_page(slug, page)
    return store


# -- _page_key -----------------------------------------------------------------

def test_page_key_no_sources():
    page = _make_page([])
    assert _page_key(page) is None


def test_page_key_single_source():
    page = _make_page(["2026-08-15T10:00:00Z"])
    assert _page_key(page) == "2026-08-15T10:00:00Z"


def test_page_key_max_of_multiple():
    page = _make_page(["2026-08-10T00:00:00Z", "2026-08-15T10:00:00Z", "2026-08-01T00:00:00Z"])
    assert _page_key(page) == "2026-08-15T10:00:00Z"


def test_page_key_skips_empty_ingested():
    page = _make_page(["", "2026-08-15T10:00:00Z", ""])
    assert _page_key(page) == "2026-08-15T10:00:00Z"


def test_page_key_date_object():
    """PyYAML parses bare date values (e.g. 'ingested: 2026-04-08') as date objects.
    _page_key must normalise these to ISO strings so json.dumps doesn't raise."""
    page = WikiPage(
        title="T", tags=[], content="", status="active", confidence="high",
        sources=[SourceRef(file="s.txt", hash="", size=0, ingested=date(2026, 4, 8))],  # type: ignore[arg-type]
    )
    result = _page_key(page)
    assert isinstance(result, str)
    assert result == "2026-04-08"


def test_page_key_datetime_object():
    """datetime objects are also normalised to ISO strings."""
    dt = datetime(2026, 8, 15, 10, 0, 0, tzinfo=timezone.utc)
    page = WikiPage(
        title="T", tags=[], content="", status="active", confidence="high",
        sources=[SourceRef(file="s.txt", hash="", size=0, ingested=dt)],  # type: ignore[arg-type]
    )
    result = _page_key(page)
    assert isinstance(result, str)
    assert result == dt.isoformat()


def test_page_key_date_is_json_serializable(tmp_path):
    """After the fix, merge_results_into_cache must not raise TypeError for date-type ingested."""
    import json as _json
    from synthadoc.agents.faithfulness_cache import merge_results_into_cache as _merge

    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    store = WikiStorage(wiki_dir)
    page = WikiPage(
        title="T", tags=[], content="", status="active", confidence="high",
        sources=[SourceRef(file="s.txt", hash="", size=0, ingested=date(2026, 4, 8))],  # type: ignore[arg-type]
    )
    store.write_page("test-slug", page)
    # Should not raise TypeError
    _merge(tmp_path, [], store, checked_slugs=["test-slug"])
    cache = read_cache(tmp_path)
    assert cache["entries"]["test-slug"]["page_key"] == "2026-04-08"


# -- read_cache / write_cache --------------------------------------------------

def test_read_cache_missing_file(tmp_path):
    result = read_cache(tmp_path)
    assert result == {"version": 1, "entries": {}}


def test_read_cache_corrupt_file(tmp_path):
    cache_file = tmp_path / ".synthadoc" / "faithfulness-cache.json"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text("NOT JSON", encoding="utf-8")
    result = read_cache(tmp_path)
    assert result == {"version": 1, "entries": {}}


def test_write_and_read_roundtrip(tmp_path):
    cache = {
        "version": 1,
        "entries": {
            "bell-labs": {
                "page_key": "2026-08-15T10:00:00Z",
                "checked_at": "2026-08-21T14:00:00Z",
                "results": [{"citation_marker": "^[src.txt:1-3]", "verdict": "supported", "reason": "ok"}],
            }
        },
    }
    write_cache(tmp_path, cache)
    loaded = read_cache(tmp_path)
    assert loaded["entries"]["bell-labs"]["page_key"] == "2026-08-15T10:00:00Z"
    assert loaded["entries"]["bell-labs"]["results"][0]["verdict"] == "supported"


# -- get_stale_slugs -----------------------------------------------------------

def test_get_stale_slugs_missing_entry(tmp_path):
    store = _make_wiki_storage(tmp_path, {"bell-labs": _make_page(["2026-08-15T10:00:00Z"])})
    stale = get_stale_slugs({}, store)
    assert "bell-labs" in stale


def test_get_stale_slugs_key_mismatch(tmp_path):
    store = _make_wiki_storage(tmp_path, {"bell-labs": _make_page(["2026-08-15T10:00:00Z"])})
    entries = {"bell-labs": {"page_key": "2026-08-01T00:00:00Z", "checked_at": "", "results": []}}
    stale = get_stale_slugs(entries, store)
    assert "bell-labs" in stale


def test_get_stale_slugs_fresh(tmp_path):
    store = _make_wiki_storage(tmp_path, {"bell-labs": _make_page(["2026-08-15T10:00:00Z"])})
    entries = {"bell-labs": {"page_key": "2026-08-15T10:00:00Z", "checked_at": "", "results": []}}
    stale = get_stale_slugs(entries, store)
    assert "bell-labs" not in stale


def test_get_stale_slugs_skips_non_active(tmp_path):
    page = WikiPage(title="T", tags=[], content="", status="draft", confidence="high",
                    sources=[_make_source("2026-08-15T10:00:00Z")])
    store = _make_wiki_storage(tmp_path, {"draft-page": page})
    stale = get_stale_slugs({}, store)
    assert "draft-page" not in stale


# -- merge_results_into_cache --------------------------------------------------

def test_merge_results_into_cache(tmp_path):
    store = _make_wiki_storage(tmp_path, {"bell-labs": _make_page(["2026-08-15T10:00:00Z"])})
    results = [FaithfulnessResult(slug="bell-labs", citation_marker="^[src.txt:1-2]",
                                   verdict="supported", reason="ok")]
    merge_results_into_cache(tmp_path, results, store)
    cache = read_cache(tmp_path)
    assert "bell-labs" in cache["entries"]
    assert cache["entries"]["bell-labs"]["page_key"] == "2026-08-15T10:00:00Z"
    assert cache["entries"]["bell-labs"]["results"][0]["verdict"] == "supported"


def test_merge_results_preserves_other_entries(tmp_path):
    store = _make_wiki_storage(tmp_path, {
        "bell-labs": _make_page(["2026-08-15T10:00:00Z"]),
        "transistor": _make_page(["2026-08-10T09:00:00Z"]),
    })
    existing = {
        "version": 1,
        "entries": {
            "transistor": {
                "page_key": "2026-08-10T09:00:00Z",
                "checked_at": "2026-08-20T00:00:00Z",
                "results": [{"citation_marker": "^[t.txt:1-1]", "verdict": "drift", "reason": "x"}],
            }
        },
    }
    write_cache(tmp_path, existing)
    results = [FaithfulnessResult(slug="bell-labs", citation_marker="^[src.txt:1-2]",
                                   verdict="supported", reason="ok")]
    merge_results_into_cache(tmp_path, results, store)
    cache = read_cache(tmp_path)
    assert cache["entries"]["transistor"]["results"][0]["verdict"] == "drift"
    assert "bell-labs" in cache["entries"]


def test_merge_results_stamps_citation_free_slug(tmp_path):
    """A checked slug with no results gets an empty cache entry (not permanently stale)."""
    store = _make_wiki_storage(tmp_path, {"no-citations": _make_page(["2026-08-15T10:00:00Z"])})
    merge_results_into_cache(tmp_path, [], store, checked_slugs=["no-citations"])
    cache = read_cache(tmp_path)
    assert "no-citations" in cache["entries"]
    assert cache["entries"]["no-citations"]["results"] == []
    assert cache["entries"]["no-citations"]["page_key"] == "2026-08-15T10:00:00Z"


def test_get_stale_slugs_citation_free_after_stamp(tmp_path):
    """After stamping a citation-free page, it is no longer stale."""
    store = _make_wiki_storage(tmp_path, {"no-citations": _make_page(["2026-08-15T10:00:00Z"])})
    merge_results_into_cache(tmp_path, [], store, checked_slugs=["no-citations"])
    cache = read_cache(tmp_path)
    stale = get_stale_slugs(cache["entries"], store)
    assert "no-citations" not in stale
