# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from typer.testing import CliRunner
from unittest.mock import patch
from synthadoc.cli.main import app

runner = CliRunner()


def _mock_get(response: dict):
    """Patch synthadoc.cli._http.get to return response."""
    return patch("synthadoc.cli.query.get", return_value=response)


def _capture_get(response: dict):
    """Patch get and capture the kwargs it was called with."""
    from unittest.mock import MagicMock
    mock = MagicMock(return_value=response)
    return patch("synthadoc.cli.query.get", mock), mock


def test_query_cli_no_gap_shows_only_answer():
    """When knowledge_gap=False, no callout must appear in output."""
    with _mock_get({"answer": "AI is great.", "citations": ["ai-page"],
                    "knowledge_gap": False, "suggested_searches": []}):
        result = runner.invoke(app, ["query", "What is AI?", "-w", ".", "--no-stream"])
    assert "AI is great." in result.output
    assert "Knowledge Gap" not in result.output


def test_query_cli_gap_shows_callout():
    """When knowledge_gap=True, the [!tip] callout must appear."""
    with _mock_get({
        "answer": "No info found.",
        "citations": [],
        "knowledge_gap": True,
        "suggested_searches": ["canadian spring vegetables", "frost dates Canada"],
    }):
        result = runner.invoke(app, ["query", "Vegetables in Canada?", "-w", "my-wiki", "--no-stream"])
    assert "[!tip] Knowledge Gap Detected" in result.output
    assert "canadian spring vegetables" in result.output
    assert "frost dates Canada" in result.output


def test_query_cli_gap_includes_wiki_name_in_terminal_commands():
    """Terminal ingest commands must include -w <wiki> from the CLI flag."""
    with _mock_get({
        "answer": "No info.",
        "citations": [],
        "knowledge_gap": True,
        "suggested_searches": ["vegetable planting guide"],
    }):
        result = runner.invoke(app, ["query", "Vegetables?", "-w", "yard-gardening-in-canada", "--no-stream"])
    assert '-w yard-gardening-in-canada' in result.output


def test_query_cli_gap_includes_command_palette_hint():
    """Callout must mention Obsidian Command Palette when gap detected."""
    with _mock_get({
        "answer": "No info.",
        "citations": [],
        "knowledge_gap": True,
        "suggested_searches": ["test query"],
    }):
        result = runner.invoke(app, ["query", "Something?", "-w", "my-wiki", "--no-stream"])
    assert "Command Palette" in result.output
    assert "Synthadoc: Ingest..." in result.output


def test_query_cli_default_timeout_is_60():
    """Without --timeout, get() must be called with timeout=60."""
    ctx, mock = _capture_get({"answer": "ok", "citations": [], "knowledge_gap": False})
    with ctx:
        runner.invoke(app, ["query", "What is AI?", "-w", ".", "--no-stream"])
    _, kwargs = mock.call_args
    assert kwargs.get("timeout") == 60


def test_query_cli_custom_timeout_forwarded():
    """--timeout N must be forwarded as both the HTTP timeout and timeout_seconds query param."""
    ctx, mock = _capture_get({"answer": "ok", "citations": [], "knowledge_gap": False})
    with ctx:
        runner.invoke(app, ["query", "What is AI?", "-w", ".", "--timeout", "120", "--no-stream"])
    _, kwargs = mock.call_args
    assert kwargs.get("timeout") == 120
    assert kwargs.get("timeout_seconds") == 120


def test_query_cli_gap_includes_requery_hint():
    """Callout must tell user to re-run their query after ingesting."""
    with _mock_get({
        "answer": "No info.",
        "citations": [],
        "knowledge_gap": True,
        "suggested_searches": ["test"],
    }):
        result = runner.invoke(app, ["query", "Something?", "-w", "my-wiki", "--no-stream"])
    assert "re-run" in result.output.lower() or "re-run" in result.output


def test_query_cmd_streams_by_default(tmp_wiki, monkeypatch):
    """synthadoc query uses SSE streaming by default."""
    called = []
    def _fake_stream(wiki, question, no_cache, timeout):
        called.append(True)
    monkeypatch.setattr("synthadoc.cli.query._stream_query", _fake_stream)
    result = runner.invoke(app, ["query", "What is AI?", "-w", "test"])
    assert called, "_stream_query should have been called"


