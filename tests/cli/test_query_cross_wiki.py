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


def test_cross_wiki_blocking_gap_shows_callout():
    """When cross-wiki blocking query returns knowledge_gap=True, [!tip] callout must appear."""
    from synthadoc.cli.main import app
    response = {
        "answer": "No relevant info found.",
        "citations": [],
        "knowledge_gap": True,
        "suggested_searches": ["canadian real estate", "housing market stats"],
        "routing_warning": "",
        "cross_wiki_searched": ["wiki-a"],
        "cross_wiki_offline": [],
        "cross_wiki_skipped": False,
        "cross_wiki_skip_reason": "",
    }
    with patch("synthadoc.cli.query.post", return_value=response):
        result = runner.invoke(app, ["query", "-w", "finance", "--cross-wiki", "--no-stream", "housing market"])
    assert "[!tip] Knowledge Gap Detected" in result.output
    assert "canadian real estate" in result.output
    assert "-w finance" in result.output


def test_cross_wiki_stream_gap_shows_callout():
    """When cross-wiki streaming query emits gap event, [!tip] callout must appear."""
    from synthadoc.cli.main import app
    events = [
        ("token", {"text": "No details found across wikis."}),
        ("gap", {"gap": True, "suggested_searches": ["quantum key distribution"]}),
        ("done", {"knowledge_gap": True, "cross_wiki_offline": [], "cross_wiki_skipped": False, "cross_wiki_skip_reason": ""}),
    ]
    with patch("synthadoc.cli.query.get_stream", return_value=iter(events)):
        result = runner.invoke(app, ["query", "-w", "tech", "--cross-wiki", "quantum encryption"])
    assert "[!tip] Knowledge Gap Detected" in result.output
    assert "quantum key distribution" in result.output
    assert "-w tech" in result.output


def test_cross_wiki_stream_no_gap_does_not_show_callout():
    """When cross-wiki streaming query has no gap, no callout appears."""
    from synthadoc.cli.main import app
    events = [
        ("token", {"text": "Verified cross-wiki answer."}),
        ("citations", {"citations": ["tech::qkd"]}),
        ("done", {"knowledge_gap": False, "cross_wiki_offline": [], "cross_wiki_skipped": False, "cross_wiki_skip_reason": ""}),
    ]
    with patch("synthadoc.cli.query.get_stream", return_value=iter(events)):
        result = runner.invoke(app, ["query", "-w", "tech", "--cross-wiki", "quantum encryption"])
    assert "Verified cross-wiki answer." in result.output
    assert "Knowledge Gap" not in result.output


def test_cross_wiki_stream_forwards_no_cache():
    """Passing --no-cache with --cross-wiki must include no_cache='true' in get_stream params."""
    from synthadoc.cli.main import app
    captured_kw = {}

    def _mock_get_stream(wiki, path, timeout=None, **params):
        captured_kw.update(params)
        return iter([("token", {"text": "Answer"})])

    with patch("synthadoc.cli.query.get_stream", side_effect=_mock_get_stream):
        runner.invoke(app, ["query", "-w", "finance", "--cross-wiki", "--no-cache", "what is leverage?"])
    assert captured_kw.get("no_cache") == "true"
