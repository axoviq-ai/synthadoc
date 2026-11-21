# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import NoReturn, Optional

import typer

from synthadoc import errors as E

ENV_VAR = "SYNTHADOC_WIKI"
DEFAULT_WIKI_FILE = Path.home() / ".synthadoc" / "default_wiki"
_REGISTRY = Path.home() / ".synthadoc" / "wikis.json"

# Canonical loopback address used for all CLI→server HTTP connections and for
# the default peer host in the cross-wiki registry.  Change here to affect all
# client-side URL constructors in the CLI.
LOOPBACK_HOST = "127.0.0.1"

CROSS_WIKI_ROUTING_PATH: Path = Path.home() / ".synthadoc" / "CROSS_WIKI_ROUTING.md"


def _read_registry() -> dict:
    if _REGISTRY.exists():
        return json.loads(_REGISTRY.read_text(encoding="utf-8"))
    return {}


def read_registry_all() -> dict:
    """Return full registry dict. Keys are wiki names, values include path/port/purpose_summary."""
    return _read_registry()


def extract_purpose_summary(wiki_root: Path) -> str:
    """Read wiki_root/wiki/purpose.md, strip YAML frontmatter, return first 500 chars of body.

    Returns an empty string when purpose.md does not exist.
    """
    purpose_path = wiki_root / "wiki" / "purpose.md"
    if not purpose_path.exists():
        return ""
    text = purpose_path.read_text(encoding="utf-8")
    # Strip YAML frontmatter delimited by --- ... ---
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            text = text[end + 3:].lstrip("\n")
    return text[:500]


def peer_base_url(entry: dict) -> str:
    """Return the base URL for a registry entry, e.g. 'http://192.0.2.1:7071'.

    Uses the optional ``host`` field (default ``127.0.0.1``) so remote peers
    registered with an explicit host are reachable without code changes.
    """
    host = entry.get("host", LOOPBACK_HOST)
    port = entry["port"]
    return f"http://{host}:{port}"


def probe_port(port: int, timeout: float = 1.0) -> bool:
    """Return True if the synthadoc server at the given port responds to /health."""
    try:
        import httpx
        httpx.get(f"http://{LOOPBACK_HOST}:{port}/health", timeout=timeout)
        return True
    except Exception:
        return False


def _docker_wiki_hint(wiki_name: str, *, known_root: Path | None = None,
                       known_port: int | None = None) -> str:
    """Return the most actionable ERR-WIKI-006 hint for the context.

    Call just before raising ERR-WIKI-006.  Returns an empty string when the
    host registry does not exist (we may already be inside a container) or
    when the wiki IS registered.

    *known_root*/*known_port* let a caller that has already resolved and
    loaded the wiki's config (e.g. serve, after load_config succeeded) pass
    the real values directly instead of re-detecting them from CWD/env —
    this is also what lets the "exists on disk" branch below omit the
    misleading `synthadoc install` suggestion (which would fail with
    WIKI_ALREADY_EXISTS) and add the path escape-hatch option instead.
    A caller passing *known_root* has already confirmed the wiki is not
    registered, so this skips the registry-existence/membership guards
    below — those only apply to the auto-detection path, where a missing
    host registry genuinely means "nothing to go on" (e.g. inside a
    container with no host registry visible at all).
    """
    root = known_root
    port = known_port
    if root is None:
        if not _REGISTRY.exists():
            return ""
        if wiki_name in _read_registry():
            return ""
        # Try to read the actual path and port from the wiki in CWD (or the
        # SYNTHADOC_WIKI env var root) so the hint shows real values.
        # Only trust the fallback root when its directory name matches the
        # requested wiki name to avoid showing another wiki's path.
        fallback_root = _fallback_wiki_root()
        if fallback_root is not None and fallback_root.name == wiki_name:
            root = fallback_root.resolve()
            try:
                import tomllib  # Python 3.11+
            except ImportError:
                import tomli as tomllib  # type: ignore[no-redef]
            try:
                cfg_text = (root / ".synthadoc" / "config.toml").read_text(encoding="utf-8")
                port = tomllib.loads(cfg_text).get("server", {}).get("port", 7070)
            except Exception:
                port = 7070

    if root is None:
        # Nothing locatable on this host at all — most likely installed inside
        # a Docker container, whose registry entry lives only in that container.
        wiki_path = f"/absolute/path/to/{wiki_name}"
        _entry_json = json.dumps({wiki_name: {"path": wiki_path, "port": 7070}})
        return (
            f"This wiki may have been installed inside a Docker container — its\n"
            f"  registry entry lives only inside that container.\n"
            f"  To use it from the host, add its entry manually to:\n"
            f"    {_REGISTRY}\n"
            f"  Example entry: {_entry_json}\n"
            f"  Or re-install it on the host: synthadoc install {wiki_name} --target <dir>"
        )

    # A real root is known — this is a plain "not yet registered" case, not
    # necessarily Docker, so drop the Docker framing and give exact, correct
    # options for what's actually on disk.
    if (root / ".synthadoc" / "config.toml").exists():
        _entry_json = json.dumps({wiki_name: {"path": str(root), "port": port if port is not None else 7070}})
        return (
            f"The wiki exists on disk but is not registered.\n"
            f"  Add it manually to {_REGISTRY}:\n"
            f"    {_entry_json}\n"
            f"  Or skip the registry entirely by passing the path instead of the name:\n"
            f"    -w {root}"
        )
    _entry_json = json.dumps({wiki_name: {"path": str(root), "port": "<port>"}})
    return (
        f"Register it by running from the parent directory:\n"
        f"  synthadoc install {wiki_name} --target {root.parent}\n"
        f"Or, if the wiki already exists on disk, add it manually to {_REGISTRY}:\n"
        f"  {_entry_json}\n"
        f"Then retry the same command."
    )


