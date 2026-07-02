# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

import httpx
import typer

from synthadoc.cli._wiki import resolve_wiki
from synthadoc.cli.install import resolve_wiki_path, _read_registry
from synthadoc.cli.main import app

plugin_app = typer.Typer(name="plugin", help="Manage the Synthadoc Obsidian plugin.")
app.add_typer(plugin_app)

_PLUGIN_SRC = Path(__file__).resolve().parent.parent / "data" / "obsidian-plugin"
_PLUGIN_FILES = ("main.js", "manifest.json", "styles.css")
_PLUGIN_ID = "synthadoc"
_DATAVIEW_ID = "dataview"
_DATAVIEW_RELEASE_URL = "https://github.com/blacksmithgu/obsidian-dataview/releases/latest/download"
_OBSIDIAN_APP_JSON_KEY = "defaultViewMode"
_OBSIDIAN_READING_VIEW = "preview"


_LOOPBACK_ADDRS = frozenset({"127.0.0.1", "::1", "localhost"})
_ANY_IFACE_ADDRS = frozenset({"0.0.0.0", "::"})


def _write_plugin_data(wiki_path: Path, plugin_dir: Path) -> None:
    """Write (or update) data.json with the wiki's server URL.

    Reads host and port from the wiki's config.toml.  If data.json already
    exists (e.g. the user has customised other settings), only ``serverUrl``
    is updated — all other keys are preserved.
    """
    import tomllib
    host = "127.0.0.1"
    port = 7070
    config_path = wiki_path / ".synthadoc" / "config.toml"
    if config_path.exists():
        try:
            cfg = tomllib.loads(config_path.read_text(encoding="utf-8"))
            srv = cfg.get("server", {})
            host = srv.get("host", "127.0.0.1")
            port = srv.get("port", 7070)
        except Exception:
            pass

    # Loopback and any-interface binds → plugin connects via 127.0.0.1 locally.
    # Specific external address → use it directly for remote vault support.
    if host in _LOOPBACK_ADDRS or host in _ANY_IFACE_ADDRS:
        server_url = f"http://127.0.0.1:{port}"
    else:
        server_url = f"http://{host}:{port}"

    data_json = plugin_dir / "data.json"
    existing: dict = {}
    if data_json.exists():
        try:
            existing = json.loads(data_json.read_text(encoding="utf-8"))
        except Exception:
            pass

    existing["serverUrl"] = server_url
    data_json.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def _update_community_plugins(wiki_path: Path, *plugin_ids: str) -> None:
    """Add plugin IDs to .obsidian/community-plugins.json, creating the file if absent."""
    obsidian_dir = wiki_path / ".obsidian"
    obsidian_dir.mkdir(parents=True, exist_ok=True)
    cp_file = obsidian_dir / "community-plugins.json"
    enabled: list[str] = []
    if cp_file.exists():
        try:
            parsed = json.loads(cp_file.read_text(encoding="utf-8"))
            if isinstance(parsed, list):
                enabled = parsed
        except Exception:
            pass
    changed = False
    for pid in plugin_ids:
        if pid not in enabled:
            enabled.append(pid)
            changed = True
    if changed:
        cp_file.write_text(json.dumps(enabled, indent=2), encoding="utf-8")


def _install_dataview(wiki_path: Path) -> str:
    """Download and install the Dataview plugin from GitHub releases.

    Returns 'installed', 'skipped' (already present), or 'failed'.
    """
    dest_dir = wiki_path / ".obsidian" / "plugins" / _DATAVIEW_ID
    if (dest_dir / "main.js").exists():
        return "skipped"
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        for fname in ("main.js", "manifest.json"):
            r = httpx.get(f"{_DATAVIEW_RELEASE_URL}/{fname}", follow_redirects=True, timeout=30)
            r.raise_for_status()
            (dest_dir / fname).write_bytes(r.content)
        try:
            r = httpx.get(f"{_DATAVIEW_RELEASE_URL}/styles.css", follow_redirects=True, timeout=30)
            if r.status_code == 200:
                (dest_dir / "styles.css").write_bytes(r.content)
        except Exception:
            pass
        return "installed"
    except Exception:
        shutil.rmtree(dest_dir, ignore_errors=True)
        return "failed"


def _set_reading_view_default(wiki_path: Path) -> bool:
    """Merge defaultViewMode=preview into .obsidian/app.json.

    Returns True if written; False if no write was needed (setting already correct).
    Treats malformed JSON as empty dict and heals the file.
    Idempotent — does not write if the setting is already correct.
    """
    obsidian_dir = wiki_path / ".obsidian"
    obsidian_dir.mkdir(parents=True, exist_ok=True)
    app_json = obsidian_dir / "app.json"
    config: dict = {}
    if app_json.exists():
        try:
            config = json.loads(app_json.read_text(encoding="utf-8"))
            if not isinstance(config, dict):
                config = {}
        except Exception:
            config = {}
    if config.get(_OBSIDIAN_APP_JSON_KEY) == _OBSIDIAN_READING_VIEW:
        return False
    config[_OBSIDIAN_APP_JSON_KEY] = _OBSIDIAN_READING_VIEW
    app_json.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return True


