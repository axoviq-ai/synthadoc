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
    """Sync an installed demo wiki with the latest bundled template.

    - raw_sources/: copies new files only (additive, never overwrites).
    - wiki/dashboard.md: updates the Dataview body to the current template
      while preserving the installed frontmatter (Obsidian-managed fields).
    - wiki/mechanical-computing.md, wiki/early-neural-networks.md and other
      new template wiki pages: copied if not already present.

    Use this after upgrading Synthadoc to pick up new features without reinstalling.
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

    installed_root = Path(entry["path"])
    updated: list[str] = []

    # ── 1. raw_sources: additive copy ─────────────────────────────────────────
    demo_sources = demo_template / "raw_sources"
    installed_sources = installed_root / "raw_sources"
    for src in demo_sources.rglob("*"):
        if not src.is_file():
            continue
        relative = src.relative_to(demo_sources)
        dest = installed_sources / relative
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            updated.append(f"  + raw_sources/{relative}")

    # ── 2. wiki/dashboard.md: replace body, preserve installed frontmatter ────
    template_dash = demo_template / "wiki" / "dashboard.md"
    installed_dash = installed_root / "wiki" / "dashboard.md"
    if template_dash.exists() and installed_dash.exists():
        tmpl_raw = template_dash.read_text(encoding="utf-8")
        inst_raw = installed_dash.read_text(encoding="utf-8")
        tmpl_body = _extract_body(tmpl_raw)
        inst_fm = _extract_frontmatter_block(inst_raw)
        new_content = f"---{inst_fm}---\n{tmpl_body}"
        if new_content.rstrip() != inst_raw.rstrip():
            installed_dash.write_text(new_content, encoding="utf-8", newline="\n")
            updated.append("  ~ wiki/dashboard.md  (Dataview sections updated)")

    # ── 3. wiki/: copy new template pages that don't exist yet ────────────────
    demo_wiki = demo_template / "wiki"
    installed_wiki = installed_root / "wiki"
    _SKIP_WIKI = {"index.md", "dashboard.md", "purpose.md"}  # user-authored or handled above
    for src in demo_wiki.glob("*.md"):
        if src.name in _SKIP_WIKI:
            continue
        dest = installed_wiki / src.name
        if not dest.exists():
            shutil.copy2(src, dest)
            updated.append(f"  + wiki/{src.name}")

    if updated:
        for line in sorted(updated):
            typer.echo(line)
    else:
        typer.echo("Already up to date — nothing to sync.")


def _extract_body(text: str) -> str:
    """Return everything after the closing '---' of a YAML frontmatter block."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2]
    return "\n" + text


def _extract_frontmatter_block(text: str) -> str:
    """Return the YAML between '---' markers, normalized to exactly one leading/trailing newline."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return "\n" + parts[1].strip() + "\n"
    return ""
