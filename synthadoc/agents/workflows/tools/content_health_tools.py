# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tool functions for ContentHealthResolverWorkflow.

These are also registered in query_agent so rollback and list tools are
available via natural language at any time, not just during a workflow run.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from synthadoc.agents.content_health_fixes import (
    dropped_sentences, heading_mismatch_error, merge_duplicate_sections, text_loss_error,
)
from synthadoc.agents.content_health_scanner import resolvable_issues, scan_page
from synthadoc.agents.workflows._rollback import restore_page_snapshot
from synthadoc.agents.workflows._tools import tool_confirm, unified_diff_preview
from synthadoc.storage.wiki import LifecycleState

if TYPE_CHECKING:
    from synthadoc.agents.workflows._base import WorkflowContext

_STATUS_OK = "success"
_STATUS_ERR = "error"

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
# The confirm card's diff viewer scrolls, so show whole-page merges in full
# (a real duplicate merge on a 4,000-word page produced a 120-line diff).
_CONFIRM_DIFF_MAX_LINES = 400


async def tool_find_content_health_issues(ctx: "WorkflowContext", slug: str = "") -> dict:
    """Return all ACTIVE pages that have resolvable content health issues, sorted by severity then count.

    Report-only issue types (thin sections, which need new facts) are left out;
    they stay on the page for the lint report.

    If ``slug`` is provided, return only that page (or empty if it has no issues /
    doesn't exist).  Use this as STEP 1 to discover which pages need repair.
    """
    if ctx.store is None:
        return {"status": _STATUS_ERR, "pages": [], "error": "No store available"}

    flagged: list[dict] = []
    for page_slug in ctx.store.list_pages():
        if slug and page_slug != slug:
            continue
        page = ctx.store.read_page(page_slug)
        if page is None or page.status != LifecycleState.ACTIVE:
            continue
        issues = resolvable_issues(page.content_health_issues)
        if not issues:
            continue
        top_sev = min(SEVERITY_ORDER.get(i["severity"], 9) for i in issues)
        flagged.append({
            "_sort": (top_sev, -len(issues)),
            "slug": page_slug,
            "title": page.title,
            "issue_count": len(issues),
            "top_severity": issues[0]["severity"],
            "issues": issues,
        })

    flagged.sort(key=lambda r: r["_sort"])
    for r in flagged:
        del r["_sort"]

    return {"status": _STATUS_OK, "total": len(flagged), "pages": flagged}


async def tool_get_page_content(ctx: "WorkflowContext", slug: str) -> dict:
    """Read the raw markdown content and existing health issues for a page."""
    if ctx.store is None:
        return {"status": _STATUS_ERR, "error": "No store available"}
    page = ctx.store.read_page(slug)
    if page is None:
        return {"status": _STATUS_ERR, "error": f"Page '{slug}' not found"}
    return {
        "status": _STATUS_OK,
        "slug": slug,
        "title": page.title,
        "content": page.content,
        "issues": resolvable_issues(page.content_health_issues),
    }


async def confirm_page_change(
    ctx: "WorkflowContext", slug: str, current: str, proposed: str, summary: str,
    yes_label: str = "Approve",
) -> bool:
    """Ask the user to approve a page change, showing the real unified diff."""
    gate = await tool_confirm(
        ctx, message=summary, yes_label=yes_label, no_label="Skip this page",
        diff=unified_diff_preview(slug, current, proposed, max_lines=_CONFIRM_DIFF_MAX_LINES),
    )
    return bool(gate.get("confirmed"))


