# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

from typing import Optional

import typer

from synthadoc.cli.main import app
from synthadoc.cli._http import get
from synthadoc.cli._wiki import read_registry_all
from synthadoc.storage.wiki import LifecycleState


def _port_from_config(wiki_path: str, wiki_name: str) -> int | None:
    """Read port from config.toml when the registry entry lacks one."""
    if not wiki_path:
        return None
    from pathlib import Path
    import tomllib
    for candidate in (
        Path(wiki_path) / wiki_name / ".synthadoc" / "config.toml",
        Path(wiki_path) / ".synthadoc" / "config.toml",
    ):
        if candidate.exists():
            try:
                with open(candidate, "rb") as f:
                    return tomllib.load(f).get("server", {}).get("port")
            except Exception:
                pass
    return None


def render_status_all(registry: dict) -> None:
    """Print a running/stopped table for all registered wikis."""
    from synthadoc.cli._wiki import probe_port
    if not registry:
        typer.echo("No wikis registered.")
        return
    typer.echo(f"{'wiki':<20} {'port':<8} {'status':<10} {'pages':<8} {'last-ingest'}")
    typer.echo("-" * 60)
    for name, entry in registry.items():
        port = entry.get("port") or _port_from_config(entry.get("path", ""), name)
        if port and probe_port(port):
            try:
                import httpx
                resp = httpx.get(f"http://127.0.0.1:{port}/status", timeout=2)
                data = resp.json()
                pages = data.get("pages", "?")
                last = data.get("last_ingest", "—")
                typer.echo(f"{name:<20} {port:<8} {'running':<10} {str(pages):<8} {last}")
            except Exception:
                typer.echo(f"{name:<20} {str(port):<8} {'running':<10} {'—':<8} —")
        else:
            typer.echo(f"{name:<20} {str(port or '?'):<8} {'stopped':<10} {'—':<8} —")


@app.command("status")
def status_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    all_wikis: bool = typer.Option(False, "--all", help="Show status for all registered wikis"),
):
    """Show wiki status. With --all: show running/stopped state for every registered wiki."""
    if all_wikis:
        render_status_all(read_registry_all())
        return

    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    result = get(wiki, "/status")
    typer.echo(f"Wiki:         {result['wiki']}")
    typer.echo(f"Pages:        {result['pages']}")
    typer.echo(f"Jobs pending: {result['jobs_pending']}")
    typer.echo(f"Jobs total:   {result['jobs_total']}")

    try:
        lc = get(wiki, "/lifecycle/status")
        counts = lc.get("counts") or lc  # server returns flat dict; tolerate old wrapped format
        typer.echo("\nPage lifecycle:")
        if not counts:
            typer.echo("  (none - run `synthadoc lint run` to initialise lifecycle states)")
            return
        _HINTS = {
            "draft":            "<- run `synthadoc lint run` to promote",
            "draft_candidates": "<- promote from candidates/ first, then lint",
            "stale":            "<- re-ingest needed",
            "contradicted":     "<- review required",
            "unlinted":         "<- run `synthadoc lint run`",
        }
        _LABELS = {
            "draft_candidates": "draft (staged)",
        }
        display_states = list(LifecycleState.ORDERED)
        if counts.get("draft_candidates", 0) > 0:
            idx = display_states.index("draft") + 1
            display_states.insert(idx, "draft_candidates")
        if counts.get("unlinted", 0) > 0:
            display_states.append("unlinted")
        for state in display_states:
            count = counts.get(state, 0)
            label = _LABELS.get(state, state)
            hint = f"  {_HINTS[state]}" if state in _HINTS and count > 0 else ""
            typer.echo(f"  {label:<14} {count}{hint}")
        if not any(counts.get(s, 0) for s in LifecycleState.ORDERED):
            typer.echo("  (run `synthadoc lint run` to initialise lifecycle states)")
    except Exception:
        pass  # server may not support lifecycle yet
