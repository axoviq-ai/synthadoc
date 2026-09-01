# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Shared tool functions for agentic workflow loops.

Each function is intended to be curried with ``functools.partial(tool_fn, ctx)``
so the loop runner can call ``fn(**tool_input)`` without knowing about the
WorkflowContext.
"""
from __future__ import annotations

import asyncio
import difflib
import os
import re
import time
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from synthadoc.agents.workflows._base import WorkflowContext

from synthadoc.agents.lint_agent import (
    _citation_source_names,
    find_broken_citation_refs,
    find_broken_wikilink_refs,
)
from synthadoc.agents.scaffold_agent import scaffold_output_paths
from synthadoc.core.queue import JobStatus

# Retry delays (seconds) when the job queue is temporarily unavailable.
# The first attempt uses 0 delay; subsequent attempts use these values.
_INGEST_RETRY_DELAYS: list[int] = [2, 4, 8]


class ToolStatus(str, Enum):
    """Tool-call result status codes returned by workflow tool functions.

    Distinct from :class:`~synthadoc.core.queue.JobStatus`, which represents
    the state of a queued background job.  These codes describe the *outcome
    of a single tool call* as seen by the LLM loop.

    Because this is a ``str`` mixin enum, members compare equal to their plain
    string values (``ToolStatus.SUCCESS == "success"`` is ``True``).  Return
    dicts therefore store plain string literals — transparent to LLM
    serialisation via ``str(result_dict)`` — while comparison sites use the
    typed members to eliminate magic strings.
    """
    SUCCESS = "success"
    FAILED  = "failed"
    TIMEOUT = "timeout"
    ERROR   = "error"


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


def _resolve_source_path(wiki_root: Path, raw_file: str) -> str:
    """Resolve a source file path stored in page metadata to an absolute string.

    URLs (http/https) are returned as-is — they are re-ingested directly by the
    ingest agent.  Absolute local paths are returned as-is.  Relative paths
    (legacy format, e.g. ``"public-domain/foo.txt"``) are first tried directly
    under *wiki_root*; if that file doesn't exist the path is retried under
    ``wiki_root/raw_sources/``.
    """
    if raw_file.startswith(("http://", "https://")):
        return raw_file
    if os.path.isabs(raw_file):
        return raw_file
    candidate = wiki_root / raw_file
    if not candidate.exists():
        candidate = wiki_root / "raw_sources" / raw_file
    return str(candidate)


async def _resolve_stale_pages(ctx: "WorkflowContext") -> list[dict]:
    """Return stale page descriptors.

    Each dict has keys ``slug``, ``source_path`` (str or None), and
    ``stale_since`` (str).
    """
    all_states = await ctx.audit_db.get_live_page_states(ctx.store.page_exists)
    stale = [p for p in all_states if p.get("state") == "stale"]
    result: list[dict] = []
    for p in stale:
        page = ctx.store.read_page(p["slug"])
        raw_file = page.sources[0].file if page and page.sources else None
        source_path: str | None = (
            _resolve_source_path(ctx.wiki_root, raw_file) if raw_file is not None else None
        )
        result.append(
            {
                "slug": p["slug"],
                "source_path": source_path,
                "stale_since": p.get("updated") or p.get("created") or "unknown",
            }
        )
    return result


# ---------------------------------------------------------------------------
# Public tool functions
# ---------------------------------------------------------------------------


async def tool_find_page_source(ctx: "WorkflowContext", slug: str) -> dict:
    """Look up the source file path for any wiki page by slug, regardless of lifecycle state.

    Returns::

        {"slug": str, "source_path": str}  — page found with a local source file
        {"error": str}                      — page not found or has no local source
    """
    page = ctx.store.read_page(slug)
    if page is None:
        return {"error": f"Page {slug!r} not found in this wiki"}
    raw_file = page.sources[0].file if page.sources else None
    if raw_file is None:
        return {"error": f"Page {slug!r} has no local source file recorded"}
    source_path = _resolve_source_path(ctx.wiki_root, raw_file)
    await ctx.send_sse_event(
        "tool_progress",
        {"tool": "find_page_source", "message": f"Found source for {slug}"},
    )
    return {"slug": slug, "source_path": source_path}


async def tool_find_stale_pages(ctx: "WorkflowContext") -> dict:
    """Return ``{"pages": [...]}`` or ``{"error": str, "pages": []}``."""
    try:
        pages = await _resolve_stale_pages(ctx)
        n = len(pages)
        label = f"Found {n} stale page{'s' if n != 1 else ''}" if pages else "No stale pages found"
        await ctx.send_sse_event("tool_progress", {"tool": "find_stale_pages", "message": label})
        return {"pages": pages}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "pages": []}


async def tool_ingest_source(ctx: "WorkflowContext", source_path: str) -> dict:
    """Enqueue an ingest job for *source_path*, wait for it to finish, and return the outcome.

    Accepts both local file paths and URLs (http/https).  For local paths the
    file must exist on disk; for URLs the ingest agent handles fetching directly.

    Returns::

        {"status": "success", "message": str}  — ingest completed successfully
        {"status": "failed",  "message": str}  — job reached a terminal failure state
        {"status": "timeout", "message": str}  — job did not complete within 300 s
        {"error": str}                          — validation error (bad path, file missing)
    """
    is_url = source_path.startswith(("http://", "https://"))

    if is_url:
        label = source_path
    else:
        # Must be an absolute path — relative paths are ambiguous on the server.
        if not os.path.isabs(source_path):
            return {"error": f"source_path must be an absolute path, got: {source_path!r}"}
        path = Path(source_path)
        if not path.exists():
            return {"error": f"File not found: {source_path!r}"}
        label = path.name

    await ctx.send_sse_event("tool_progress", {"tool": "ingest_source", "message": f"Re-ingesting: {label}"})

    # Enqueue.  force=True bypasses the dedup check so stale pages are always
    # re-ingested.  bust_cache=False lets the analysis/citation caches be used
    # when the source content is unchanged — the cache key is a content hash, so
    # genuinely changed sources still trigger fresh LLM analysis regardless.
    # allow_external_paths=True: the tool runs server-side (always localhost), so
    # source files outside the wiki root are safe to re-ingest — they are paths
    # already stored in the wiki metadata from the original ingest.
    last_error: str | None = None
    job_id: str | None = None
    for delay in [0] + _INGEST_RETRY_DELAYS:
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            job_id = await ctx.queue.enqueue(
                "ingest", {"source": source_path, "force": True, "bust_cache": False,
                           "allow_external_paths": True}
            )
            break
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)

    if job_id is None:
        return {"error": f"Failed to enqueue after retries: {last_error}"}

    # Poll until terminal so the caller gets the outcome in a single tool call.
    # Include job_id in the response so the caller can optionally verify via poll_job.
    result = await tool_poll_job(ctx, job_id, timeout_seconds=300, job_label=f"Ingest: {label}")
    result["job_id"] = job_id

    status = result.get("status", ToolStatus.FAILED)
    if status == ToolStatus.SUCCESS:
        await ctx.send_sse_event("tool_progress", {"tool": "ingest_source", "message": f"✓ {label} re-ingested"})
    elif status == ToolStatus.TIMEOUT:
        await ctx.send_sse_event("tool_progress", {"tool": "ingest_source", "message": f"✗ {label}: timed out"})
    else:
        await ctx.send_sse_event("tool_progress", {"tool": "ingest_source", "message": f"✗ {label}: failed"})
    return result


async def tool_poll_job(
    ctx: "WorkflowContext",
    job_id: str,
    timeout_seconds: int = 240,
    job_label: str = "Job",
) -> dict:
    """Poll a job until it reaches a terminal state or the timeout expires.

    Returns::

        {"status": "success",  "message": str}  — job completed successfully
        {"status": "failed",   "message": str}  — job hit a terminal failure state
        {"status": "timeout",  "message": str}  — timed out before terminal state
    """
    start = time.monotonic()
    attempt = 0

    while True:
        elapsed = time.monotonic() - start
        if elapsed >= timeout_seconds:
            return {
                "status": "timeout",
                "message": f"Job {job_id} timed out after {int(elapsed)}s",
            }

        try:
            job = await ctx.queue.get_job(job_id)
        except Exception as exc:  # noqa: BLE001
            return {"status": "failed", "message": f"Queue error for job {job_id}: {exc}"}

        if job is not None and job.status.is_terminal:
            if job.status == JobStatus.COMPLETED:
                return {
                    "status": ToolStatus.SUCCESS,
                    "message": f"Job {job_id} completed successfully",
                }
            return {
                "status": "failed",
                "message": f"Job {job_id} ended with status {job.status.value!r}",
            }

        await ctx.send_sse_event(
            "tool_progress",
            {
                "tool": "poll_job",
                "job_id": job_id,
                "message": f"{job_label} running... ({int(elapsed)}s)",
            },
        )
        await asyncio.sleep(min(1 * (2**attempt), 30))
        attempt += 1


async def tool_run_lint(ctx: "WorkflowContext", scope: str = "all") -> dict:
    """Enqueue a lint job, poll until it completes, and return the final status.

    Mirrors ``tool_ingest_source``: the caller gets a single blocking call
    rather than a job_id that needs a separate ``poll_job`` follow-up.

    Returns::

        {"status": "success",  "message": str}  — lint completed
        {"status": "failed",   "message": str}  — lint hit a terminal failure
        {"status": "timeout",  "message": str}  — timed out (5 min limit)
        {"error": str}                           — failed to enqueue
    """
    await ctx.send_sse_event("tool_progress", {"tool": "run_lint", "message": "Running wiki lint check..."})
    try:
        job_id = await ctx.queue.enqueue(
            "lint",
            {
                "scope": scope,
                "auto_resolve": False,
                "adversarial": False,
                "lifecycle": True,
            },
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}

    return await tool_poll_job(ctx, job_id, timeout_seconds=300, job_label="Lint")


async def tool_get_lint_report(ctx: "WorkflowContext") -> dict:
    """Read the full lint state from the audit DB and page frontmatter.

    Returns::

        {
          "last_run": {
            "timestamp": str, "dangling_removed": int, "orphans": int,
            "contradictions_resolved": int, "contradictions_flagged": int
          },
          "contradicted_pages": [{"slug": str, "since": str}],
          "adversarial_warnings": [{"slug": str, "count": int}],
          "orphan_slugs": [str]
        }

    "last_run" is an empty dict if no lint run has been recorded yet.
    """
    await ctx.send_sse_event(
        "tool_progress",
        {"tool": "get_lint_report", "message": "Reading lint report..."},
    )
    summary = await ctx.audit_db.get_last_lint_summary() if ctx.audit_db else None

    all_states = await ctx.audit_db.get_live_page_states(ctx.store.page_exists) \
        if ctx.audit_db else []
    contradicted = [
        {"slug": p["slug"], "since": (p.get("updated_at") or "")[:10]}
        for p in all_states if p.get("state") == "contradicted"
    ]

    warned: list[dict] = []
    orphan_slugs: list[str] = []
    if ctx.store:
        for slug in ctx.store.list_pages():
            page = ctx.store.read_page(slug)
            if page and page.lint_warnings:
                warned.append({"slug": slug, "count": len(page.lint_warnings)})
            if page and page.orphan:
                orphan_slugs.append(slug)
        warned.sort(key=lambda x: x["count"], reverse=True)
        orphan_slugs.sort()

    return {
        "last_run": summary or {},
        "contradicted_pages": contradicted,
        "adversarial_warnings": warned,
        "orphan_slugs": orphan_slugs,
    }


async def tool_get_page_states(ctx: "WorkflowContext", slugs: list[str]) -> dict:
    """Return the current lifecycle state of one or more wiki pages by slug.

    Returns::

        {"pages": [{"slug": str, "state": str}]}

    ``state`` is one of ``"active"``, ``"stale"``, ``"draft"``, ``"archived"``,
    or ``"unknown"`` if the page has no lifecycle record yet.
    """
    results: list[dict] = []
    for slug in slugs:
        try:
            row = await ctx.audit_db.get_page_state(slug)
            state = row["state"] if row else "unknown"
        except Exception:  # noqa: BLE001
            state = "unknown"
        results.append({"slug": slug, "state": state})
    await ctx.send_sse_event(
        "tool_progress",
        {"tool": "get_page_states", "message": "Checking page states after re-ingest..."},
    )
    return {"pages": results}


# Extracts wikilink slug, excluding display text and anchors: [[slug]], [[slug|text]], [[slug#anchor]]
_WIKILINK_SCAN_RE = re.compile(r"\[\[([^\]|#]+?)(?:[|#][^\]]*)?\]\]")
# Matches every valid ^[...] citation marker shape (including malformed ones without line range)
_CITATION_MARKER_RE = re.compile(r"^\^\[[^\]]*\]$")

# Captures slug + optional suffix (|display or #anchor) for targeted replacement
_WIKILINK_REPLACE_RE = re.compile(r"\[\[([^\]|#]+?)((?:[|#][^\]]*))?\]\]")


def _normalize_slug(raw: str) -> str:
    return raw.strip().lower().replace(" ", "-")


def _apply_single_fix(content: str, old_ref: str, new_ref: str | None) -> tuple[str, int]:
    """Replace all [[old_ref]] occurrences with [[new_ref]] or plain display text.

    Returns (updated_content, number_of_replacements).
    """
    changes = 0

    def _replacer(m: re.Match) -> str:
        nonlocal changes
        if _normalize_slug(m.group(1)) != old_ref:
            return m.group(0)
        suffix = m.group(2) or ""
        changes += 1
        if new_ref:
            return f"[[{new_ref}{suffix}]]"
        # Remove link — keep display text if present, else the raw slug text
        if suffix.startswith("|"):
            return suffix[1:]
        return m.group(1).strip()

    return _WIKILINK_REPLACE_RE.sub(_replacer, content), changes


async def tool_find_broken_wikilinks(
    ctx: "WorkflowContext",
    page_slug: str | None = None,
) -> dict:
    """Scan wiki pages for ``[[slug]]`` references that resolve to no existing page.

    If *page_slug* is given, only that one page is scanned (single-page mode).
    Otherwise all active pages are scanned.

    Stale, draft, and archived pages are excluded from the scan — they must be
    promoted to active first to be included.

    Uses ``difflib.get_close_matches`` (stdlib) to suggest fuzzy corrections.

    Returns::

        {
          "pages":        [{"slug": str, "broken_links": [{"ref": str, "suggestion": str|null}]}],
          "scanned":      int,   # number of pages scanned
          "total_broken": int,   # total broken link references found
        }
    """
    all_states = await ctx.audit_db.get_live_page_states(ctx.store.page_exists)
    active_slugs: set[str] = {p["slug"] for p in all_states if p.get("state") == "active"}
    all_slugs: list[str] = ctx.store.all_slugs()
    all_slug_set: set[str] = set(all_slugs)

    # Single-page mode: restrict to the requested slug (must be active).
    if page_slug is not None:
        scan_slugs: set[str] = {page_slug} if page_slug in active_slugs else set()
        scope_label = f"page '{page_slug}'"
    else:
        scan_slugs = active_slugs
        scope_label = f"{len(active_slugs)} active page{'s' if len(active_slugs) != 1 else ''}"

    await ctx.send_sse_event(
        "tool_progress",
        {"tool": "find_broken_wikilinks",
         "message": f"Scanning {scope_label} for broken wikilinks..."},
    )

    # Build page_texts for the pages in scope so find_broken_wikilink_refs can
    # work as a pure function (no store access inside).
    page_texts: dict[str, str] = {}
    page_title: str | None = None   # populated in single-page mode for use in LLM summary
    for slug in sorted(scan_slugs):
        page = ctx.store.read_page(slug)
        if not page or not page.content:
            continue
        if page_slug is not None:
            page_title = page.title or None   # surface display title for summary
        page_texts[slug] = page.content

    # Delegate detection to the shared pure function (reused by /lifecycle/status).
    broken_by_slug = find_broken_wikilink_refs(page_texts, all_slug_set)

    # Enrich with fuzzy suggestions for display in the confirm message.
    pages_with_issues: list[dict] = []
    total_broken = 0
    for slug in sorted(broken_by_slug):
        enriched: list[dict] = []
        for dead_ref in broken_by_slug[slug]:
            matches = difflib.get_close_matches(dead_ref, all_slugs, n=1, cutoff=0.72)
            enriched.append({"ref": dead_ref, "suggestion": matches[0] if matches else None})
        pages_with_issues.append({"slug": slug, "broken_links": enriched})
        total_broken += len(enriched)

    n_pages = len(pages_with_issues)
    if n_pages:
        msg = (
            f"Found {total_broken} broken wikilink{'s' if total_broken != 1 else ''} "
            f"across {n_pages} page{'s' if n_pages != 1 else ''}"
        )
    else:
        msg = f"No broken wikilinks found on {scope_label}"

    await ctx.send_sse_event("tool_progress", {"tool": "find_broken_wikilinks", "message": msg})
    result: dict = {"pages": pages_with_issues, "scanned": len(scan_slugs), "total_broken": total_broken}
    if page_slug is not None:
        result["page_title"] = page_title   # display title for use in single-page summary
    return result


async def tool_find_broken_citations(
    ctx: "WorkflowContext",
    page_slug: str | None = None,
) -> dict:
    """Scan wiki pages for broken source citation markers.

    Returns a dict with keys: pages, total_issues, scanned.

    Active-page determination uses the store directly (frontmatter ``status:
    active``) rather than the audit DB, so this tool is consistent with
    ``GET /lifecycle/status`` which drives the pre-prompt chip.  The audit DB
    is not the right filter here: pages can have ``status: active`` in their
    frontmatter without a corresponding audit-DB entry (e.g. wiki imports),
    and those pages would show a broken-citation chip but then appear clean
    to the workflow — a confusing mismatch.
    """
    extracted_dir = Path(ctx.wiki_root) / ".synthadoc" / "extracted"

    if page_slug is not None:
        # Single-page mode: check existence and active status via the store.
        page_check = ctx.store.read_page(page_slug)
        if page_check is not None and page_check.status == "active":
            scan_slugs: list[str] | None = [page_slug]
        else:
            scan_slugs = []
        scope_label = f"page '{page_slug}'"
    else:
        # Whole-wiki mode: pass None so find_broken_citation_refs calls
        # store.list_pages() and filters by frontmatter status itself.
        scan_slugs = None
        scope_label = "active pages"

    await ctx.send_sse_event(
        "tool_progress",
        {"tool": "find_broken_citations",
         "message": f"Scanning {scope_label} for broken citation markers..."},
    )

    if page_slug is not None and not scan_slugs:
        # Requested slug is inactive or doesn't exist — return empty immediately.
        broken_by_slug: dict[str, list[dict]] = {}
    else:
        broken_by_slug = find_broken_citation_refs(
            ctx.store, extracted_dir,
            slugs=scan_slugs,
        )

    pages_with_issues: list[dict] = []
    total_issues = 0
    for slug in sorted(broken_by_slug):
        page = ctx.store.read_page(slug)
        page_sources: list[str] = []
        if page and page.sources:
            for s in page.sources:
                page_sources.extend(sorted(_citation_source_names(s.file)))
        pages_with_issues.append({
            "slug": slug,
            "title": page.title if page else None,
            "issues": broken_by_slug[slug],
            "page_sources": page_sources,
        })
        total_issues += len(broken_by_slug[slug])

    n_pages = len(pages_with_issues)
    n_scanned = len(scan_slugs) if scan_slugs is not None else len(ctx.store.list_pages())
    if n_pages:
        msg = (
            f"Found {total_issues} broken citation{'s' if total_issues != 1 else ''} "
            f"across {n_pages} page{'s' if n_pages != 1 else ''}"
        )
    else:
        msg = f"No broken citations found on {scope_label}"

    await ctx.send_sse_event("tool_progress", {"tool": "find_broken_citations", "message": msg})
    return {"pages": pages_with_issues, "scanned": n_scanned, "total_issues": total_issues}


async def tool_apply_citation_fixes(
    ctx: "WorkflowContext",
    page_slug: str,
    fixes: list[dict],
) -> dict:
    """Apply citation marker patches to a single wiki page.

    Each entry in *fixes* is a dict with keys old_citation and new_citation.
    new_citation=None removes the marker; a string value replaces it.
    """
    page = ctx.store.read_page(page_slug)
    if page is None:
        return {"status": ToolStatus.ERROR, "error": f"Page {page_slug!r} not found", "changes": 0, "page": page_slug}

    content = page.content or ""
    total_changes = 0
    for fix in fixes:
        old_citation = fix.get("old_citation", "").strip()
        new_citation = fix.get("new_citation") or None  # empty string treated as removal
        if not old_citation:
            continue
        # Guard against a hallucinated or truncated value that would globally replace
        # arbitrary text. Skip any fix whose old_citation is not shaped like a citation marker.
        if not _CITATION_MARKER_RE.match(old_citation):
            continue
        if new_citation is not None:
            updated = content.replace(old_citation, new_citation)
        else:
            updated = content.replace(old_citation, "")
        if updated != content:
            total_changes += 1
            content = updated

    if total_changes == 0:
        return {"status": ToolStatus.SUCCESS, "changes": 0, "page": page_slug}

    page.content = content
    with ctx.store.page_lock(page_slug):
        ctx.store.write_page(page_slug, page)

    n = total_changes
    await ctx.send_sse_event(
        "tool_progress",
        {"tool": "apply_citation_fixes",
         "message": f"{page_slug}: {n} citation{'s' if n != 1 else ''} fixed"},
    )
    return {"status": ToolStatus.SUCCESS, "changes": total_changes, "page": page_slug}


async def tool_apply_link_fixes(
    ctx: "WorkflowContext",
    page_slug: str,
    fixes: list[dict],
) -> dict:
    """Apply wikilink corrections to a single wiki page's content.

    Each entry in *fixes* is ``{"old_ref": str, "new_ref": str | null}``.
    ``new_ref=null`` removes the link entirely, keeping any display text.

    Writes directly to the wiki store (same path used by ``cascade_archive``).

    Returns::

        {"status": "success", "changes": int, "page": str}
        {"status": "error",   "error": str}
    """
    page = ctx.store.read_page(page_slug)
    if page is None:
        return {"status": ToolStatus.ERROR, "error": f"Page {page_slug!r} not found"}

    content = page.content
    total_changes = 0
    for fix in fixes:
        old_ref = fix.get("old_ref", "").strip()
        new_ref = fix.get("new_ref") or None  # treat empty string as None
        if not old_ref:
            continue
        content, n = _apply_single_fix(content, old_ref, new_ref)
        total_changes += n

    if total_changes == 0:
        return {"status": ToolStatus.SUCCESS, "changes": 0, "page": page_slug}

    page.content = content
    with ctx.store.page_lock(page_slug):
        ctx.store.write_page(page_slug, page)

    await ctx.send_sse_event(
        "tool_progress",
        {"tool": "apply_link_fixes",
         "message": f"✓ {page_slug}: {total_changes} link{'s' if total_changes != 1 else ''} fixed"},
    )
    return {"status": ToolStatus.SUCCESS, "changes": total_changes, "page": page_slug}


async def tool_get_scaffold_preview(ctx: "WorkflowContext") -> dict:
    """Return the domain and list of files that a scaffold run will overwrite.

    Reads the domain from the workflow context (set from wiki config at
    startup).  Lists every file the scaffold job unconditionally writes plus
    ``ROUTING.md`` when it already exists (it is regenerated, not created from
    scratch).

    Returns::

        {"domain": str, "files_to_overwrite": [str]}
    """
    domain = ctx.domain or "General"

    routing_exists = (ctx.wiki_root / "ROUTING.md").exists()
    files = [str(p) for p in scaffold_output_paths(ctx.wiki_root, include_routing=routing_exists)]

    await ctx.send_sse_event(
        "tool_progress",
        {"tool": "get_scaffold_preview", "message": f"Domain: {domain!r}"},
    )
    return {"domain": domain, "files_to_overwrite": files}


async def tool_run_scaffold(ctx: "WorkflowContext", domain: str) -> dict:
    """Ask for confirmation then enqueue a scaffold job, wait for it to finish.

    Sends a ``confirm_request`` SSE to the client before enqueueing the job.
    If the user declines (or the 120-second timeout fires), returns a
    ``"cancelled"`` status without touching any files.

    Returns::

        {"status": "success", "domain": str, "categories_updated": int,
         "routing_regenerated": bool}
        {"status": "cancelled", "message": str}   — user declined or timeout
        {"status": "failed"|"timeout", "message": str}
        {"error": str}  — enqueue failed
    """
    # Build the list of files that will be overwritten so the confirm dialog
    # is informative (mirrors tool_get_scaffold_preview logic).
    routing_exists = (ctx.wiki_root / "ROUTING.md").exists()
    files = scaffold_output_paths(ctx.wiki_root, include_routing=routing_exists)
    file_lines = "\n".join(f"  • {p}" for p in files)
    confirm_message = (
        f"Scaffold will overwrite the following files for domain **{domain}**:\n\n"
        f"{file_lines}\n\n"
        "User-written content above the `<!-- synthadoc:scaffold -->` marker "
        "in `index.md` and `purpose.md` is preserved."
    )

    confirm_result = await tool_confirm(
        ctx,
        message=confirm_message,
        yes_label="Run scaffold",
        no_label="Cancel",
    )
    if not confirm_result.get("confirmed"):
        return {"status": "cancelled", "message": "Scaffold cancelled by user."}

    await ctx.send_sse_event(
        "tool_progress",
        {"tool": "run_scaffold", "message": f"Running scaffold for '{domain}'..."},
    )
    try:
        job_id = await ctx.queue.enqueue("scaffold", {"domain": domain})
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}

    poll_result = await tool_poll_job(ctx, job_id, timeout_seconds=300, job_label="Scaffold")
    if poll_result.get("status") != ToolStatus.SUCCESS:
        return poll_result

    categories_updated = 0
    routing_regenerated = False
    try:
        job = await ctx.queue.get_job(job_id)
        if job and job.result:
            categories_updated = job.result.get("categories_updated", 0)
            routing_regenerated = bool(job.result.get("routing_regenerated", False))
    except Exception:  # noqa: BLE001
        pass

    await ctx.send_sse_event(
        "tool_progress",
        {"tool": "run_scaffold",
         "message": f"✓ Scaffold complete — {categories_updated} page{'s' if categories_updated != 1 else ''} categorised"},
    )
    return {
        "status": ToolStatus.SUCCESS,
        "domain": domain,
        "categories_updated": categories_updated,
        "routing_regenerated": routing_regenerated,
    }


async def tool_confirm(
    ctx: "WorkflowContext",
    message: str,
    yes_label: str = "Yes",
    no_label: str = "No",
    *,
    diff: str | None = None,
) -> dict:
    """Send a confirmation request to the client and wait for the response.

    Registers an :class:`asyncio.Event` gate in ``ctx.confirm_registry`` keyed
    by ``ctx.session_id``.  The HTTP handler resolves the gate when the user
    responds.

    When *diff* is provided (a unified-diff string), it is included in the SSE
    payload so the web UI can render a syntax-highlighted diff viewer alongside
    the confirmation buttons rather than embedding raw diff text in *message*.

    Returns ``{"confirmed": bool}``.  Times out with ``{"confirmed": False}``
    after 120 seconds.
    """
    gate = asyncio.Event()
    ctx.confirm_registry[ctx.session_id] = gate
    ctx.confirm_result_registry[ctx.session_id] = False
    try:
        payload: dict = {
            "session_id": ctx.session_id,
            "message": message,
            "yes_label": yes_label,
            "no_label": no_label,
        }
        if diff is not None:
            payload["diff"] = diff
        try:
            await ctx.send_sse_event("confirm_request", payload)
        except Exception:  # noqa: BLE001
            return {"confirmed": False}
        try:
            await asyncio.wait_for(gate.wait(), timeout=120.0)
            confirmed = ctx.confirm_result_registry.get(ctx.session_id, False)
            return {"confirmed": confirmed}
        except asyncio.TimeoutError:
            return {"confirmed": False}
    finally:
        ctx.confirm_registry.pop(ctx.session_id, None)
        ctx.confirm_result_registry.pop(ctx.session_id, None)


# ---------------------------------------------------------------------------
# Generic content and lifecycle tools (v1.3.0 framework extension)
# Usable by any workflow — not contradiction-resolver-specific.
# ---------------------------------------------------------------------------


async def tool_read_page_content(ctx: "WorkflowContext", slug: str) -> dict:
    """Return the full content and metadata for a single wiki page.

    Any workflow that needs to read a page before editing it should use this
    tool instead of accessing ctx.store directly.

    Returns::

        {"slug": str, "title": str, "content": str, "lint_warnings": list,
         "contradiction_note": str | None, "status": str}
        {"error": str}  — page not found
    """
    page = ctx.store.read_page(slug)
    if page is None:
        return {"error": f"Page not found: {slug!r}"}
    await ctx.send_sse_event(
        "tool_progress",
        {"tool": "read_page_content", "message": f"Reading page: {slug}"},
    )
    return {
        "slug": slug,
        "title": page.title or slug,
        "content": page.content or "",
        "lint_warnings": page.lint_warnings or [],
        "contradiction_note": page.contradiction_note,
        "status": page.status if page.status else "unknown",
    }


def _load_gate_threshold(wiki_root: Path) -> "int | None":
    """Load adversarial_gate_threshold from config.toml; return None if unavailable."""
    try:
        cfg_path = wiki_root / ".synthadoc" / "config.toml"
        if cfg_path.exists():
            from synthadoc.config import load_config
            cfg = load_config(project_config=cfg_path)
            return cfg.lint.adversarial_gate_threshold
    except Exception:  # noqa: BLE001
        pass
    return None


async def tool_run_scoped_lint(ctx: "WorkflowContext", slug: str) -> dict:
    """Re-lint a single page (adversarial + contradiction check only).

    Enqueues a ``scope="slug"`` lint job, waits for completion, then reads
    the page's updated state from the store.  Intended for fix-verify loops:
    run after applying a change to check whether the page now passes the gate.

    Returns::

        {"pass": bool, "warnings_count": int, "contradiction_note": str | None}
        {"pass": False, "error": str}  — enqueue or poll failure
    """
    await ctx.send_sse_event(
        "tool_progress",
        {"tool": "run_scoped_lint", "message": f"Re-linting {slug}..."},
    )
    try:
        job_id = await ctx.queue.enqueue(
            "lint",
            {"scope": "slug", "slug": slug, "adversarial": True, "lifecycle": False},
        )
    except Exception as exc:  # noqa: BLE001
        return {"pass": False, "warnings_count": 0, "contradiction_note": None,
                "error": str(exc)}

    poll_result = await tool_poll_job(
        ctx, job_id, timeout_seconds=120, job_label=f"Scoped lint: {slug}"
    )
    if poll_result.get("status") != ToolStatus.SUCCESS:
        return {"pass": False, "warnings_count": 0, "contradiction_note": None,
                "error": poll_result.get("message", "lint job did not succeed")}

    page = ctx.store.read_page(slug)
    if page is None:
        return {"pass": False, "warnings_count": 0, "contradiction_note": None,
                "error": "Page disappeared after lint"}

    warnings_count = len(page.lint_warnings or [])
    contradiction_note = page.contradiction_note
    threshold = _load_gate_threshold(ctx.wiki_root)
    gate_ok = threshold is None or threshold <= 0 or warnings_count < threshold
    passed = gate_ok and not contradiction_note

    await ctx.send_sse_event(
        "tool_progress",
        {"tool": "run_scoped_lint",
         "message": f"{'✓' if passed else '✗'} {slug}: {'passed' if passed else 'failed'}"},
    )
    return {"pass": passed, "warnings_count": warnings_count,
            "contradiction_note": contradiction_note}


async def tool_propose_and_apply(
    ctx: "WorkflowContext",
    slug: str,
    new_content: str,
    strategy_name: str,
    rationale: str,
) -> dict:
    """Show a unified diff to the user and write the page only if they approve.

    The diff is embedded in a ``confirm_request`` SSE message so both the web
    UI modal and the CLI terminal receive it.  Approval calls
    ``ctx.store.write_page``; rejection leaves the page unchanged.

    Does NOT alter the page's lifecycle state — callers must call
    ``tool_transition_lifecycle_state`` separately after lint passes.

    Returns::

        {"applied": bool, "diff_preview": str}
        {"applied": False, "error": str}  — page not found
    """
    page = ctx.store.read_page(slug)
    if page is None:
        return {"applied": False, "diff_preview": "",
                "error": f"Page not found: {slug!r}"}

    old_lines = (page.content or "").splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff_lines = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"{slug} (current)", tofile=f"{slug} (proposed)", n=3,
    ))
    diff_preview = "".join(diff_lines[:80])
    if len(diff_lines) > 80:
        diff_preview += f"\n... ({len(diff_lines) - 80} more lines not shown)"

    confirm_message = (
        f"**Strategy:** {strategy_name}\n\n"
        f"**Rationale:** {rationale}\n\n"
        f"Apply changes to `{slug}`?"
    )
    result = await tool_confirm(
        ctx, message=confirm_message, yes_label="Apply", no_label="Skip",
        diff=diff_preview,
    )
    confirmed = result.get("confirmed", False)
    if confirmed:
        page.content = new_content
        # Clear the contradiction note so scoped lint can pass for source-conflict
        # pages.  tool_run_scoped_lint marks a page as failed if contradiction_note
        # is not None, regardless of content quality.  Applying approved new content
        # is the act of resolving the conflict, so the note must be cleared here.
        page.contradiction_note = None
        with ctx.store.page_lock(slug):
            ctx.store.write_page(slug, page)
        await ctx.send_sse_event(
            "tool_progress",
            {"tool": "propose_and_apply", "message": f"✓ Applied {strategy_name} to {slug}"},
        )
    return {"applied": confirmed, "diff_preview": diff_preview}


_VALID_STATES: frozenset[str] = frozenset(
    {"active", "draft", "stale", "contradicted", "archived"}
)


async def tool_transition_lifecycle_state(
    ctx: "WorkflowContext",
    slug: str,
    to_state: str,
    reason: str,
) -> dict:
    """Transition a page to a new lifecycle state and record an audit event.

    Validates both the target state name and the transition graph before
    writing — the same rules enforced by the HTTP endpoint and MCP server.
    Any workflow that moves pages between states should use this tool so the
    audit trail is always complete.

    LifecycleState in this codebase uses plain string constants (not an enum).
    Assigning page.status = to_state is correct; do NOT call LifecycleState(to_state).

    Returns::

        {"success": True, "from_state": str, "to_state": str}
        {"success": False, "error": str}
    """
    from synthadoc.storage.wiki import validate_lifecycle_transition

    if to_state not in _VALID_STATES:
        return {
            "success": False,
            "error": f"Unknown lifecycle state {to_state!r}. Valid: {sorted(_VALID_STATES)}",
        }

    page = ctx.store.read_page(slug)
    if page is None:
        return {"success": False, "error": f"Page not found: {slug!r}"}

    from_state = page.status if page.status else "unknown"

    # Enforce the lifecycle state-machine graph — same rules as the HTTP endpoint
    # and MCP server.  Lint and ingest bypass this check intentionally (they write
    # via write_page() directly); this tool is user-driven and must not be more
    # permissive than the other user-facing surfaces.
    err = validate_lifecycle_transition(from_state, to_state)
    if err:
        return {"success": False, "error": err}

    page.status = to_state  # LifecycleState constants are plain strings

    if to_state == "active":
        page.contradiction_note = None  # clear stale contradiction note on promotion

    ctx.store.write_page(slug, page)

    # Invalidate the query cache and search index so the next query reflects
    # the new lifecycle state.  Both hooks are None in tests and CLI contexts
    # that don't wire up the orchestrator.
    if ctx.bump_epoch:
        ctx.bump_epoch()
    if ctx.invalidate_search:
        ctx.invalidate_search()

    if ctx.audit_db:
        # Update page_states so GET /lifecycle/pages reflects the change immediately.
        # This is separate from the audit event — set_page_state owns the current-state
        # table; record_lifecycle_event owns the immutable event log.
        try:
            await ctx.audit_db.set_page_state(slug, to_state, "workflow")
        except Exception:  # noqa: BLE001
            pass  # DB failure must not abort the workflow
        try:
            await ctx.audit_db.record_lifecycle_event(
                slug, from_state, to_state, reason, "workflow",
                content_snapshot=page.content or None,
            )
        except Exception:  # noqa: BLE001
            pass  # audit failure must not abort the workflow

    await ctx.send_sse_event(
        "tool_progress",
        {"tool": "transition_lifecycle_state",
         "message": f"✓ {slug}: {from_state} → {to_state}"},
    )
    return {"success": True, "from_state": from_state, "to_state": to_state}


async def tool_notify(ctx: "WorkflowContext", message: str, level: str = "info") -> dict:
    """Send a non-blocking notice SSE event to the user without ending the loop.

    Use this in place of plain-text output whenever you need to communicate
    a status update mid-workflow (e.g. escalation messages, skip notices).
    Unlike plain-text output, this tool call does NOT terminate the loop.

    level: "info" | "warning" | "error"  (for UI styling; "info" is the default)

    Returns: {"sent": True}
    """
    await ctx.send_sse_event("notice", {"text": message, "level": level})
    return {"sent": True}


async def tool_get_wiki_status(ctx: "WorkflowContext") -> dict:
    """Return a lifecycle state count for user-managed pages in the wiki.

    System pages (index, log, dashboard, purpose, overview) are excluded
    so the count matches what ``synthadoc status`` reports.

    Useful as a final ground-truth check at the end of a maintenance workflow.

    Returns::

        {"active": int, "draft": int, "stale": int,
         "contradicted": int, "archived": int}
    """
    from synthadoc.storage.wiki import SYSTEM_PAGE_SLUGS  # avoid top-level circular import

    counts: dict[str, int] = {
        "active": 0, "draft": 0, "stale": 0, "contradicted": 0, "archived": 0,
    }
    for slug in ctx.store.list_pages():
        if slug in SYSTEM_PAGE_SLUGS:
            continue
        page = ctx.store.read_page(slug)
        if page is None:
            continue
        key = page.status if page.status else "draft"
        if key in counts:
            counts[key] += 1
    await ctx.send_sse_event(
        "tool_progress",
        {"tool": "get_wiki_status",
         "message": (
             f"Wiki status: {counts['active']} active, "
             f"{counts['contradicted']} contradicted"
         )},
    )
    return counts
