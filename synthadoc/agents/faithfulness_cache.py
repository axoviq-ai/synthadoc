# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Persistence layer for faithfulness audit results.

Cache file: {wiki_root}/.synthadoc/faithfulness-cache.json
Schema: {"version": 1, "entries": {"<slug>": {"page_key": "...", "checked_at": "...", "results": [...]}}}

page_key = max(s.ingested for s in page.sources if s.ingested).
A page whose key differs from the stored key is stale; a missing entry is also stale.
Non-active pages are never included in stale computations.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from synthadoc.storage.wiki import LifecycleState

if TYPE_CHECKING:
    from synthadoc.agents.citation_faithfulness import FaithfulnessResult
    from synthadoc.storage.wiki import WikiPage, WikiStorage

_CACHE_FILENAME = "faithfulness-cache.json"


def _cache_path(wiki_root: Path) -> Path:
    return wiki_root / ".synthadoc" / _CACHE_FILENAME


def _page_key(page: "WikiPage") -> str | None:
    """Return the max ingested timestamp across all sources, as an ISO string, or None.

    YAML parsers may return date/datetime objects rather than strings when the
    ingested value is unquoted (e.g. ``ingested: 2026-07-15``).  We normalise
    to a string so the result is always JSON-serialisable and compares correctly
    against the string already stored in the cache JSON.
    """
    raw = [s.ingested for s in page.sources if s.ingested]
    if not raw:
        return None
    # Convert each value to a comparable, serialisable string.
    strs: list[str] = []
    for v in raw:
        if hasattr(v, "isoformat"):      # datetime.date / datetime.datetime
            strs.append(v.isoformat())
        else:
            strs.append(str(v))
    return max(strs)


def read_cache(wiki_root: Path) -> dict:
    """Read the cache file; return empty skeleton on missing or corrupt file."""
    path = _cache_path(wiki_root)
    if not path.exists():
        return {"version": 1, "entries": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "entries" not in data:
            return {"version": 1, "entries": {}}
        return data
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "entries": {}}


def write_cache(wiki_root: Path, cache: dict) -> None:
    """Atomically write cache to disk (write to .tmp then rename)."""
    path = _cache_path(wiki_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def get_stale_slugs(cache_entries: dict, store: "WikiStorage") -> list[str]:
    """Return slugs of active pages whose cache entry is missing or outdated."""
    stale: list[str] = []
    for slug in store.all_slugs():
        page = store.read_page(slug)
        if page is None or page.status != LifecycleState.ACTIVE:
            continue
        key = _page_key(page)
        entry = cache_entries.get(slug)
        if entry is None or entry.get("page_key") != key:
            stale.append(slug)
    return stale


def merge_results_into_cache(
    wiki_root: Path,
    results: "list[FaithfulnessResult]",
    store: "WikiStorage",
    checked_slugs: "list[str] | None" = None,
) -> None:
    """Update cache entries for every slug that appears in results.

    If checked_slugs is provided, also write empty-result entries for any
    checked slug that produced no citations — preventing them from appearing
    as stale on subsequent calls.
    """
    cache = read_cache(wiki_root)
    checked_at = datetime.now(timezone.utc).isoformat()

    by_slug: dict[str, list[dict]] = {}
    for r in results:
        by_slug.setdefault(r.slug, []).append({
            "citation_marker": r.citation_marker,
            "verdict": r.verdict,
            "reason": r.reason,
        })

    for slug, slug_results in by_slug.items():
        page = store.read_page(slug)
        key = _page_key(page) if page else None
        cache["entries"][slug] = {
            "page_key": key,
            "checked_at": checked_at,
            "results": slug_results,
        }

    # Write empty entries for checked slugs that produced no citations
    if checked_slugs:
        for slug in checked_slugs:
            if slug not in by_slug:
                page = store.read_page(slug)
                key = _page_key(page) if page else None
                cache["entries"][slug] = {
                    "page_key": key,
                    "checked_at": checked_at,
                    "results": [],
                }

    write_cache(wiki_root, cache)
