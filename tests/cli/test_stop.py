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
