# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import hashlib
import json
import platform
import re
import socket
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _iter_wiki_files(
    wiki_root: Path,
    include_sources: bool,
    include_exports: bool,
    include_cache: bool,
):
    """Yield (abs_path, archive_name) for each file to include in the backup."""
    wiki_dir = wiki_root / "wiki"
    if wiki_dir.is_dir():
        for f in sorted(wiki_dir.rglob("*.md")):
            yield f, str(f.relative_to(wiki_root)).replace("\\", "/")

    for name in ("AGENTS.md", "ROUTING.md", "log.md"):
        p = wiki_root / name
        if p.exists():
            yield p, name
    for p in sorted(wiki_root.glob("*.txt")):
        yield p, p.name

    # hooks/ — user-customisable scripts; lost silently if not backed up
    hooks_dir = wiki_root / "hooks"
    if hooks_dir.is_dir():
        for f in sorted(hooks_dir.rglob("*")):
            if f.is_file():
                yield f, str(f.relative_to(wiki_root)).replace("\\", "/")

    sd = wiki_root / ".synthadoc"
    for name in ("config.toml", "audit.db"):
        p = sd / name
        if p.exists():
            yield p, f".synthadoc/{name}"

    # extracted/ — text sidecars + PDF pagemaps written by ingest agent.
    # Required by the Source Viewer and Provenance citation modal — without
    # these files the plugin shows "Could not read source file for <name>".
    extracted_dir = sd / "extracted"
    if extracted_dir.is_dir():
        for f in sorted(extracted_dir.rglob("*")):
            if f.is_file():
                yield f, str(f.relative_to(wiki_root)).replace("\\", "/")

    if include_cache:
        p = sd / "cache.db"
        if p.exists():
            yield p, ".synthadoc/cache.db"

    if include_exports:
        exports_dir = wiki_root / "exports"
        if exports_dir.is_dir():
            for f in sorted(exports_dir.rglob("*")):
                if f.is_file():
                    yield f, str(f.relative_to(wiki_root)).replace("\\", "/")

    if include_sources:
        sources_dir = wiki_root / "raw_sources"
        if sources_dir.is_dir():
            for f in sorted(sources_dir.rglob("*")):
                if f.is_file():
                    yield f, str(f.relative_to(wiki_root)).replace("\\", "/")


def _count_pages(wiki_root: Path) -> int:
    from synthadoc.agents.lint_agent import LINT_SKIP_SLUGS
    wiki_dir = wiki_root / "wiki"
    if not wiki_dir.is_dir():
        return 0
    return sum(1 for p in wiki_dir.glob("*.md") if p.stem not in LINT_SKIP_SLUGS)


def _compute_content_checksum(zip_path: Path) -> str:
    """SHA-256 of all non-manifest members in sorted name order."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        h = hashlib.sha256()
        for name in sorted(zf.namelist()):
            if name == "manifest.json":
                continue
            h.update(zf.read(name))
    return h.hexdigest()


def create_backup(
    wiki_root: Path,
    output_dir: Path,
    wiki_name: str,
    synthadoc_version: str,
    db_schema_version: int,
    cache_version: str,
    include_sources: bool = False,
    include_exports: bool = True,
    include_cache: bool = True,
) -> Path:
    """Create a ZIP_DEFLATED backup archive and return its path."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    zip_name = f"synthadoc-backup-{wiki_name}-{ts}.zip"
    zip_path = Path(output_dir) / zip_name
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    manifest: dict = {
        "synthadoc_version": synthadoc_version,
        "db_schema_version": db_schema_version,
        "cache_version": cache_version,
        "wiki_name": wiki_name,
        "backed_up_at": datetime.now(timezone.utc).isoformat(),
        "source_os": platform.system().lower(),
        "source_hostname": socket.gethostname(),
        "page_count": _count_pages(wiki_root),
        "includes_sources": include_sources,
        "includes_exports": include_exports,
        "includes_cache": include_cache,
        "obsidian_plugin": (wiki_root / ".obsidian" / "plugins" / "synthadoc" / "main.js").exists(),
        "checksum_sha256": "",
    }

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for abs_path, arc_name in _iter_wiki_files(
            wiki_root, include_sources, include_exports, include_cache
        ):
            zf.write(abs_path, arc_name)

    manifest["checksum_sha256"] = _compute_content_checksum(zip_path)
    with zipfile.ZipFile(zip_path, "a", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    return zip_path


def read_manifest(zip_path: Path) -> dict:
    """Read manifest.json from a backup zip (last entry wins on duplicate names)."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        if "manifest.json" not in zf.namelist():
            raise ValueError("No manifest.json found in archive.")
        with zf.open("manifest.json") as f:
            return json.loads(f.read().decode("utf-8"))


def validate_manifest(manifest: dict, current_db_schema_version: int) -> None:
    """Raise ValueError if the backup requires a newer Synthadoc installation."""
    backup_ver = manifest.get("db_schema_version", 0)
    if backup_ver > current_db_schema_version:
        raise ValueError(
            f"This backup requires db_schema_version={backup_ver}, "
            f"but this installation has {current_db_schema_version}. "
            f"Upgrade Synthadoc first, then retry the restore."
        )


def verify_checksum(zip_path: Path, expected: str) -> bool:
    """Return True if content checksum matches, or if expected is empty."""
    if not expected:
        return True
    return _compute_content_checksum(zip_path) == expected


def extract_backup(zip_path: Path, target_dir: Path, wiki_name: str) -> Path:
    """Extract backup to target_dir/<wiki_name>/ and return the wiki root path."""
    wiki_root = Path(target_dir) / wiki_name
    wiki_root.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            if member == "manifest.json":
                continue
            dest = wiki_root / member
            dest = dest.resolve()
            if not dest.is_relative_to(wiki_root.resolve()):
                continue  # skip any member that would escape the target directory
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(member))

    return wiki_root


def rewrite_config(config_path: Path, new_port: int, new_domain: Optional[str] = None) -> None:
    """Update port (and optionally domain name) in config.toml using regex replacement.

    Uses targeted line-level regex so complex structures like [[schedule.jobs]] are
    preserved exactly — no full TOML re-serialization.
    """
    text = config_path.read_text(encoding="utf-8")
    text = re.sub(r"^(port\s*=\s*)\d+", rf"\g<1>{new_port}", text, flags=re.MULTILINE)
    if new_domain is not None:
        text = re.sub(
            r'^(domain\s*=\s*)"[^"]*"',
            lambda m: f'{m.group(1)}"{new_domain}"',
            text,
            flags=re.MULTILINE,
        )
    config_path.write_text(text, encoding="utf-8", newline="\n")
