# tests/test_cli_run.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for synthadoc/cli/run.py — the 'synthadoc run' subcommand."""
from __future__ import annotations

import re
import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock


def _strip_ansi(text: str) -> str:
    """Remove ANSI colour/style escape sequences from *text*.

    Older versions of rich (Python 3.11 CI) render option names with colour
    codes inserted between the two leading dashes, e.g. ``-\\x1b[...]-slug``,
    which breaks plain substring checks.  Stripping ANSI codes first makes
    the assertions version-agnostic.
    """
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_run_command_exists_on_app():
    """synthadoc run is a registered typer command."""
    from synthadoc.cli.main import app
    runner = CliRunner()
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "contradiction-resolver" in result.output.lower()


def test_run_contradiction_resolver_help():
    """contradiction-resolver subcommand shows help without error.

    The output is stripped of ANSI escape codes before asserting: older rich
    versions insert colour codes between the leading dashes of each option name
    (``-\\x1b[...]-slug``), which breaks a plain ``in`` check.
    """
    from synthadoc.cli.main import app
    runner = CliRunner()
    result = runner.invoke(app, ["run", "contradiction-resolver", "--help"])
    assert result.exit_code == 0
    clean = _strip_ansi(result.output)
    assert "--slug" in clean
    assert "--type" in clean


def test_run_contradiction_resolver_calls_stream_query():
    """contradiction-resolver invocation calls _stream_query with the right question."""
    from synthadoc.cli.main import app
    runner = CliRunner()

    with patch("synthadoc.cli.run._stream_query") as mock_sq, \
         patch("synthadoc.cli.run._resolve_wiki", return_value="test-wiki"):
        result = runner.invoke(app, [
            "run", "contradiction-resolver",
            "-w", "test-wiki",
        ])
    assert mock_sq.called
    call_args = mock_sq.call_args
    question = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("question", "")
    assert "contradiction" in question.lower()


def test_run_contradiction_resolver_with_slug():
    """--slug flag is forwarded in the query string."""
    from synthadoc.cli.main import app
    runner = CliRunner()

    with patch("synthadoc.cli.run._stream_query") as mock_sq, \
         patch("synthadoc.cli.run._resolve_wiki", return_value="test-wiki"):
        runner.invoke(app, [
            "run", "contradiction-resolver",
            "--slug", "alan-turing",
            "-w", "test-wiki",
        ])

    assert mock_sq.called
    call_args = mock_sq.call_args
    question = call_args[0][1] if len(call_args[0]) > 1 else ""
    assert "alan-turing" in question


def test_run_contradiction_resolver_with_type_gate():
    """--type gate flag is forwarded in the query string."""
    from synthadoc.cli.main import app
    runner = CliRunner()

    with patch("synthadoc.cli.run._stream_query") as mock_sq, \
         patch("synthadoc.cli.run._resolve_wiki", return_value="test-wiki"):
        runner.invoke(app, [
            "run", "contradiction-resolver",
            "--type", "gate",
            "-w", "test-wiki",
        ])

    assert mock_sq.called
    call_args = mock_sq.call_args
    question = call_args[0][1] if len(call_args[0]) > 1 else ""
    assert "gate" in question


def test_workflow_re_matches_contradiction_resolver():
    """_WORKFLOW_RE in query.py must route contradiction resolver to long timeout."""
    import synthadoc.cli.query as q
    assert q._WORKFLOW_RE.search("run contradiction resolver")
    assert q._WORKFLOW_RE.search("fix contradicted pages")
    assert q._WORKFLOW_RE.search("resolve contradictions")
