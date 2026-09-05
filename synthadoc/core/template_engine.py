# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import re
import shutil
from pathlib import Path

_TEMPLATES_ROOT = Path(__file__).parent.parent / "templates"

# Reject anything that is not exactly two lowercase-alphanumeric-hyphen segments
_TEMPLATE_REF_RE = re.compile(r"^[a-z][a-z0-9-]*/[a-z][a-z0-9-]*$")


def list_templates() -> dict[str, list[str]]:
    """Return {category: [domain, ...]} from filesystem, sorted.

    New template folders appear automatically — no hardcoded registry.
    """
    result: dict[str, list[str]] = {}
    if not _TEMPLATES_ROOT.is_dir():
        return result
    for cat_dir in sorted(_TEMPLATES_ROOT.iterdir()):
        if not cat_dir.is_dir() or cat_dir.name.startswith("_"):
            continue
        domains = sorted(
            d.name for d in cat_dir.iterdir()
            if d.is_dir() and not d.name.startswith("_")
        )
        if domains:
            result[cat_dir.name] = domains
    return result


def get_template_path(template_ref: str) -> Path:
    """Resolve 'finance/investment' → absolute Path.

    Raises ValueError with an available-templates hint if not found.
    Validates ref against regex before any filesystem access.
    """
    if not _TEMPLATE_REF_RE.match(template_ref):
        raise ValueError(
            f"Invalid template ref {template_ref!r}. "
            "Must match category/domain using lowercase letters, digits, and hyphens only."
        )
    path = _TEMPLATES_ROOT / template_ref
    if not path.is_dir():
        available = ", ".join(
            f"{cat}/{dom}"
            for cat, doms in list_templates().items()
            for dom in doms
        )
        raise ValueError(
            f"Unknown template {template_ref!r}. "
            f"Available: {available or '(none installed)'}"
        )
    return path


def get_template_description(template_ref: str) -> str:
    """Return one-line description from description.txt (stripped)."""
    p = get_template_path(template_ref) / "description.txt"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    return template_ref


def get_template_guidelines(template_ref: str) -> str:
    """Return full contents of guidelines.md."""
    p = get_template_path(template_ref) / "guidelines.md"
    return p.read_text(encoding="utf-8")


def apply_template(wiki_root: Path, template_ref: str) -> None:
    """Apply a domain template delta onto a freshly init_wiki()'d directory.

    Steps (in order):
    1. Validate and resolve template_ref → template_path
    2. Copy routing.md → wiki_root/ROUTING.md
    3. Copy wiki/purpose.md → wiki_root/wiki/purpose.md  (overwrites init_wiki version)
    4. Copy wiki/index.md  → wiki_root/wiki/index.md    (overwrites init_wiki version)
    5. Copy remaining wiki/*.md stubs → wiki_root/wiki/ (additive; never overwrites existing)

    Does NOT write AGENTS/CLAUDE/GEMINI.md — caller (install.py) handles those.
    Does NOT patch staging config — caller handles that too.
    """
    template_path = get_template_path(template_ref)
    wiki_dir = wiki_root / "wiki"

    # 1. ROUTING.md
    shutil.copy2(template_path / "routing.md", wiki_root / "ROUTING.md")

    # 2-3. purpose.md and index.md — always overwrite
    for name in ("purpose.md", "index.md"):
        src = template_path / "wiki" / name
        if src.exists():
            shutil.copy2(src, wiki_dir / name)

    # 4. Remaining stubs — additive, do not overwrite existing user pages
    for src in sorted((template_path / "wiki").glob("*.md")):
        if src.name in ("purpose.md", "index.md"):
            continue
        dest = wiki_dir / src.name
        if not dest.exists():
            shutil.copy2(src, dest)
