# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from typing import Optional

import typer

from synthadoc.cli._port import assign_wiki_port as _assign_wiki_port, _DEFAULT_PORT
from synthadoc.cli._wiki import _normalise_wiki_name
from synthadoc import errors as E

_REGISTRY = Path.home() / ".synthadoc" / "wikis.json"

_DEMOS = {
    "history-of-computing": Path(__file__).parent.parent / "demos" / "history-of-computing",
    "ai-research": Path(__file__).parent.parent / "demos" / "ai-research",
}


def _read_registry() -> dict:
    """Read registry from this module's _REGISTRY path (monkeypatchable in tests)."""
    if _REGISTRY.exists():
        return json.loads(_REGISTRY.read_text(encoding="utf-8"))
    return {}


def resolve_wiki_path(wiki: str) -> Path:
    """Resolve a wiki name or path to an absolute Path via the install registry."""
    wiki = _normalise_wiki_name(wiki)
    registry = _read_registry()
    if wiki in registry:
        return Path(registry[wiki]["path"])
    return Path(wiki)


def _write_registry(data: dict) -> None:
    _REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    _REGISTRY.write_text(json.dumps(data, indent=2), encoding="utf-8", newline="\n")


def _get_reserved_ports() -> set[int]:
    """Return all ports currently assigned to registered wikis.

    Reads the ``port`` field from each registry entry when present. Falls back
    to parsing ``.synthadoc/config.toml`` for older entries that pre-date port
    tracking.  Missing wikis or unreadable configs are silently skipped.
    """
    import tomllib
    registry = _read_registry()
    ports: set[int] = set()
    for entry in registry.values():
        if "port" in entry:
            ports.add(int(entry["port"]))
            continue
        config_path = Path(entry.get("path", "")) / ".synthadoc" / "config.toml"
        if config_path.exists():
            try:
                data = tomllib.loads(config_path.read_text(encoding="utf-8"))
                p = data.get("server", {}).get("port")
                if p:
                    ports.add(int(p))
            except Exception:
                pass
    return ports


from synthadoc.cli.main import app  # noqa: E402
from synthadoc.cli._init import (  # noqa: E402
    init_wiki, _CONFIG_TOML, _AGENTS_MD, _CLAUDE_MD, _GEMINI_MD,
)
from synthadoc.core.template_engine import (  # noqa: E402
    apply_template, get_template_guidelines,
)
from synthadoc.cli._utils import _patch_toml  # noqa: E402
from synthadoc.core.scheduler import Scheduler  # noqa: E402
from synthadoc.cli.plugin import (  # noqa: E402
    _install_plugin_into,
    _DATAVIEW_ID,
    _PLUGIN_ID,
    _PLUGIN_SRC,
)




