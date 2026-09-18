# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Optional

import typer
import yaml

from synthadoc.cli._utils import _patch_toml, _toml_value  # noqa: F401  (re-exported for internal callers)
from synthadoc.cli._wiki import resolve_wiki
from synthadoc.cli._wiki import resolve_wiki_path
from synthadoc.cli.main import app
from synthadoc.config import STAGING_POLICIES, STAGING_CONFIDENCE_LEVELS
from synthadoc.utils import atomic_write_text

staging_app = typer.Typer(name="staging", help="Manage staging policy for new wiki pages.")
candidates_app = typer.Typer(name="candidates", help="Review, promote, or discard candidate pages.")
app.add_typer(staging_app)
app.add_typer(candidates_app)


def _cfg_path(root: Path) -> Path:
    return root / ".synthadoc" / "config.toml"


def _paths(wiki: Optional[str]) -> tuple[Path, Path, Path]:
    """Return (root, cfg_file, cand_dir) from the --wiki option."""
    root = resolve_wiki_path(resolve_wiki(wiki))
    return root, _cfg_path(root), root / "wiki" / "candidates"


@staging_app.command("policy")
def staging_policy_cmd(
    policy: Optional[str] = typer.Argument(None, help="off | all | threshold"),
    min_confidence: Optional[str] = typer.Option(None, "--min-confidence"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w", help="Wiki name or path"),
) -> None:
    """Show or set the staging policy."""
    root, cfg_file, _ = _paths(wiki)
    raw = tomllib.loads(cfg_file.read_text()) if cfg_file.exists() else {}

    if policy is None:
        current = raw.get("ingest", {}).get("staging_policy", "off")
        min_c = raw.get("ingest", {}).get("staging_confidence_min", "high")
        typer.echo(f"Staging policy: {current}")
        if current == "threshold":
            typer.echo(f"Minimum confidence for auto-promote: {min_c}")
        return

    if policy not in STAGING_POLICIES:
        typer.echo(f"Policy must be one of: {', '.join(sorted(STAGING_POLICIES))}")
        raise typer.Exit(1)
    if min_confidence and min_confidence not in STAGING_CONFIDENCE_LEVELS:
        typer.echo(f"min-confidence must be one of: {', '.join(sorted(STAGING_CONFIDENCE_LEVELS))}")
        raise typer.Exit(1)

    updates = {"staging_policy": policy}
    if min_confidence:
        updates["staging_confidence_min"] = min_confidence

    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    _patch_toml(cfg_file, "ingest", updates)
    msg = f"Staging policy updated: {policy}"
    if policy == "threshold" and min_confidence:
        msg += f" (min-confidence: {min_confidence})"
    typer.echo(msg)
    typer.echo("Takes effect on next ingest job - no restart needed.")


@candidates_app.command("list")
def candidates_list(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w", help="Wiki name or path"),
) -> None:
    """List all candidate pages awaiting review."""
    _, _, cand_dir = _paths(wiki)
    pages = sorted(cand_dir.glob("*.md")) if cand_dir.exists() else []
    if not pages:
        typer.echo("No candidates.")
        return
    typer.echo(f"Candidates ({len(pages)}):")
    for p in pages:
        fm = _read_frontmatter(p)
        conf = fm.get("confidence", "?")
        created = fm.get("created", "?")
        typer.echo(f"  {p.stem:<30} confidence: {conf:<8} ingested: {created}")


def _page_title(path: Path) -> str:
    """Extract the title field from a page's YAML frontmatter, or derive it from the slug."""
    fm = _read_frontmatter(path)
    if fm.get("title"):
        return str(fm["title"])
    return path.stem.replace("-", " ").title()


def _add_to_index(wiki_dir: Path, entries: list[tuple[str, str]]) -> None:
    """Append [[slug]] - Title entries to index.md under ## Recently Added."""
    index_path = wiki_dir / "index.md"
    if not index_path.exists() or not entries:
        return
    text = index_path.read_text(encoding="utf-8")
    new_lines = [f"- [[{slug}]] - {title}" for slug, title in entries]
    if "## Recently Added" in text:
        lines = text.splitlines()
        insert_at = len(lines)
        in_section = False
        for i, line in enumerate(lines):
            if line.strip() == "## Recently Added":
                in_section = True
                insert_at = i + 1
            elif in_section:
                if line.startswith("## "):
                    insert_at = i
                    break
                insert_at = i + 1
        for j, entry in enumerate(new_lines):
            lines.insert(insert_at + j, entry)
        atomic_write_text(index_path, "\n".join(lines) + "\n")
    else:
        section = "\n\n## Recently Added\n" + "\n".join(new_lines) + "\n"
        atomic_write_text(index_path, text.rstrip() + section)


@candidates_app.command("promote")
def candidates_promote(
    slug: Optional[str] = typer.Argument(None),
    all_: bool = typer.Option(False, "--all"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w", help="Wiki name or path"),
) -> None:
    """Promote candidate(s) to the main wiki."""
    from synthadoc.cli._http import post as http_post
    wiki_name = resolve_wiki(wiki)

    if all_:
        result = http_post(wiki_name, "/candidates/promote-all", {})
        count = result.get("count", 0)
        for s in result.get("promoted", []):
            typer.echo(f"  Promoted {s} -> wiki/{s}.md")
        if count:
            typer.echo(f"  Overview refresh queued ({count} page(s) promoted)")
        else:
            typer.echo("  No candidates to promote.")
    elif slug:
        result = http_post(wiki_name, f"/candidates/{slug}/promote", {})
        action = "Updated" if result.get("updated") else "Promoted"
        typer.echo(f"  {action} {slug} -> wiki/{slug}.md")
        typer.echo("  Overview refresh queued")
    else:
        typer.echo("Specify a slug or use --all.")


@candidates_app.command("discard")
def candidates_discard(
    slug: Optional[str] = typer.Argument(None),
    all_: bool = typer.Option(False, "--all"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w", help="Wiki name or path"),
) -> None:
    """Discard candidate page(s)."""
    _, _, cand_dir = _paths(wiki)

    targets = list(cand_dir.glob("*.md")) if all_ else []
    if not all_ and slug:
        targets = [cand_dir / f"{slug}.md"]

    for src in targets:
        src.unlink(missing_ok=True)
        typer.echo(f"  Discarded {src.stem}")


def _read_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except Exception:
        return {}