def test_query_cmd_no_stream_uses_blocking(tmp_wiki, monkeypatch):
    """synthadoc query --no-stream uses the blocking GET /query endpoint."""
    called_paths = []
    def _fake_get(wiki, path, **kw):
        called_paths.append(path)
        return {"answer": "ok", "citations": [], "knowledge_gap": False, "suggested_searches": []}
    monkeypatch.setattr("synthadoc.cli.query.get", _fake_get)
    result = runner.invoke(app, ["query", "What is AI?", "-w", "test", "--no-stream"])
    assert any("/query" in p for p in called_paths), "blocking /query endpoint should have been called"


def test_query_cmd_no_stream_no_cache_flag_forwarded(monkeypatch):
    """--no-stream --no-cache must forward no_cache=true to blocking get()."""
    received_kwargs = {}

    def _fake_get(wiki, path, **kw):
        received_kwargs.update(kw)
        return {"answer": "ok", "citations": [], "knowledge_gap": False, "suggested_searches": []}

    monkeypatch.setattr("synthadoc.cli.query.get", _fake_get)
    runner.invoke(app, ["query", "What is AI?", "-w", "test", "--no-stream", "--no-cache"])
    assert received_kwargs.get("no_cache") == "true"


def test_stream_query_prints_tokens(monkeypatch):
    """_stream_query must print token text as it arrives."""
    events = [
        ("token", {"text": "Hello"}),
        ("token", {"text": " world"}),
        ("done", {"next_hints": []}),
    ]
    monkeypatch.setattr("synthadoc.cli.query.get_stream", lambda *a, **kw: iter(events))
    from synthadoc.cli.query import _stream_query
    output = []
    monkeypatch.setattr("typer.echo", lambda msg, **kw: output.append(str(msg)))
    _stream_query("my-wiki", "Hello?", no_cache=False, timeout=60)
    combined = "".join(output)
    assert "Hello" in combined
    assert "world" in combined


def test_stream_query_shows_citations(monkeypatch):
    """_stream_query must print sources line when citations arrive."""
    events = [
        ("citations", {"citations": ["page-1", "page-2"]}),
        ("done", {"next_hints": []}),
    ]
    monkeypatch.setattr("synthadoc.cli.query.get_stream", lambda *a, **kw: iter(events))
    from synthadoc.cli.query import _stream_query
    output = []
    monkeypatch.setattr("typer.echo", lambda msg, **kw: output.append(str(msg)))
    _stream_query("my-wiki", "Question?", no_cache=False, timeout=60)
    combined = "".join(output)
    assert "[[page-1]]" in combined
    assert "[[page-2]]" in combined


def test_stream_query_shows_knowledge_gap(monkeypatch):
    """_stream_query must show gap callout when gap event arrives."""
    events = [
        ("gap", {"suggested_searches": ["topic A", "topic B"]}),
        ("done", {"next_hints": []}),
    ]
    monkeypatch.setattr("synthadoc.cli.query.get_stream", lambda *a, **kw: iter(events))
    from synthadoc.cli.query import _stream_query
    output = []
    monkeypatch.setattr("typer.echo", lambda msg, **kw: output.append(str(msg)))
    _stream_query("my-wiki", "Question?", no_cache=False, timeout=60)
    combined = "".join(output)
    assert "Knowledge Gap" in combined
    assert "topic A" in combined


def test_stream_query_error_event_stops_stream(monkeypatch):
    """_stream_query must print error and return early on error event."""
    events = [
        ("error", {"message": "LLM timeout"}),
        ("token", {"text": "should not appear"}),
    ]
    monkeypatch.setattr("synthadoc.cli.query.get_stream", lambda *a, **kw: iter(events))
    from synthadoc.cli.query import _stream_query
    err_output = []
    output = []
    monkeypatch.setattr(
        "typer.echo",
        lambda msg, err=False, **kw: err_output.append(str(msg)) if err else output.append(str(msg)),
    )
    _stream_query("my-wiki", "Question?", no_cache=False, timeout=60)
    combined_err = "".join(err_output)
    combined_out = "".join(output)
    assert "LLM timeout" in combined_err
    assert "should not appear" not in combined_out


