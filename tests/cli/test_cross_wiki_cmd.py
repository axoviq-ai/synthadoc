# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from typer.testing import CliRunner
from unittest.mock import patch

runner = CliRunner()

def test_cross_wiki_routing_init_creates_file(tmp_path):
    from synthadoc.cli.main import app
    registry = {"a": {"path": "/x", "port": 7070, "purpose_summary": "finance"}}
    routing_path = tmp_path / "CROSS_WIKI_ROUTING.md"
    # Patch the shared constant in _wiki (single source of truth) — not a local _ROUTING_PATH
    with patch("synthadoc.cli.cross_wiki.read_registry_all", return_value=registry):
        with patch("synthadoc.cli.cross_wiki.CROSS_WIKI_ROUTING_PATH", routing_path):
            result = runner.invoke(app, ["cross-wiki", "routing", "init"])
    assert routing_path.exists()
    content = routing_path.read_text()
    assert "## default" in content

def test_cross_wiki_routing_show_prints_content(tmp_path):
    from synthadoc.cli.main import app
    routing_path = tmp_path / "CROSS_WIKI_ROUTING.md"
    routing_path.write_text("## default\nwikis: a\nkeywords:\n")
    with patch("synthadoc.cli.cross_wiki.CROSS_WIKI_ROUTING_PATH", routing_path):
        result = runner.invoke(app, ["cross-wiki", "routing", "show"])
    assert "default" in result.output

def test_cross_wiki_status_delegates_to_status_all():
    from synthadoc.cli.main import app
    with patch("synthadoc.cli.cross_wiki.render_status_all") as mock_status:
        runner.invoke(app, ["cross-wiki", "status"])
    mock_status.assert_called_once()
