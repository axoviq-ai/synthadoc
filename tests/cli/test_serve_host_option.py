# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for serve --host option."""
from __future__ import annotations
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from synthadoc.cli.main import app

runner = CliRunner()


def _make_cfg(host: str = "127.0.0.1", port: int = 7070):
    from synthadoc.config import Config, AgentConfig, AgentsConfig, ServerConfig
    return Config(
        server=ServerConfig(host=host, port=port),
        agents=AgentsConfig(default=AgentConfig(provider="anthropic", model="claude-opus-4-6")),
    )



_REGISTERED = {".": {"path": ".", "port": 7070}}


def test_host_option_accepted():
    """--host 0.0.0.0 must be accepted without 'No such option' error."""
    cfg = _make_cfg()
    with patch("synthadoc.cli._wiki.resolve_wiki", return_value="."), \
         patch("synthadoc.cli.serve.resolve_wiki_path", return_value=MagicMock()), \
         patch("synthadoc.config.load_config", return_value=cfg), \
         patch("synthadoc.cli.serve.read_registry_all", return_value=_REGISTERED), \
         patch("synthadoc.cli.serve._check_wiki"), \
         patch("synthadoc.cli.serve._check_port"), \
         patch("synthadoc.cli.serve._check_network"), \
         patch("synthadoc.cli.serve._sync_registry_port"), \
         patch("synthadoc.cli.serve._sync_plugin_config"), \
         patch("synthadoc.core.logging_config.setup_logging"), \
         patch("synthadoc.providers._require_env"), \
         patch("synthadoc.integration.http_server.create_app", return_value=MagicMock()), \
         patch("uvicorn.Config", return_value=MagicMock()), \
         patch("uvicorn.Server", return_value=MagicMock()):
        result = runner.invoke(app, ["serve", "-w", ".", "--host", "0.0.0.0", "--http-only"])
    assert "No such option" not in (result.output or ""), result.output
    assert result.exit_code != 2, result.output


def test_host_option_overrides_config():
    """--host value must reach uvicorn.Config as the host kwarg."""
    cfg = _make_cfg(host="127.0.0.1")
    with patch("synthadoc.cli._wiki.resolve_wiki", return_value="."), \
         patch("synthadoc.cli.serve.resolve_wiki_path", return_value=MagicMock()), \
         patch("synthadoc.config.load_config", return_value=cfg), \
         patch("synthadoc.cli.serve.read_registry_all", return_value=_REGISTERED), \
         patch("synthadoc.cli.serve._check_wiki"), \
         patch("synthadoc.cli.serve._check_port"), \
         patch("synthadoc.cli.serve._check_network"), \
         patch("synthadoc.cli.serve._sync_registry_port"), \
         patch("synthadoc.cli.serve._sync_plugin_config"), \
         patch("synthadoc.core.logging_config.setup_logging"), \
         patch("synthadoc.providers._require_env"), \
         patch("synthadoc.integration.http_server.create_app", return_value=MagicMock()), \
         patch("uvicorn.Config", return_value=MagicMock()) as mock_cfg_cls, \
         patch("uvicorn.Server", return_value=MagicMock()):
        runner.invoke(app, ["serve", "-w", ".", "--host", "0.0.0.0", "--http-only"])
    assert mock_cfg_cls.called, "uvicorn.Config was not called"
    call_kwargs = mock_cfg_cls.call_args[1]
    assert call_kwargs.get("host") == "0.0.0.0", \
        f"Expected host='0.0.0.0', got: {call_kwargs}"


def test_no_host_option_uses_config():
    """When --host is omitted, cfg.server.host must reach uvicorn.Config unchanged."""
    cfg = _make_cfg(host="127.0.0.1")
    with patch("synthadoc.cli._wiki.resolve_wiki", return_value="."), \
         patch("synthadoc.cli.serve.resolve_wiki_path", return_value=MagicMock()), \
         patch("synthadoc.config.load_config", return_value=cfg), \
         patch("synthadoc.cli.serve.read_registry_all", return_value=_REGISTERED), \
         patch("synthadoc.cli.serve._check_wiki"), \
         patch("synthadoc.cli.serve._check_port"), \
         patch("synthadoc.cli.serve._check_network"), \
         patch("synthadoc.cli.serve._sync_registry_port"), \
         patch("synthadoc.cli.serve._sync_plugin_config"), \
         patch("synthadoc.core.logging_config.setup_logging"), \
         patch("synthadoc.providers._require_env"), \
         patch("synthadoc.integration.http_server.create_app", return_value=MagicMock()), \
         patch("uvicorn.Config", return_value=MagicMock()) as mock_cfg_cls, \
         patch("uvicorn.Server", return_value=MagicMock()):
        runner.invoke(app, ["serve", "-w", ".", "--http-only"])
    assert mock_cfg_cls.called, "uvicorn.Config was not called"
    call_kwargs = mock_cfg_cls.call_args[1]
    assert call_kwargs.get("host") == "127.0.0.1", \
        f"Expected host='127.0.0.1', got: {call_kwargs}"


def test_serve_allows_path_wiki_without_registry():
    """serve must not raise ERR-WIKI-006 when wiki is a filesystem path (Docker -w /wiki)."""
    cfg = _make_cfg()
    with patch("synthadoc.cli._wiki.resolve_wiki", return_value="/wiki"), \
         patch("synthadoc.cli.serve.resolve_wiki_path", return_value=MagicMock()), \
         patch("synthadoc.config.load_config", return_value=cfg), \
         patch("synthadoc.cli.serve.read_registry_all", return_value={}), \
         patch("synthadoc.cli.serve._check_wiki"), \
         patch("synthadoc.cli.serve._check_port"), \
         patch("synthadoc.cli.serve._check_network"), \
         patch("synthadoc.cli.serve._sync_registry_port"), \
         patch("synthadoc.cli.serve._sync_plugin_config"), \
         patch("synthadoc.core.logging_config.setup_logging"), \
         patch("synthadoc.providers._require_env"), \
         patch("synthadoc.integration.http_server.create_app", return_value=MagicMock()), \
         patch("uvicorn.Config", return_value=MagicMock()), \
         patch("uvicorn.Server", return_value=MagicMock()):
        result = runner.invoke(app, ["serve", "-w", "/wiki", "--http-only"])
    assert "ERR-WIKI-006" not in (result.output or ""), \
        f"Path-based wiki should not require registry, got: {result.output}"
    assert "not registered" not in (result.output or "").lower(), \
        f"Path-based wiki should not require registry, got: {result.output}"


def test_serve_fails_when_wiki_not_registered():
    """serve must exit non-zero with ERR-WIKI-006 when the wiki is not registered."""
    cfg = _make_cfg()
    with patch("synthadoc.cli._wiki.resolve_wiki", return_value="unregistered-wiki"), \
         patch("synthadoc.cli.serve.resolve_wiki_path", return_value=MagicMock()), \
         patch("synthadoc.config.load_config", return_value=cfg), \
         patch("synthadoc.cli.serve.read_registry_all", return_value={}):
        result = runner.invoke(app, ["serve", "-w", "unregistered-wiki", "--http-only"])
    assert result.exit_code != 0, "Expected non-zero exit for unregistered wiki"
    assert "ERR-WIKI-006" in (result.output or "") or "not registered" in (result.output or "").lower(), \
        f"Expected registration error, got: {result.output}"