async def tool_apply_content_health_fix(
    ctx: "WorkflowContext",
    slug: str,
    content: str,
    issues_fixed: list[str],
) -> dict:
    """Show the user the real diff of a proposed fix, then write it if approved.

    The approval card is built from the actual current and proposed content, never
    from a model's description of the change. A rewrite that drops a sentence is
    rejected before the user is asked.
    """
    if ctx.store is None:
        return {"status": _STATUS_ERR, "error": "No store available"}
    page = ctx.store.read_page(slug)
    if page is None:
        return {"status": _STATUS_ERR, "error": f"Page '{slug}' not found"}
    rejection = text_loss_error(slug, page.content, content)
    if rejection is None:
        rejection = heading_mismatch_error(slug, page.content, content, issues_fixed=issues_fixed)
    if rejection:
        return rejection
    summary = (
        f"**{slug}** — apply content-health fix ({', '.join(map(str, issues_fixed)) or 'structural'})?\n\n"
        "Every sentence of the current page is kept (checked before this card)."
    )
    if not await confirm_page_change(ctx, slug, page.content, content, summary):
        return {"status": "cancelled", "slug": slug,
                "message": f"Fix for '{slug}' skipped by the user."}
    return await tool_write_content_health_fix(ctx, slug=slug, content=content,
                                               issues_fixed=issues_fixed)


async def tool_write_content_health_fix(
    ctx: "WorkflowContext",
    slug: str,
    content: str,
    issues_fixed: list[str],
    *,
    skip_heading_check: bool = False,
) -> dict:
    """Apply a content-health fix to a page.

    Snapshots the current content before writing, stores a fix_record keyed by
    the snapshot's stable DB id, then re-scans to verify the fix worked.
    The GATED_TOOLS confirm gate must be open before this tool is called.

    Rejects (writes nothing) a rewrite that drops any prose sentence of the
    current page: the model's own BEFORE/AFTER summary cannot be trusted to
    report lost text, e.g. when duplicate sections hold different sentences.
    Also rejects a heading change not accounted for by ``issues_fixed``, unless
    ``skip_heading_check`` is set (the pure-Python duplicate-merge path
    legitimately removes duplicate headings on purpose).
    """
    if ctx.store is None or ctx.audit_db is None:
        return {"status": _STATUS_ERR, "error": "No store or audit_db available"}
    page = ctx.store.read_page(slug)
    if page is None:
        return {"status": _STATUS_ERR, "error": f"Page '{slug}' not found"}

    rejection = text_loss_error(slug, page.content, content)
    if rejection:
        return rejection

    if not skip_heading_check:
        rejection = heading_mismatch_error(slug, page.content, content, issues_fixed=issues_fixed)
        if rejection:
            return rejection

    # Snapshot CURRENT content (pre-fix) so it can be restored on rollback.
    await ctx.audit_db.snapshot_if_changed(
        slug, page.content, triggered_by="content-health-fix", reason="content-health-fix"
    )
    # Get the snapshot that was just recorded (index 1 = newest).
    snapshots = await ctx.audit_db.list_page_snapshots(slug)
    snapshot_id = snapshots[0]["id"] if snapshots else None
    snapshot_index = 1

    page.content = content
    page.content_health_fix_record = {
        "slug": slug,
        "snapshot_id": snapshot_id,
        "snapshot_index_before": snapshot_index,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "issues_fixed": issues_fixed,
    }

    # Re-scan to verify and update the stored issue list.
    remaining = scan_page(slug, content)
    page.content_health_issues = [asdict(i) for i in remaining]

    ctx.store.write_page(slug, page)
    if ctx.bump_epoch:
        ctx.bump_epoch()

    return {
        "status": _STATUS_OK,
        "slug": slug,
        "snapshot_id": snapshot_id,
        "snapshot_index": snapshot_index,
        "remaining_issues": len(resolvable_issues(page.content_health_issues)),
        "fix_record": page.content_health_fix_record,
    }


