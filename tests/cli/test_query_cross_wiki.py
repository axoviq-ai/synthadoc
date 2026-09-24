# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock

runner = CliRunner()


def test_cross_wiki_flag_calls_cross_wiki_endpoint():
    from synthadoc.cli.main import app
    response = {
        "answer": "Cross-wiki answer", "citations": ["wiki-a::Page1"],
        "knowledge_gap": False, "routing_warning": "",
        "cross_wiki_searched": ["wiki-a", "wiki-b"], "cross_wiki_offline": [],
        "cross_wiki_skipped": False, "cross_wiki_skip_reason": "",
    }
    with patch("synthadoc.cli.query.post", return_value=response) as mock_post:
        result = runner.invoke(app, ["query", "-w", "finance", "--cross-wiki", "--no-stream", "what is leverage?"])
    assert mock_post.call_args[0][1] == "/cross-wiki/query"
    assert "Cross-wiki answer" in result.output


def test_cross_wiki_offline_warning_shown():
    from synthadoc.cli.main import app
    response = {
        "answer": "Partial answer", "citations": [],
        "knowledge_gap": False, "routing_warning": "",
        "cross_wiki_searched": ["wiki-a", "wiki-b"], "cross_wiki_offline": ["wiki-b"],
        "cross_wiki_skipped": False, "cross_wiki_skip_reason": "",
    }
    with patch("synthadoc.cli.query.post", return_value=response):
        result = runner.invoke(app, ["query", "-w", "finance", "--cross-wiki", "--no-stream", "anything"])
    assert "wiki-b" in result.output
    assert "offline" in result.output.lower()


def test_cross_wiki_skipped_footnote_shown():
    from synthadoc.cli.main import app
    response = {
        "answer": "Lint started", "citations": [],
        "knowledge_gap": False, "routing_warning": "",
        "cross_wiki_searched": [], "cross_wiki_offline": [],
        "cross_wiki_skipped": True, "cross_wiki_skip_reason": "operation detected",
    }
    with patch("synthadoc.cli.query.post", return_value=response):
        result = runner.invoke(app, ["query", "-w", "finance", "--cross-wiki", "--no-stream", "run lint"])
    assert "operation" in result.output.lower() or "finance" in result.output.lower()