def test_stream_query_timeout_error_shows_cli_tip(monkeypatch):
    """When the server returns a 'timed out' error event, the CLI must print
    a tip about --timeout and CPU-only inference (not 'Settings gear')."""
    events = [
        ("error", {"message": "Query timed out after 300s."}),
    ]
    monkeypatch.setattr("synthadoc.cli.query.get_stream", lambda *a, **kw: iter(events))
    from synthadoc.cli.query import _stream_query
    err_output = []
    monkeypatch.setattr(
        "typer.echo",
        lambda msg, err=False, **kw: err_output.append(str(msg)) if err else None,
    )
    _stream_query("my-wiki", "Question?", no_cache=False, timeout=300)
    combined_err = "".join(err_output)
    assert "timed out after 300s" in combined_err
    assert "--timeout 600" in combined_err
    assert "CPU" in combined_err
    assert "Settings" not in combined_err


def test_stream_query_exit_from_get_stream_propagates(monkeypatch):
    """If get_stream raises typer.Exit (e.g. from _timeout_error), _stream_query
    must NOT print 'stream interrupted' — it must re-raise so the exit is clean."""
    import typer as _typer

    def _raise_exit(*a, **kw):
        raise _typer.Exit(1)

    monkeypatch.setattr("synthadoc.cli.query.get_stream", _raise_exit)
    from synthadoc.cli.query import _stream_query
    interrupted_msgs = []
    monkeypatch.setattr(
        "typer.echo",
        lambda msg, err=False, **kw: interrupted_msgs.append(str(msg)),
    )
    with pytest.raises(_typer.Exit):
        _stream_query("my-wiki", "Question?", no_cache=False, timeout=60)
    assert not any("stream interrupted" in m for m in interrupted_msgs)


def test_stream_query_unexpected_exception_prints_interrupted(monkeypatch):
    """Unexpected exceptions during streaming must print 'stream interrupted' and not re-raise."""
    def _raise_unexpected(*a, **kw):
        raise RuntimeError("connection dropped")

    monkeypatch.setattr("synthadoc.cli.query.get_stream", _raise_unexpected)
    from synthadoc.cli.query import _stream_query
    err_msgs = []
    monkeypatch.setattr(
        "typer.echo",
        lambda msg, err=False, **kw: err_msgs.append(str(msg)) if err else None,
    )
    _stream_query("my-wiki", "Question?", no_cache=False, timeout=60)
    combined = "".join(err_msgs)
    assert "stream interrupted" in combined
    assert "RuntimeError" in combined


def test_stream_query_no_cache_flag_passed(monkeypatch):
    """_stream_query must pass no_cache=true param when no_cache=True."""
    received_params = {}

    def _fake_stream(wiki, path, timeout, **params):
        received_params.update(params)
        return iter([])

    monkeypatch.setattr("synthadoc.cli.query.get_stream", _fake_stream)
    from synthadoc.cli.query import _stream_query
    _stream_query("my-wiki", "Q?", no_cache=True, timeout=60)
    assert received_params.get("no_cache") == "true"


def test_stream_query_forwards_timeout_seconds_to_server(monkeypatch):
    """--timeout N must be forwarded as timeout_seconds=N query param so the server
    honours the user's intent rather than defaulting to 60s internally."""
    received_params = {}

    def _fake_stream(wiki, path, timeout, **params):
        received_params.update(params)
        return iter([])

    monkeypatch.setattr("synthadoc.cli.query.get_stream", _fake_stream)
    from synthadoc.cli.query import _stream_query
    _stream_query("my-wiki", "Q?", no_cache=False, timeout=180)
    assert received_params.get("timeout_seconds") == 180


def test_no_stream_query_forwards_timeout_seconds_to_server():
    """--no-stream path must also forward timeout_seconds so the blocking endpoint
    uses the user-supplied timeout rather than the server default of 60s."""
    received_params = {}

    def _fake_get(wiki, path, timeout, **params):
        received_params.update(params)
        return {"answer": "ok", "citations": [], "knowledge_gap": False}

    from unittest.mock import patch
    with patch("synthadoc.cli.query.get", side_effect=_fake_get):
        runner.invoke(app, ["query", "Q?", "-w", "my-wiki", "--timeout", "180", "--no-stream"])
    assert received_params.get("timeout_seconds") == 180
