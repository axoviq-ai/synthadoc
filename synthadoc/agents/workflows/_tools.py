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
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from synthadoc.agents.workflows._base import WorkflowContext

from synthadoc.agents.scaffold_agent import scaffold_output_paths

# Retry delays (seconds) when the job queue is temporarily unavailable.
# The first attempt uses 0 delay; subsequent attempts use these values.
_INGEST_RETRY_DELAYS: list[int] = [2, 4, 8]

# JobStatus.value strings that indicate the job has reached a terminal state.
_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"completed", "failed", "dead", "cancelled", "skipped"}
)


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

    status = result.get("status", "failed")
    if status == "success":
        await ctx.send_sse_event("tool_progress", {"tool": "ingest_source", "message": f"✓ {label} re-ingested"})
    else:
        await ctx.send_sse_event("tool_progress", {"tool": "ingest_source", "message": f"✗ {label}: {status}"})
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

        if job is not None and job.status.value in _TERMINAL_STATUSES:
            if job.status.value == "completed":
                return {
                    "status": "success",
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
    """Enqueue a lint job and return its ID.

    Returns ``{"job_id": str}`` or ``{"error": str}``.
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
        return {"job_id": job_id}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


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


async def tool_find_broken_wikilinks(ctx: "WorkflowContext") -> dict:
    """Scan all *active* wiki pages for ``[[slug]]`` references that resolve to no existing page.

    Stale, draft, and archived pages are excluded — they must be promoted to
    active first to be included in the scan.

    Uses ``difflib.get_close_matches`` (stdlib, no extra dependency) to suggest
    fuzzy corrections for likely typos.

    Returns::

        {
          "pages":        [{"slug": str, "broken_links": [{"ref": str, "suggestion": str|null}]}],
          "scanned":      int,   # number of active pages scanned
          "total_broken": int,   # total broken link references found
        }
    """
    all_states = await ctx.audit_db.get_live_page_states(ctx.store.page_exists)
    active_slugs: set[str] = {p["slug"] for p in all_states if p.get("state") == "active"}
    all_slugs: list[str] = ctx.store.all_slugs()
    all_slug_set: set[str] = set(all_slugs)

    n_active = len(active_slugs)
    await ctx.send_sse_event(
        "tool_progress",
        {"tool": "find_broken_wikilinks",
         "message": f"Scanning {n_active} active page{'s' if n_active != 1 else ''} for broken wikilinks..."},
    )

    pages_with_issues: list[dict] = []
    total_broken = 0

    for slug in sorted(active_slugs):
        page = ctx.store.read_page(slug)
        if not page or not page.content:
            continue
        refs = _WIKILINK_SCAN_RE.findall(page.content)
        broken: list[dict] = []
        seen: set[str] = set()
        for ref in refs:
            normalized = _normalize_slug(ref)
            if normalized in all_slug_set or normalized in seen:
                continue
            seen.add(normalized)
            matches = difflib.get_close_matches(normalized, all_slugs, n=1, cutoff=0.72)
            broken.append({"ref": normalized, "suggestion": matches[0] if matches else None})
        if broken:
            pages_with_issues.append({"slug": slug, "broken_links": broken})
            total_broken += len(broken)

    n_pages = len(pages_with_issues)
    if n_pages:
        msg = (
            f"Found {total_broken} broken wikilink{'s' if total_broken != 1 else ''} "
            f"across {n_pages} active page{'s' if n_pages != 1 else ''}"
        )
    else:
        msg = f"No broken wikilinks found across {n_active} active page{'s' if n_active != 1 else ''}"

    await ctx.send_sse_event("tool_progress", {"tool": "find_broken_wikilinks", "message": msg})
    return {"pages": pages_with_issues, "scanned": n_active, "total_broken": total_broken}


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
        return {"status": "error", "error": f"Page {page_slug!r} not found"}

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
        return {"status": "success", "changes": 0, "page": page_slug}

    page.content = content
    with ctx.store.page_lock(page_slug):
        ctx.store.write_page(page_slug, page)

    await ctx.send_sse_event(
        "tool_progress",
        {"tool": "apply_link_fixes",
         "message": f"✓ {page_slug}: {total_changes} link{'s' if total_changes != 1 else ''} fixed"},
    )
    return {"status": "success", "changes": total_changes, "page": page_slug}


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
    """Enqueue a scaffold job, wait for it to finish, and return the outcome.

    Returns::

        {"status": "success", "domain": str, "categories_updated": int,
         "routing_regenerated": bool}
        {"status": "failed"|"timeout", "message": str}
        {"error": str}  — enqueue failed
    """
    await ctx.send_sse_event(
        "tool_progress",
        {"tool": "run_scaffold", "message": f"Running scaffold for '{domain}'..."},
    )
    try:
        job_id = await ctx.queue.enqueue("scaffold", {"domain": domain})
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}

    poll_result = await tool_poll_job(ctx, job_id, timeout_seconds=300, job_label="Scaffold")
    if poll_result.get("status") != "success":
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
        "status": "success",
        "domain": domain,
        "categories_updated": categories_updated,
        "routing_regenerated": routing_regenerated,
    }


async def tool_confirm(
    ctx: "WorkflowContext",
    message: str,
    yes_label: str = "Yes",
    no_label: str = "No",
) -> dict:
    """Send a confirmation request to the client and wait for the response.

    Registers an :class:`asyncio.Event` gate in ``ctx.confirm_registry`` keyed
    by ``ctx.session_id``.  The HTTP handler resolves the gate when the user
    responds.

    Returns ``{"confirmed": bool}``.  Times out with ``{"confirmed": False}``
    after 120 seconds.
    """
    gate = asyncio.Event()
    ctx.confirm_registry[ctx.session_id] = gate
    ctx.confirm_result_registry[ctx.session_id] = False
    try:
        try:
            await ctx.send_sse_event(
                "confirm_request",
                {
                    "session_id": ctx.session_id,
                    "message": message,
                    "yes_label": yes_label,
                    "no_label": no_label,
                },
            )
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
