# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import httpx
import pytest
import typer
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from synthadoc.cli.main import app

runner = CliRunner()


def _patch_server_url(url="http://127.0.0.1:7777"):
    return patch("synthadoc.cli._http.server_url", return_value=url)


def _patch_resolve_wiki():
    return patch("synthadoc.cli._wiki.resolve_wiki", return_value="my-wiki")


def _patch_httpx_get_ok():
    mock = MagicMock(return_value=MagicMock(status_code=200))
    return patch("synthadoc.cli.web.httpx.get", mock)


def test_web_cmd_no_browser_prints_url():
    """--no-browser must print URL without opening browser."""
    with _patch_resolve_wiki(), _patch_server_url(), _patch_httpx_get_ok():
        result = runner.invoke(app, ["web", "-w", "my-wiki", "--no-browser"])
    assert "http://127.0.0.1:7777/app" in result.output
    assert "(--no-browser" in result.output


def test_web_cmd_opens_browser_by_default():
    """Without --no-browser, webbrowser.open must be called."""
    opened = []
    with _patch_resolve_wiki(), _patch_server_url(), _patch_httpx_get_ok(), \
         patch("synthadoc.cli.web.webbrowser.open", side_effect=lambda u: opened.append(u)):
        runner.invoke(app, ["web", "-w", "my-wiki"])
    assert any("/app" in u for u in opened)


def test_web_cmd_port_from_config():
    """Port must come from the wiki config (server_url), not a CLI flag."""
    with _patch_resolve_wiki(), _patch_server_url("http://127.0.0.1:9090"), \
         _patch_httpx_get_ok():
        result = runner.invoke(app, ["web", "-w", "my-wiki", "--no-browser"])
    assert "9090" in result.output


def test_web_cmd_connect_error_exits():
    """ConnectError must exit with a helpful message (server not running)."""
    with _patch_resolve_wiki(), _patch_server_url(), \
         patch("synthadoc.cli.web.httpx.get", side_effect=httpx.ConnectError("refused")), \
         patch("synthadoc.cli._http._no_server", side_effect=typer.Exit(1)):
        result = runner.invoke(app, ["web", "-w", "my-wiki"])
    assert result.exit_code != 0


def test_web_cmd_request_error_proceeds():
    """Other RequestError (e.g. ReadTimeout) must NOT exit — server is running."""
    opened = []
    with _patch_resolve_wiki(), _patch_server_url(), \
         patch("synthadoc.cli.web.httpx.get", side_effect=httpx.ReadTimeout("timeout")), \
         patch("synthadoc.cli.web.webbrowser.open", side_effect=lambda u: opened.append(u)):
        result = runner.invoke(app, ["web", "-w", "my-wiki"])
    assert any("/app" in u for u in opened)
