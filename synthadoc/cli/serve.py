# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import os
import socket
import sys
import time
import subprocess
from pathlib import Path
from typing import Optional

import typer

from synthadoc.cli.main import app
from synthadoc.cli._wiki import (
    resolve_wiki_path, read_registry_all, _REGISTRY,
)
from synthadoc import errors as E
from synthadoc.config import Provider

# Internal env var set on the detached child to suppress duplicate banner output.
_NO_BANNER_ENV = "_SYNTHADOC_NO_BANNER"

_PROVIDER_HOSTS = {
    Provider.ANTHROPIC: ("api.anthropic.com", 443),
    Provider.OPENAI:    ("api.openai.com", 443),
    Provider.GEMINI:    ("generativelanguage.googleapis.com", 443),
    Provider.GROQ:      ("api.groq.com", 443),
}

# Loopback addresses — the Obsidian plugin always connects via 127.0.0.1 for these.
_LOOPBACK_ADDRS: frozenset[str] = frozenset({"127.0.0.1", "::1", "localhost"})
# "All interfaces" binds — plugin still reaches the server via 127.0.0.1 locally.
_ANY_IFACE_ADDRS: frozenset[str] = frozenset({"0.0.0.0", "::"})


def _plugin_url(host: str, port: int) -> str:
    """Return the URL the Obsidian plugin should use to reach the server.

    When the server binds to a loopback or any-interface address, the plugin
    always runs on the same machine, so 127.0.0.1 works.  When bound to a
    specific external address, use that address directly so remote vaults
    can connect.
    """
    if host in _LOOPBACK_ADDRS or host in _ANY_IFACE_ADDRS:
        return f"http://127.0.0.1:{port}"
    return f"http://{host}:{port}"


def _sync_plugin_config(wiki_root: Path, host: str, port: int) -> None:
    """Update the Obsidian plugin data.json if its serverUrl differs from the served address.

    Called at startup so that manual config.toml edits are automatically
    reflected in the plugin — the user only needs to reload Obsidian.
    Silently no-ops if the plugin is not installed in this vault.
    """
    import json
    data_json = wiki_root / ".obsidian" / "plugins" / "synthadoc" / "data.json"
    if not data_json.exists():
        return
    try:
        data = json.loads(data_json.read_text(encoding="utf-8"))
        expected_url = _plugin_url(host, port)
        if data.get("serverUrl") != expected_url:
            old_url = data.get("serverUrl", "(none)")
            data["serverUrl"] = expected_url
            data_json.write_text(json.dumps(data, indent=2), encoding="utf-8", newline="\n")
            typer.echo(
                f"Notice: plugin server URL updated {old_url!r} → {expected_url!r}.\n"
                f"Reload Obsidian (Cmd+R / Ctrl+R) if it is already open."
            )
    except Exception:
        pass  # never block startup due to a plugin config issue


def _sync_registry_port(wiki_name: str, port: int) -> None:
    """Update the registry port for a wiki when it differs (e.g. config.toml edited manually)."""
    from synthadoc.cli.install import _read_registry, _write_registry
    try:
        registry = _read_registry()
        if wiki_name in registry and registry[wiki_name].get("port") != port:
            registry[wiki_name]["port"] = port
            _write_registry(registry)
    except Exception:
        pass


