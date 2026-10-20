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
import re as _re
from enum import StrEnum
from typing import TYPE_CHECKING

from synthadoc.storage.wiki import LifecycleState

if TYPE_CHECKING:
    from synthadoc.agents.workflows._base import WorkflowContext

_log = logging.getLogger(__name__)

_TOKENS_PER_PAGE_UPPER = 4000
_USD_PER_1K_TOKENS = 0.003
_SECONDS_PER_PAGE = 90


class ContradictionPageType(StrEnum):
    """Classification of a contradicted page, returned by tool_get_contradicted_pages.

    GATE     -- has adversarial lint warnings only (no contradiction_note)
    CONFLICT -- has a contradiction_note only (no lint warnings)
    BOTH     -- has both lint warnings and a contradiction_note
    UNKNOWN  -- contradicted status set but neither warnings nor note present
    """

    GATE = "gate"
    CONFLICT = "conflict"
    BOTH = "both"
    UNKNOWN = "unknown"


async def tool_get_contradicted_pages(
    ctx: "WorkflowContext", scope: str = "all"
) -> dict:
    """List contradicted pages, classified by contradiction type.

    scope: "all" | "gate" | "conflict"
    Returns: {"pages": [{"slug", "type", "warnings_count", "contradiction_note"}]}
    type values: ContradictionPageType members (StrEnum -- compare freely with strings)
    """
    PT = ContradictionPageType
    results: list[dict] = []
    for slug in ctx.store.list_pages():
        page = ctx.store.read_page(slug)
        if page is None or page.status != LifecycleState.CONTRADICTED:
            continue
        has_warnings = bool(page.lint_warnings)
        has_note = bool(page.contradiction_note)

        if has_warnings and has_note:
            page_type = PT.BOTH
        elif has_warnings:
            page_type = PT.GATE
        elif has_note:
            page_type = PT.CONFLICT
        else:
            page_type = PT.UNKNOWN

        if scope == "gate" and page_type not in (PT.GATE, PT.BOTH):
            continue
        if scope == "conflict" and page_type not in (PT.CONFLICT, PT.BOTH):
            continue

        results.append({
            "slug": slug,
            "type": page_type,
            "warnings_count": len(page.lint_warnings or []),
            "contradiction_note": page.contradiction_note,
        })
    return {"pages": results}


def _extract_note_source_file(note: str) -> str | None:
    """Parse a contradiction_note for the ingest source filename.

    The ingest agent writes notes in the form:
      "Flagged while ingesting 'first-compiler-controversy.md': ..."
    Returns the bare filename, or None if not found.
    """
    m = _re.search(r"ingesting\s+['\"]([^'\"]+)['\"]", note, _re.IGNORECASE)
    return m.group(1) if m else None


async def tool_read_source_content(ctx: "WorkflowContext", slug: str) -> dict:
    """Return source text for a contradicted page using a layered fallback.

    Fallback order:
    1. raw_sources/<source_file>       -- original ingest content (page.sources)
    2. .synthadoc/extracted/<stem>.txt -- pre-processed text (page.sources)
    3. raw_sources/<note_source_file>  -- source named in contradiction_note
    4. contradiction_note              -- minimal context when sources are missing
    5. Empty string                    -- fallback_used="none"

    Returns: {"slug", "source_text", "source_path", "fallback_used"}
    """
    page = ctx.store.read_page(slug)
    if page is None:
        return {"error": f"Page not found: {slug!r}"}

    for src in (page.sources or []):
        if not src.file:
            continue
        raw_path = ctx.wiki_root / "raw_sources" / src.file
        if raw_path.exists():
            try:
                text = raw_path.read_text(encoding="utf-8", errors="replace")
                return {"slug": slug, "source_text": text[:8000],
                        "source_path": str(raw_path), "fallback_used": "raw_sources"}
            except OSError:
                pass
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

    if page.contradiction_note:
        note_file = _extract_note_source_file(page.contradiction_note)
        if note_file:
            note_raw = ctx.wiki_root / "raw_sources" / note_file
            if note_raw.exists():
                try:
                    text = note_raw.read_text(encoding="utf-8", errors="replace")
                    return {"slug": slug, "source_text": text[:8000],
                            "source_path": str(note_raw), "fallback_used": "note_source"}
                except OSError:
                    pass

    if page.contradiction_note:
        return {"slug": slug, "source_text": page.contradiction_note,
                "source_path": None, "fallback_used": "contradiction_note"}

    return {"slug": slug, "source_text": "", "source_path": None, "fallback_used": "none"}


async def tool_cost_estimate(ctx: "WorkflowContext", page_count: int) -> dict:
    """Upper-bound cost estimate AND user approval gate (combined).

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

    cost_label = ctx.cost_label(estimate["estimated_usd"])

    notice_text = (
        f"Updated estimate: {page_count} page(s), "
        f"{cost_label}, "
        f"about {estimate['estimated_minutes']} minute(s)."
    )
    try:
        await ctx.send_sse_event("notice", {"text": notice_text})
    except Exception:  # noqa: BLE001
        pass

    confirm_result = await tool_confirm(
        ctx,
        message=(
            f"**Contradiction Resolver -- ready to start**\n\n"
            f"- Pages to process: **{page_count}**\n"
            f"- Estimated cost: **{cost_label}**\n"
            f"- Estimated time: ~**{estimate['estimated_minutes']} min**\n\n"
            "Proceed with resolution?"
        ),
        yes_label="Proceed",
        no_label="Cancel",
    )

    return {**estimate, "confirmed": confirm_result.get("confirmed", False)}


def _format_cr_summary(
    fixed: list[dict],
    unresolved: list[dict],
    skipped: list[str],
    wiki_status: dict,
) -> str:
    """Render the Contradiction Resolver final summary as a markdown string."""
    lines: list[str] = ["**Contradiction Resolver -- Complete**", ""]

    lines.append(f"**Fixed ({len(fixed)}):**")
    if fixed:
        for item in fixed:
            lines.append(f"- {item['slug']} -- {item['note']}")
    else:
        lines.append("- (none)")

    lines.append("")
    lines.append(f"**Unresolved ({len(unresolved)}):**")
    if unresolved:
        for item in unresolved:
            lines.append(f"- {item['slug']}: {item['reason']}")
        lines.append("")
        lines.append(
            "_Tip: re-run the contradiction resolver for multi-strategy "
            "retry on unresolved pages._"
        )
    else:
        lines.append("- (none)")

    lines.append("")
    lines.append(f"**Skipped ({len(skipped)}):**")
    if skipped:
        for s in skipped:
            lines.append(f"- {s}")
    else:
        lines.append("- (none)")

    status_str = ", ".join(
        f"{k}: {v}" for k, v in wiki_status.items()
        if k not in ("tool", "message")
    )
    lines.append("")
    lines.append(f"**Wiki status (live):** {status_str}")

    return "\n".join(lines)


async def tool_format_summary(
    ctx: "WorkflowContext",
    fixed: list[dict],
    unresolved: list[dict],
    skipped: list[str],
) -> dict:
    """Format and emit the final Contradiction Resolver summary (CLI-provider path).

    Returns: {"status": "success", "summary": <formatted text>}
    """
    from synthadoc.agents.workflows._tools import (  # avoid circular at module level
        tool_get_wiki_status,
    )

    wiki_status = await tool_get_wiki_status(ctx)
    text = _format_cr_summary(fixed, unresolved, skipped, wiki_status)

    await ctx.send_sse_event("token", {"text": text})
    await ctx.send_sse_event("final_text", {"text": text})

    return {"status": "success", "summary": text}
