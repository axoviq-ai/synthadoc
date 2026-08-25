# synthadoc/agents/workflows/contradiction_resolver_tools.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Contradiction-resolver-specific tool functions.

Only tools whose logic is specific to the contradiction domain belong here.
Generic tools (read_page_content, run_scoped_lint, propose_and_apply,
transition_lifecycle_state, get_wiki_status) live in _tools.py so all
future workflows can reuse them.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from synthadoc.storage.wiki import LifecycleState

if TYPE_CHECKING:
    from synthadoc.agents.workflows._base import WorkflowContext

_log = logging.getLogger(__name__)

_TOKENS_PER_PAGE_UPPER = 4000
_USD_PER_1K_TOKENS = 0.003
_SECONDS_PER_PAGE = 90


async def tool_get_contradicted_pages(
    ctx: "WorkflowContext", scope: str = "all"
) -> dict:
    """List contradicted pages, classified by contradiction type.

    scope: "all" | "gate" | "conflict"
    Returns: {"pages": [{"slug", "type", "warnings_count", "contradiction_note"}]}
    type values: "gate" | "conflict" | "both" | "unknown"
    """
    results: list[dict] = []
    for slug in ctx.store.list_pages():
        page = ctx.store.read_page(slug)
        if page is None or page.status != LifecycleState.CONTRADICTED:
            continue
        has_warnings = bool(page.lint_warnings)
        has_note = bool(page.contradiction_note)

        if has_warnings and has_note:
            page_type = "both"
        elif has_warnings:
            page_type = "gate"
        elif has_note:
            page_type = "conflict"
        else:
            page_type = "unknown"

        if scope == "gate" and page_type not in ("gate", "both"):
            continue
        if scope == "conflict" and page_type not in ("conflict", "both"):
            continue

        results.append({
            "slug": slug,
            "type": page_type,
            "warnings_count": len(page.lint_warnings or []),
            "contradiction_note": page.contradiction_note,
        })
    return {"pages": results}


async def tool_read_source_content(ctx: "WorkflowContext", slug: str) -> dict:
    """Return source text for a contradicted page using a layered fallback.

    Fallback order:
    1. raw_sources/<source_file>       — original ingest content
    2. .synthadoc/extracted/<stem>.txt — pre-processed text
    3. contradiction_note              — minimal context when sources are missing
    4. Empty string                    — fallback_used="none"

    Returns: {"slug", "source_text", "source_path", "fallback_used"}
    """
    page = ctx.store.read_page(slug)
    if page is None:
        return {"error": f"Page not found: {slug!r}"}

    for src in (page.sources or []):
        if not src.file:
            continue
        # 1. raw_sources/
        raw_path = ctx.wiki_root / "raw_sources" / src.file
        if raw_path.exists():
            try:
                text = raw_path.read_text(encoding="utf-8", errors="replace")
                return {"slug": slug, "source_text": text[:8000],
                        "source_path": str(raw_path), "fallback_used": "raw_sources"}
            except OSError:
                pass
        # 2. .synthadoc/extracted/
        extracted_dir = ctx.wiki_root / ".synthadoc" / "extracted"
        stem = src.file.rsplit(".", 1)[0] if "." in src.file else src.file
        for candidate in (src.file, f"{stem}.txt"):
            ext_path = extracted_dir / candidate
            if ext_path.exists():
                try:
                    text = ext_path.read_text(encoding="utf-8", errors="replace")
                    return {"slug": slug, "source_text": text[:8000],
                            "source_path": str(ext_path), "fallback_used": "extracted"}
                except OSError:
                    pass

    # 3. contradiction_note
    if page.contradiction_note:
        return {"slug": slug, "source_text": page.contradiction_note,
                "source_path": None, "fallback_used": "contradiction_note"}

    return {"slug": slug, "source_text": "", "source_path": None, "fallback_used": "none"}


async def tool_cost_estimate(ctx: "WorkflowContext", page_count: int) -> dict:
    """Upper-bound cost estimate AND user approval gate (combined).

    Sends the estimate as a notice SSE event so the user sees it immediately,
    then calls tool_confirm internally to ask whether to proceed.  Combining
    both steps into one tool call prevents the LLM from accidentally producing
    a plain-text summary between the estimate and the approval request, which
    would terminate the workflow loop prematurely.

    Returns: {"confirmed": bool, "pages", "estimated_tokens",
              "estimated_usd", "estimated_minutes"}
    """
    from synthadoc.agents.workflows._tools import tool_confirm  # avoid circular at module level

    tokens = _TOKENS_PER_PAGE_UPPER * max(page_count, 1)
    usd = (tokens / 1000) * _USD_PER_1K_TOKENS
    minutes = max(1, (page_count * _SECONDS_PER_PAGE) // 60)
    estimate = {
        "pages": page_count,
        "estimated_tokens": tokens,
        "estimated_usd": round(usd, 4),
        "estimated_minutes": minutes,
    }

    # Show the estimate as a notice so the user can read it while the ConfirmCard loads.
    notice_text = (
        f"Updated estimate: {page_count} page(s), "
        f"~${estimate['estimated_usd']:.2f}, "
        f"about {estimate['estimated_minutes']} minute(s)."
    )
    try:
        await ctx.send_sse_event("notice", {"text": notice_text})
    except Exception:  # noqa: BLE001
        pass

    # Ask for approval — this blocks until the user responds (or 120 s timeout).
    confirm_result = await tool_confirm(
        ctx,
        message=(
            f"**Contradiction Resolver — ready to start**\n\n"
            f"- Pages to process: **{page_count}**\n"
            f"- Estimated cost: ~**${estimate['estimated_usd']:.2f}**\n"
            f"- Estimated time: ~**{estimate['estimated_minutes']} min**\n\n"
            "Proceed with resolution?"
        ),
        yes_label="Proceed",
        no_label="Cancel",
    )

    return {**estimate, "confirmed": confirm_result.get("confirmed", False)}
