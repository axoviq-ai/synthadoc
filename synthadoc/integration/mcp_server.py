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
    async def synthadoc_export(
        format: str = "okf",
        output_path: str = "",
        status_filter: str = "all",
    ) -> dict:
        """Export the wiki to disk in a structured format.

        format: "okf" (Open Knowledge Format — folder of Markdown files),
                "llms.txt" (compact LLM-ready plain text),
                "llms-full.txt" (full content), "json", "graphml".
        output_path: directory (for okf) or file path (for other formats).
                Optional — if omitted, okf defaults to
                <wiki_root>/exports/<wiki_name>-okf-<date>/ and other formats
                return content inline in the response.
        status_filter: "all" (default), or a lifecycle state such as "active".

        OKF returns: {"format", "output_path", "files_written": N, "pages": N}
        Other formats with output_path: {"format", "output_path", "pages": N}
        Other formats without output_path: {"format", "content": str, "pages": N}
        """
        from datetime import date
        from synthadoc.agents.export_agent import ExportAgent, ExportOptions, EXPORT_FORMATS
        if format not in EXPORT_FORMATS:
            return {"error": f"unknown format {format!r}. Valid: {sorted(EXPORT_FORMATS)}"}

        agent = ExportAgent(
            store=orchestrator._store,
            wiki_name=orchestrator._root.name,
            audit_db_path=orchestrator._root / ".synthadoc" / "audit.db",
            routing_path=orchestrator._root / "ROUTING.md",
        )
        opts = ExportOptions(format=format, status_filter=status_filter)
        content = await agent.export(opts)
        page_count = len(orchestrator._store.list_pages())

        if format == "okf":
            if output_path:
                out = Path(output_path)
            else:
                out = orchestrator._root / "exports" / f"{orchestrator._root.name}-okf-{date.today()}"
            out.mkdir(parents=True, exist_ok=True)
            for rel_path, text in content.items():
                target = out / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
            return {"format": format, "output_path": str(out), "files_written": len(content), "pages": page_count}

        if output_path:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(content if isinstance(content, str) else str(content), encoding="utf-8")
            return {"format": format, "output_path": str(out), "pages": page_count}

        return {"format": format, "content": content, "pages": page_count}

    @mcp.tool()
    async def synthadoc_context(goal: str, token_budget: int = 10000) -> dict:
        """Build a token-budgeted context pack for a goal or question.

        Ranks and selects the most relevant page excerpts that fit within
        token_budget tokens (default: 10 000). Returns pages with slug, excerpt,
        relevance, confidence, and estimated token count, plus omitted slugs that
        exceeded the budget. Use this instead of search + multiple read_page calls
        when you need a curated, budget-aware set of excerpts for synthesis.

        To change the default permanently, set context_token_budget in config.toml:
            [query]
            context_token_budget = 20000
        """
        from synthadoc.agents.context_agent import ContextAgent
        from synthadoc.providers import make_provider
        budget = token_budget or orchestrator._cfg.query.context_token_budget
        agent = ContextAgent(
            provider=make_provider("query", orchestrator._cfg),
            store=orchestrator._store,
            search=orchestrator._search,
            token_budget=budget,
        )
        pack = await agent.build(goal, token_budget=budget)
        return pack.to_dict()

    @mcp.tool()
    async def synthadoc_lint(scope: str = "all") -> dict:
        """Enqueue a lint job (LLM analysis). Returns a job_id — poll with synthadoc_jobs.

        scope: "all" to lint the whole wiki, or a page slug to lint one page.
        Do NOT pass "report" here — use synthadoc_lint_report for a zero-cost status read.
        """
        job_id = await orchestrator.lint(scope=scope)
        return {"job_id": job_id, "scope": scope}

    @mcp.tool()
    async def synthadoc_lint_report() -> dict:
        """Read the current lint state: contradicted pages, orphans, adversarial warnings.

        Zero cost — reads wiki files directly, no LLM call, no job enqueued.
        Use this to check wiki health. Use synthadoc_lint to run a fresh analysis.
        """
        from synthadoc.agents.lint_agent import read_current_lint_state
        state = read_current_lint_state(orchestrator._store)
        adv_count = sum(len(p["warnings"]) for p in state.adv_pages)
        return {
            "contradicted": state.contradicted,
            "orphans": state.orphans,
            "adversarial_warnings": adv_count,
            "adversarial_pages": [p["slug"] for p in state.adv_pages],
        }

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
    async def synthadoc_list_pages(status: str = "all") -> dict:
        """List all wiki pages with title, status, and type.

        status: filter by lifecycle state — "all" (default), "active", "draft",
        "contradicted", "stale", or "archived".
        Use synthadoc_read_page to get full content and sources for a specific page.
        """
        slugs = orchestrator._store.list_pages()
        pages = []
        for slug in slugs:
            page = orchestrator._store.read_page(slug)
            if page is None:
                continue
            if status != "all" and page.status != status:
                continue
            pages.append({
                "slug": slug,
                "title": page.title,
                "status": page.status,
                "type": page.type or "",
                "has_sources": bool(page.sources),
            })
        return {"pages": pages, "total": len(pages)}

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
            "lint_warnings": list(page.lint_warnings) if page.lint_warnings else [],
            "sources": [{"file": s.file, "ingested": s.ingested} for s in (page.sources or [])],
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
        await orchestrator._audit.set_page_state(slug, to_state, TriggerSource.MCP)
        await orchestrator._audit.record_lifecycle_event(
            slug, from_state, to_state, reason, TriggerSource.MCP
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