async def tool_merge_duplicate_sections(ctx: "WorkflowContext", slug: str) -> dict:
    """Merge a page's duplicate sections in Python (no LLM), after user approval.

    Every later copy of a duplicated heading is folded into the first one, keeping
    every sentence and dropping only word-for-word repeats (see
    :func:`merge_duplicate_sections`). Shows the real diff for approval, then
    writes through :func:`tool_write_content_health_fix`, so the page gets
    the same snapshot, fix record and re-scan as any other fix.
    """
    if ctx.store is None:
        return {"status": _STATUS_ERR, "error": "No store available"}
    page = ctx.store.read_page(slug)
    if page is None:
        return {"status": _STATUS_ERR, "error": f"Page '{slug}' not found"}

    merge = merge_duplicate_sections(page.content)
    if not merge.merged:
        return {
            "status": _STATUS_OK, "slug": slug, "merged": [], "skipped": merge.skipped,
            "message": "No duplicate sections could be merged automatically.",
        }

    summary = (
        f"**{slug}** — merge duplicate sections: {', '.join(merge.merged)}\n\n"
        "Later copies are folded into the first one. Every sentence is kept; only "
        "paragraphs repeated word for word are dropped, so the merged text may read "
        f"repetitively and is worth a human edit ({len(page.content)} → {len(merge.content)} chars)."
    )
    if not await confirm_page_change(ctx, slug, page.content, merge.content, summary, yes_label="Merge"):
        return {"status": "cancelled", "slug": slug,
                "message": f"Merge of duplicate sections on '{slug}' skipped by the user."}

    result = await tool_write_content_health_fix(
        ctx, slug=slug, content=merge.content,
        issues_fixed=[f"duplicate_section x{len(merge.merged)} (merged, no sentences dropped)"],
        skip_heading_check=True,
    )
    return {**result, "merged": merge.merged, "skipped": merge.skipped}


async def tool_dismiss_content_health_issues(
    ctx: "WorkflowContext",
    slug: str,
    reason: str,
) -> dict:
    """Dismiss all current content health issues on a page without modifying content.

    Use this when every remaining issue requires adding factual content (e.g.
    all issues are 'thin_section') and cannot be resolved by structural fixes.
    Clears the resolvable ``content_health_issues`` from the page frontmatter so
    the hint chip stops surfacing it (report-only issues stay for the lint report),
    and records the dismissal in ``content_health_fix_record``.
    Does NOT snapshot the page — content is unchanged.

    Always call ``notify`` FIRST to explain to the user what is being dismissed
    and why, then call this tool to persist the dismissal.
    """
    if ctx.store is None:
        return {"status": _STATUS_ERR, "error": "No store available"}
    page = ctx.store.read_page(slug)
    if page is None:
        return {"status": _STATUS_ERR, "error": f"Page '{slug}' not found"}

    dismissed = resolvable_issues(page.content_health_issues)
    dismissed_count = len(dismissed)
    dismissed_types = list({i.get("type", "unknown") for i in dismissed})

    # Report-only issues (thin sections) stay so the lint report still lists them.
    page.content_health_issues = [i for i in page.content_health_issues if i not in dismissed]
    # Merge into any existing fix_record so prior structural fixes aren't lost.
    existing = page.content_health_fix_record or {}
    existing.update({
        "dismissed_at": datetime.now(timezone.utc).isoformat(),
        "dismissed_count": dismissed_count,
        "dismissed_types": dismissed_types,
        "dismissed_reason": reason,
    })
    if "slug" not in existing:
        existing["slug"] = slug
    if "timestamp" not in existing:
        existing["timestamp"] = existing["dismissed_at"]
    if "issues_fixed" not in existing:
        existing["issues_fixed"] = []
    page.content_health_fix_record = existing

    ctx.store.write_page(slug, page)
    if ctx.bump_epoch:
        ctx.bump_epoch()

    return {
        "status": _STATUS_OK,
        "slug": slug,
        "dismissed_count": dismissed_count,
        "dismissed_types": dismissed_types,
        "remaining_issues": 0,
        "reason": reason,
    }