def _install_plugin_into(wiki_path: Path) -> list[str]:
    """Copy plugin files into wiki_path and write data.json.  Returns copied filenames."""
    dest_dir = wiki_path / ".obsidian" / "plugins" / _PLUGIN_ID
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for filename in _PLUGIN_FILES:
        src = _PLUGIN_SRC / filename
        if src.exists():
            shutil.copy2(src, dest_dir / filename)
            copied.append(filename)
    if copied:
        _write_plugin_data(wiki_path, dest_dir)
    return copied


@plugin_app.command("install")
def plugin_install_cmd(
    wiki: Optional[str] = typer.Argument(None, help="Wiki name (uses default if omitted)"),
    w: Optional[str] = typer.Option(None, "--wiki", "-w", help="Wiki name or path"),
):
    """Copy the built Obsidian plugin into a wiki vault.

    \b
    Examples:
      synthadoc plugin install ai-research
      synthadoc plugin install -w ai-research
      synthadoc plugin install               # uses default wiki (synthadoc use <name>)
    """
    wiki_name = resolve_wiki(w or wiki)
    wiki_path = resolve_wiki_path(wiki_name)

    if not wiki_path.exists():
        typer.echo(
            f"Error: wiki path '{wiki_path}' does not exist on disk.\n"
            f"The registry entry for '{wiki_name}' may be stale.",
            err=True,
        )
        raise typer.Exit(1)

    if not _PLUGIN_SRC.exists():
        typer.echo(
            f"Error: plugin data not found at '{_PLUGIN_SRC}'.\n"
            "Reinstall synthadoc or run: python scripts/sync_plugin.py",
            err=True,
        )
        raise typer.Exit(1)

    copied = _install_plugin_into(wiki_path)

    if not copied:
        typer.echo(
            "Error: no plugin files found in synthadoc/data/obsidian-plugin/.\n"
            "Run: python scripts/sync_plugin.py",
            err=True,
        )
        raise typer.Exit(1)

    dataview_status = _install_dataview(wiki_path)
    _update_community_plugins(wiki_path, _DATAVIEW_ID, _PLUGIN_ID)
    _set_reading_view_default(wiki_path)

    dest_dir = wiki_path / ".obsidian" / "plugins" / _PLUGIN_ID
    typer.echo(f"Plugin installed into: {dest_dir}")
    for f in copied:
        typer.echo(f"  copied  {f}")
    typer.echo(f"  wrote   data.json (server URL configured automatically)")
    if dataview_status == "installed":
        typer.echo(f"  installed Dataview dependency")
    elif dataview_status == "skipped":
        typer.echo(f"  Dataview already installed — skipped")
    else:
        typer.echo(f"  Note: Dataview download failed — install it manually via Obsidian Settings > Community Plugins")
    typer.echo(f"  community-plugins.json updated — both plugins pre-enabled")
    typer.echo("  set     app.json defaultViewMode=preview (Reading View)")
    typer.echo("          (Restart Obsidian or reopen this vault for the setting to take effect.)")
    typer.echo()
    typer.echo("Open Obsidian and open this vault — both plugins are already enabled, no manual steps required.")


@plugin_app.command("upgrade")
def plugin_upgrade_cmd():
    """Upgrade the Obsidian plugin in every registered wiki vault.

    \b
    Reads the wiki registry and reinstalls the latest plugin files into each
    vault that already has the plugin directory.  Run this after updating
    Synthadoc (pip install -e '.[dev]') to keep all wikis in sync.

    \b
    Examples:
      synthadoc plugin upgrade
    """
    if not _PLUGIN_SRC.exists():
        typer.echo(
            f"Error: plugin data not found at '{_PLUGIN_SRC}'.\n"
            "Reinstall synthadoc or run: python scripts/sync_plugin.py",
            err=True,
        )
        raise typer.Exit(1)

    registry = _read_registry()
    if not registry:
        typer.echo("No wikis registered. Use 'synthadoc init' to create a wiki first.")
        raise typer.Exit(0)

    upgraded: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    for name, meta in registry.items():
        wiki_path = Path(meta.get("path", ""))
        if not wiki_path.exists():
            errors.append(f"  {name}: path '{wiki_path}' not found on disk (stale registry entry)")
            continue
        try:
            copied = _install_plugin_into(wiki_path)
            if copied:
                _set_reading_view_default(wiki_path)
                upgraded.append(name)
            else:
                skipped.append(f"  {name}: no plugin files found — run: python scripts/sync_plugin.py")
        except Exception as exc:
            errors.append(f"  {name}: {exc}")

    if upgraded:
        typer.echo(f"Upgraded {len(upgraded)} wiki(s):")
        for name in upgraded:
            typer.echo(f"  {name}")
    if skipped:
        typer.echo("Skipped:")
        for msg in skipped:
            typer.echo(msg)
    if errors:
        typer.echo("Errors:")
        for msg in errors:
            typer.echo(msg)
    if not upgraded and not skipped and not errors:
        typer.echo("Nothing to upgrade.")
