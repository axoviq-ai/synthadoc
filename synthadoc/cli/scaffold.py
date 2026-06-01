# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

from typing import Optional

import typer

from synthadoc.cli.main import app
from synthadoc import errors as E


@app.command("scaffold")
def scaffold_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w", help="Wiki name or path"),
):
    """Re-generate domain-specific scaffold files for an existing wiki.

    Rewrites index.md, AGENTS.md, and purpose.md using the LLM.
    The LLM call runs on the server — no API key needed on the client.
    Monitor progress with: synthadoc jobs

    Examples:

      synthadoc scaffold -w my-research

      synthadoc scaffold -w ~/wikis/my-research
    """
    from synthadoc.cli._wiki import resolve_wiki
    from synthadoc.cli._http import get, post

    wiki = resolve_wiki(wiki)

    try:
        cfg_info = get(wiki, "/config")
        domain = cfg_info.get("domain", "General")
    except Exception as exc:
        E.cli_error(E.SERVER_NOT_RUNNING,
                    f"Cannot reach server: {exc}",
                    "Run `synthadoc serve` first.")

    typer.echo(f"Queuing scaffold for domain: {domain}…")
    try:
        result = post(wiki, "/jobs/scaffold", {"domain": domain})
    except Exception as exc:
        E.cli_error(E.AGENT_FAILED,
                    f"Scaffold request failed: {exc}",
                    "Is `synthadoc serve` running?")

    job_id = result.get("job_id", "?")
    typer.echo(f"Scaffold job queued: {job_id}")
    typer.echo("Monitor progress with: synthadoc jobs")
