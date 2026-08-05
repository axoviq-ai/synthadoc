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
        source_path = page.sources[0].file if page and page.sources else None
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


async def tool_find_stale_pages(ctx: "WorkflowContext") -> dict:
    """Return ``{"pages": [...]}`` or ``{"error": str, "pages": []}``."""
    try:
        pages = await _resolve_stale_pages(ctx)
        return {"pages": pages}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "pages": []}


async def tool_ingest_source(ctx: "WorkflowContext", source_path: str) -> dict:
    """Validate *source_path* and enqueue an ingest job.

    Validation order:
    1. Must be an absolute path.
    2. Must resolve within ``ctx.wiki_root``.
    3. File must exist on disk.

    Returns ``{"job_id": str}`` on success or ``{"error": str}`` on failure.
    """
    path = Path(source_path)

    # 1. Absolute path check (use os.path.isabs so /foo is treated as absolute on Windows too)
    if not os.path.isabs(source_path):
        return {"error": f"source_path must be an absolute path, got: {source_path!r}"}

    # 2. Must be inside wiki_root
    wiki_root_resolved = ctx.wiki_root.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(wiki_root_resolved)
    except ValueError:
        return {
            "error": (
                f"source_path is outside wiki root {wiki_root_resolved}: {source_path!r}"
            )
        }

    # 3. File must exist
    if not path.exists():
        return {"error": f"File not found: {source_path!r}"}

    # Enqueue with retries for transient queue-full errors.
    last_error: str | None = None
    for delay in [0] + _INGEST_RETRY_DELAYS:
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            job_id = await ctx.queue.enqueue("ingest", {"source": source_path})
            return {"job_id": job_id}
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
    return {"error": f"Failed to enqueue after retries: {last_error}"}


async def tool_poll_job(
    ctx: "WorkflowContext",
    job_id: str,
    timeout_seconds: int = 120,
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

        job = await ctx.queue.get_job(job_id)
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
                "message": f"Waiting for job {job_id}... ({int(elapsed)}s elapsed)",
            },
        )
        await asyncio.sleep(min(1 * (2**attempt), 30))
        attempt += 1


async def tool_run_lint(ctx: "WorkflowContext", scope: str = "all") -> dict:
    """Enqueue a lint job and return its ID.

    Returns ``{"job_id": str}`` or ``{"error": str}``.
    """
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
        await ctx.send_sse_event(
            "confirm_request",
            {
                "session_id": ctx.session_id,
                "message": message,
                "yes_label": yes_label,
                "no_label": no_label,
            },
        )
        try:
            await asyncio.wait_for(gate.wait(), timeout=120.0)
            confirmed = ctx.confirm_result_registry.get(ctx.session_id, False)
            return {"confirmed": confirmed}
        except asyncio.TimeoutError:
            return {"confirmed": False}
    finally:
        ctx.confirm_registry.pop(ctx.session_id, None)
        ctx.confirm_result_registry.pop(ctx.session_id, None)
