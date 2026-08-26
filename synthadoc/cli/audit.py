# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from synthadoc.storage.wiki import WikiStorage

import typer
from rich.console import Console
from rich.table import Table

audit_app = typer.Typer(name="audit", help="Inspect ingest history and costs.")
console = Console()


def _get_audit_db(wiki: str):
    from synthadoc.cli.install import resolve_wiki_path
    from synthadoc.storage.log import AuditDB
    root = resolve_wiki_path(wiki)
    return AuditDB(root / ".synthadoc" / "audit.db")


@audit_app.command("history")
def history_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    limit: int = typer.Option(50, "--limit", "-n"),
    offset: int = typer.Option(0, "--offset"),
    as_json: bool = typer.Option(False, "--json", help="Output raw JSON"),
):
    """Show recent ingest history."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    db = _get_audit_db(wiki)

    async def _fetch():
        await db.init()
        records, total = await db.list_ingests(limit=limit, offset=offset)
        return records, total

    records, total = asyncio.run(_fetch())
    if as_json:
        typer.echo(json.dumps(records, indent=2))
        return
    page_info = f"offset {offset}, " if offset else ""
    table = Table(title=f"Ingest History ({page_info}{len(records)} of {total})")
    table.add_column("Timestamp", style="dim")
    table.add_column("Source")
    table.add_column("Wiki Page", style="cyan")
    table.add_column("Tokens", justify="right")
    table.add_column("Cost (USD)", justify="right")
    for r in records:
        table.add_row(
            r.get("ingested_at", "")[:16],
            Path(r.get("source_path", "")).name,
            r.get("wiki_page", ""),
            str(r.get("tokens") or 0),
            f"${r.get('cost_usd') or 0:.4f}",
        )
    console.print(table)


@audit_app.command("cost")
def cost_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    days: int = typer.Option(30, "--days"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Show token and cost summary."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    db = _get_audit_db(wiki)

    async def _fetch():
        await db.init()
        return await db.cost_summary(days=days)

    summary = asyncio.run(_fetch())
    if as_json:
        typer.echo(json.dumps(summary, indent=2))
        return
    console.print(f"\n[bold]Cost summary — last {days} days[/bold]")
    console.print(f"  Total tokens : {summary['total_tokens']:,}")
    console.print(f"  Total cost   : ${summary['total_cost_usd']:.4f}")
    if summary["daily"]:
        table = Table(title="Daily breakdown")
        table.add_column("Day")
        table.add_column("Cost (USD)", justify="right")
        for row in summary["daily"]:
            table.add_row(row["day"], f"${row['cost_usd']:.4f}")
        console.print(table)


@audit_app.command("queries")
def queries_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    limit: int = typer.Option(50, "--limit", "-n"),
    offset: int = typer.Option(0, "--offset"),
    as_json: bool = typer.Option(False, "--json", help="Output raw JSON"),
):
    """Show recent query history."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    db = _get_audit_db(wiki)

    async def _fetch():
        await db.init()
        records, total = await db.list_queries(limit=limit, offset=offset)
        return records, total

    records, total = asyncio.run(_fetch())
    if as_json:
        typer.echo(json.dumps(records, indent=2))
        return
    page_info = f"offset {offset}, " if offset else ""
    table = Table(title=f"Query History ({page_info}{len(records)} of {total})")
    table.add_column("Timestamp", style="dim")
    table.add_column("Question")
    table.add_column("Sub-Qs", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("Cost (USD)", justify="right")
    for r in records:
        table.add_row(
            r.get("queried_at", "")[:16],
            r.get("question", "")[:80],
            str(r.get("sub_questions_count") or 1),
            str(r.get("tokens") or 0),
            f"${r.get('cost_usd') or 0:.4f}",
        )
    console.print(table)


@audit_app.command("citations")
def citations_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    page: Optional[str] = typer.Option(None, "--page", help="Filter by page slug"),
    source: Optional[str] = typer.Option(None, "--source", help="Filter by source filename"),
    broken: bool = typer.Option(False, "--broken", help="Show validation failures only"),
    faithfulness: bool = typer.Option(
        False, "--faithfulness",
        help="Verify claim text is supported by cited source lines (LLM audit, opt-in)."
    ),
    yes: bool = typer.Option(False, "--yes", help="Skip cost confirmation (faithfulness mode only)"),
    force: bool = typer.Option(
        False, "--force",
        help="Re-audit all pages even if the cache is fresh (faithfulness mode only)."
    ),
    limit: int = typer.Option(50, "--limit", "-n"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Show claim-level citations, validation failures, or run a faithfulness audit."""
    if faithfulness:
        _run_faithfulness(wiki=wiki, page=page, yes=yes, force=force, as_json=as_json)
        return

    import json as _json
    from synthadoc.cli._wiki import resolve_wiki
    db_wiki = resolve_wiki(wiki)
    db = _get_audit_db(db_wiki)

    async def _fetch():
        await db.init()
        if broken:
            return await db.list_citation_failures(limit=limit)
        return await db.list_citations(
            page_slug=page, source_file=source, limit=limit
        )

    records = asyncio.run(_fetch())
    if as_json:
        typer.echo(_json.dumps(records, indent=2, default=str))
        return

    if not records:
        typer.echo("No citations found.")
        return

    if broken:
        typer.echo(f"Citation Validation Failures ({len(records)}):\n")
        for r in records:
            ts = (r.get("event_time") or "")[:16]
            slug = r.get("page_slug") or r.get("slug") or ""
            citation = r.get("citation") or ""
            reason = r.get("reason") or ""
            typer.echo(f"  [{ts}] {slug}  {citation} — {reason}")
    else:
        typer.echo(f"Claim Citations (last {limit}):\n")
        table = Table(title="Claim Citations")
        table.add_column("Page", style="cyan")
        table.add_column("Source")
        table.add_column("Lines", justify="right")
        table.add_column("Claim")
        for r in records:
            page_s = r.get("page_slug") or ""
            src = r.get("source_file") or ""
            lines = f"{r.get('line_start')}-{r.get('line_end')}"
            claim = (r.get("claim_excerpt") or "")[:60]
            table.add_row(page_s, src, lines, claim)
        console.print(table)


def _collect_checks_for_cost(
    wiki_root: "Path",
    store: "WikiStorage",
    page_slug: Optional[str],
) -> "dict[str, list]":
    """Thin wrapper kept for call-site compatibility.

    Delegates to ``citation_faithfulness.collect_checks_for_pages``, which is
    also used by the HTTP dry-run endpoint so the logic lives in one place.
    """
    from synthadoc.agents.citation_faithfulness_agent import collect_checks_for_pages
    return collect_checks_for_pages(wiki_root, store, page_slug)


def _render_faithfulness(results: list, as_json: bool) -> None:
    import json as _json
    from rich.markup import escape as _escape

    if as_json:
        typer.echo(_json.dumps(
            [{"slug": r.slug, "citation_marker": r.citation_marker,
              "verdict": r.verdict, "reason": r.reason}
             for r in results],
            indent=2,
        ))
        return

    if not results:
        typer.echo("No citations found in active pages.")
        return

    _VERDICT_STYLE = {
        "supported":     ("[green]✅ supported[/green]", ""),
        "drift":         ("[yellow]⚠️  drift[/yellow]", ""),
        "hallucination": ("[red]❌ hallucination[/red]", ""),
        "skipped":       ("[dim]—  skipped[/dim]", ""),
    }
    slugs = sorted({r.slug for r in results})
    n_pages = len(slugs)
    table = Table(
        title=f"Citation Faithfulness Report — {len(results)} citations across {n_pages} pages"
    )
    table.add_column("Page", style="cyan", no_wrap=True, max_width=30)
    table.add_column("Citation", no_wrap=True, max_width=44)
    table.add_column("Verdict", no_wrap=True)
    table.add_column("Reason", min_width=45)
    for r in results:
        verdict_cell = _VERDICT_STYLE.get(r.verdict, (r.verdict, ""))[0]
        table.add_row(r.slug, _escape(r.citation_marker), verdict_cell, r.reason or "")
    console.print(table)

    counts = {"hallucination": 0, "drift": 0, "supported": 0, "skipped": 0}
    for r in results:
        counts[r.verdict] = counts.get(r.verdict, 0) + 1
    summary_parts = []
    if counts["hallucination"]:
        summary_parts.append(f"[red]{counts['hallucination']} hallucination{'s' if counts['hallucination'] != 1 else ''}[/red]")
    if counts["drift"]:
        summary_parts.append(f"[yellow]{counts['drift']} drift{'s' if counts['drift'] != 1 else ''}[/yellow]")
    if counts["supported"]:
        summary_parts.append(f"[green]{counts['supported']} supported[/green]")
    if counts["skipped"]:
        summary_parts.append(f"[dim]{counts['skipped']} skipped[/dim]")
    console.print("\nSummary: " + " · ".join(summary_parts))


def _run_faithfulness(
    wiki: Optional[str],
    page: Optional[str],
    yes: bool,
    force: bool,
    as_json: bool,
) -> None:
    """Cache-aware faithfulness audit delegated to the running server.

    Decision logic (applied before any LLM call):
      - Fresh cache, no stale pages → display cached results, exit (no LLM).
      - Stale pages exist           → re-audit stale pages only (stale_only).
      - No cache at all             → full audit.
      - --force                     → full audit regardless of cache state.

    The server owns the LLM provider; no API key is needed in the CLI.
    """
    import time
    from synthadoc.cli._wiki import resolve_wiki
    from synthadoc.cli.install import resolve_wiki_path
    from synthadoc.cli._http import post as http_post, get as http_get
    from synthadoc.config import load_config
    from synthadoc.storage.wiki import WikiStorage
    from synthadoc.agents.citation_faithfulness_agent import (
        FaithfulnessResult,
        estimate_faithfulness_tokens,
    )
    from synthadoc.agents.faithfulness_cache import (
        read_cache,
        get_stale_slugs,
    )

    from synthadoc.providers.pricing import estimate_cost
    from synthadoc.core.queue import JobStatus

    wiki_name = resolve_wiki(wiki)
    wiki_root = resolve_wiki_path(wiki_name)
    cfg = load_config(project_config=wiki_root / ".synthadoc" / "config.toml")
    store = WikiStorage(wiki_root / "wiki")
    agent_cfg = cfg.agents.resolve("adversarial")

    # ── Determine audit scope from cache ─────────────────────────────────────
    cache = read_cache(wiki_root)
    entries = cache.get("entries", {})
    has_cache = bool(entries)

    if force:
        stale_only = False
        needs_run = True
    elif not has_cache:
        # No cache at all — full run
        stale_only = False
        needs_run = True
    else:
        stale_slugs = get_stale_slugs(entries, store)
        if page:
            # For a specific page: stale if its entry is missing/outdated
            page_stale = page in stale_slugs or page not in entries
            stale_only = True if page_stale and has_cache else False
            needs_run = page_stale
        else:
            stale_only = True
            needs_run = bool(stale_slugs)

    # ── No LLM needed — show cached results ──────────────────────────────────
    if not needs_run:
        if page:
            slugs_to_show = [page] if page in entries else []
        else:
            slugs_to_show = list(entries.keys())
        _show_from_cache(entries, slugs_to_show, as_json)
        checked_at = cache.get("checked_at") or ""
        if checked_at:
            console.print(f"[dim]Cache is up to date (last audited: {checked_at[:19]}). "
                          f"Use --force to re-audit.[/dim]")
        else:
            console.print("[dim]Cache is up to date. Use --force to re-audit.[/dim]")
        return

    # ── Cost estimate + confirmation (always shown when LLM run is needed) ────
    if not yes:
        scope_page = page if (page and not stale_only) else None
        pages_with_checks = _collect_checks_for_cost(wiki_root, store, scope_page)
        total_citations = sum(len(v) for v in pages_with_checks.values())
        est_tokens = estimate_faithfulness_tokens(pages_with_checks)
        est_cost = estimate_cost(
            agent_cfg.model,
            input_tokens=est_tokens,
            output_tokens=est_tokens // 5,
            is_local=agent_cfg.is_local,
        )
        # Hard gate: block immediately if over the configured cost ceiling.
        if est_cost >= cfg.cost.hard_gate_usd:
            console.print(
                f"[red]Cost gate:[/red] faithfulness audit estimated "
                f"${est_cost:.4f} — exceeds hard_gate_usd "
                f"${cfg.cost.hard_gate_usd:.2f}. "
                f"Raise [cost].hard_gate_usd in config.toml or scope to a single page."
            )
            raise typer.Exit(1)
        # Always confirm before any LLM run, regardless of cost size.
        scope_desc = "stale pages only" if stale_only else "all active pages"
        console.print(
            f"\n[bold]Citation faithfulness audit[/bold] — {scope_desc}\n"
            f"  {len(pages_with_checks)} page(s)  ·  "
            f"{total_citations} citation(s)  ·  "
            f"~{est_tokens:,} tokens  ·  "
            f"${est_cost:.4f} estimated"
        )
        confirm = input("\nRun audit? [y/N] ").strip().lower()
        if confirm != "y":
            console.print("[yellow]Audit cancelled.[/yellow]")
            raise typer.Exit(0)

    # ── Enqueue job on the running server ─────────────────────────────────────
    body: dict = {}
    if page:
        body["page_slug"] = page
    if stale_only:
        body["stale_only"] = True
    result = http_post(wiki_name, "/audit/citations/faithfulness", body)
    job_id: str = result.get("job_id", "")
    if not job_id:
        console.print(f"[red]Unexpected response from server:[/red] {result}")
        raise typer.Exit(1)

    scope_label = f'"{page}"' if page else ("stale pages" if stale_only else "all active pages")
    console.print(f"[dim]Auditing {scope_label} — job {job_id}…[/dim]")

    # ── Poll until terminal ───────────────────────────────────────────────────
    POLL_SECONDS = 3
    while True:
        job = http_get(wiki_name, f"/jobs/{job_id}")
        status: str = job.get("status", "unknown")
        if status in (JobStatus.PENDING, JobStatus.IN_PROGRESS):
            progress = job.get("progress") or {}
            phase = progress.get("phase", "starting")
            checked = progress.get("pages_checked", 0)
            total_pages = progress.get("pages_total", 0)
            current = progress.get("current_slug", "")
            if phase == "auditing" and total_pages:
                console.print(
                    f"[dim]({checked}/{total_pages})[/dim] Checking [bold]{current}[/bold]…"
                )
            time.sleep(POLL_SECONDS)
        elif status == JobStatus.COMPLETED:
            break
        else:
            error = job.get("error") or "unknown error"
            console.print(f"[red]Audit job {status}:[/red] {error}")
            raise typer.Exit(1)

    # ── Read results from (now-updated) cache and display ────────────────────
    cache = read_cache(wiki_root)
    entries = cache.get("entries", {})
    slugs_to_show = [page] if page else list(entries.keys())
    _show_from_cache(entries, slugs_to_show, as_json)


def _show_from_cache(
    entries: dict,
    slugs: list,
    as_json: bool,
) -> None:
    """Reconstruct FaithfulnessResult objects from cache entries and render them."""
    from synthadoc.agents.citation_faithfulness_agent import FaithfulnessResult

    all_results: list[FaithfulnessResult] = []
    for slug in slugs:
        entry = entries.get(slug, {})
        for r in entry.get("results", []):
            all_results.append(FaithfulnessResult(
                slug=slug,
                citation_marker=r["citation_marker"],
                verdict=r["verdict"],
                reason=r.get("reason", ""),
            ))

    _render_faithfulness(all_results, as_json)

    has_issues = any(r.verdict in ("drift", "hallucination") for r in all_results)
    raise SystemExit(1 if has_issues else 0)


lifecycle_audit_app = typer.Typer(help="Lifecycle event management.")
audit_app.add_typer(lifecycle_audit_app, name="lifecycle")


@lifecycle_audit_app.command("purge")
def lifecycle_purge(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    before: Optional[str] = typer.Option(None, "--before", help="ISO date e.g. 2026-01-01"),
    keep_latest: Optional[int] = typer.Option(None, "--keep-latest", help="Keep N most recent events per slug"),
) -> None:
    """Purge old lifecycle events from audit.db."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki_name = resolve_wiki(wiki)
    db = _get_audit_db(wiki_name)

    async def _run():
        await db.init()
        await db.purge_lifecycle_events(before_date=before, keep_latest=keep_latest)

    asyncio.run(_run())
    typer.echo("Lifecycle events purged.")


@audit_app.command("events")
def events_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    limit: int = typer.Option(100, "--limit", "-n"),
    offset: int = typer.Option(0, "--offset"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Show raw audit events."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    db = _get_audit_db(wiki)

    async def _fetch():
        await db.init()
        events, total = await db.list_events(limit=limit, offset=offset)
        return events, total

    events, total = asyncio.run(_fetch())
    if as_json:
        typer.echo(json.dumps(events, indent=2))
        return
    page_info = f"offset {offset}, " if offset else ""
    table = Table(title=f"Audit Events ({page_info}{len(events)} of {total})")
    table.add_column("Timestamp", style="dim")
    table.add_column("Job ID", style="dim")
    table.add_column("Event", style="cyan")
    table.add_column("Metadata")
    for e in events:
        table.add_row(
            e.get("timestamp", "")[:16],
            e.get("job_id") or "",
            e.get("event", ""),
            e.get("metadata") or "",
        )
    console.print(table)
