# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""CLI subcommands for sensitive-data detection and redaction.

Commands
--------
synthadoc retract scan [-w WIKI] [--slug SLUG] [--apply] [--yes]
synthadoc retract status [-w WIKI] [--limit N] [--json]
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from synthadoc.utils import fmt_ts

retract_app = typer.Typer(
    name="retract",
    help="Detect and redact sensitive data in wiki pages.",
)
console = Console()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_wiki_root(wiki: str) -> Path:
    from synthadoc.cli.install import resolve_wiki_path
    return resolve_wiki_path(wiki)


def _resolve_pages_dir(wiki_root: Path) -> Path:
    """Return the directory that holds wiki page .md files (always wiki_root/wiki/)."""
    return wiki_root / "wiki"


def _load_wiki_config(wiki_root: Path):
    from synthadoc.config import load_config
    cfg_path = wiki_root / ".synthadoc" / "config.toml"
    return load_config(project_config=cfg_path if cfg_path.exists() else None)


def _get_audit_db(wiki_root: Path):
    from synthadoc.storage.log import AuditDB
    return AuditDB(wiki_root / ".synthadoc" / "audit.db")


def _last_cycle_cutoff(wiki_root: Path) -> "datetime | None":
    """Return the UTC datetime of the last completed scan cycle, or None if none exists."""
    db = _get_audit_db(wiki_root)

    async def _fetch():
        await db.init()
        return await db.get_last_retract_cycle()

    cycle = asyncio.run(_fetch())
    if not cycle:
        return None
    ts = cycle.get("timestamp", "")
    if not ts:
        return None
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _mtime_utc(path: Path) -> datetime:
    """Return file modification time as a UTC-aware datetime."""
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@retract_app.command("scan")
def scan_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    slug: Optional[str] = typer.Option(None, "--slug", help="Scan a single page slug"),
    apply: bool = typer.Option(False, "--apply", help="Apply redactions (write back to files)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
    changed_only: bool = typer.Option(
        False, "--changed-only",
        help="Only scan pages modified since the last scan cycle (skips unchanged files).",
    ),
):
    """Scan wiki pages for sensitive data.

    \b
    Dry-run by default — prints matches (slug + line number + data type)
    without revealing any sensitive values.

    Use --apply to write [REDACTED] substitutions back to each page.
    The audit log records slug, match count, and pattern types; never
    any fragment of the sensitive value itself.

    Use --changed-only to skip pages that have not been modified since
    the last completed scan cycle.  Useful on large wikis where most
    pages are stable between runs.
    """
    from synthadoc.cli._wiki import resolve_wiki
    from synthadoc.core.retract import SensitiveScanner

    wiki = resolve_wiki(wiki)
    wiki_root = _resolve_wiki_root(wiki)
    pages_dir = _resolve_pages_dir(wiki_root)
    cfg = _load_wiki_config(wiki_root)
    scanner = SensitiveScanner(cfg.security)

    # Collect target slugs
    if slug:
        slugs = [slug]
    else:
        slugs = [p.stem for p in pages_dir.glob("*.md")]
        if changed_only:
            cutoff_dt = _last_cycle_cutoff(wiki_root)
            if cutoff_dt is None:
                console.print("[dim]--changed-only: no previous scan recorded — scanning all pages.[/dim]")
            else:
                before = len(slugs)
                slugs = [
                    s for s in slugs
                    if _mtime_utc(pages_dir / f"{s}.md") > cutoff_dt
                ]
                skipped = before - len(slugs)
                if skipped:
                    console.print(
                        f"[dim]--changed-only: {skipped} page(s) unchanged since last scan — skipped.[/dim]"
                    )
                if not slugs:
                    console.print("[green]✓[/green] No pages modified since the last scan.")
                    return

    # Scan all targets
    all_matches = {}   # slug → list[ScanMatch]
    all_contents = {}  # slug → str  (same read used for scanning; avoids TOCTOU in _apply)
    pages_scanned = 0
    for s in sorted(slugs):
        page_path = pages_dir / f"{s}.md"
        if not page_path.exists():
            console.print(f"[yellow]Warning: page not found: {s}[/yellow]")
            continue
        content = page_path.read_text(encoding="utf-8")
        matches = scanner.scan_page(s, content)
        pages_scanned += 1
        if matches:
            all_matches[s] = matches
            all_contents[s] = content

    total_matches = sum(len(m) for m in all_matches.values())

    if not all_matches:
        console.print(
            f"[green]✓[/green] {pages_scanned} page(s) scanned — no sensitive data detected."
        )
        return

    # Display results table (no values, only metadata).
    # "Type" shows the data category; for custom patterns the pattern name is
    # appended in parentheses so the column stays compact when all matches are
    # built-in patterns.
    table = Table(title=f"Sensitive Data Scan — {pages_scanned} page(s) scanned, {total_matches} match(es) in {len(all_matches)} page(s)")
    table.add_column("Page", style="cyan")
    table.add_column("Line", justify="right")
    table.add_column("Type")
    for s, matches in sorted(all_matches.items()):
        for m in matches:
            type_label = m.data_type.value
            if m.pattern_name != m.data_type.value:
                type_label = f"{m.data_type.value} ({m.pattern_name})"
            table.add_row(m.slug, str(m.line_no), type_label)
    console.print(table)

    if not apply:
        console.print(
            f"\n[dim]{pages_scanned} page(s) scanned, {total_matches} match(es) found. "
            f"Run with --apply to redact.[/dim]"
        )
        return

    # Confirm before writing
    if not yes:
        confirmed = typer.confirm(
            f"Apply [REDACTED] substitutions to {len(all_matches)} page(s)?",
            default=False,
        )
        if not confirmed:
            typer.echo("Aborted.")
            raise typer.Exit(0)

    # Apply redactions
    db = _get_audit_db(wiki_root)

    async def _apply():
        await db.init()
        total_lines = 0
        for s, matches in all_matches.items():
            page_path = pages_dir / f"{s}.md"
            # Use the content captured at scan time — do not re-read to avoid TOCTOU.
            content = all_contents[s]
            masked, lines_changed = scanner.mask_page(s, content, matches)
            if lines_changed > 0:
                page_path.write_text(masked, encoding="utf-8")
                total_lines += lines_changed
                pattern_names = list({m.pattern_name for m in matches})
                await db.record_retract_event(
                    slug=s,
                    matches_count=len(matches),
                    pattern_names=pattern_names,
                    applied=True,
                )
                console.print(f"  [green]✓[/green] {s} — {lines_changed} line(s) redacted")
        return total_lines

    total_lines = asyncio.run(_apply())
    console.print(f"\n[bold green]Done.[/bold green] {total_lines} line(s) redacted across {len(all_matches)} page(s).")


