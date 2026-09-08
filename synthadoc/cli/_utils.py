# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from synthadoc.utils import atomic_write_text


def _resolve_root(wiki_root: Optional[str]) -> Path:
    """Return the wiki root Path; defaults to CWD when wiki_root is None."""
    return Path(wiki_root) if wiki_root else Path(".")


def _toml_value(v: object) -> str:
    """Serialise a Python value as a TOML literal (not JSON)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, dict):
        pairs = ", ".join(f"{k} = {_toml_value(val)}" for k, val in v.items())
        return "{" + pairs + "}"
    if isinstance(v, list):
        items = ", ".join(_toml_value(i) for i in v)
        return "[" + items + "]"
    return json.dumps(v)


def _patch_toml(path: Path, section: str, pairs: dict) -> None:
    """Patch specific keys in a TOML section without touching other lines or comments."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = text.splitlines()

    section_header = f"[{section}]"
    in_target = False
    patched_keys: set[str] = set()
    result: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_target:
                for k, v in pairs.items():
                    if k not in patched_keys:
                        result.append(f"{k} = {_toml_value(v)}")
                        patched_keys.add(k)
            in_target = stripped == section_header
            result.append(line)
            continue

        if in_target and "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            if key in pairs:
                result.append(f"{key} = {_toml_value(pairs[key])}")
                patched_keys.add(key)
                continue

        result.append(line)

    if in_target:
        for k, v in pairs.items():
            if k not in patched_keys:
                result.append(f"{k} = {_toml_value(v)}")
                patched_keys.add(k)

    if not patched_keys:
        if result and result[-1].strip():
            result.append("")
        result.append(f"[{section}]")
        for k, v in pairs.items():
            result.append(f"{k} = {_toml_value(v)}")

    atomic_write_text(path, "\n".join(result) + "\n")


# ── Sync helpers (shared between templates sync and demo sync) ─────────────────

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
    """Return the YAML between '---' markers, normalised to exactly one leading/trailing newline."""
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


def _is_stub(path: Path) -> bool:
    """Return True if a wiki page is still in its original template-stub state.

    A page is a stub when it has never been ingested: both ``sources: []``
    and ``confidence: low`` must be present in its frontmatter.  Either
    condition alone is insufficient — an actively maintained low-confidence
    page may still have real sources.
    """
    text = path.read_text(encoding="utf-8")
    return "sources: []" in text and "confidence: low" in text
