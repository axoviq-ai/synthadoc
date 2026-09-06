# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import typer

from synthadoc.cli.main import app

template_app = typer.Typer(help="Browse available domain templates.")
app.add_typer(template_app, name="templates")


@template_app.command("list")
def list_templates_cmd() -> None:
    """List available demo wikis and domain templates."""
    from synthadoc.cli.install import _DEMOS, _read_registry
    from synthadoc.core.template_engine import list_templates, get_template_description

    registry = _read_registry()

    # ── Demos section ─────────────────────────────────────────────────────────
    typer.echo("Demos  " + "─" * 52)
    for demo_name in _DEMOS:
        status = ""
        if demo_name in registry:
            status = f"  (installed at {registry[demo_name]['path']})"
        typer.echo(f"  {demo_name:<30}{status}")
    typer.echo()
    typer.echo("  Install:  synthadoc install <name> --demo")
    typer.echo()

    # ── Templates section ──────────────────────────────────────────────────────
    typer.echo("Templates  " + "─" * 50)
    templates = list_templates()
    if not templates:
        typer.echo("\n  No templates installed.")
    else:
        for category, domains in templates.items():
            typer.echo(f"\n  {category}/")
            for domain in domains:
                ref = f"{category}/{domain}"
                desc = get_template_description(ref)
                typer.echo(f"    {domain:<26}{desc}")

    typer.echo()
    typer.echo("  Install:  synthadoc install <name> --target <dir> --template <category/domain>")
    typer.echo("  Example:  synthadoc install my-wiki --target ~/wikis --template finance/investment")
