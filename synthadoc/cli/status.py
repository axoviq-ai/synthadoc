# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

from typing import Optional

import typer

from synthadoc.cli.main import app
from synthadoc.cli._http import get
from synthadoc.storage.wiki import LifecycleState


@app.command("status")
def status_cmd(wiki: Optional[str] = typer.Option(None, "--wiki", "-w")):
    """Show wiki status including lifecycle summary. Requires synthadoc serve to be running."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    result = get(wiki, "/status")
    typer.echo(f"Wiki:         {result['wiki']}")
    typer.echo(f"Pages:        {result['pages']}")
    typer.echo(f"Jobs pending: {result['jobs_pending']}")
    typer.echo(f"Jobs total:   {result['jobs_total']}")

    try:
        lc = get(wiki, "/lifecycle/status")
        counts = lc.get('counts', {})
        typer.echo("\nPage lifecycle:")
        if not counts:
            typer.echo("  (none — run `synthadoc lint run` to initialise lifecycle states)")
        else:
            _HINTS = {
                "draft":            "<- run `synthadoc lint run` to promote",
                "draft_candidates": "<- promote from candidates/ first, then lint",
                "stale":            "<- re-ingest needed",
                "contradicted":     "<- review required",
            }
            _LABELS = {
                "draft_candidates": "draft (staged)",
            }
            display_states = list(LifecycleState.ORDERED)
            if counts.get("draft_candidates", 0) > 0:
                idx = display_states.index("draft") + 1
                display_states.insert(idx, "draft_candidates")
            for state in display_states:
                count = counts.get(state, 0)
                label = _LABELS.get(state, state)
                hint = f"  {_HINTS[state]}" if state in _HINTS and count > 0 else ""
                typer.echo(f"  {label:<14} {count}{hint}")
    except Exception:
        pass  # server may not support lifecycle yet