def _check_port(port: int, host: str = "127.0.0.1") -> None:
    """Fail early if the port is already bound by another process on the target host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if sys.platform == "win32":
            # SO_REUSEADDR on Windows lets any socket bind to an occupied port —
            # the opposite of what we want here.  SO_EXCLUSIVEADDRUSE correctly
            # fails the bind if anything else already holds the port.
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            # On POSIX, SO_REUSEADDR lets the check succeed on a TIME_WAIT port
            # (so a quick restart doesn't false-alarm) while still failing when
            # the port is actively held in LISTEN state by another process.
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
        except OSError:
            E.cli_error(
                E.SRV_PORT_IN_USE,
                f"Port {port} is already in use.",
                f"  Option 1 — Stop the existing process and retry.\n"
                f"  Option 2 — Use a different port:\n"
                f"               synthadoc serve -w <wiki> --port {port + 1}\n"
                f"             (update the Server URL in the Obsidian plugin settings to match)",
            )


def _check_wiki(root: Path, wiki_arg: str = "") -> None:
    """Fail early if the wiki directory is missing or incomplete."""
    if not root.exists():
        name = wiki_arg or root.name
        E.cli_error(
            E.WIKI_NOT_FOUND,
            f"Wiki directory not found: {root}",
            f"Run 'synthadoc install {name} --target <dir>' to create it,\n"
            f"or check that the --wiki name matches a registered wiki.",
        )
    wiki_dir = root / "wiki"
    if not wiki_dir.is_dir():
        E.cli_error(
            E.WIKI_INVALID,
            f"{root} does not look like a synthadoc wiki (missing wiki/ subfolder).",
            "If this is a new wiki, run 'synthadoc install' to set it up properly.",
        )
    if not os.access(wiki_dir, os.W_OK):
        E.cli_error(
            E.WIKI_NOT_WRITABLE,
            f"Wiki directory is not writable: {wiki_dir}",
            "Check file permissions.",
        )


def _check_network(provider: str) -> None:
    """Warn (don't block) if the provider API host is unreachable."""
    target = _PROVIDER_HOSTS.get(provider)
    if not target:
        return  # ollama or unknown — skip
    host, port = target
    try:
        with socket.create_connection((host, port), timeout=3):
            pass
    except OSError:
        typer.echo(
            f"Warning: cannot reach {host}:{port} — network may be unavailable or blocked.\n"
            f"The server will start, but ingest and query jobs will fail until connectivity\n"
            f"is restored. If you use a proxy, ensure it is configured in your environment.\n",
            err=True,
        )


def _check_api_key(cfg, agent_name: str = "ingest") -> None:
    """Fail early with a clean message if the configured provider is unusable.

    Delegates to make_provider itself (discarding the constructed provider)
    rather than maintaining a parallel if/elif list of providers that need a
    key. That list previously covered only anthropic/openai/gemini/groq and
    silently missed minimax/deepseek/kimi/qwen — misconfiguring one of those
    let the server start successfully, with the error only ever surfacing
    later from a real query instead of at startup like every other provider.

    Every provider's __init__ only constructs a local SDK client object (no
    network calls) except the CLI-based ones (claude-code, opencode), which
    check the binary is on PATH and raise EnvironmentError if not — also a
    known, actionable, startup-time problem, so it's caught here too rather
    than left to surface mid-query.

    MissingApiKeyError/EnvironmentError's own messages already carry the
    error code and a fix — it's the whole reason this check exists, so they
    must reach the user as plain text, not as an unhandled exception with a
    Rich traceback box on top of it.
    """
    from synthadoc.providers import make_provider
    try:
        make_provider(agent_name, cfg)
    except (E.MissingApiKeyError, EnvironmentError) as exc:
        typer.echo(f"\n{exc}\n", err=True)
        raise typer.Exit(1)


def _spawn_background(wiki_root: Path, effective_port: int, log_path: Path,
                       banner_kwargs: dict | None = None) -> None:
    """Detach the server as a background process and return to the shell."""
    # Strip --background / -b from the forwarded args.
    server_args = [a for a in sys.argv[1:] if a not in ("--background", "-b")]

    shared_env = {**os.environ, _NO_BANNER_ENV: "1"}
    if sys.platform == "win32":
        # pythonw.exe runs Python with no console window at all — the child
        # process has zero console association, so the parent's CMD/PowerShell
        # window returns to the prompt as soon as the parent exits.
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        interpreter = str(pythonw) if pythonw.exists() else sys.executable
        cmd = [interpreter, "-m", "synthadoc"] + server_args
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            env=shared_env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
        )
    else:
        cmd = [sys.argv[0]] + server_args
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            env=shared_env,
            start_new_session=True,
        )

    # Persist PID so the user (or a stop command) can terminate the server.
    pid_path = wiki_root / ".synthadoc" / "server.pid"
    pid_path.write_text(str(proc.pid), encoding="utf-8")

    if banner_kwargs is not None:
        from synthadoc.cli.logo import print_banner
        print_banner(**banner_kwargs, pid=proc.pid)

    # Brief pause — detect immediate crashes before telling the user it worked.
    time.sleep(1.5)
    if proc.poll() is not None:
        E.cli_error(
            E.SRV_BG_CRASH,
            f"Background server exited immediately (code {proc.returncode}).",
            f"Check logs: {log_path}",
        )

    typer.echo(
        f"\nServer running in background\n"
        f"  PID   {proc.pid}\n"
        f"  Port  {effective_port}\n"
        f"  Logs  {log_path}\n"
        f"\nTo stop: kill {proc.pid}"
        + (f"  (or: taskkill /PID {proc.pid} /F)" if sys.platform == "win32" else "")
    )


