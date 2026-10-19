# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

import typer

from synthadoc.cli.main import app
from synthadoc.cli._wiki import _fallback_wiki_root
from synthadoc.cli._utils import (
    _extract_body,
    _extract_frontmatter_block,
    _inject_type_if_missing,
    _is_stub,
    _strip_bom,
)

template_app = typer.Typer(help="Browse and manage domain templates.")
app.add_typer(template_app, name="templates")


# ── Origin helpers ────────────────────────────────────────────────────────────

def _read_origin(wiki_root: Path) -> dict:
    """Read .synthadoc/origin.json; return {} if absent or unreadable."""
    origin_file = wiki_root / ".synthadoc" / "origin.json"
    if origin_file.exists():
        try:
            return json.loads(origin_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _print_sync_result(name: str, updated: list[str]) -> None:
    """Print the standard sync result block for one wiki."""
    if updated:
        typer.echo(f"{name}:")
        for line in updated:
            typer.echo(line)
    else:
        typer.echo(f"{name}: already up to date")


@template_app.command("list")
def list_templates_cmd() -> None:
    """List available demo wikis and domain templates."""
    from synthadoc.cli.install import _DEMOS, _read_registry
    from synthadoc.core.template_engine import list_templates, get_template_description

    registry = _read_registry()

    # ── Demos section ─────────────────────────────────────────────────────────
    typer.echo("Demos  " + "-" * 52)
    for demo_name in _DEMOS:
        status = ""
        if demo_name in registry:
            status = f"  (installed at {registry[demo_name]['path']})"
        typer.echo(f"  {demo_name:<30}{status}")
    typer.echo()
    typer.echo("  Install:  synthadoc install <name> --target <dir> --demo")
    typer.echo("  Example:  synthadoc install history-of-computing --target ~/wikis --demo")
    typer.echo()

    # ── Templates section ──────────────────────────────────────────────────────
    typer.echo("Templates  " + "-" * 50)
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


@template_app.command("sync")
def sync_cmd(
    name: Optional[str] = typer.Argument(
        None,
        help=(
            "Wiki name to sync. Omit to sync all wikis installed from a template or demo."
        ),
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help=(
            "Also update wiki stub pages that have never been ingested "
            "(status: draft, confidence: low, sources: [])."
        ),
    ),
) -> None:
    """Sync installed wiki(s) with the latest bundled template or demo.

    For domain-template wikis, updates:

    \b
      ~ seeds.md          — getting-started guide (always refreshed)
      ~ ROUTING.md        — routing config (always refreshed)
      ~ AGENTS/CLAUDE/GEMINI.md — regenerated from updated guidelines
      ~ raw_sources/template-*.md — intake form originals (user copies untouched)
      ~ wiki/purpose.md   — section markers merged; user prose preserved
      + wiki/<stub>.md    — new stubs added; existing pages never removed
      ~ wiki/<stub>.md    — updated only when --force AND sources: [] (never ingested)

    For demo wikis, syncs raw_sources (removes superseded binary files replaced
    by plain-text equivalents in the current package, copies in new files) and
    updates wiki pages and dashboard.

    Use this after upgrading synthadoc to pick up updated guidelines, seeds,
    and new stub pages without reinstalling.
    """
    _do_sync(name=name, force=force)


# ── Orchestrator ──────────────────────────────────────────────────────────────

def _do_sync(name: Optional[str], force: bool) -> None:
    """Route each wiki to the appropriate sync handler."""
    from synthadoc.cli.install import _DEMOS, _read_registry

    registry = _read_registry()

    if name is not None:
        if name not in registry:
            typer.echo(
                f"Wiki '{name}' is not registered. "
                "Run 'synthadoc install' first.",
                err=True,
            )
            raise typer.Exit(1)
        targets = [name]
    else:
        # All wikis that came from a template or demo
        targets = [
            n for n, e in registry.items()
            if (e.get("category") and e.get("template")) or n in _DEMOS
        ]
        if not targets:
            # Docker fallback: no registry — use SYNTHADOC_WIKI or CWD
            wiki_root = _fallback_wiki_root()
            if wiki_root is None:
                typer.echo("No template or demo wikis found. Nothing to sync.")
                raise typer.Exit(0)
            _do_sync_from_origin(wiki_root, force)
            return

    any_changes = False
    for target in targets:
        entry = registry[target]
        wiki_root = Path(entry["path"])

        if not wiki_root.is_dir():
            typer.echo(f"{target}: directory not found at {wiki_root} - skipping", err=True)
            continue

        cat = entry.get("category")
        tmpl = entry.get("template")

        if cat and tmpl:
            updated = _sync_template_wiki(
                wiki_root=wiki_root,
                template_ref=f"{cat}/{tmpl}",
                wiki_name=target,
                force=force,
            )
        elif target in _DEMOS:
            updated = _sync_demo_wiki(
                wiki_root=wiki_root,
                demo_template=_DEMOS[target],
                force=force,
            )
        else:
            msg = (
                f"Wiki '{target}' was not installed from a template or demo and cannot be synced.\n"
                "Only wikis installed with --template or --demo support sync."
            )
            if name is not None:
                # Explicit name — treat as an error
                typer.echo(msg, err=True)
                raise typer.Exit(1)
            else:
                # Scanning all wikis — skip silently
                continue

        _print_sync_result(target, updated)
        any_changes = True

    if not any_changes:
        typer.echo("Already up to date - nothing to sync.")


def _do_sync_from_origin(wiki_root: Path, force: bool) -> None:
    """Sync a single wiki using its .synthadoc/origin.json — Docker path."""
    from synthadoc.cli.install import _DEMOS
    from synthadoc.core.template_engine import get_template_path

    origin = _read_origin(wiki_root)
    origin_type = origin.get("type")

    if origin_type == "template":
        ref = origin.get("ref", "")
        # Validate the ref still exists in this version of Synthadoc
        try:
            get_template_path(ref)
        except (ValueError, FileNotFoundError):
            typer.echo(
                f"Error: template '{ref}' not found in this version of Synthadoc.\n"
                f"  Recorded in .synthadoc/origin.json — check for a typo.\n"
                f"  Run 'synthadoc templates list' to see available templates.\n"
                f"  To fix: synthadoc templates set-origin <correct-ref>",
                err=True,
            )
            raise typer.Exit(1)
        wiki_name = wiki_root.name
        updated = _sync_template_wiki(
            wiki_root=wiki_root,
            template_ref=ref,
            wiki_name=wiki_name,
            force=force,
        )
        _print_sync_result(wiki_name, updated)

    elif origin_type == "demo":
        demo_name = origin.get("name", "")
        if demo_name not in _DEMOS:
            typer.echo(
                f"Error: demo '{demo_name}' not found in this version of Synthadoc.\n"
                f"  Recorded in .synthadoc/origin.json — check for a typo.\n"
                f"  To fix: synthadoc templates set-origin <correct-demo-name>",
                err=True,
            )
            raise typer.Exit(1)
        wiki_name = wiki_root.name
        updated = _sync_demo_wiki(
            wiki_root=wiki_root,
            demo_template=_DEMOS[demo_name],
            force=force,
        )
        _print_sync_result(wiki_name, updated)

    else:
        typer.echo(
            "No template or demo origin found for this wiki. Nothing to sync.\n"
            "  (Custom wikis are not installed from a template and have nothing to sync.)"
        )
        raise typer.Exit(0)


# ── Template-wiki sync ────────────────────────────────────────────────────────

def _sync_template_wiki(
    wiki_root: Path,
    template_ref: str,
    wiki_name: str,
    force: bool,
) -> list[str]:
    """Sync a domain-template wiki against its bundled template. Returns a change log."""
    from synthadoc.core.template_engine import get_template_path, get_template_guidelines

    template_path = get_template_path(template_ref)
    updated: list[str] = []

    def _sub(text: str) -> str:
        return text.replace("<wiki>", wiki_name) if wiki_name else text

    def _write(src: Path, dest: Path) -> bool:
        """Write src → dest with <wiki> substitution. Returns True if content changed."""
        new_text = _sub(src.read_text(encoding="utf-8"))
        if dest.exists() and dest.read_text(encoding="utf-8").rstrip() == new_text.rstrip():
            return False
        dest.write_text(new_text, encoding="utf-8", newline="\n")
        return True

    # 1. seeds.md — human reference doc; always refresh
    seeds_src = template_path / "seeds.md"
    if seeds_src.exists():
        if _write(seeds_src, wiki_root / "seeds.md"):
            updated.append("  ~ seeds.md  (updated from template)")

    # 2. ROUTING.md — pure system config; always refresh
    routing_src = template_path / "routing.md"
    if routing_src.exists():
        if _write(routing_src, wiki_root / "ROUTING.md"):
            updated.append("  ~ ROUTING.md  (updated from template)")

    # 3. AGENTS/CLAUDE/GEMINI.md — regenerate body from updated guidelines;
    #    preserve the first header line which carries the wiki's domain name.
    guidelines = get_template_guidelines(template_ref)
    for fname in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
        dest = wiki_root / fname
        if not dest.exists():
            continue
        existing = dest.read_text(encoding="utf-8")
        header_line = existing.split("\n", 1)[0]  # e.g. "# AGENTS.md — My Wiki"
        new_content = header_line + "\n\n" + guidelines.rstrip() + "\n"
        if new_content.rstrip() != existing.rstrip():
            dest.write_text(new_content, encoding="utf-8", newline="\n")
            updated.append(f"  ~ {fname}  (guidelines updated)")

    # 4. raw_sources/template-*.md — update intake form originals;
    #    user copies never have the "template-" prefix so they are always safe.
    raw_src_root = template_path / "raw_sources"
    raw_dest_root = wiki_root / "raw_sources"
    if raw_src_root.is_dir():
        for src in sorted(raw_src_root.rglob("template-*.md")):
            rel = src.relative_to(raw_src_root)
            dest = raw_dest_root / rel
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(_sub(src.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
                updated.append(f"  + raw_sources/{rel}")
            elif _write(src, dest):
                updated.append(f"  ~ raw_sources/{rel}  (intake form updated)")

    # 5. wiki/purpose.md — merge template scaffolding, preserve user prose
    template_purpose = template_path / "wiki" / "purpose.md"
    installed_purpose = wiki_root / "wiki" / "purpose.md"
    if template_purpose.exists():
        from synthadoc.agents.scaffold_agent import preserve_user_zone
        tmpl_raw = template_purpose.read_text(encoding="utf-8")
        inst_raw = installed_purpose.read_text(encoding="utf-8") if installed_purpose.exists() else ""
        merged = preserve_user_zone(inst_raw, tmpl_raw)
        if merged.rstrip() != inst_raw.rstrip():
            installed_purpose.write_text(merged, encoding="utf-8", newline="\n")
            updated.append("  ~ wiki/purpose.md  (section markers updated, user edits preserved)")

    # 6. Other wiki stubs
    #    - additive: copy new stubs that don't exist yet
    #    - --force: overwrite stubs that are still in template-stub state (sources: [])
    wiki_src = template_path / "wiki"
    wiki_dest = wiki_root / "wiki"
    _SKIP = {"purpose.md", "index.md"}
    for src in sorted(wiki_src.glob("*.md")):
        if src.name in _SKIP:
            continue
        dest = wiki_dest / src.name
        if not dest.exists():
            shutil.copy2(src, dest)
            updated.append(f"  + wiki/{src.name}")
        elif force and _is_stub(dest):
            shutil.copy2(src, dest)
            updated.append(f"  ~ wiki/{src.name}  (stub refreshed from template)")

    return updated


# ── Demo-wiki sync ────────────────────────────────────────────────────────────

def _sync_demo_wiki(
    wiki_root: Path,
    demo_template: Path,
    force: bool,
) -> list[str]:
    """Sync a demo wiki against its bundled template. Mirrors the legacy demo sync logic."""
    updated: list[str] = []

    # 1. raw_sources: sync template files and remove superseded ones.
    #
    #    "Superseded" means the installed wiki has a file whose stem matches a
    #    template file but with a different extension — e.g. report.pdf when the
    #    template now ships report.md.  These were bundled with the demo (not
    #    user-created), so removing them is always safe.  User-added files (stems
    #    with no matching template entry) are never touched.
    demo_sources = demo_template / "raw_sources"
    installed_sources = wiki_root / "raw_sources"
    installed_sources.mkdir(exist_ok=True)

    tmpl_by_stem: dict[str, Path] = {
        f.stem: f for f in demo_sources.rglob("*") if f.is_file()
    }
    tmpl_names = {f.name for f in tmpl_by_stem.values()}

    for existing in list(installed_sources.rglob("*")):
        if existing.is_file() and existing.stem in tmpl_by_stem and existing.name not in tmpl_names:
            existing.unlink()
            updated.append(f"  - raw_sources/{existing.relative_to(installed_sources)}  (superseded)")

    for src in demo_sources.rglob("*"):
        if not src.is_file():
            continue
        relative = src.relative_to(demo_sources)
        dest = installed_sources / relative
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            updated.append(f"  + raw_sources/{relative}")

    # 2. wiki/dashboard.md: replace body, preserve installed frontmatter
    template_dash = demo_template / "wiki" / "dashboard.md"
    installed_dash = wiki_root / "wiki" / "dashboard.md"
    if template_dash.exists() and installed_dash.exists():
        tmpl_raw = template_dash.read_text(encoding="utf-8")
        inst_raw = installed_dash.read_text(encoding="utf-8")
        tmpl_body = _extract_body(tmpl_raw)
        inst_fm = _extract_frontmatter_block(inst_raw)
        new_content = f"---{inst_fm}---\n{tmpl_body}"
        if new_content.rstrip() != inst_raw.rstrip():
            installed_dash.write_text(new_content, encoding="utf-8", newline="\n")
            updated.append("  ~ wiki/dashboard.md  (Dataview sections updated)")

    # 3. wiki/purpose.md: update section markers via preserve_user_zone
    template_purpose = demo_template / "wiki" / "purpose.md"
    installed_purpose = wiki_root / "wiki" / "purpose.md"
    if template_purpose.exists():
        from synthadoc.agents.scaffold_agent import preserve_user_zone
        tmpl_raw = template_purpose.read_text(encoding="utf-8")
        inst_raw = installed_purpose.read_text(encoding="utf-8") if installed_purpose.exists() else ""
        merged = preserve_user_zone(inst_raw, tmpl_raw)
        if merged.rstrip() != inst_raw.rstrip():
            installed_purpose.write_text(merged, encoding="utf-8", newline="\n")
            updated.append("  ~ wiki/purpose.md  (section markers updated, user edits preserved)")

    # 4. wiki/: copy new template pages that don't exist yet; --force updates all
    demo_wiki = demo_template / "wiki"
    installed_wiki = wiki_root / "wiki"
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

    # 5. wiki/: backfill missing metadata fields (e.g. type:)
    for src in demo_wiki.glob("*.md"):
        if src.name in _SKIP_WIKI:
            continue
        dest = installed_wiki / src.name
        if dest.exists() and _inject_type_if_missing(dest, src):
            updated.append(f"  ~ wiki/{src.name}  (type: backfilled)")

    return updated


# ── set-origin ────────────────────────────────────────────────────────────────

@template_app.command("set-origin")
def set_origin_cmd(
    ref: str = typer.Argument(
        help=(
            "Template ref (e.g. finance/investment) or demo name "
            "(e.g. history-of-computing)."
        )
    ),
) -> None:
    """Record which template or demo this wiki was installed from.

    Use this if .synthadoc/origin.json is missing or contains the wrong ref —
    for example, after manually creating a wiki or after a registry corruption.

    \b
    Examples:
      synthadoc templates set-origin finance/investment
      synthadoc templates set-origin history-of-computing
    """
    from synthadoc.cli.install import _DEMOS, _write_origin
    from synthadoc.core.template_engine import get_template_path

    wiki_root = _fallback_wiki_root()
    if wiki_root is None:
        typer.echo(
            "Error: could not determine the wiki directory.\n"
            "  Set SYNTHADOC_WIKI or run from inside a wiki directory.",
            err=True,
        )
        raise typer.Exit(1)

    if "/" in ref:
        # Template ref
        try:
            get_template_path(ref)
        except (ValueError, FileNotFoundError):
            typer.echo(
                f"Error: template '{ref}' not found in this version of Synthadoc.\n"
                f"  Run 'synthadoc templates list' to see available templates.",
                err=True,
            )
            raise typer.Exit(1)
        label = f"template '{ref}'"
        _write_origin(wiki_root, demo=None, template=ref)
    else:
        # Demo name
        if ref not in _DEMOS:
            typer.echo(
                f"Error: demo '{ref}' not found in this version of Synthadoc.\n"
                f"  Available demos: {', '.join(_DEMOS) or '(none)'}",
                err=True,
            )
            raise typer.Exit(1)
        label = f"demo '{ref}'"
        _write_origin(wiki_root, demo=ref, template=None)

    origin_file = wiki_root / ".synthadoc" / "origin.json"
    typer.echo(f"Origin set to {label} in {origin_file}")
