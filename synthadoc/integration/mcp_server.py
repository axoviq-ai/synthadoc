# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations


def create_mcp_server(orchestrator):
    """Create the FastMCP server bound to a shared Orchestrator singleton.

    The caller is responsible for calling orchestrator.init() before the
    first tool invocation arrives.
    """
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("synthadoc")

    @mcp.tool()
    async def synthadoc_ingest(source: str) -> dict:
        """Ingest a source document or URL into the wiki."""
        job_id = await orchestrator.ingest(source, auto_confirm=True)
        return {"job_id": job_id, "source": source}

    @mcp.tool()
    async def synthadoc_query(question: str) -> dict:
        """Query the wiki and return a synthesized answer with citations."""
        result = await orchestrator.query(question)
        return {"answer": result.answer, "citations": result.citations}

    @mcp.tool()
    async def synthadoc_lint(scope: str = "all") -> dict:
        """Run lint checks on the wiki."""
        report = await orchestrator.lint(scope=scope)
        return {"contradictions_found": report.contradictions_found,
                "orphans": report.orphan_slugs}

    @mcp.tool()
    async def synthadoc_search(terms: str) -> dict:
        """Search the wiki with BM25 hybrid search."""
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

    _VALID_STATES = {"active", "draft", "stale", "contradicted", "archived"}

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
        from synthadoc.storage.wiki import TriggerSource
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
        from synthadoc.core.queue import JobStatus

        _VALID = {"all", "pending", "running", "completed", "failed", "skipped", "cancelled", "dead"}
        if status not in _VALID:
            return {"error": f"invalid status {status!r}. Valid: {', '.join(sorted(_VALID))}"}

        _STATUS_MAP = {"running": "in_progress"}
        queue_status: "JobStatus | None" = None
        if status != "all":
            mapped = _STATUS_MAP.get(status, status)
            try:
                queue_status = JobStatus(mapped)
            except ValueError:
                return {"error": f"internal: could not map {status!r} to a JobStatus value"}

        jobs = await orchestrator.queue.list_jobs(status=queue_status)
        result = []
        for j in jobs:
            entry: dict = {
                "id": j.id,
                "operation": j.operation,
                "status": j.status.value if hasattr(j.status, "value") else str(j.status),
                "created": str(j.created_at) if j.created_at else "",
            }
            source = (j.payload or {}).get("source")
            if source:
                entry["source"] = source
            if j.error:
                entry["error"] = j.error
            result.append(entry)
        return {"jobs": result}

    return mcp
