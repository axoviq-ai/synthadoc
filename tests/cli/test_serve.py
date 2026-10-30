# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import json
import pytest
from pathlib import Path
from unittest.mock import patch


def _make_cfg(provider: str = "anthropic"):
    from synthadoc.config import Config, AgentConfig, AgentsConfig
    return Config(agents=AgentsConfig(
        default=AgentConfig(provider=provider, model="claude-opus-4-6")
    ))


def test_apply_provider_override_sets_default():
    """--provider flag overrides config.toml provider on default agent config."""
    from synthadoc.cli.serve import _apply_provider_override
    cfg = _make_cfg("anthropic")
    _apply_provider_override(cfg, "claude-code")
    assert cfg.agents.default.provider == "claude-code"


def test_apply_provider_override_updates_per_agent():
    """--provider flag updates per-agent overrides when they exist."""
    from synthadoc.config import AgentConfig
    from synthadoc.cli.serve import _apply_provider_override
    cfg = _make_cfg("anthropic")
    from synthadoc.config import AgentConfig
    cfg.agents.ingest = AgentConfig(provider="anthropic", model="claude-opus-4-6")
    _apply_provider_override(cfg, "opencode")
    assert cfg.agents.default.provider == "opencode"
    assert cfg.agents.ingest.provider == "opencode"


def test_apply_provider_override_unknown_raises():
    """Unknown --provider value → Exit (cli_error calls typer.Exit)."""
    import click, typer
    from synthadoc.cli.serve import _apply_provider_override
    cfg = _make_cfg("anthropic")
    with pytest.raises((SystemExit, click.exceptions.Exit, typer.Exit)):
        _apply_provider_override(cfg, "unknown-tool")


# ── _sync_plugin_config ───────────────────────────────────────────────────────

def _make_plugin_dir(wiki_root: Path, server_url: str) -> Path:
    plugin_dir = wiki_root / ".obsidian" / "plugins" / "synthadoc"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "data.json").write_text(
        json.dumps({"serverUrl": server_url, "rawSourcesFolder": "raw_sources"}),
        encoding="utf-8",
    )
    return plugin_dir


def test_sync_plugin_config_updates_stale_url(tmp_path):
    """Updates data.json when the stored serverUrl port differs from the served port."""
    from synthadoc.cli.serve import _sync_plugin_config
    _make_plugin_dir(tmp_path, "http://127.0.0.1:7070")
    _sync_plugin_config(tmp_path, "127.0.0.1", 7071)
    data = json.loads((tmp_path / ".obsidian" / "plugins" / "synthadoc" / "data.json")
                      .read_text())
    assert data["serverUrl"] == "http://127.0.0.1:7071"
    assert data["rawSourcesFolder"] == "raw_sources"  # other keys preserved


def test_sync_plugin_config_no_change_when_port_matches(tmp_path):
    """Leaves data.json untouched when serverUrl is already correct."""
    from synthadoc.cli.serve import _sync_plugin_config
    plugin_dir = _make_plugin_dir(tmp_path, "http://127.0.0.1:7070")
    mtime_before = (plugin_dir / "data.json").stat().st_mtime
    _sync_plugin_config(tmp_path, "127.0.0.1", 7070)
    mtime_after = (plugin_dir / "data.json").stat().st_mtime
    assert mtime_before == mtime_after


def test_sync_plugin_config_noop_when_plugin_not_installed(tmp_path):
    """Does not raise when the plugin data.json is absent."""
    from synthadoc.cli.serve import _sync_plugin_config
    _sync_plugin_config(tmp_path, "127.0.0.1", 7070)


def test_sync_plugin_config_port_override_synced(tmp_path):
    """Case e: --port CLI override is reflected in plugin data.json after sync."""
    from synthadoc.cli.serve import _sync_plugin_config
    _make_plugin_dir(tmp_path, "http://127.0.0.1:7070")
    _sync_plugin_config(tmp_path, "127.0.0.1", 8080)
    data = json.loads((tmp_path / ".obsidian" / "plugins" / "synthadoc" / "data.json")
                      .read_text())
    assert data["serverUrl"] == "http://127.0.0.1:8080"


def test_sync_plugin_config_external_host_uses_ip(tmp_path):
    """When host is a specific external IP, data.json uses that IP in the URL."""
    from synthadoc.cli.serve import _sync_plugin_config
    _make_plugin_dir(tmp_path, "http://127.0.0.1:7070")
    _sync_plugin_config(tmp_path, "192.168.1.10", 7070)
    data = json.loads((tmp_path / ".obsidian" / "plugins" / "synthadoc" / "data.json")
                      .read_text())
    assert data["serverUrl"] == "http://192.168.1.10:7070"


