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

from synthadoc.agents.content_health_scanner import scan_page
from synthadoc.storage.wiki import LifecycleState

if TYPE_CHECKING:
    from synthadoc.agents.workflows._base import WorkflowContext

_STATUS_OK = "success"
_STATUS_ERR = "error"


async def tool_find_content_health_issues(ctx: "WorkflowContext", slug: str = "") -> dict:
    """Return all ACTIVE pages that have content health issues, sorted by severity then count.

    If ``slug`` is provided, return only that page (or empty if it has no issues /
    doesn't exist).  Use this as STEP 1 to discover which pages need repair.
    """
    if ctx.store is None:
        return {"status": _STATUS_ERR, "pages": [], "error": "No store available"}

    _SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    flagged: list[dict] = []
    for page_slug in ctx.store.list_pages():
        if slug and page_slug != slug:
            continue
        page = ctx.store.read_page(page_slug)
        if page is None or page.status != LifecycleState.ACTIVE or not page.content_health_issues:
            continue
        top_sev = min(_SEVERITY_ORDER.get(i["severity"], 9) for i in page.content_health_issues)
        flagged.append({
            "_sort": (top_sev, -len(page.content_health_issues)),
            "slug": page_slug,
            "title": page.title,
            "issue_count": len(page.content_health_issues),
            "top_severity": page.content_health_issues[0]["severity"],
            "issues": page.content_health_issues,
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
        "issues": page.content_health_issues,
    }


async def tool_write_content_health_fix(
    ctx: "WorkflowContext",
    slug: str,
    content: str,
    issues_fixed: list[str],
) -> dict:
    """Apply a content-health fix to a page.

    Snapshots the current content before writing, stores a fix_record keyed by
    the snapshot's stable DB id, then re-scans to verify the fix worked.
    The GATED_TOOLS confirm gate must be open before this tool is called.
    """
    if ctx.store is None or ctx.audit_db is None:
        return {"status": _STATUS_ERR, "error": "No store or audit_db available"}
    page = ctx.store.read_page(slug)
    if page is None:
        return {"status": _STATUS_ERR, "error": f"Page '{slug}' not found"}

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
        "remaining_issues": len(remaining),
        "fix_record": page.content_health_fix_record,
    }


async def tool_list_content_health_fixes(ctx: "WorkflowContext") -> dict:
    """Return all pages that have a content_health_fix_record, sorted by timestamp desc."""
    if ctx.store is None:
        return {"status": _STATUS_ERR, "fixes": []}
    fixes = []
    for slug in ctx.store.list_pages():
        page = ctx.store.read_page(slug)
        if page is not None and page.content_health_fix_record:
            record = page.content_health_fix_record
            fixes.append({
                "slug": slug,
                "title": page.title,
                "fixed_at": record.get("timestamp", ""),
                "issues_fixed": record.get("issues_fixed", []),
                "snapshot_id": record.get("snapshot_id"),
                "snapshot_index_before": record.get("snapshot_index_before"),
            })
    fixes.sort(key=lambda r: r["fixed_at"], reverse=True)
    return {"fixes": fixes}


async def tool_rollback_content_health_fix(ctx: "WorkflowContext", slug: str) -> dict:
    """Roll back a page to its pre-fix snapshot using the stored fix_record.

    Resolves the stored snapshot_id to its current index (since 1-based indices
    shift as new snapshots are added) then restores the page content.
    """
    if ctx.store is None or ctx.audit_db is None:
        return {"status": _STATUS_ERR, "message": "No store or audit_db available"}
    page = ctx.store.read_page(slug)
    if page is None:
        return {"status": _STATUS_ERR, "message": f"Page '{slug}' not found"}
    if not page.content_health_fix_record:
        return {"status": _STATUS_ERR, "message": f"No content health fix recorded for '{slug}'"}

    stored_snapshot_id = page.content_health_fix_record.get("snapshot_id")
    stored_snapshot_index = page.content_health_fix_record.get("snapshot_index_before", 1)

    # Resolve the current index for the stored snapshot id (robust to new snapshots added later).
    if stored_snapshot_id is not None:
        snapshots = await ctx.audit_db.list_page_snapshots(slug)
        resolved_index = next(
            (s["index"] for s in snapshots if s.get("id") == stored_snapshot_id),
            stored_snapshot_index,  # fallback to stored index if id not found
        )
    else:
        resolved_index = stored_snapshot_index

    snapshot = await ctx.audit_db.get_snapshot_by_index(slug, resolved_index)
    if snapshot is None or snapshot.get("content_snapshot") is None:
        return {
            "status": _STATUS_ERR,
            "message": f"Snapshot {resolved_index} for '{slug}' not found in audit log",
        }

    restored_content = snapshot["content_snapshot"]
    page.content = restored_content
    page.content_health_fix_record = None
    # Restore issues from the original content.
    page.content_health_issues = [asdict(i) for i in scan_page(slug, restored_content)]
    ctx.store.write_page(slug, page)
    if ctx.bump_epoch:
        ctx.bump_epoch()

    return {
        "status": _STATUS_OK,
        "slug": slug,
        "rolled_back_to_snapshot": resolved_index,
        "message": f"'{slug}' rolled back to snapshot #{resolved_index}",
    }
