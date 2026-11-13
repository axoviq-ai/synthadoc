# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock

runner = CliRunner()


def test_serve_all_spawns_each_wiki():
    from synthadoc.cli.main import app
    registry = {
        "finance": {"port": 7070, "path": "/wikis/finance"},
        "legal":   {"port": 7071, "path": "/wikis/legal"},
    }
    with patch("synthadoc.cli.serve.read_registry_all", return_value=registry):
        with patch("synthadoc.cli._wiki.probe_port", return_value=False):  # shared helper
            with patch("synthadoc.cli.serve._spawn_background_for_path", return_value=(4242, 7070)) as mock_spawn,                  patch("synthadoc.cli.serve._wait_for_health", return_value=True),                  patch("synthadoc.cli.serve.system_memory_mb", return_value=(64000.0, 8000.0)),                  patch("synthadoc.cli.serve.process_memory_mb", return_value=300.0):
                result = runner.invoke(app, ["serve", "--all", "--background"])
    assert mock_spawn.call_count == 2


def test_serve_all_skips_already_running():
    from synthadoc.cli.main import app
    registry = {"finance": {"port": 7070, "path": "/wikis/finance"}}
    with patch("synthadoc.cli.serve.read_registry_all", return_value=registry):
        with patch("synthadoc.cli._wiki.probe_port", return_value=True):  # shared helper
            with patch("synthadoc.cli.serve._spawn_background_for_path") as mock_spawn:
                runner.invoke(app, ["serve", "--all", "--background"])
    mock_spawn.assert_not_called()