def _spawn_background_for_path(wiki_path: Path, wiki_name: str) -> None:
    """Start a single wiki in background from its path. Used by --all."""
    from synthadoc.config import load_config
    try:
        cfg = load_config(project_config=wiki_path / ".synthadoc" / "config.toml")
    except Exception as exc:
        typer.echo(f"  {wiki_name}: config error — {exc}", err=True)
        return
    port = cfg.server.port
    log_path = wiki_path / ".synthadoc" / "logs" / "synthadoc.log"
    _spawn_background(wiki_path, port, log_path)


def _apply_provider_override(cfg, provider_name: str) -> None:
    """Override the provider field on all agent configs in cfg in-place."""
    from synthadoc.config import KNOWN_PROVIDERS
    if provider_name not in KNOWN_PROVIDERS:
        E.cli_error(
            E.CFG_UNKNOWN_PROVIDER,
            f"Unknown provider: {provider_name!r}",
            f"Supported providers: {', '.join(sorted(KNOWN_PROVIDERS))}",
        )
    cfg.agents.default.provider = provider_name
    for slot in ("ingest", "query", "lint", "skill"):
        override = getattr(cfg.agents, slot, None)
        if override is not None:
            override.provider = provider_name


@app.command("serve")
def serve_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    port: Optional[int] = typer.Option(None, "--port",
        help="Port override. Defaults to [server] port in config (7070)."),
    mcp_only: bool = typer.Option(False, "--mcp-only"),
    http_only: bool = typer.Option(False, "--http-only"),
    verbose: bool = typer.Option(False, "--verbose", "-v",
        help="Set console log level to DEBUG (file always logs DEBUG)."),
    background: bool = typer.Option(False, "--background", "-b",
        help="Detach the server to the background. Banner is shown then the shell is released; "
             "all subsequent logs go to the wiki log file."),
    provider_override: Optional[str] = typer.Option(
        None, "--provider",
        help="Override config.toml provider for all agents for this server session "
             "(e.g. anthropic, claude-code, opencode). Does not require editing config.toml.",
    ),
    host: Optional[str] = typer.Option(
        None, "--host",
        help="Bind address override (e.g. 0.0.0.0 for Docker or remote access). "
             "Defaults to [server] host in config (127.0.0.1).",
    ),
    all_wikis: bool = typer.Option(False, "--all",
        help="Start all registered wikis in background."),
):
    """Start MCP + HTTP API servers (localhost only).

    Each wiki declares its port in .synthadoc/config.toml:

        [server]
        port = 7071

    Run one server per wiki on its own port, then set the matching
    Server URL in the Obsidian plugin settings for each vault.
    """
    if all_wikis:
        registry = read_registry_all()
        for name, entry in registry.items():
            port_val = entry.get("port")
            path = Path(entry["path"])
            from synthadoc.cli._wiki import probe_port as _probe_port
            if port_val and _probe_port(port_val):
                typer.echo(f"  {name}: already running on port {port_val}")
                continue
            _spawn_background_for_path(path, name)
            typer.echo(f"  {name}: started in background")
        return

    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)

    import uvicorn
    from synthadoc.config import load_config
    from synthadoc.core.logging_config import setup_logging

    root = resolve_wiki_path(wiki)

    try:
        cfg = load_config(project_config=root / ".synthadoc" / "config.toml")
    except E.ConfigError as exc:
        E.cli_error(exc.code, str(exc), exc.hint)

    # Name-based wikis (e.g. -w my-wiki) require a registry entry — the name
    # alone does not locate the wiki on disk.
    # Path-based wikis (e.g. -w /wiki in Docker, -w . from inside the wiki dir)
    # are self-describing: config.toml loaded above is proof the wiki is valid.
    _wiki_is_path = wiki.startswith(".") or "/" in wiki or os.sep in wiki
    if wiki not in read_registry_all() and not _wiki_is_path:
        import json as _json
        abs_root = root.resolve()
        # json.dumps produces a quoted, backslash-escaped string safe to paste into wikis.json
        _path_json = _json.dumps(str(abs_root))
        _port = cfg.server.port
        _wiki_on_disk = (abs_root / ".synthadoc" / "config.toml").exists()
        if _wiki_on_disk:
            _hint = (
                f"The wiki exists on disk but is not registered.\n"
                f"Add it manually to {_REGISTRY}:\n"
                f'  "{wiki}": {{"path": {_path_json}, "port": {_port}}}\n'
                f"Then retry: synthadoc serve -w {wiki}"
            )
        else:
            _hint = (
                f"Register it by running from the parent directory:\n"
                f"  synthadoc install {wiki} --target {abs_root.parent}\n"
                f"Or, if the wiki already exists on disk, add it manually to {_REGISTRY}:\n"
                f'  "{wiki}": {{"path": {_path_json}, "port": {_port}}}\n'
                f"Then retry: synthadoc serve -w {wiki}"
            )
        E.cli_error(E.WIKI_NOT_REGISTERED, f"Wiki '{wiki}' is not registered in {_REGISTRY}.", _hint)
    effective_port = port if port is not None else cfg.server.port
    if host is not None:
        cfg.server.host = host

    if provider_override:
        _apply_provider_override(cfg, provider_override)

    provider = cfg.agents.resolve("ingest").provider

    # Warn when binding to an external interface — synthadoc has no built-in auth.
    if cfg.server.host not in _LOOPBACK_ADDRS:
        typer.echo(
            f"Warning: binding to {cfg.server.host!r} — server reachable from the network.\n"
            "synthadoc has no built-in authentication. Restrict access via firewall\n"
            "or network controls before exposing to untrusted networks.",
            err=True,
        )

    # Keep registry and plugin in sync if config.toml port was manually changed
    _sync_registry_port(wiki or "", effective_port)
    _sync_plugin_config(root, cfg.server.host, effective_port)

    # Pre-flight checks — run before binding the port or starting workers
    _check_wiki(root, wiki_arg=wiki or "")

    # Logging — must come after wiki root is validated so the logs dir can be created
    setup_logging(root, cfg=cfg.logs, verbose=verbose)

    _check_api_key(cfg)

    # Propagate web_search config to env so WebSearchSkill can read it
    os.environ.setdefault(
        "SYNTHADOC_WEB_SEARCH_MAX_RESULTS",
        str(cfg.web_search.max_results),
    )
    if cfg.web_search.provider == "tavily" and not os.environ.get("TAVILY_API_KEY"):
        typer.echo(
            "Warning: TAVILY_API_KEY is not set. Web search jobs will fail.\n"
            "Get a free key at https://tavily.com",
            err=True,
        )

    if not mcp_only:
        _check_port(effective_port, host=cfg.server.host)

    _check_network(provider)

    _print_banner = not os.environ.get(_NO_BANNER_ENV) and not mcp_only
    if _print_banner:
        mode = "MCP (stdio)" if mcp_only else "HTTP" if http_only else "HTTP + MCP"
        _agent_cfg = cfg.agents.resolve("default")
        _override_count = sum(
            1 for slot in ("ingest", "query", "lint", "skill")
            if getattr(cfg.agents, slot, None) is not None
        )
        _llm_note = f"(+ {_override_count} override{'s' if _override_count != 1 else ''})" if _override_count else ""
        _banner_kwargs = dict(port=effective_port, wiki=str(root), mode=mode,
                              provider=_agent_cfg.provider, model=_agent_cfg.model,
                              llm_note=_llm_note)

    if background:
        log_path = root / ".synthadoc" / "logs" / "synthadoc.log"
        _spawn_background(root, effective_port, log_path,
                          banner_kwargs=_banner_kwargs if _print_banner else None)
        return

    if _print_banner:
        from synthadoc.cli.logo import print_banner
        print_banner(**_banner_kwargs)

    if not mcp_only:
        import asyncio
        import signal
        from synthadoc.integration.http_server import create_app
        http_app = create_app(wiki_root=root, enable_mcp=not http_only)
        config = uvicorn.Config(http_app, host=cfg.server.host, port=effective_port,
                                log_level="warning", log_config=None)
        server = uvicorn.Server(config)
        http_app.state.uvicorn_server = server
        if sys.platform == "win32":  # pragma: no cover
            # On Windows asyncio cannot install signal handlers via
            # add_signal_handler(), so uvicorn only catches SIGINT via the
            # default KeyboardInterrupt path — which can get stuck when
            # background tasks are running.  Register both SIGINT and
            # SIGBREAK (Ctrl+Break) explicitly so either key combo delivers
            # a clean shutdown via uvicorn's own should_exit flag.
            def _win_exit(sig, frame):
                server.should_exit = True
            signal.signal(signal.SIGINT, _win_exit)
            try:
                signal.signal(signal.SIGBREAK, _win_exit)
            except (AttributeError, OSError):
                pass
        asyncio.run(server.serve())
    else:
        import asyncio
        from synthadoc.core.orchestrator import Orchestrator
        from synthadoc.integration.mcp_server import create_mcp_server

        async def _stdio_main() -> None:
            orch = Orchestrator(wiki_root=root, config=cfg)
            await orch.init()
            mcp = create_mcp_server(orchestrator=orch)
            try:
                await mcp.run_stdio_async()
            finally:
                await orch.close()

        asyncio.run(_stdio_main())
