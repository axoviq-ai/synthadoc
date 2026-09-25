# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from typer.testing import CliRunner
from unittest.mock import patch
import httpx

runner = CliRunner()

def test_status_all_prints_table():
    from synthadoc.cli.main import app
    registry = {
        "finance": {"port": 7070, "path": "/x"},
        "legal":   {"port": 7071, "path": "/y"},
    }
    def fake_get(url, **kwargs):
        r = httpx.Response(200, json={"wiki": "finance", "pages": 10, "jobs_pending": 0, "jobs_total": 0})
        return r
    with patch("synthadoc.cli.status.read_registry_all", return_value=registry):
        with patch("httpx.get", side_effect=fake_get):
            result = runner.invoke(app, ["status", "--all"])
    assert "finance" in result.output
    assert "legal" in result.output

def test_status_all_shows_stopped_for_offline_wiki():
    from synthadoc.cli.main import app
    registry = {"finance": {"port": 7070, "path": "/x"}}
    with patch("synthadoc.cli.status.read_registry_all", return_value=registry):
        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            result = runner.invoke(app, ["status", "--all"])
    assert "stopped" in result.output.lower() or "finance" in result.output


def test_port_from_config_reads_toml(tmp_path):
    """_port_from_config returns port from config.toml when registry lacks it."""
    from synthadoc.cli.status import _port_from_config
    cfg_dir = tmp_path / ".synthadoc"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text("[server]\nport = 7099\n")
    assert _port_from_config(str(tmp_path), "any-name") == 7099


def test_port_from_config_returns_none_when_missing(tmp_path):
    """_port_from_config returns None when no config.toml exists."""
    from synthadoc.cli.status import _port_from_config
    assert _port_from_config(str(tmp_path), "any-name") is None


def test_port_from_config_returns_none_on_malformed_toml(tmp_path):
    """_port_from_config returns None when config.toml is unreadable."""
    from synthadoc.cli.status import _port_from_config
    cfg_dir = tmp_path / ".synthadoc"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text("not valid toml ][[[")
    assert _port_from_config(str(tmp_path), "any-name") is None


def test_status_all_uses_config_fallback_when_port_missing(tmp_path):
    """render_status_all shows port read from config.toml when registry entry lacks port."""
    from synthadoc.cli.main import app
    cfg_dir = tmp_path / ".synthadoc"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text("[server]\nport = 7088\n")
    registry = {"garden-wiki": {"path": str(tmp_path)}}  # no 'port' key
    with patch("synthadoc.cli.status.read_registry_all", return_value=registry):
        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            result = runner.invoke(app, ["status", "--all"])
    assert "7088" in result.output
    assert "?" not in result.output
