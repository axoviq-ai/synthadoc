# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

from typing import Optional

import httpx
import typer

from synthadoc.cli.main import app
from synthadoc.cli._http import server_url
from synthadoc.cli._wiki import resolve_wiki, resolve_wiki_path
from synthadoc import errors as E


@app.command("export")
def export_cmd(
    format: str = typer.Option(..., "--format", "-f",
        help="Output format: llms.txt, llms-full.txt, graphml, json, okf"),
    output: Optional[str] = typer.Option(None, "--output", "-o",
        help=(
            "Destination path. For --format okf: required — a base directory; "
            "the bundle is written into <base>/<wiki>-okf-<YYYY-MM-DD>/ "
            "(created automatically). For all other formats: optional file path; "
            "omit to print to stdout."
        )),
    status: str = typer.Option("all", "--status", "-s",
        help="Filter pages by lifecycle state: all, active, draft, stale, contradicted, archived"),
    context_pack: Optional[str] = typer.Option(None, "--context-pack", "-c",
        help="Export only pages in named context pack"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
):
    """Export wiki as llms.txt, llms-full.txt, graphml, json, or OKF v0.2 bundle directory.

    For --format okf, --output <base-dir> is required. The bundle is written
    into <base-dir>/<wiki>-okf-<YYYY-MM-DD>/ so each export gets its own
    timestamped folder. All other formats print to stdout when --output is omitted.
    """
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
        from datetime import datetime, timezone
        # Strip a stray trailing quote that Windows cmd.exe injects when a
        # backslash-terminated path is double-quoted: "C:\path\" → C:\path"
        output = output.rstrip('"')
        manifest: dict = resp.json()
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # wiki_name may be "." when resolved from CWD; use the real directory name.
        bundle_name = Path(resolve_wiki_path(wiki_name)).resolve().name
        out_dir = Path(output) / f"{bundle_name}-okf-{ts}"
        for rel_path, content in manifest.items():
            dest = out_dir / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8", newline="\n")
        typer.echo(f"OKF bundle written to {out_dir} ({len(manifest)} files)", err=True)
        return

    content = resp.text
    if output:
        from pathlib import Path
        Path(output).write_text(content, encoding="utf-8")
        typer.echo(f"Exported to {output}", err=True)
    else:
        typer.echo(content, nl=False)
