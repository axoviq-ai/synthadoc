# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from pathlib import Path
from typing import Optional

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
    name: Optional[str] = typer.Argument(
        None,
        help="Demo wiki name to sync (e.g. history-of-computing). Omit to sync all installed demos.",
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite existing wiki pages from the latest template."
    ),
) -> None:
    """[Deprecated] Sync installed demo wiki(s) with the latest bundled template.

    This command is deprecated. Use 'synthadoc templates sync' instead, which
    handles both demo wikis and domain-template wikis in one place.
    """
    typer.echo(
        "Warning: 'synthadoc demo sync' is deprecated and will be removed in a future version.\n"
        "Use 'synthadoc templates sync' instead.",
        err=True,
    )
    from synthadoc.cli.templates import _do_sync
    _do_sync(name=name, force=force)