async def tool_list_content_health_fixes(ctx: "WorkflowContext") -> dict:
    """Return all pages that have a content_health_fix_record, sorted by timestamp desc.

    ``action`` says what the workflow did: "fixed" (content rewritten, pre-fix
    snapshot saved), "dismissed" (issues cleared, content unchanged, so there is no
    snapshot), or "fixed+dismissed" (rewritten, then the remaining issues dismissed).
    """
    if ctx.store is None:
        return {"status": _STATUS_ERR, "fixes": []}
    fixes = []
    for slug in ctx.store.list_pages():
        page = ctx.store.read_page(slug)
        if page is not None and page.content_health_fix_record:
            record = page.content_health_fix_record
            fixed = _has_snapshot(record)
            dismissed = "dismissed_at" in record
            entry = {
                "slug": slug,
                "title": page.title,
                "action": "fixed+dismissed" if fixed and dismissed else "dismissed" if dismissed else "fixed",
                "fixed_at": record.get("timestamp", ""),
                "issues_fixed": record.get("issues_fixed", []),
                "snapshot_id": record.get("snapshot_id"),
                "snapshot_index_before": record.get("snapshot_index_before"),
            }
            if dismissed:
                entry.update({
                    "dismissed_at": record.get("dismissed_at"),
                    "dismissed_count": record.get("dismissed_count", 0),
                    "dismissed_types": record.get("dismissed_types", []),
                    "dismissed_reason": record.get("dismissed_reason", ""),
                })
            fixes.append(entry)
    fixes.sort(key=lambda r: r["fixed_at"], reverse=True)
    return {"fixes": fixes}


def _has_snapshot(record: dict) -> bool:
    """True when the record belongs to a content rewrite (a pre-fix snapshot exists)."""
    return record.get("snapshot_id") is not None or "snapshot_index_before" in record


async def tool_rollback_content_health_fix(ctx: "WorkflowContext", slug: str) -> dict:
    """Roll back a page to its pre-fix snapshot using the stored fix_record.

    Resolves the stored snapshot_id to its current index (since 1-based indices
    shift as new snapshots are added) then restores the page content.

    A dismissal-only record has no snapshot because the content was never changed;
    rolling it back undoes the dismissal (issues re-scanned from the current
    content) and leaves the content as it is.
    """
    if ctx.store is None or ctx.audit_db is None:
        return {"status": _STATUS_ERR, "message": "No store or audit_db available"}
    page = ctx.store.read_page(slug)
    if page is None:
        return {"status": _STATUS_ERR, "message": f"Page '{slug}' not found"}
    if not page.content_health_fix_record:
        return {"status": _STATUS_ERR, "message": f"No content health fix recorded for '{slug}'"}

    if not _has_snapshot(page.content_health_fix_record):
        page.content_health_fix_record = None
        page.content_health_issues = [asdict(i) for i in scan_page(slug, page.content)]
        ctx.store.write_page(slug, page)
        if ctx.bump_epoch:
            ctx.bump_epoch()
        restored = len(page.content_health_issues)
        return {
            "status": _STATUS_OK,
            "slug": slug,
            "restored_issues": restored,
            "message": (
                f"Dismissal undone for '{slug}': {restored} issue(s) restored. "
                "Content was not changed (a dismissal never edits the page)."
            ),
        }

    stored_snapshot_id = page.content_health_fix_record.get("snapshot_id")
    stored_snapshot_index = page.content_health_fix_record.get("snapshot_index_before", 1)

    restore_result = await restore_page_snapshot(
        ctx, slug, stored_snapshot_id, stored_snapshot_index,
    )
    if restore_result["status"] != _STATUS_OK:
        return {"status": _STATUS_ERR, "message": restore_result["error"]}

    resolved_index = restore_result["resolved_index"]
    restored_content = restore_result["restored_content"]
    page = ctx.store.read_page(slug)
    page.content_health_fix_record = None
    page.content_health_issues = [asdict(i) for i in scan_page(slug, restored_content)]
    ctx.store.write_page(slug, page)

    return {
        "status": _STATUS_OK,
        "slug": slug,
        "rolled_back_to_snapshot": resolved_index,
        "message": f"'{slug}' rolled back to snapshot #{resolved_index}",
    }
