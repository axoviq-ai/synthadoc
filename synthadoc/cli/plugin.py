# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

import typer

from synthadoc.cli._wiki import resolve_wiki
from synthadoc.cli.install import resolve_wiki_path
from synthadoc.cli.main import app

plugin_app = typer.Typer(name="plugin", help="Manage the Synthadoc Obsidian plugin.")
app.add_typer(plugin_app)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_PLUGIN_SRC = _REPO_ROOT / "obsidian-plugin"
_PLUGIN_FILES = ("main.js", "manifest.json", "styles.css")
_PLUGIN_ID = "synthadoc"


@plugin_app.command("install")
def plugin_install_cmd(
    wiki: Optional[str] = typer.Argument(None, help="Wiki name (uses default if omitted)"),
    w: Optional[str] = typer.Option(None, "--wiki", "-w", help="Wiki name or path"),
):
    """Copy the built Obsidian plugin into a wiki vault.

    \b
    Examples:
      synthadoc plugin install ai-research
      synthadoc plugin install -w ai-research
      synthadoc plugin install               # uses default wiki (synthadoc use <name>)
    """
    wiki_name = resolve_wiki(w or wiki)
    wiki_path = resolve_wiki_path(wiki_name)

    if not wiki_path.exists():
        typer.echo(
            f"Error: wiki path '{wiki_path}' does not exist on disk.\n"
            f"The registry entry for '{wiki_name}' may be stale.",
            err=True,
        )
        raise typer.Exit(1)

    if not _PLUGIN_SRC.exists():
        typer.echo(
            f"Error: obsidian-plugin/ not found at '{_PLUGIN_SRC}'.\n"
            "Run this command from the synthadoc repo root.",
            err=True,
        )
        raise typer.Exit(1)

    dest_dir = wiki_path / ".obsidian" / "plugins" / _PLUGIN_ID
    dest_dir.mkdir(parents=True, exist_ok=True)

    copied = []
    for filename in _PLUGIN_FILES:
        src = _PLUGIN_SRC / filename
        if src.exists():
            shutil.copy2(src, dest_dir / filename)
            copied.append(filename)

    if not copied:
        typer.echo(
            "Error: no plugin files found in obsidian-plugin/.\n"
            "Build the plugin first: cd obsidian-plugin && npm run build",
            err=True,
        )
        raise typer.Exit(1)

    typer.echo(f"Plugin installed into: {dest_dir}")
    for f in copied:
        typer.echo(f"  copied  {f}")
    typer.echo()
    typer.echo("Open Obsidian, go to Settings > Community Plugins, and enable 'Synthadoc'.")
    typer.echo("Set the server URL to match your wiki's configured port.")
