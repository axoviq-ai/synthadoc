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
