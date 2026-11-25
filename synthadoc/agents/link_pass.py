# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
"""Cross-link pages that were promoted together, so a batch import is not all orphans.

With staging on, every source of a batch is decided while the wiki holds only the
template pages, and the ingest prompt may only link pages that already exist. So no
page of the batch links to another one, and lint reports nearly every page as an
orphan. This pass runs after promotion, when all the pages exist together.

It uses the wiki's own search, not an LLM: no extra cost, and a link can only point
at a page that exists. Each promoted page gets a short list of related pages, and
each of those pages links back, because an orphan needs an inbound link. Links go
in a marked "Related" section at the end of the page and the body is never edited.
The pass is idempotent: a link that is already on the page is not added again.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from synthadoc.storage.wiki import LifecycleState, SYSTEM_PAGE_SLUGS

if TYPE_CHECKING:  # pragma: no cover
    from synthadoc.storage.search import HybridSearch
    from synthadoc.storage.wiki import WikiPage, WikiStorage

logger = logging.getLogger(__name__)

RELATED_HEADING = "## Related"
RELATED_MARKER = "<!-- synthadoc:related -->"

# Only pages in circulation are linked to or from. Archived pages are retired, and a
# contradicted page is in dispute, so neither should gain new inbound links.
_LINKABLE_STATES = frozenset({LifecycleState.ACTIVE, LifecycleState.DRAFT, ""})

# A related page must score at least this fraction of the best match for the same
# page, so a long tail of weak matches is not linked just to fill the quota.
_MIN_RELATIVE_SCORE = 0.3
_QUERY_BODY_WORDS = 60

_BULLET_RE = re.compile(r"^\s*[-*+]\s+\[\[")


@dataclass
class LinkPassResult:
    # page slug -> the slugs that were added to its Related section
    added: dict[str, list[str]] = field(default_factory=dict)

    @property
    def pages_changed(self) -> int:
        return len(self.added)

    @property
    def links_added(self) -> int:
        return sum(len(v) for v in self.added.values())


def _links_to(content: str, slug: str) -> bool:
    """True when *content* already has a [[slug]], [[slug|alias]] or [[slug#anchor]]."""
    return re.search(r"\[\[" + re.escape(slug) + r"(?:[|#][^\]]*)?\]\]", content) is not None


def add_related_links(content: str, targets: list[tuple[str, str]]) -> str:
    """Return *content* with a Related bullet for each (slug, title) not yet linked.

    Bullets go under the synthadoc marker when the page has one, otherwise in a
    new "Related" section at the end. The rest of the page is left untouched.
    """
    bullets = [f"- [[{slug}]] — {title}" for slug, title in targets
               if not _links_to(content, slug)]
    if not bullets:
        return content

    if RELATED_MARKER in content:
        lines = content.split("\n")
        at = next(i for i, line in enumerate(lines) if RELATED_MARKER in line)
        end = at + 1
        while end < len(lines) and _BULLET_RE.match(lines[end]):
            end += 1
        lines[end:end] = bullets
        return "\n".join(lines)

    return content.rstrip("\n") + f"\n\n{RELATED_HEADING}\n{RELATED_MARKER}\n" + "\n".join(bullets) + "\n"


def _query_terms(page: "WikiPage") -> list[str]:
    body = " ".join((page.content or "").split()[:_QUERY_BODY_WORDS])
    return [t for t in [page.title or "", *(page.tags or []), body] if t]


def _is_linkable(page: "WikiPage | None") -> bool:
    return page is not None and (page.status or "") in _LINKABLE_STATES


def link_promoted_pages(
    store: "WikiStorage",
    search: "HybridSearch",
    slugs: list[str],
    *,
    max_per_page: int = 3,
) -> LinkPassResult:
    """Link each of *slugs* to its closest pages, and each of those back to it."""
    result = LinkPassResult()
    if max_per_page <= 0 or not slugs:
        return result

    search.invalidate_index()   # the promoted pages were just moved into wiki/
    titles: dict[str, str] = {}

    def _title(slug: str, page: "WikiPage") -> str:
        titles.setdefault(slug, page.title or slug.replace("-", " ").title())
        return titles[slug]

    # slug -> {target slug, ...}; every pair is recorded in both directions
    wanted: dict[str, dict[str, None]] = {}

    for slug in slugs:
        if slug in SYSTEM_PAGE_SLUGS:
            continue
        page = store.read_page(slug)
        if not _is_linkable(page):
            continue
        _title(slug, page)
        hits = [h for h in search.bm25_search(_query_terms(page), top_n=max_per_page + 6)
                if h.slug != slug and h.slug not in SYSTEM_PAGE_SLUGS and h.score > 0]
        if not hits:
            continue
        floor = hits[0].score * _MIN_RELATIVE_SCORE
        chosen = 0
        for hit in hits:
            if chosen >= max_per_page:
                break
            if hit.score < floor:
                break
            target = store.read_page(hit.slug)
            if not _is_linkable(target):
                continue
            _title(hit.slug, target)
            wanted.setdefault(slug, {})[hit.slug] = None
            wanted.setdefault(hit.slug, {})[slug] = None
            chosen += 1

    for slug, targets in wanted.items():
        pairs = [(t, titles[t]) for t in targets]
        before: list[str] = []

        def _apply(page: "WikiPage", _pairs=pairs, _before=before) -> None:
            updated = add_related_links(page.content or "", _pairs)
            if updated != (page.content or ""):
                _before.extend(t for t, _ in _pairs if not _links_to(page.content or "", t))
                page.content = updated

        store.update_page(slug, _apply)
        if before:
            result.added[slug] = before

    if result.added:
        search.invalidate_index()
    logger.info("link pass: %d page(s) updated, %d link(s) added (from %d promoted page(s))",
                result.pages_changed, result.links_added, len(slugs))
    return result