@app.command("install")
def install_cmd(
    name: str = typer.Argument(help="Name for the new wiki"),
    target: str = typer.Option(..., "--target", "-t", help="Parent directory to install into"),
    demo: bool = typer.Option(False, "--demo", "-d", help="Install from a demo template matching <name>"),
    domain: str = typer.Option("General", "--domain", help="Knowledge domain (fresh wikis only)"),
    port: Optional[int] = typer.Option(None, "--port", help="Server port (default: auto-detect from 7070)"),
    template: Optional[str] = typer.Option(
        None,
        "--template", "-T",
        help=(
            'Domain template to apply (e.g. finance/investment). '
            'Run "synthadoc templates list" to see all options.'
        ),
    ),
):
    """Create a new wiki, optionally from a demo template.

    Examples:

      synthadoc install my-research --target ~/wikis

      synthadoc install history-of-computing --target ~/wikis --demo
    """
    dest = (Path(target) / name).resolve()

    # Registry check first â€” same name cannot be installed twice regardless of --target path
    registry = _read_registry()
    if name in registry:
        entry = registry[name]
        kind = f"demo ({entry['demo']})" if entry.get("demo") else "wiki"
        E.cli_error(
            E.WIKI_ALREADY_EXISTS,
            f"'{name}' is already installed as a {kind} at {entry['path']}.",
            f"To reinstall: synthadoc uninstall {name}  then install again.",
        )

    if dest.exists():
        E.cli_error(
            E.WIKI_ALREADY_EXISTS,
            f"'{name}' already exists at {dest} but is not tracked by synthadoc.",
            f"It may be a leftover from a previous install. To remove it:\n"
            f"  rm -rf \"{dest}\"    # Linux / macOS\n"
            f"  Remove-Item -Recurse -Force \"{dest}\"    # Windows PowerShell\n"
            f"Then run install again.",
        )

    if demo and template:
        E.cli_error(
            E.WIKI_INVALID,
            "--demo and --template cannot be used together.",
            "Use --demo for built-in demo wikis, or --template for a domain template.",
        )

    # Validate template ref before creating any directories â€” an invalid ref must
    # not leave an orphaned unregistered directory on disk.
    if template:
        try:
            guidelines = get_template_guidelines(template)
        except (ValueError, FileNotFoundError) as exc:
            E.cli_error(E.WIKI_INVALID, str(exc), 'Run "synthadoc templates list" for available templates.')

    # â”€â”€ Port resolution â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if port is not None:
        effective_port = port
    else:
        effective_port = _assign_wiki_port(_get_reserved_ports(), _DEFAULT_PORT)
        if effective_port != _DEFAULT_PORT:
            typer.echo(
                f"Port {_DEFAULT_PORT} is already assigned or in use. "
                f"Using port {effective_port} for '{name}'.\n"
                f"Tip: use --port <N> to override."
            )

    if demo:
        if name not in _DEMOS:
            E.cli_error(
                E.WIKI_DEMO_NOT_FOUND,
                f"No demo template named '{name}'.",
                f"Available demos: {', '.join(_DEMOS)}",
            )
        shutil.copytree(_DEMOS[name], dest, ignore=shutil.ignore_patterns("_*", "__pycache__"))
        # Ensure operational directories exist â€” the demo template may not include
        # empty dirs (git doesn't track them) and shutil.copytree won't create them.
        (dest / ".synthadoc" / "logs").mkdir(parents=True, exist_ok=True)
        # Write config.toml â€” .synthadoc/ is git-ignored so it can't be bundled
        # in the demo template; generate it here the same way init_wiki does.
        (dest / ".synthadoc" / "config.toml").write_text(
            _CONFIG_TOML.format(domain=domain, port=effective_port),
            encoding="utf-8", newline="\n",
        )
    else:
        init_wiki(dest, domain, port=effective_port)

    if template:
        # `guidelines` already resolved before init_wiki â€” ref is valid at this point

        # Overwrite skill files with domain-specific guidelines
        skill_kw = dict(domain=domain, guidelines=guidelines, port=effective_port)
        for fname, tmpl in [
            ("AGENTS.md", _AGENTS_MD),
            ("CLAUDE.md", _CLAUDE_MD),
            ("GEMINI.md", _GEMINI_MD),
        ]:
            (dest / fname).write_text(tmpl.format(**skill_kw), encoding="utf-8", newline="\n")

        try:
            apply_template(dest, template)
        except ValueError as exc:
            E.cli_error(E.WIKI_INVALID, str(exc), 'Run "synthadoc templates list" for available templates.')
        except FileNotFoundError as exc:
            E.cli_error(E.WIKI_INVALID, f"Template '{template}' is missing a required file: {exc}", "")

        # Enable staging: all new ingests land in candidates/ for review
        _patch_toml(
            dest / ".synthadoc" / "config.toml",
            "ingest",
            {"staging_policy": "all"},
        )

        # Pre-register weekly maintenance schedule (no-op until content is ingested)
        try:
            sched = Scheduler(wiki=name, wiki_root=str(dest))
            sched.add(op="lint run", cron="0 2 * * 0")   # weekly Sunday 2am
            sched.add(op="scaffold", cron="0 3 * * 0")   # weekly Sunday 3am
        except Exception:
            pass  # scheduler DB may not exist until first server run â€” non-fatal

    registry = _read_registry()
    registry[name] = {
        "path": str(dest),
        "demo": name if demo else None,
        "installed": date.today().isoformat(),
        "port": effective_port,
        **({"category": template.split("/")[0], "template": template.split("/")[1]}
           if template else {}),
    }
    _write_registry(registry)

    # â”€â”€ Obsidian plugin â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _plugin_ok = False
    _dataview_status = "skipped"
    if _PLUGIN_SRC.exists():
        copied = _install_plugin_into(dest)
        if copied:
            from synthadoc.cli.plugin import (
                _install_dataview,
                _update_community_plugins,
                _set_reading_view_default,
                _patch_workspace_reading_view,
            )
            _dataview_status = _install_dataview(dest)
            _update_community_plugins(dest, _DATAVIEW_ID, _PLUGIN_ID)
            _set_reading_view_default(dest)
            _patch_workspace_reading_view(dest)
            _plugin_ok = True

    typer.echo(f"Wiki '{name}' installed.")
    typer.echo(f"  Port   {effective_port}")
    if _plugin_ok:
        if _dataview_status in ("installed", "skipped"):
            typer.echo(f"  Plugin Obsidian plugin ready")
        else:
            typer.echo(f"  Plugin Obsidian plugin installed")
            typer.echo(f"  Warn   Dataview unavailable (GitHub unreachable).")
            typer.echo(f"         To complete setup: synthadoc plugin install -w {name}")
    if not demo:
        typer.echo()
        typer.echo(f"Next steps:")
        typer.echo(f”  1. Edit {name}/.synthadoc/config.toml -- set your LLM provider and API key”)
        typer.echo(f"  2. Set as default wiki:   synthadoc use {name}")
        typer.echo(f"  3. Start the server:      synthadoc serve")
        typer.echo(f"  4. Ingest your sources:   synthadoc ingest <file>")
        typer.echo(f"  5. Generate index:        synthadoc scaffold")

    if template:
        typer.echo()
        typer.echo(f"  Template: {template}")
        typer.echo(f"  Staging:  enabled (all ingests land in candidates/ for review)")
        typer.echo(f"  Schedule: weekly lint + scaffold registered (active after first serve)")
        typer.echo(f"  Start:    review wiki/seeds.md for domain-specific starter resources")


