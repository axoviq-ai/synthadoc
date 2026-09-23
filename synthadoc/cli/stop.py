# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import os
import signal
from pathlib import Path
from typing import Optional

import httpx
import typer

from synthadoc.cli.main import app
from synthadoc.cli._wiki import read_registry_all, resolve_wiki_path


def _stop_wiki(wiki_name: str) -> bool:
    """Stop wiki by name. Returns True if stopped, False if not running."""
    try:
        path = resolve_wiki_path(wiki_name)
    except Exception:
        typer.echo(f"  {wiki_name}: not found in registry", err=True)
        return False

    # Try POST /shutdown first
    pid_file = path / ".synthadoc" / "server.pid"
    config_path = path / ".synthadoc" / "config.toml"
    if config_path.exists():
        try:
            from synthadoc.config import load_config
            cfg = load_config(project_config=config_path)
            resp = httpx.post(f"http://127.0.0.1:{cfg.server.port}/shutdown", timeout=5)
            if resp.status_code in (200, 204):
                typer.echo(f"  {wiki_name}: stopped")
                if pid_file.exists():
                    pid_file.unlink(missing_ok=True)
                return True
        except Exception:
            pass

    # Fallback: kill via PID file
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            pid_file.unlink(missing_ok=True)
            typer.echo(f"  {wiki_name}: stopped (via PID {pid})")
            return True
        except (ProcessLookupError, ValueError):
            pid_file.unlink(missing_ok=True)

    typer.echo(f"  {wiki_name}: not running")
    return False


@app.command("stop")
def stop_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w", help="Wiki name to stop"),
    all_wikis: bool = typer.Option(False, "--all", help="Stop all running wikis"),
):
    """Stop a running wiki server."""
    if all_wikis:
        registry = read_registry_all()
        if not registry:
            typer.echo("No wikis registered.")
            return
        for name in registry:
            _stop_wiki(name)
        return

    if wiki:
        _stop_wiki(wiki)
        return

    # No args: try resolve from cwd
    from synthadoc.cli._wiki import resolve_wiki
    resolved = resolve_wiki(None)
    if resolved:
        _stop_wiki(resolved)
    else:
        typer.echo("Error: specify -w <wiki> or --all", err=True)
        raise typer.Exit(1)
