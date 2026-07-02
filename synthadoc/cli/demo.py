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
    name: str = typer.Argument(
        None,
        help="Demo wiki name to sync (e.g. history-of-computing). Omit to sync all installed demos.",
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite existing wiki pages from the latest template."
    ),
) -> None:
    """Sync installed demo wiki(s) with the latest bundled template.

    - raw_sources/: copies new files only (additive, never overwrites).
    - wiki/dashboard.md: updates the Dataview body to the current template
      while preserving the installed frontmatter (Obsidian-managed fields).
    - New template wiki pages: copied if not already present.
    - Existing pages: new metadata fields (e.g. type:) backfilled if missing.

    Omit the wiki name to sync all installed demo wikis at once.
    Use this after upgrading Synthadoc to pick up new features without reinstalling.
    """
    registry = _read_registry()

    # Determine which wikis to sync
    if name is not None:
        if name not in registry:
            typer.echo(
                f"Wiki '{name}' not found in registry. Run: synthadoc install {name} --demo"
            )
            raise typer.Exit(1)
        if name not in _DEMOS:
            typer.echo(f"No bundled demo template found for '{name}'")
            raise typer.Exit(1)
        targets = [name]
    else:
        targets = [n for n in registry if n in _DEMOS]
        if not targets:
            typer.echo("No installed demo wikis found.")
            raise typer.Exit(0)

    any_output = False
    for target in targets:
        entry = registry[target]
        demo_template = _DEMOS[target]
        installed_root = Path(entry["path"])
        updated: list[str] = []

        # ── 1. raw_sources: additive copy ─────────────────────────────────────
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

        # ── 2. wiki/dashboard.md: replace body, preserve installed frontmatter
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

        # ── 3. wiki/: copy new template pages that don't exist yet ────────────
        demo_wiki = demo_template / "wiki"
        installed_wiki = installed_root / "wiki"
        _SKIP_WIKI = {"index.md", "dashboard.md", "purpose.md"}
        for src in demo_wiki.glob("*.md"):
            if src.name in _SKIP_WIKI:
                continue
            dest = installed_wiki / src.name
            if not dest.exists():
                shutil.copy2(src, dest)
                updated.append(f"  + wiki/{src.name}")
            elif force:
                shutil.copy2(src, dest)
                updated.append(f"  ~ wiki/{src.name}  (updated from template)")

        # ── 4. wiki/: backfill missing metadata fields (e.g. type:) ──────────
        for src in demo_wiki.glob("*.md"):
            if src.name in _SKIP_WIKI:
                continue
            dest = installed_wiki / src.name
            if dest.exists() and _inject_type_if_missing(dest, src):
                updated.append(f"  ~ wiki/{src.name}  (type: backfilled)")

        if updated:
            typer.echo(f"{target}:")
            for line in sorted(updated):
                typer.echo(line)
            any_output = True
        else:
            typer.echo(f"{target}: already up to date")
            any_output = True

    if not any_output:
        typer.echo("Already up to date — nothing to sync.")


def _strip_bom(text: str) -> str:
    """Remove UTF-8 BOM (U+FEFF) if present at the start of text."""
    return text.lstrip("﻿")


def _extract_body(text: str) -> str:
    """Return everything after the closing '---' of a YAML frontmatter block."""
    text = _strip_bom(text)
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2]
    return "\n" + text


def _extract_frontmatter_block(text: str) -> str:
    """Return the YAML between '---' markers, normalized to exactly one leading/trailing newline."""
    text = _strip_bom(text)
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return "\n" + parts[1].strip() + "\n"
    return ""


def _inject_type_if_missing(installed_path: Path, template_path: Path) -> bool:
    """Add type: field to an installed page if the template has one and the page lacks it.

    Returns True if the file was modified.
    """
    tmpl_raw = template_path.read_text(encoding="utf-8")
    tmpl_fm = _extract_frontmatter_block(tmpl_raw)
    type_line = next(
        (line.strip() for line in tmpl_fm.splitlines() if line.strip().startswith("type:")),
        None,
    )
    if not type_line:
        return False

    inst_raw = installed_path.read_text(encoding="utf-8")
    inst_fm = _extract_frontmatter_block(inst_raw)
    if any(line.strip().startswith("type:") for line in inst_fm.splitlines()):
        return False

    inst_body = _extract_body(inst_raw)
    new_fm = inst_fm.rstrip("\n") + f"\n{type_line}\n"
    installed_path.write_text(f"---{new_fm}---{inst_body}", encoding="utf-8", newline="\n")
    return True
