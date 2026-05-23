# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

from typing import Optional

import typer

from synthadoc.cli._http import get, post
from synthadoc.cli._wiki import resolve_wiki
from synthadoc.storage.wiki import LifecycleState, TriggerSource

lifecycle_app = typer.Typer(name="lifecycle", help="Manage page lifecycle states.")


def _transition_cmd(slug: str, to_state: str, wiki: str, reason: str) -> None:
    result = post(wiki, "/lifecycle/transition", {
        "slug": slug, "to_state": to_state, "reason": reason,
    })
    if result.get("ok"):
        typer.echo(f"  {slug}: {result['from_state']} -> {result['to_state']}")
    else:
        typer.echo(f"  Error: {result.get('detail', 'unknown error')}", err=True)
        raise typer.Exit(1)


@lifecycle_app.command("activate")
def lifecycle_activate(
    slug: str = typer.Argument(..., help="Page slug to activate"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    reason: str = typer.Option(..., "--reason", help="Reason for activation (required)"),
) -> None:
    """Promote a draft page to active."""
    _transition_cmd(slug, LifecycleState.ACTIVE, resolve_wiki(wiki), reason)


@lifecycle_app.command("archive")
def lifecycle_archive(
    slug: str = typer.Argument(..., help="Page slug to archive"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    reason: str = typer.Option(..., "--reason", help="Reason for archiving (required)"),
) -> None:
    """Archive a page (retain for reference)."""
    _transition_cmd(slug, LifecycleState.ARCHIVED, resolve_wiki(wiki), reason)


@lifecycle_app.command("restore")
def lifecycle_restore(
    slug: str = typer.Argument(..., help="Page slug to restore"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    reason: str = typer.Option(..., "--reason", help="Reason for restoring (required)"),
) -> None:
    """Restore an archived page to draft."""
    _transition_cmd(slug, LifecycleState.DRAFT, resolve_wiki(wiki), reason)


@lifecycle_app.command("log")
def lifecycle_log(
    slug: Optional[str] = typer.Argument(None, help="Page slug (omit for all pages)"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    state: Optional[str] = typer.Option(None, "--state", help="Filter by to_state"),
    limit: int = typer.Option(50, "--limit"),
    offset: int = typer.Option(0, "--offset"),
) -> None:
    """Show lifecycle event history."""
    params: dict = {"limit": limit, "offset": offset}
    if slug:
        params["slug"] = slug
    if state:
        params["to_state"] = state
    result = get(resolve_wiki(wiki), "/lifecycle/events", **params)
    events = result.get("events", [])
    if not events:
        typer.echo("No lifecycle events found.")
        return
    typer.echo(f"{'Slug':<25} {'From':<14} {'To':<14} {'By':<12} {'Timestamp':<22} Reason")
    typer.echo("-" * 100)
    for e in events:
        typer.echo(
            f"{e['slug']:<25} {(e['from_state'] or 'null'):<14} {e['to_state']:<14}"
            f" {e['triggered_by']:<12} {e['timestamp'][:19]:<22} {e.get('reason', '')}"
        )