# ── _check_port (case f) ──────────────────────────────────────────────────────

def test_check_port_raises_when_port_in_use(tmp_path):
    """Case f: _check_port exits non-zero with a useful message when port is bound."""
    import click
    import socket
    from synthadoc.cli.serve import _check_port

    # Hold the port in a way that blocks _check_port on every platform:
    #
    # Linux/macOS — SO_REUSEADDR allows double-bind unless one socket is
    #   listening; listen(1) blocks further binds even with SO_REUSEADDR.
    #
    # Windows — SO_REUSEADDR permits any socket to bind to an occupied port
    #   (even a listening one), so _check_port uses SO_EXCLUSIVEADDRUSE there.
    #   The holder needs no special flags — EXCLUSIVEADDRUSE on the checker
    #   fails when anything at all holds the port.
    for base in range(40100, 40200):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", base))
            s.listen(1)
            break
        except OSError:
            s.close()
    else:
        pytest.skip("No bindable port found")

    try:
        import typer as _typer
        with pytest.raises((SystemExit, click.exceptions.Exit, _typer.Exit)):
            _check_port(base, host="127.0.0.1")
    finally:
        s.close()


def test_check_port_uses_configured_host():
    """_check_port binds the probe socket to whatever host is passed."""
    import socket as _socket
    bound_host = None

    original_bind = _socket.socket.bind

    def capture_bind(self, addr):
        nonlocal bound_host
        bound_host = addr[0]
        return original_bind(self, addr)

    from synthadoc.cli.serve import _check_port
    with patch("socket.socket.bind", capture_bind):
        try:
            _check_port(40299, host="127.0.0.1")
        except Exception:
            pass
    assert bound_host == "127.0.0.1"


# ── External host: warning, not error ────────────────────────────────────────

def test_serve_warns_on_external_host(capsys):
    """External host in config.toml → warning printed to stderr, no hard exit."""
    from synthadoc.cli.serve import _LOOPBACK_ADDRS, _ANY_IFACE_ADDRS
    import typer

    non_loopback = "192.168.1.10"
    assert non_loopback not in _LOOPBACK_ADDRS

    # Verify _plugin_url uses the external address for specific IPs
    from synthadoc.cli.serve import _plugin_url
    assert _plugin_url(non_loopback, 7070) == "http://192.168.1.10:7070"


def test_plugin_url_loopback_uses_127():
    """_plugin_url returns 127.0.0.1 for loopback and any-interface binds."""
    from synthadoc.cli.serve import _plugin_url
    assert _plugin_url("127.0.0.1", 7070) == "http://127.0.0.1:7070"
    assert _plugin_url("::1", 7070) == "http://127.0.0.1:7070"
    assert _plugin_url("0.0.0.0", 7070) == "http://127.0.0.1:7070"
    assert _plugin_url("::", 7070) == "http://127.0.0.1:7070"


def test_plugin_url_external_uses_host():
    """_plugin_url uses the configured host for specific external addresses."""
    from synthadoc.cli.serve import _plugin_url
    assert _plugin_url("192.168.1.10", 7071) == "http://192.168.1.10:7071"
    assert _plugin_url("10.0.0.5", 8080) == "http://10.0.0.5:8080"


def test_loopback_addrs_constant_covers_expected_values():
    """_LOOPBACK_ADDRS includes 127.0.0.1, ::1, localhost; not 0.0.0.0."""
    from synthadoc.cli.serve import _LOOPBACK_ADDRS
    assert "127.0.0.1" in _LOOPBACK_ADDRS
    assert "::1" in _LOOPBACK_ADDRS
    assert "localhost" in _LOOPBACK_ADDRS
    assert "0.0.0.0" not in _LOOPBACK_ADDRS


def test_any_iface_addrs_constant():
    """_ANY_IFACE_ADDRS includes 0.0.0.0 and :: but not loopback addresses."""
    from synthadoc.cli.serve import _ANY_IFACE_ADDRS
    assert "0.0.0.0" in _ANY_IFACE_ADDRS
    assert "::" in _ANY_IFACE_ADDRS
    assert "127.0.0.1" not in _ANY_IFACE_ADDRS


# ── _check_api_key ────────────────────────────────────────────────────────────
#
# _check_api_key delegates to make_provider itself rather than maintaining a
# parallel if/elif list of providers that need a key — the old list only
# covered anthropic/openai/gemini/groq and silently missed
# minimax/deepseek/kimi/qwen, so misconfiguring one of those let the server
# start successfully with the error only surfacing later, from a real query.

