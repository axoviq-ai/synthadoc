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

    import time
    job_id = result.get("job_id", "?")
    typer.echo(f"Scaffold job queued: {job_id}")
    typer.echo("Waiting for scaffold to complete…")

    while True:
        time.sleep(2)
        try:
            job = get(wiki, f"/jobs/{job_id}")
        except Exception:
            typer.echo("Monitor progress with: synthadoc jobs")
            break
        status = job.get("status", "")
        if status == "completed":
            cats = (job.get("result") or {}).get("categories_updated", 0)
            typer.echo("Scaffold complete.")
            typer.echo("  index.md    updated")
            typer.echo("  AGENTS.md   updated")
            typer.echo("  CLAUDE.md   updated")
            typer.echo("  GEMINI.md   updated")
            typer.echo("  purpose.md  updated")
            typer.echo(f"  categories  stamped on {cats} page(s)")
            break
        if status in ("failed", "dead"):
            error = job.get("error") or "unknown error"
            E.cli_error(E.AGENT_FAILED, f"Scaffold failed: {error}",
                        "Check `synthadoc jobs` for details.")
            break
