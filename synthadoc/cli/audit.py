# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from synthadoc.cli.install import resolve_wiki_path

audit_app = typer.Typer(name="audit", help="Inspect ingest history and costs.")
console = Console()


def _get_audit_db(wiki: str):
    from synthadoc.storage.log import AuditDB
    root = resolve_wiki_path(wiki)
    return AuditDB(root / ".synthadoc" / "audit.db")


@audit_app.command("history")
def history_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    limit: int = typer.Option(50, "--limit", "-n"),
    as_json: bool = typer.Option(False, "--json", help="Output raw JSON"),
):
    """Show recent ingest history."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    db = _get_audit_db(wiki)

    async def _fetch():
        await db.init()
        return await db.list_ingests(limit=limit)

    records = asyncio.run(_fetch())
    if as_json:
        typer.echo(json.dumps(records, indent=2))
        return
    table = Table(title=f"Ingest History (last {limit})")
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
    as_json: bool = typer.Option(False, "--json", help="Output raw JSON"),
):
    """Show recent query history."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    db = _get_audit_db(wiki)

    async def _fetch():
        await db.init()
        return await db.list_queries(limit=limit)

    records = asyncio.run(_fetch())
    if as_json:
        typer.echo(json.dumps(records, indent=2))
        return
    table = Table(title=f"Query History (last {limit})")
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
    limit: int = typer.Option(50, "--limit", "-n"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Show claim-level citations and validation failures."""
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


@audit_app.command("events")
def events_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    limit: int = typer.Option(100, "--limit", "-n"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Show raw audit events."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    db = _get_audit_db(wiki)

    async def _fetch():
        await db.init()
        return await db.list_events(limit=limit)

    events = asyncio.run(_fetch())
    if as_json:
        typer.echo(json.dumps(events, indent=2))
        return
    table = Table(title=f"Audit Events (last {limit})")
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
