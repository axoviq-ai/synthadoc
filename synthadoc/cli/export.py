# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

from typing import Optional

import httpx
import typer

from synthadoc.cli.main import app
from synthadoc.cli._http import server_url
from synthadoc.cli._wiki import resolve_wiki
from synthadoc import errors as E


@app.command("export")
def export_cmd(
    format: str = typer.Option(..., "--format", "-f",
        help="Output format: llms.txt, llms-full.txt, graphml, json, okf"),
    output: Optional[str] = typer.Option(None, "--output", "-o",
        help="Write to file (or directory for --format okf). Defaults to stdout."),
    status: str = typer.Option("all", "--status", "-s",
        help="Filter pages by lifecycle state: all, active, draft, stale, contradicted, archived"),
    context_pack: Optional[str] = typer.Option(None, "--context-pack", "-c",
        help="Export only pages in named context pack"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
):
    """Export wiki as llms.txt, llms-full.txt, graphml, json, or okf bundle directory."""
    wiki_name = resolve_wiki(wiki)
    url = server_url(wiki_name)
    body: dict = {"format": format, "status_filter": status}
    if context_pack:
        body["context_pack"] = context_pack

    try:
        resp = httpx.post(f"{url}/export", json=body, timeout=60)
        resp.raise_for_status()
    except httpx.ConnectError:
        E.cli_error(E.SRV_NOT_RUNNING,
                    f"No synthadoc server is running for wiki '{wiki_name}'.",
                    f"Start it with:\n  synthadoc serve -w {wiki_name}")
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", exc.response.text)
        except Exception:
            detail = exc.response.text
        E.cli_error(E.SRV_HTTP_ERROR, f"Export failed: {detail}")

    if format == "okf":
        if not output:
            typer.echo("Error: --output <directory> is required for --format okf.", err=True)
            raise typer.Exit(1)
        from pathlib import Path
        manifest: dict = resp.json()
        out_dir = Path(output)
        for rel_path, content in manifest.items():
            dest = out_dir / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8", newline="\n")
        typer.echo(f"OKF bundle written to {output} ({len(manifest)} files)", err=True)
        return

    content = resp.text
    if output:
        from pathlib import Path
        Path(output).write_text(content, encoding="utf-8")
        typer.echo(f"Exported to {output}", err=True)
    else:
        typer.echo(content, nl=False)
