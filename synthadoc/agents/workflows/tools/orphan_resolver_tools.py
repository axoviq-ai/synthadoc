# synthadoc/agents/workflows/tools/orphan_resolver_tools.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
"""Orphan-resolver-specific tool functions.

Domain tools whose logic is specific to the orphan-resolver workflow.
Generic tools (read_page_content, propose_and_apply, confirm, notify)
live in _tools.py and are reused directly.
"""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from synthadoc.agents.lint_agent import find_orphan_slugs
from synthadoc.agents.workflows._tools import tool_confirm
from synthadoc.storage.wiki import LifecycleState

if TYPE_CHECKING:
    from synthadoc.agents.workflows._base import WorkflowContext

_log = logging.getLogger(__name__)

# Wikilink pattern: [[slug]] or [[slug|display]] or [[slug#anchor]]
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:[|#][^\]]+)?\]\]")

_TOKENS_PER_ORPHAN_UPPER = 24_000   # 4 strategies × ~6 000 tokens each
_USD_PER_1K_TOKENS = 0.003
_SECONDS_PER_ORPHAN = 120


# ---------------------------------------------------------------------------
# tool_find_orphaned_pages
# ---------------------------------------------------------------------------

async def tool_find_orphaned_pages(ctx: "WorkflowContext") -> dict:
    """Return all active pages that have no inbound [[wikilinks]] from other active pages.

    Delegates to find_orphan_slugs() from lint_agent — the canonical graph-level
    computation. Only active pages enter the graph.

    Returns: {"orphans": [slug, ...], "count": N}
    """
    if ctx.store is None:
        return {"orphans": [], "count": 0}

    page_texts: dict[str, str] = {}
    for slug in ctx.store.list_pages():
        page = ctx.store.read_page(slug)
        if page and page.status == LifecycleState.ACTIVE:
            page_texts[slug] = page.content or ""

    orphans = find_orphan_slugs(page_texts)
    return {"orphans": orphans, "count": len(orphans)}


# ---------------------------------------------------------------------------
# tool_verify_orphan_resolved
# ---------------------------------------------------------------------------

async def tool_verify_orphan_resolved(
    ctx: "WorkflowContext", orphan_slug: str
) -> dict:
    """Re-run find_orphan_slugs() to check if orphan_slug has been resolved.

    Must be called AFTER tool_propose_and_apply so the page on disk has been
    updated.  Performs a full graph-level recomputation — the only reliable way
    to confirm resolution.

    Returns: {"resolved": bool, "linked_by": [slugs that now reference orphan_slug]}
    """
    if ctx.store is None:
        return {"resolved": False, "linked_by": []}

    page_texts: dict[str, str] = {}
    for slug in ctx.store.list_pages():
        page = ctx.store.read_page(slug)
        if page and page.status == LifecycleState.ACTIVE:
            page_texts[slug] = page.content or ""

    # Guard: if the slug is not in the active page set at all (e.g. the page was
    # archived or deleted), it trivially won't appear in remaining_orphans — which
    # would cause a false resolved=True.  Return False so callers can distinguish
    # "genuinely resolved" from "never tracked".
    if orphan_slug not in page_texts:
        return {"resolved": False, "linked_by": []}

    remaining_orphans = find_orphan_slugs(page_texts)

    if orphan_slug not in remaining_orphans:
        # Collect which pages now contain a wikilink to orphan_slug
        linked_by: list[str] = []
        for slug, text in page_texts.items():
            if slug == orphan_slug:
                continue
            for m in _WIKILINK_RE.finditer(text):
                target = m.group(1).strip().lower().replace(" ", "-")
                if target == orphan_slug:
                    linked_by.append(slug)
                    break
        return {"resolved": True, "linked_by": linked_by}

    return {"resolved": False, "linked_by": []}


# ---------------------------------------------------------------------------
# tool_estimate_and_confirm
# ---------------------------------------------------------------------------

async def tool_estimate_and_confirm(
    ctx: "WorkflowContext", orphan_count: int
) -> dict:
    """Show a cost/time estimate and request user approval before any edits.

    Combines the estimate notice and the confirm gate into a single tool call
    (same pattern as tool_cost_estimate in contradiction_resolver_tools).
    Do NOT call tool_confirm separately after this.

    Returns: {"confirmed": bool, "orphan_count": int, "estimated_usd": float}
    """
    estimated_usd = (orphan_count * _TOKENS_PER_ORPHAN_UPPER / 1000) * _USD_PER_1K_TOKENS
    estimated_minutes = max(1, orphan_count * (_SECONDS_PER_ORPHAN // 60))
    estimated_calls = 3 + orphan_count * 15

    message = (
        f"Orphan Resolver — Cost Estimate\n"
        f"  Pages to process:    {orphan_count}\n"
        f"  Estimated tool calls: ~{estimated_calls}\n"
        f"  Estimated time:       ~{estimated_minutes} min\n"
        f"  Estimated cost:       ~${estimated_usd:.2f} USD\n"
        f"\nProceed with orphan resolver?"
    )
    result = await tool_confirm(ctx, message, yes_label="Proceed", no_label="Cancel")
    return {
        **result,
        "orphan_count": orphan_count,
        "estimated_usd": round(estimated_usd, 4),
    }


# ---------------------------------------------------------------------------
# tool_search_orphan_candidates
# ---------------------------------------------------------------------------

async def tool_search_orphan_candidates(
    ctx: "WorkflowContext",
    orphan_slug: str,
    strategy: str,
    exclude_slugs: list[str] | None = None,
) -> dict:
    """Find candidate pages that could naturally reference the orphan.

    strategy values (try in order across 4 attempts):
      "title_bm25"          — BM25 search using orphan slug/title keywords
      "content_bm25"        — BM25 search using key terms from orphan's first paragraph
      "full_title_scan"     — return all active page titles for LLM selection (no BM25)
      "contextual_reasoning"— return orphan body + all titles for LLM structural reasoning

    exclude_slugs: slugs already tried across all prior attempts; never returned again.
    The tool adds newly returned candidates to tried_slugs so callers track exclusions.

    Returns:
      For title_bm25 / content_bm25:
        {"candidates": [slug, ...], "strategy": str, "tried_slugs": [slug, ...]}

      For full_title_scan:
        {"candidates": [], "all_page_titles": [{"slug": str, "title": str}, ...],
         "strategy": str, "tried_slugs": [slug, ...]}

      For contextual_reasoning:
        {"candidates": [], "all_page_titles": [...], "orphan_content": str,
         "strategy": str, "tried_slugs": [slug, ...]}

      On any error: {"candidates": [], "error": str, "strategy": str, "tried_slugs": [...]}
    """
    exclude: set[str] = set(exclude_slugs or [])
    exclude.add(orphan_slug)  # self-links are never useful

    if strategy == "title_bm25":
        if ctx.search is None:
            return {"candidates": [], "strategy": strategy,
                    "tried_slugs": list(exclude), "error": "search unavailable"}
        query_terms = orphan_slug.replace("-", " ").replace("_", " ").split()
        results = ctx.search.bm25_search(query_terms, top_n=10)
        candidates = [r.slug for r in results if r.slug not in exclude][:5]
        return {
            "candidates": candidates,
            "strategy": strategy,
            "tried_slugs": list(exclude | set(candidates)),
        }

    elif strategy == "content_bm25":
        if ctx.search is None or ctx.store is None:
            return {"candidates": [], "strategy": strategy,
                    "tried_slugs": list(exclude), "error": "search or store unavailable"}
        page = ctx.store.read_page(orphan_slug)
        if not page or not page.content:
            return {"candidates": [], "strategy": strategy, "tried_slugs": list(exclude)}
        # Extract meaningful words from the first 300 characters of the page body
        first_chunk = (page.content or "")[:300]
        words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9]{2,}\b", first_chunk)
        query_terms = list(dict.fromkeys(words))[:10]   # dedup, preserve order
        results = ctx.search.bm25_search(query_terms, top_n=10)
        candidates = [r.slug for r in results if r.slug not in exclude][:5]
        return {
            "candidates": candidates,
            "strategy": strategy,
            "tried_slugs": list(exclude | set(candidates)),
        }

    elif strategy in ("full_title_scan", "contextual_reasoning"):
        if ctx.store is None:
            return {"candidates": [], "all_page_titles": [], "strategy": strategy,
                    "tried_slugs": list(exclude), "error": "store unavailable"}
        all_pages: list[dict] = []
        for slug in ctx.store.list_pages():
            if slug in exclude:
                continue
            page = ctx.store.read_page(slug)
            if page and page.status == LifecycleState.ACTIVE:
                all_pages.append({"slug": slug, "title": page.title or slug})

        result: dict = {
            "candidates": [],           # LLM selects from all_page_titles
            "all_page_titles": all_pages,
            "strategy": strategy,
            "tried_slugs": list(exclude),
        }
        if strategy == "contextual_reasoning":
            orphan_page = ctx.store.read_page(orphan_slug)
            result["orphan_content"] = (orphan_page.content or "") if orphan_page else ""
        return result

    else:
        return {
            "candidates": [],
            "strategy": strategy,
            "tried_slugs": list(exclude),
            "error": f"Unknown strategy: {strategy!r}",
        }
