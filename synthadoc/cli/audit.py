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
    limit: int = typer.Option(50, "--limit", "-n"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Show claim-level citations, validation failures, or run a faithfulness audit."""
    if faithfulness:
        _run_faithfulness(wiki=wiki, page=page, yes=yes, as_json=as_json)
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
    """Collect citation checks without any LLM calls (for cost estimation)."""
    from synthadoc.agents.citation_faithfulness import extract_citations_for_check
    extracted_dir = wiki_root / ".synthadoc" / "extracted"
    pages_with_checks = {}

    if page_slug is not None:
        slugs = [page_slug]
    else:
        slugs = store.all_slugs()

    for slug in slugs:
        page = store.read_page(slug)
        if page is None or page.status != "active":
            continue
        checks, _ = extract_citations_for_check(slug, page, extracted_dir)
        if checks:
            pages_with_checks[slug] = checks
    return pages_with_checks


def _render_faithfulness(results: list, as_json: bool) -> None:
    import json as _json

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
    table.add_column("Page", style="cyan", no_wrap=True)
    table.add_column("Citation", no_wrap=True)
    table.add_column("Verdict")
    table.add_column("Reason")
    for r in results:
        verdict_cell = _VERDICT_STYLE.get(r.verdict, (r.verdict, ""))[0]
        table.add_row(r.slug, r.citation_marker, verdict_cell, r.reason or "")
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
    as_json: bool,
) -> None:
    """Delegate the faithfulness audit to the running server (no API key required here).

    The server owns the LLM provider and runs the audit as a background job.
    The CLI enqueues the job, polls for progress, then reads the finished
    results from the faithfulness cache.
    """
    import time
    from synthadoc.cli._wiki import resolve_wiki
    from synthadoc.cli.install import resolve_wiki_path
    from synthadoc.cli._http import post as http_post, get as http_get
    from synthadoc.config import load_config
    from synthadoc.storage.wiki import WikiStorage
    from synthadoc.agents.citation_faithfulness import estimate_faithfulness_tokens
    from synthadoc.core.cost_guard import CostGuard, CostEstimate, CostGateError
    from synthadoc.providers.pricing import estimate_cost

    wiki_name = resolve_wiki(wiki)
    wiki_root = resolve_wiki_path(wiki_name)
    cfg = load_config(project_config=wiki_root / ".synthadoc" / "config.toml")
    store = WikiStorage(wiki_root / "wiki")
    agent_cfg = cfg.agents.resolve("query")

    # ── Cost check (local, no API key needed) ────────────────────────────────
    if not yes:
        pages_with_checks = _collect_checks_for_cost(wiki_root, store, page)
        total_citations = sum(len(v) for v in pages_with_checks.values())
        est_tokens = estimate_faithfulness_tokens(pages_with_checks)
        est_cost = estimate_cost(
            agent_cfg.model,
            input_tokens=est_tokens,
            output_tokens=est_tokens // 5,
            is_local=agent_cfg.is_local,
        )
        guard = CostGuard(cfg.cost)
        try:
            guard.check(
                CostEstimate(
                    tokens=est_tokens,
                    cost_usd=est_cost,
                    operation=(
                        f"citation faithfulness audit "
                        f"({total_citations} citations across {len(pages_with_checks)} pages)"
                    ),
                ),
                interactive=True,
            )
        except CostGateError:
            console.print("[yellow]Audit cancelled.[/yellow]")
            raise typer.Exit(1)

    # ── Enqueue job on the running server ─────────────────────────────────────
    body: dict = {}
    if page:
        body["page_slug"] = page
    result = http_post(wiki_name, "/audit/citations/faithfulness", body)
    job_id: str = result.get("job_id", "")
    if not job_id:
        console.print(f"[red]Unexpected response from server:[/red] {result}")
        raise typer.Exit(1)

    console.print(f"[dim]Job {job_id[:8]}… enqueued — waiting for results[/dim]")

    # ── Poll until terminal ───────────────────────────────────────────────────
    POLL_SECONDS = 3
    while True:
        job = http_get(wiki_name, f"/jobs/{job_id}")
        status: str = job.get("status", "unknown")
        if status in ("pending", "in_progress"):
            progress = job.get("progress") or {}
            phase = progress.get("phase", "starting")
            checked = progress.get("pages_checked", 0)
            total_pages = progress.get("pages_total", 0)
            current = progress.get("current_slug", "")
            if phase == "auditing" and total_pages:
                msg = f"[dim]({checked}/{total_pages})[/dim] Checking [bold]{current}[/bold]…"
            else:
                msg = "[dim]Starting audit…[/dim]"
            console.print(msg)
            time.sleep(POLL_SECONDS)
        elif status == "completed":
            break
        else:
            error = job.get("error") or "unknown error"
            console.print(f"[red]Audit job {status}:[/red] {error}")
            raise typer.Exit(1)

    # ── Read results from cache and display ───────────────────────────────────
    from synthadoc.agents.faithfulness_cache import read_cache
    from synthadoc.agents.citation_faithfulness import FaithfulnessResult

    cache = read_cache(wiki_root)
    entries = cache.get("entries", {})

    if page:
        slugs_to_show = [page] if page in entries else []
    else:
        slugs_to_show = list(entries.keys())

    all_results: list[FaithfulnessResult] = []
    for slug in slugs_to_show:
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
