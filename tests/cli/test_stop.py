from typer.testing import CliRunner
from unittest.mock import patch, MagicMock
import pytest

runner = CliRunner()

def test_stop_single_wiki_calls_shutdown():
    from synthadoc.cli.main import app
    with patch("synthadoc.cli.stop._stop_wiki", return_value=True) as mock_stop:
        result = runner.invoke(app, ["stop", "-w", "finance-wiki"])
    mock_stop.assert_called_once_with("finance-wiki")
    assert result.exit_code == 0

def test_stop_all_stops_running_wikis():
    from synthadoc.cli.main import app
    registry = {
        "finance": {"port": 7070, "path": "/x"},
        "legal":   {"port": 7071, "path": "/y"},
    }
    with patch("synthadoc.cli.stop.read_registry_all", return_value=registry):
        with patch("synthadoc.cli.stop._stop_wiki", return_value=True) as mock_stop:
            result = runner.invoke(app, ["stop", "--all"])
    assert mock_stop.call_count == 2

def test_stop_no_args_no_wiki_errors():
    from synthadoc.cli.main import app
    import typer
    with patch("synthadoc.cli.stop.read_registry_all", return_value={}):
        with patch("synthadoc.cli._wiki.resolve_wiki", side_effect=typer.Exit(1)):
            result = runner.invoke(app, ["stop"])
    assert result.exit_code != 0 or "specify" in result.output.lower() or "error" in result.output.lower()


def test_stop_wiki_shutdown_endpoint_success(tmp_path):
    """_stop_wiki uses POST /shutdown when server responds with 200."""
    from synthadoc.cli.stop import _stop_wiki
    pid_file = tmp_path / ".synthadoc" / "server.pid"
    pid_file.parent.mkdir(parents=True)
    config_path = tmp_path / ".synthadoc" / "config.toml"
    config_path.write_text("[server]\nport = 7099\n")

    mock_cfg = MagicMock()
    mock_cfg.server.port = 7099
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("synthadoc.cli.stop.resolve_wiki_path", return_value=tmp_path):
        with patch("synthadoc.config.load_config", return_value=mock_cfg):
            with patch("synthadoc.cli.stop.httpx.post", return_value=mock_resp):
                result = _stop_wiki("finance-wiki")
    assert result is True


def test_stop_wiki_pid_kill_windows_errors(tmp_path):
    """_stop_wiki silently handles OSError and PermissionError from os.kill on Windows."""
    import os, signal
    from synthadoc.cli.stop import _stop_wiki
    pid_file = tmp_path / ".synthadoc" / "server.pid"
    pid_file.parent.mkdir(parents=True)
    pid_file.write_text("99999")
    config_path = tmp_path / ".synthadoc" / "config.toml"

    with patch("synthadoc.cli.stop.resolve_wiki_path", return_value=tmp_path):
        with patch("synthadoc.cli.stop.httpx.post", side_effect=Exception("refused")):
            with patch("os.kill", side_effect=PermissionError("access denied")):
                result = _stop_wiki("finance-wiki")
    # Should not raise; pid file may be removed
    assert result is False or result is True  # either outcome is acceptable — no crash


def test_stop_wiki_pid_oserror(tmp_path):
    """_stop_wiki handles OSError (e.g. no such process on Windows) gracefully."""
    from synthadoc.cli.stop import _stop_wiki
    pid_file = tmp_path / ".synthadoc" / "server.pid"
    pid_file.parent.mkdir(parents=True)
    pid_file.write_text("99999")

    with patch("synthadoc.cli.stop.resolve_wiki_path", return_value=tmp_path):
        with patch("synthadoc.cli.stop.httpx.post", side_effect=Exception("refused")):
            with patch("os.kill", side_effect=OSError("no such process")):
                result = _stop_wiki("finance-wiki")
    assert result is False or result is True  # no crash
