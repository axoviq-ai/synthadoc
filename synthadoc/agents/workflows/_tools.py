# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Shared tool functions for agentic workflow loops.

Each function is intended to be curried with ``functools.partial(tool_fn, ctx)``
so the loop runner can call ``fn(**tool_input)`` without knowing about the
WorkflowContext.
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from synthadoc.agents.workflows._base import WorkflowContext

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
    result = await tool_poll_job(ctx, job_id, timeout_seconds=300)
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
                "message": f"Ingest running... ({int(elapsed)}s)",
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