def _raise_wiki_not_registered(wiki_name: str, fallback_hint: str = "", *,
                                known_root: Path | None = None,
                                known_port: int | None = None) -> NoReturn:
    """Raise ERR-WIKI-006 with the most actionable message for the context.

    When the host registry exists but the wiki is absent, the Docker hint fires.
    Otherwise falls back to *fallback_hint* (or a generic install hint).

    *known_root*/*known_port* are forwarded to `_docker_wiki_hint` — pass them
    when the caller already resolved and loaded the wiki (see its docstring).
    Passing *known_root* means the caller has already confirmed the wiki is
    not registered, so that case always takes the rich-hint branch below,
    regardless of whether the host registry file itself exists yet.
    """
    if known_root is not None or (_REGISTRY.exists() and wiki_name not in _read_registry()):
        E.cli_error(
            E.WIKI_NOT_REGISTERED,
            f"Wiki '{wiki_name}' is not registered on this host.",
            _docker_wiki_hint(wiki_name, known_root=known_root, known_port=known_port),
        )
    else:
        E.cli_error(
            E.WIKI_NOT_REGISTERED,
            f"Wiki '{wiki_name}' is not installed.",
            fallback_hint or f"Make sure wiki '{wiki_name}' was installed with 'synthadoc install'.",
        )


def _fallback_wiki_root() -> Optional[Path]:
    """Return a wiki root from SYNTHADOC_WIKI env var or CWD, or None.

    Used by commands that need to locate a single wiki when the host registry
    (~/.synthadoc/wikis.json) is absent — e.g. inside a Docker container.
    """
    env_wiki = os.environ.get(ENV_VAR, "").strip()
    if env_wiki:
        p = Path(env_wiki)
        if p.is_dir():
            return p
    cwd = Path.cwd()
    if (cwd / ".synthadoc" / "config.toml").exists():
        return cwd
    return None


def resolve_wiki_path(wiki: str) -> Path:
    """Resolve a wiki name or path to an absolute Path.

    Lookup order:
    1. Registry name match  — ``synthadoc status -w history-of-computing``
    2. Filesystem path      — ``synthadoc status -w ~/wikis/history-of-computing``
    """
    wiki = _normalise_wiki_name(wiki)
    registry = _read_registry()
    if wiki in registry:
        return Path(registry[wiki]["path"])
    return Path(wiki)


def _normalise_wiki_name(name: str) -> str:
    """Strip trailing path separators that macOS tab-completion appends."""
    return name.strip().rstrip("/\\")


def _read_default_wiki() -> Optional[str]:
    """Return the saved default wiki name, or None if not set."""
    try:
        text = DEFAULT_WIKI_FILE.read_text(encoding="utf-8").strip()
        return text or None
    except FileNotFoundError:
        return None


def _write_default_wiki(name: Optional[str]) -> None:
    """Write (or clear) the saved default wiki name."""
    DEFAULT_WIKI_FILE.parent.mkdir(parents=True, exist_ok=True)
    if name:
        DEFAULT_WIKI_FILE.write_text(_normalise_wiki_name(name), encoding="utf-8")
    elif DEFAULT_WIKI_FILE.exists():
        DEFAULT_WIKI_FILE.unlink()


def resolve_wiki(explicit: Optional[str]) -> str:
    """Resolve the active wiki from the priority chain.

    Priority: explicit -w arg > SYNTHADOC_WIKI env var >
              ~/.synthadoc/default_wiki > CWD fallback > error.

    All hint messages are written to stderr so stdout stays
    machine-readable for automation pipelines.
    """
    env_wiki = os.environ.get(ENV_VAR, "").strip() or None
    saved_wiki = _read_default_wiki()

    if explicit is not None:
        if env_wiki and explicit != env_wiki:
            typer.echo(
                f"[wiki: {explicit}]  overrides {ENV_VAR}='{env_wiki}'",
                err=True,
            )
        elif saved_wiki and explicit != saved_wiki:
            typer.echo(
                f"[wiki: {explicit}]  overrides saved default '{saved_wiki}'",
                err=True,
            )
        else:
            typer.echo(f"[wiki: {explicit}]", err=True)
        return explicit

    if env_wiki:
        typer.echo(f"[wiki: {env_wiki}]", err=True)
        return env_wiki

    if saved_wiki:
        typer.echo(f"[wiki: {saved_wiki}]", err=True)
        return saved_wiki

    # Backward compat: user is inside a wiki directory
    if Path(".synthadoc/config.toml").exists():
        cwd_name = Path(".").resolve().name
        typer.echo(f"[wiki: {cwd_name} (current directory)]", err=True)
        return "."

    typer.echo(
        "Error: No wiki specified.\n"
        "  Pass -w <name> on this command, or run 'synthadoc use <name>' to\n"
        "  save a default — you won't need -w again unless switching wikis.",
        err=True,
    )
    raise typer.Exit(1)