@app.command("list")
def list_cmd():
    """List all installed wikis."""
    registry = _read_registry()
    if not registry:
        typer.echo("No wikis installed. Run 'synthadoc install' to create one.")
        return

    show_type = any(e.get("category") for e in registry.values())

    if show_type:
        typer.echo(f"{'NAME':<30}  {'INSTALLED':<12}  {'PORT':<6}  TYPE")
        typer.echo("â”€" * 70)
        for name, entry in registry.items():
            cat = entry.get("category", "")
            tmpl = entry.get("template", "")
            if cat and tmpl:
                type_col = f"{cat}/{tmpl}"
            elif entry.get("demo"):
                type_col = "demo"
            else:
                type_col = "â€”"
            installed = entry.get("installed", "")
            port_str = str(entry["port"]) if entry.get("port") else "â€”"
            typer.echo(f"{name:<30}  {installed:<12}  {port_str:<6}  {type_col}")
    else:
        for name, entry in registry.items():
            demo_tag = "  [demo]" if entry.get("demo") else ""
            installed = entry.get("installed", "")
            port_str = f"  port: {entry['port']}" if entry.get("port") else ""
            typer.echo(f"{name:<30}  installed: {installed}{port_str}{demo_tag}")


@app.command("uninstall")
def uninstall_cmd(
    name: str = typer.Argument(help="Name of the wiki to remove"),
):
    """Permanently delete an installed wiki.

    Requires two confirmations: a y/N prompt followed by typing the wiki name.
    There is no --yes flag â€” this operation is irreversible.
    """
    name = _normalise_wiki_name(name)
    registry = _read_registry()

    if name not in registry:
        E.cli_error(
            E.WIKI_NOT_REGISTERED,
            f"Wiki '{name}' is not in the registry.",
            f"It may have already been uninstalled or was never installed via `synthadoc install`.\n"
            f"If the directory still exists, remove it manually:\n"
            f"  rm -rf <path-to-wiki>    # Linux / macOS\n"
            f"  Remove-Item -Recurse -Force <path-to-wiki>    # Windows PowerShell",
        )

    dest = Path(registry[name]["path"])

    if not dest.exists():
        typer.echo(f"Wiki '{name}' no longer exists on disk â€” removing from registry.")
        del registry[name]
        _write_registry(registry)
        raise typer.Exit(0)

    # First confirmation
    typer.confirm(
        f"Delete wiki '{name}' at {dest} and all its contents?",
        abort=True,
    )

    # Second confirmation â€” must type the exact name
    typed = typer.prompt(f"Type '{name}' to confirm permanent deletion")
    if typed != name:
        typer.echo("Name did not match â€” aborted. Nothing was deleted.")
        raise typer.Exit(1)

    shutil.rmtree(dest)
    del registry[name]
    _write_registry(registry)
    typer.echo(f"Wiki '{name}' removed.")
