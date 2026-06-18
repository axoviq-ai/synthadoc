# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations
from pathlib import Path


def create_mcp_server(orchestrator):
    """Create the FastMCP server bound to a shared Orchestrator singleton.

    The caller is responsible for calling orchestrator.init() before the
    first tool invocation arrives.
    """
    from mcp.server.fastmcp import FastMCP
    from synthadoc.core.queue import JobStatus
    from synthadoc.storage.wiki import LifecycleState, TriggerSource

    # ── Lifecycle states ─────────────────────────────────────────────────
    _VALID_STATES = LifecycleState.ALL          # single source of truth

    # ── Job status constants ─────────────────────────────────────────────
    # "running" is the user-facing alias for the internal IN_PROGRESS value.
    # _DISPLAY_STATUS: internal → display; _STATUS_MAP: display → internal.
    _DISPLAY_STATUS = {JobStatus.IN_PROGRESS.value: "running"}
    _STATUS_MAP = {v: k for k, v in _DISPLAY_STATUS.items()}
    _VALID_JOB_STATUS = {"all"} | {_DISPLAY_STATUS.get(j.value, j.value) for j in JobStatus}

    _root = getattr(orchestrator, "_root", None)
    _wiki_name = _root.name if isinstance(_root, Path) and _root.name else ""
    _server_name = f"synthadoc-{_wiki_name}" if _wiki_name else "synthadoc"
    mcp = FastMCP(_server_name)

    @mcp.tool()
    async def synthadoc_ingest(source: str) -> dict:
        """Ingest a source document or URL into the wiki."""
        job_id = await orchestrator.ingest(source, auto_confirm=True)
        return {"job_id": job_id, "source": source}

    @mcp.tool()
    async def synthadoc_lint(scope: str = "all") -> dict:
        """Run lint checks on the wiki."""
        report = await orchestrator.lint(scope=scope)
        return {"contradictions_found": report.contradictions_found,
                "orphans": report.orphan_slugs}

    @mcp.tool()
    async def synthadoc_search(terms: str) -> dict:
        """Search the wiki with BM25 keyword search. Returns page titles, slugs, and snippets.

        Use this to find relevant pages, then synthadoc_read_page to get full content.
        Synthesize the answer yourself — no LLM is called on the Synthadoc side.
        """
        results = orchestrator._search.bm25_search(terms.split(), top_n=10)
        return {
            "results": [
                {"slug": r.slug, "score": r.score, "title": r.title, "snippet": r.snippet}
                for r in results
            ]
        }

    @mcp.tool()
    async def synthadoc_status() -> dict:
        """Get wiki status: page count and path."""
        return {
            "pages": len(orchestrator._store.list_pages()),
            "wiki": str(orchestrator._root),
        }

    @mcp.tool()
    async def synthadoc_write_page(slug: str, content: str, title: str = "") -> dict:
        """Update the content of an existing wiki page.

        Only updates content (and optionally title) — lifecycle state is unchanged.
        Use synthadoc_lifecycle to transition state after editing.
        Clears contradiction_note if present, since a manual edit implies resolution.

        Returns the updated slug, title, and status.
        """
        from datetime import date
        page = orchestrator._store.read_page(slug)
        if page is None:
            return {"error": "page not found", "slug": slug}
        page.content = content
        if title:
            page.title = title
        page.contradiction_note = None
        page.updated = date.today().isoformat()
        orchestrator._store.write_page(slug, page)
        orchestrator._bump_epoch()
        return {"slug": slug, "title": page.title, "status": page.status}

    @mcp.tool()
    async def synthadoc_read_page(slug: str) -> dict:
        """Read a wiki page by slug and return its full content and metadata."""
        page = orchestrator._store.read_page(slug)
        if page is None:
            return {"error": "page not found", "slug": slug}
        return {
            "slug": slug,
            "title": page.title,
            "content": page.content,
            "status": page.status,
            "type": page.type or "",
            "tags": page.tags,
        }

    @mcp.tool()
    async def synthadoc_lifecycle(slug: str, to_state: str, reason: str) -> dict:
        """Transition a wiki page's lifecycle state.

        Valid to_state values: active, draft, stale, contradicted, archived.
        All transitions are permitted (no graph enforcement).
        """
        from datetime import datetime, timezone
        if to_state not in _VALID_STATES:
            return {
                "error": (
                    f"invalid to_state {to_state!r}. "
                    f"Valid: {', '.join(sorted(_VALID_STATES))}"
                )
            }
        page = orchestrator._store.read_page(slug)
        if page is None:
            return {"error": "page not found", "slug": slug}
        from_state = page.status
        page.status = to_state
        orchestrator._store.write_page(slug, page)
        await orchestrator._audit.set_page_state(slug, to_state, TriggerSource.USER)
        await orchestrator._audit.record_lifecycle_event(
            slug, from_state, to_state, reason, TriggerSource.USER
        )
        orchestrator._bump_epoch()
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {
            "slug": slug,
            "from_state": from_state,
            "to_state": to_state,
            "reason": reason,
            "timestamp": ts,
        }

    @mcp.tool()
    async def synthadoc_jobs(status: str = "all") -> dict:
        """List recent jobs, optionally filtered by status.

        Valid status values: all, pending, running, completed, failed, skipped, cancelled, dead.
        'running' maps to the internal 'in_progress' state.
        """
        if status not in _VALID_JOB_STATUS:
            return {"error": f"invalid status {status!r}. Valid: {', '.join(sorted(_VALID_JOB_STATUS))}"}

        queue_status: JobStatus | None = None
        if status != "all":
            mapped = _STATUS_MAP.get(status, status)
            try:
                queue_status = JobStatus(mapped)
            except ValueError:
                return {"error": f"internal: could not map {status!r} to a JobStatus value"}

        jobs = await orchestrator.queue.list_jobs(status=queue_status)
        result = []
        for j in jobs:
            raw_status = j.status.value if hasattr(j.status, "value") else str(j.status)
            entry: dict = {
                "id": j.id,
                "operation": j.operation,
                "status": _DISPLAY_STATUS.get(raw_status, raw_status),
                "created": str(j.created_at) if j.created_at else "",
            }
            source = (j.payload or {}).get("source")
            if source:
                entry["source"] = source
            if j.error:
                entry["error"] = j.error
            result.append(entry)
        return {"jobs": result}

    # Prepend "Wiki: <name>." to every tool description so Claude can route
    # correctly when multiple Synthadoc servers are connected simultaneously.
    if _wiki_name:
        _prefix = f"Wiki: {_wiki_name}. "
        for _tool in mcp._tool_manager._tools.values():
            _tool.description = _prefix + (_tool.description or "")

    return mcp
