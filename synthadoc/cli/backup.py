# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path
from typing import Optional

import typer

from synthadoc import __version__
from synthadoc.cli.main import app
from synthadoc.cli.install import (
    _read_registry,
    _write_registry,
    _get_reserved_ports,
    resolve_wiki_path,
    _DEMOS,
)
from synthadoc.cli._port import assign_wiki_port, _DEFAULT_PORT
from synthadoc.cli._wiki import resolve_wiki
from synthadoc.core.backup_engine import (
    create_backup,
    read_manifest,
    validate_manifest,
    verify_checksum,
    extract_backup,
    rewrite_config,
)
from synthadoc.core.cache import CACHE_VERSION
from synthadoc.storage.log import DB_SCHEMA_VERSION
from synthadoc import errors as E


@app.command("backup")
def backup_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    output: str = typer.Option(".", "--output", "-o", help="Directory to write the backup zip"),
    include_sources: bool = typer.Option(False, "--include-sources", help="Include raw_sources/"),
    no_exports: bool = typer.Option(False, "--no-exports", help="Exclude exports/"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Exclude cache.db"),
) -> None:
    """Backup a wiki domain to a portable compressed zip file.

    \b
    Examples:
      synthadoc backup -w history-of-computing
      synthadoc backup -w history-of-computing --output ~/backups --include-sources
    """
    wiki_name = resolve_wiki(wiki)
    wiki_root = resolve_wiki_path(wiki_name)

    if not (wiki_root / ".synthadoc" / "config.toml").exists():
        E.cli_error(
            E.WIKI_NOT_REGISTERED,
            f"Wiki '{wiki_name}' is not installed at '{wiki_root}'.",
            "Run 'synthadoc list' to see registered wikis.",
        )

    output_dir = Path(output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    typer.echo(f"Backing up '{wiki_name}'...")

    zip_path = create_backup(
        wiki_root=wiki_root,
        output_dir=output_dir,
        wiki_name=wiki_name,
        synthadoc_version=__version__,
        db_schema_version=DB_SCHEMA_VERSION,
        cache_version=CACHE_VERSION,
        include_sources=include_sources,
        include_exports=not no_exports,
        include_cache=not no_cache,
    )

    size_mb = zip_path.stat().st_size / 1_048_576
    manifest = read_manifest(zip_path)
    typer.echo(f"\n✓ {zip_path.name}  ({size_mb:.1f} MB)")
    typer.echo(f"  Pages:    {manifest.get('page_count', '?')}")
    typer.echo(f"  Sources:  {'included' if include_sources else 'excluded  (use --include-sources to add)'}")
    typer.echo(f"  Exports:  {'excluded' if no_exports else 'included'}")
    typer.echo(f"  Cache:    {'excluded' if no_cache else 'included'}")
    typer.echo(f"  Path:     {zip_path}")
