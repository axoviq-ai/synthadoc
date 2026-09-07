# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import re
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


def apply_template(wiki_root: Path, template_ref: str, wiki_name: str = "") -> None:
    """Apply a domain template delta onto a freshly init_wiki()'d directory.

    Steps (in order):
    1. Validate and resolve template_ref → template_path
    2. Copy routing.md  → wiki_root/ROUTING.md
    3. Copy seeds.md    → wiki_root/seeds.md   (getting-started guide; NOT a wiki page)
    4. Copy wiki/purpose.md → wiki_root/wiki/purpose.md  (overwrites init_wiki version)
    5. Copy wiki/index.md  → wiki_root/wiki/index.md    (overwrites init_wiki version)
    6. Copy remaining wiki/*.md stubs → wiki_root/wiki/ (additive; never overwrites existing)
    7. Copy raw_sources/ tree → wiki_root/raw_sources/  (additive; never overwrites existing)

    ``seeds.md`` lives at the template root (not inside ``wiki/``) so it is
    installed as a human reference file at ``wiki_root/seeds.md`` and is never
    indexed or queried by the engine.

    ``raw_sources/`` is an optional directory in each template that holds blank
    intake forms for the domain (e.g. ``raw_sources/properties/blank-property-intake.md``
    for real-estate templates).  The subfolder name is domain-specific; the copy
    preserves the full directory structure.  Users copy a blank form, fill in their
    data, and run ``synthadoc ingest raw_sources/<folder>/<filename>.md -w <wiki>``.

    When ``wiki_name`` is provided every occurrence of the literal token ``<wiki>``
    in copied files is replaced with the actual wiki name so ingest commands are
    ready to run immediately without manual find-and-replace.

    Does NOT write AGENTS/CLAUDE/GEMINI.md — caller (install.py) handles those.
    Does NOT patch staging config — caller handles that too.
    """
    template_path = get_template_path(template_ref)
    wiki_dir = wiki_root / "wiki"

    def _write(src: Path, dest: Path) -> None:
        """Copy src → dest, substituting <wiki> when wiki_name is set."""
        text = src.read_text(encoding="utf-8")
        if wiki_name:
            text = text.replace("<wiki>", wiki_name)
        dest.write_text(text, encoding="utf-8", newline="\n")

    # 1. ROUTING.md
    _write(template_path / "routing.md", wiki_root / "ROUTING.md")

    # 2. seeds.md — human getting-started guide; installed at wiki root, NOT inside wiki/
    seeds_src = template_path / "seeds.md"
    if seeds_src.exists():
        _write(seeds_src, wiki_root / "seeds.md")

    # 3-4. purpose.md and index.md — always overwrite
    for name in ("purpose.md", "index.md"):
        src = template_path / "wiki" / name
        if src.exists():
            _write(src, wiki_dir / name)

    # 4. Remaining wiki stubs — additive, do not overwrite existing user pages
    for src in sorted((template_path / "wiki").glob("*.md")):
        if src.name in ("purpose.md", "index.md"):
            continue
        dest = wiki_dir / src.name
        if not dest.exists():
            _write(src, dest)

    # 5. raw_sources/ — copy entire tree additively (never overwrites existing files)
    raw_src_root = template_path / "raw_sources"
    if raw_src_root.is_dir():
        raw_dest_root = wiki_root / "raw_sources"
        for src in sorted(raw_src_root.rglob("*")):
            if not src.is_file():
                continue
            dest = raw_dest_root / src.relative_to(raw_src_root)
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                _write(src, dest)
