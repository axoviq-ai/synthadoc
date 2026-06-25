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
    resolve_wiki_path,
    _read_registry,
    _write_registry,
    _get_reserved_ports,
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
    no_sources: bool = typer.Option(False, "--no-sources", help="Exclude raw_sources/"),
    no_exports: bool = typer.Option(False, "--no-exports", help="Exclude exports/"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Exclude cache.db"),
) -> None:
    """Backup a wiki domain to a portable compressed zip file.

    \b
    Examples:
      synthadoc backup -w history-of-computing
      synthadoc backup -w history-of-computing --output ~/backups --no-sources
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
        include_sources=not no_sources,
        include_exports=not no_exports,
        include_cache=not no_cache,
    )

    size_mb = zip_path.stat().st_size / 1_048_576
    manifest = read_manifest(zip_path)
    typer.echo(f"\n✓ {zip_path.name}  ({size_mb:.1f} MB)")
    typer.echo(f"  Pages:    {manifest.get('page_count', '?')}")
    typer.echo(f"  Sources:  {'excluded  (use --no-sources to skip next time)' if no_sources else 'included'}")
    typer.echo(f"  Exports:  {'excluded' if no_exports else 'included'}")
    typer.echo(f"  Cache:    {'excluded' if no_cache else 'included'}")
    typer.echo(f"  Path:     {zip_path}")


@app.command("restore")
def restore_cmd(
    backup_file: str = typer.Argument(help="Path to the backup zip file"),
    name: Optional[str] = typer.Option(None, "--name", help="Override wiki name on restore"),
    target: Optional[str] = typer.Option(None, "--target", "-t", help="Parent directory for the restored wiki (default: same folder as the zip)"),
    port: Optional[int] = typer.Option(None, "--port", help="Override server port"),
) -> None:
    """Restore a wiki domain from a backup zip.

    \b
    Examples:
      synthadoc restore synthadoc-backup-history-of-computing-20260624.zip
      synthadoc restore backup.zip --name my-wiki --target ~/wikis --port 7071
    """
    zip_path = Path(backup_file).resolve()
    if not zip_path.exists():
        E.cli_error(E.WIKI_NOT_FOUND, f"Backup file not found: {zip_path}", "")

    # Read and validate manifest
    try:
        manifest = read_manifest(zip_path)
    except Exception as exc:
        E.cli_error(E.WIKI_INVALID, f"Cannot read manifest: {exc}", "")

    try:
        validate_manifest(manifest, DB_SCHEMA_VERSION)
    except ValueError as exc:
        E.cli_error(E.BACKUP_INCOMPATIBLE, str(exc), "")

    if not verify_checksum(zip_path, manifest.get("checksum_sha256", "")):
        E.cli_error(
            E.WIKI_INVALID,
            "Backup checksum mismatch — archive may be corrupted.",
            "Use a fresh backup copy.",
        )

    original_name: str = manifest["wiki_name"]
    wiki_name: str = name or original_name

    # Name conflict check
    registry = _read_registry()
    stale_port: int | None = None
    if wiki_name in registry:
        existing_path = registry[wiki_name]["path"]
        if Path(existing_path).exists():
            E.cli_error(
                E.WIKI_ALREADY_EXISTS,
                f"Wiki '{wiki_name}' is already registered at {existing_path}.",
                f"Use --name to choose a different name, or uninstall first:\n"
                f"  synthadoc uninstall {wiki_name}",
            )
        else:
            raw_port = registry[wiki_name].get("port")
            if raw_port:
                stale_port = int(raw_port)
            typer.echo(
                f"  Note: '{wiki_name}' was registered at {existing_path} "
                f"but that path no longer exists — proceeding with restore.",
                err=True,
            )

    # Demo wiki rename warning
    if wiki_name != original_name and original_name in _DEMOS:
        typer.echo(
            f"\nWARNING: This backup is the '{original_name}' demo wiki.\n"
            f"Renaming it to '{wiki_name}' will break 'synthadoc demo sync {original_name}'.",
            err=True,
        )
        if not typer.confirm("Continue?", default=False):
            typer.echo("Restore aborted.")
            raise typer.Exit(0)

    # Resolve target directory — default to same folder as the zip
    if target is None:
        target_dir = zip_path.parent
        typer.echo(f"Restoring to: {target_dir}")
    else:
        target_dir = Path(target.strip()).resolve()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        E.cli_error(
            E.WIKI_INVALID,
            f"Cannot create target directory '{target_dir}': {exc.strerror}",
            "Check the path is valid and you have write permission.",
        )

    # Port resolution
    if port is not None:
        effective_port = port
    else:
        backed_up_port = _read_backed_up_port(zip_path)
        reserved = _get_reserved_ports()
        if stale_port is not None:
            reserved.discard(stale_port)
        effective_port = assign_wiki_port(reserved, start=backed_up_port)
        if effective_port != backed_up_port:
            raw = typer.prompt(
                f"Port {backed_up_port} is taken. Suggested: {effective_port} "
                f"— press Enter to accept or type a different port",
                default=str(effective_port),
            )
            try:
                effective_port = int(raw)
            except ValueError:
                pass

    # Extract
    typer.echo(f"\nRestoring '{wiki_name}' to {target_dir / wiki_name} ...")
    wiki_root = extract_backup(zip_path, target_dir, wiki_name)

    # Rewrite config.toml
    config_path = wiki_root / ".synthadoc" / "config.toml"
    if config_path.exists():
        new_domain = wiki_name if wiki_name != original_name else None
        rewrite_config(config_path, effective_port, new_domain)

    # Update registry
    registry[wiki_name] = {
        "path": str(wiki_root),
        "demo": wiki_name if wiki_name in _DEMOS else None,
        "installed": date.today().isoformat(),
        "port": effective_port,
    }
    _write_registry(registry)

    # Re-apply scheduled jobs (non-fatal)
    _apply_schedules(wiki_root, wiki_name)

    # Auto-reinstall Obsidian plugin if it was present when the backup was made.
    if manifest.get("obsidian_plugin"):
        from synthadoc.cli.plugin import _install_plugin_into, _update_community_plugins, _PLUGIN_SRC, _DATAVIEW_ID, _PLUGIN_ID
        if _PLUGIN_SRC.exists():
            _install_plugin_into(wiki_root)
            _update_community_plugins(wiki_root, _DATAVIEW_ID, _PLUGIN_ID)

    typer.echo(f"\n✓ Restored '{wiki_name}' on port {effective_port}")
    typer.echo(f"  Path: {wiki_root}")
    if manifest.get("obsidian_plugin"):
        typer.echo(f"  ✓ Obsidian plugin reinstalled")
    typer.echo(f"\nNext steps:")
    typer.echo(f"  • Set your LLM API key in your shell environment")
    typer.echo(f"  • Start the server:   synthadoc serve -w {wiki_name}")
    if manifest.get("obsidian_plugin"):
        typer.echo(f"  • Open the vault in Obsidian — plugin is ready")


def _read_backed_up_port(zip_path: Path) -> int:
    """Extract server port from config.toml inside the zip, fallback to 7070."""
    import tomllib
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            data = tomllib.loads(zf.read(".synthadoc/config.toml").decode("utf-8"))
            return int(data.get("server", {}).get("port", _DEFAULT_PORT))
    except Exception:
        return _DEFAULT_PORT


def _apply_schedules(wiki_root: Path, wiki_name: str) -> None:
    """Re-apply OS scheduled tasks from config.toml — non-fatal on error."""
    import subprocess
    import sys
    try:
        subprocess.run(
            [sys.executable, "-m", "synthadoc", "schedule", "apply", "--wiki", str(wiki_root)],
            timeout=30,
            check=False,
            capture_output=True,
        )
    except Exception:
        typer.echo(
            f"  Warning: could not re-apply scheduled tasks.\n"
            f"  Run manually: synthadoc schedule apply -w {wiki_name}",
            err=True,
        )