def test_check_api_key_missing_env_exits_cleanly_without_traceback(monkeypatch, capsys):
    """A missing API key must produce a clean message + exit(1), not an
    unhandled MissingApiKeyError propagating as a raw traceback."""
    import click
    import typer
    from synthadoc.cli.serve import _check_api_key

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = _make_cfg("anthropic")

    with pytest.raises((click.exceptions.Exit, typer.Exit)) as exc_info:
        _check_api_key(cfg)

    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert "ANTHROPIC_API_KEY is not set" in captured.err
    assert "ERR-CFG-001" in captured.err


def test_check_api_key_missing_env_names_the_real_config_path(monkeypatch, capsys):
    """When cfg.config_path is known, the message must point at that real
    file (shortened to the wiki-dir-relative form) rather than a generic
    'config.toml' mention — and must NOT leak the full absolute path, which
    would expose the user's home directory and OS username."""
    import click
    import typer
    from synthadoc.cli.serve import _check_api_key

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = _make_cfg("anthropic")
    cfg.config_path = Path("/Users/paulchen/wikis/history-of-computing/.synthadoc/config.toml")

    with pytest.raises((click.exceptions.Exit, typer.Exit)):
        _check_api_key(cfg)

    captured = capsys.readouterr()
    assert "see history-of-computing/.synthadoc/config.toml's [agents] section" in captured.err
    assert "/Users/paulchen" not in captured.err


def test_check_api_key_present_env_does_not_raise(monkeypatch):
    """A present API key must not raise anything."""
    from synthadoc.cli.serve import _check_api_key

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    _check_api_key(_make_cfg("anthropic"))  # must not raise


def test_check_api_key_cli_provider_skips_check(monkeypatch):
    """CLI/local providers (claude-code, opencode, ollama) need no API key."""
    from synthadoc.cli.serve import _check_api_key

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _check_api_key(_make_cfg("ollama"))  # must not raise


@pytest.mark.parametrize("provider,env_var", [
    ("minimax", "MINIMAX_API_KEY"),
    ("deepseek", "DEEPSEEK_API_KEY"),
])
def test_check_api_key_covers_minimax_and_deepseek(monkeypatch, capsys, provider, env_var):
    """Regression test: these two providers were completely missing from the
    old if/elif list, so a missing key silently passed startup and only
    surfaced later from a real query — reported directly against minimax."""
    import click
    import typer
    from synthadoc.cli.serve import _check_api_key

    monkeypatch.delenv(env_var, raising=False)

    with pytest.raises((click.exceptions.Exit, typer.Exit)) as exc_info:
        _check_api_key(_make_cfg(provider))

    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert f"{env_var} is not set" in captured.err


def test_check_api_key_covers_kimi(monkeypatch, capsys):
    import click
    import typer
    from synthadoc.config import Config, AgentConfig, AgentsConfig
    from synthadoc.cli.serve import _check_api_key

    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    cfg = Config(agents=AgentsConfig(default=AgentConfig(provider="kimi", model="kimi-k3")))

    with pytest.raises((click.exceptions.Exit, typer.Exit)) as exc_info:
        _check_api_key(cfg)

    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert "KIMI_API_KEY" in captured.err


def test_check_api_key_covers_qwen_dashscope_model(monkeypatch, capsys):
    """Qwen only needs a key for DashScope-pattern model names (e.g.
    'qwen-plus'); a non-DashScope name routes to local Ollama instead, so
    this specifically uses a DashScope-pattern model to exercise the key
    check — a plain model name would silently skip it (correctly)."""
    import click
    import typer
    from synthadoc.config import Config, AgentConfig, AgentsConfig
    from synthadoc.cli.serve import _check_api_key

    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    cfg = Config(agents=AgentsConfig(default=AgentConfig(provider="qwen", model="qwen-plus")))

    with pytest.raises((click.exceptions.Exit, typer.Exit)) as exc_info:
        _check_api_key(cfg)

    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert "QWEN_API_KEY" in captured.err


def test_check_api_key_missing_cli_binary_exits_cleanly(monkeypatch, capsys):
    """claude-code/opencode check the binary is on PATH at construction time
    (EnvironmentError, not MissingApiKeyError) — also a known, actionable,
    startup-time problem, so it must exit cleanly too, not traceback."""
    import click
    import typer
    from synthadoc.cli.serve import _check_api_key

    monkeypatch.setattr("synthadoc.providers.coding_tool._find_binary", lambda name: None)
    cfg = _make_cfg("claude-code")

    with pytest.raises((click.exceptions.Exit, typer.Exit)) as exc_info:
        _check_api_key(cfg)

    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert "ERR-PROV-003" in captured.err
    assert "not found in PATH" in captured.err
