# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

import typer

from synthadoc.cli.main import app
from synthadoc.cli._wiki import resolve_wiki_path
from synthadoc import errors as E

schedule_app = typer.Typer(help="Manage recurring scheduled operations.")
app.add_typer(schedule_app, name="schedule")


def _resolve_and_validate(wiki: Optional[str]) -> Path:
    if wiki is None:
        E.cli_error(
            E.WIKI_NOT_FOUND,
            "--wiki / -w is required for schedule commands.",
            "Provide a registered wiki name: synthadoc schedule <cmd> -w <name>",
        )
    root = resolve_wiki_path(wiki)
    if not (root / ".synthadoc" / "config.toml").exists():
        E.cli_error(
            E.WIKI_NOT_REGISTERED,
            f"Wiki '{wiki}' is not installed.",
            f"Make sure wiki '{wiki}' was installed with 'synthadoc install'.",
        )
    return root


@schedule_app.command("add")
def add_cmd(
    op: str = typer.Option(..., "--op", help="synthadoc operation (e.g. 'lint run')"),
    cron: str = typer.Option(..., "--cron", help="Cron expression"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
) -> None:
    """Register a recurring operation with the synthadoc server scheduler."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    from synthadoc.core.scheduler import Scheduler
    root = _resolve_and_validate(wiki)
    sched = Scheduler(wiki=wiki, wiki_root=str(root))
    entry_id = sched.add(op=op, cron=cron)
    typer.echo(f"Scheduled: {entry_id}")


@schedule_app.command("list")
def list_cmd(wiki: Optional[str] = typer.Option(None, "--wiki", "-w")) -> None:
    """List all synthadoc-registered scheduled jobs with schedule and run history."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    from synthadoc.core.scheduler import Scheduler
    root = _resolve_and_validate(wiki)
    sched = Scheduler(wiki=wiki, wiki_root=str(root))
    entries = sched.list()
    if not entries:
        typer.echo("No scheduled jobs found.")
        return
    typer.echo(f"{'ID':<20} {'Schedule':<18} {'Next Run':<20} {'Last Run':<20} {'Last Result':<14} Command")
    typer.echo("-" * 110)
    for e in entries:
        typer.echo(
            f"{e.id:<20} {(e.cron or '—'):<18} {(e.next_run or '—'):<20}"
            f" {(e.last_run or '—'):<20} {(e.last_result or '—'):<14} {e.op}"
        )


@schedule_app.command("remove")
def remove_cmd(
    entry_id: str = typer.Argument(...),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
) -> None:
    """Remove a scheduled job by ID."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    from synthadoc.core.scheduler import Scheduler
    root = _resolve_and_validate(wiki)
    sched = Scheduler(wiki=wiki, wiki_root=str(root))
    sched.remove(entry_id)
    typer.echo(f"Removed: {entry_id}")


@schedule_app.command("apply")
def apply_cmd(wiki: Optional[str] = typer.Option(None, "--wiki", "-w")) -> None:
    """Register all jobs declared in [schedule] in the project config."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    from synthadoc.config import load_config
    from synthadoc.core.scheduler import Scheduler, ScheduleEntry
    root = _resolve_and_validate(wiki)
    cfg = load_config(project_config=root / ".synthadoc" / "config.toml")
    sched = Scheduler(wiki=wiki, wiki_root=str(root))
    ids = sched.apply([ScheduleEntry(op=j.op, cron=j.cron, wiki=wiki)
                       for j in cfg.schedule.jobs])
    for entry_id in ids:
        typer.echo(f"Registered: {entry_id}")


@schedule_app.command("run")
def run_cmd(
    op: str = typer.Option(..., "--op", help="Operation to run (e.g. 'lint run')"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
) -> None:
    """Execute a scheduled operation and record the result in the audit trail."""
    from synthadoc.cli._wiki import resolve_wiki
    from synthadoc.storage.log import AuditDB

    wiki_name = resolve_wiki(wiki)
    root = _resolve_and_validate(wiki_name)
    run_id = f"run-{uuid.uuid4().hex[:8]}"

    db = AuditDB(root / ".synthadoc" / "audit.db")
    asyncio.run(db.init())
    asyncio.run(db.record_scheduled_run_start(run_id, op, wiki_name))

    typer.echo(f"[schedule] {run_id}  {op}  starting")
    t0 = time.monotonic()
    try:
        cmd = [sys.executable, "-m", "synthadoc", "-w", wiki_name] + op.split()
        sub_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        result = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True,
                                encoding="utf-8", env=sub_env)
        duration = time.monotonic() - t0
        if result.stdout:
            typer.echo(result.stdout, nl=False)
        if result.returncode == 0:
            asyncio.run(db.record_scheduled_run_finish(run_id, "success", duration))
            typer.echo(f"[schedule] {run_id}  {op}  {duration:.1f}s  success")
        else:
            stderr_snippet = result.stderr.strip()[:300] if result.stderr else ""
            err = f"exit code {result.returncode}" + (f": {stderr_snippet}" if stderr_snippet else "")
            asyncio.run(db.record_scheduled_run_finish(run_id, "failed", duration, err))
            if result.stderr:
                typer.echo(result.stderr, nl=False, err=True)
            typer.echo(f"[schedule] {run_id}  {op}  {duration:.1f}s  failed ({err})", err=True)
            raise typer.Exit(result.returncode)
    except typer.Exit:
        raise
    except Exception as exc:
        duration = time.monotonic() - t0
        asyncio.run(db.record_scheduled_run_finish(run_id, "failed", duration, str(exc)))
        typer.echo(f"  {run_id}  {op}  failed: {exc}", err=True)
        raise typer.Exit(1)


@schedule_app.command("history")
def history_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    limit: int = typer.Option(20, "--limit", "-n"),
) -> None:
    """Show recent scheduled run history from the audit trail."""
    from synthadoc.cli._wiki import resolve_wiki
    from synthadoc.storage.log import AuditDB

    wiki_name = resolve_wiki(wiki)
    root = _resolve_and_validate(wiki_name)
    db = AuditDB(root / ".synthadoc" / "audit.db")

    async def _fetch():
        await db.init()
        return await db.list_scheduled_runs(limit=limit)

    from synthadoc.core.scheduler import _format_run_ts

    runs = asyncio.run(_fetch())
    if not runs:
        typer.echo("No scheduled run history found.")
        return

    typer.echo(f"{'Run ID':<20} {'Op':<14} {'Started':<20} {'Duration':>10}  Status")
    typer.echo("-" * 72)
    for r in runs:
        dur = f"{r['duration_s']:.1f}s" if r.get("duration_s") is not None else "-"
        started = _format_run_ts(r.get("started_at") or "")
        typer.echo(
            f"{r['run_id']:<20} {r['op']:<14} {started:<20} {dur:>10}  {r.get('status') or '-'}"
        )

    detail_runs = [
        r for r in runs
        if (r.get("status") == "success" and r.get("output"))
        or (r.get("status") != "success" and (r.get("error") or r.get("output")))
    ]
    if detail_runs:
        typer.echo("")
        typer.echo("Details")
        typer.echo("-" * 7)
        for r in detail_runs:
            typer.echo(f"{r['run_id']}  {r['op']}  {r.get('status') or '-'}")
            content = (
                r.get("error") if r.get("status") != "success"
                else r.get("output") or ""
            )
            for line in (content or "").splitlines():
                typer.echo(f"  {line}")
            typer.echo("")
