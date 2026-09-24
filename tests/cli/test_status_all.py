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