@retract_app.command("status")
def status_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max rows to show"),
    as_json: bool = typer.Option(False, "--json", help="Output raw JSON"),
):
    """Show recent sensitive-data scan results from the audit log."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    wiki_root = _resolve_wiki_root(wiki)
    cfg = _load_wiki_config(wiki_root)
    db = _get_audit_db(wiki_root)

    async def _fetch():
        await db.init()
        cycle = await db.get_last_retract_cycle()
        events = await db.list_retract_events(limit=limit)
        return cycle, events

    cycle, events = asyncio.run(_fetch())

    if as_json:
        typer.echo(json.dumps({"cycle": cycle, "events": events}, indent=2))
        return

    # --- Schedule header ---
    console.print()
    console.print("[bold]Background Scan Schedule[/bold]")
    if cycle is None:
        console.print("  Last run:  [dim]Not yet run (server may still be in 60-second startup delay)[/dim]")
        console.print("  Next run:  [dim]Unknown[/dim]")
        console.print("  Status:    [dim]Pending[/dim]")
    else:
        cycle_meta = json.loads(cycle.get("metadata") or "{}")
        last_ts = fmt_ts(cycle.get("timestamp"))
        pages_checked = cycle_meta.get("pages_scanned", 0)
        pages_matched = cycle_meta.get("pages_with_matches", 0)
        next_run_raw = cycle_meta.get("next_run_at", "")
        cycle_error = cycle_meta.get("error")

        # Compute "in X days/hours" for next run
        next_run_display = fmt_ts(next_run_raw) if next_run_raw else "Unknown"
        try:
            next_dt = datetime.fromisoformat(next_run_raw.replace("Z", "+00:00"))
            delta = next_dt - datetime.now(timezone.utc)
            total_secs = int(delta.total_seconds())
            if total_secs < 0:
                in_str = "[dim](overdue — server may be stopped)[/dim]"
            elif total_secs < 3600:
                in_str = f"(in {total_secs // 60} min)"
            elif total_secs < 86400:
                in_str = f"(in {total_secs // 3600}h {(total_secs % 3600) // 60}m)"
            else:
                in_str = f"(in {total_secs // 86400}d {(total_secs % 86400) // 3600}h)"
        except Exception:  # noqa: BLE001
            in_str = ""

        status_str = (
            f"[red]ERROR — {cycle_error}[/red]" if cycle_error else "[green]OK[/green]"
        )
        interval_days = cfg.security.scan_interval_days
        console.print(f"  Interval:  every {interval_days} day(s)")
        console.print(
            f"  Last run:  [dim]{last_ts}[/dim] — "
            f"{pages_checked} page(s) checked, {pages_matched} with redactions"
        )
        console.print(f"  Next run:  {next_run_display} {in_str}")
        console.print(f"  Status:    {status_str}")

    console.print()

    if not events:
        console.print("[dim]No per-page redaction records found.[/dim]")
        return

    table = Table(title=f"Per-page Redaction History (last {len(events)})")
    table.add_column("Timestamp", style="dim")
    table.add_column("Page", style="cyan")
    table.add_column("Matches", justify="right")
    table.add_column("Applied")
    table.add_column("Pattern Types")
    for evt in events:
        meta = json.loads(evt.get("metadata") or "{}")
        applied = "[green]yes[/green]" if meta.get("applied") else "[dim]no[/dim]"
        table.add_row(
            fmt_ts(evt.get("timestamp")),
            meta.get("slug", ""),
            str(meta.get("matches_count", 0)),
            applied,
            ", ".join(meta.get("pattern_names", [])),
        )
    console.print(table)
