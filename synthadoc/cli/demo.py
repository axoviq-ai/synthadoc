# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import shutil
from pathlib import Path

import typer

from synthadoc.cli.main import app
from synthadoc.cli.install import _DEMOS, _read_registry

demo_app = typer.Typer(help="Demo wiki templates.")
app.add_typer(demo_app, name="demo")


@demo_app.command("list")
def list_demos():
    """List available demo templates and their install status."""
    registry = _read_registry()
    for name in _DEMOS:
        entry = registry.get(name)
        if entry:
            typer.echo(f"  {name}  (installed at {entry['path']})")
        else:
            typer.echo(f"  {name}")


@demo_app.command("sync")
def sync_demo(
    name: str = typer.Argument(..., help="Installed wiki name to sync (e.g. history-of-computing)"),
) -> None:
    """Copy any new source files from the bundled demo into an existing installed wiki.

    Additive only — never overwrites existing files. Use this after upgrading Synthadoc
    to pick up new demo source files without reinstalling.
    """
    registry = _read_registry()
    entry = registry.get(name)
    if entry is None:
        typer.echo(
            f"Wiki '{name}' not found in registry. Run: synthadoc install {name} --demo"
        )
        raise typer.Exit(1)

    demo_template = _DEMOS.get(name)
    if demo_template is None:
        typer.echo(f"No bundled demo template found for '{name}'")
        raise typer.Exit(1)

    demo_sources = demo_template / "raw_sources"
    installed_sources = Path(entry["path"]) / "raw_sources"

    copied: list[Path] = []
    for src in demo_sources.rglob("*"):
        if not src.is_file():
            continue
        relative = src.relative_to(demo_sources)
        dest = installed_sources / relative
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied.append(relative)

    if copied:
        for rel in sorted(copied):
            typer.echo(f"  + {rel}")
    else:
        typer.echo("Already up to date — no new files to copy.")
