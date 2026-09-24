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
            with patch("synthadoc.cli.serve._spawn_background_for_path") as mock_spawn:
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
