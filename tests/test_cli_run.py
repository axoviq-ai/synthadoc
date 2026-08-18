# tests/test_cli_run.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for synthadoc/cli/workflow.py — the 'synthadoc workflow' subcommand group."""
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


# ── top-level 'workflow' command ──────────────────────────────────────────────

def test_workflow_command_exists_on_app():
    """synthadoc workflow is a registered typer command group."""
    from synthadoc.cli.main import app
    runner = CliRunner()
    result = runner.invoke(app, ["workflow", "--help"])
    assert result.exit_code == 0
    assert "run" in result.output.lower()


def test_workflow_run_subcommand_exists():
    """synthadoc workflow run lists contradiction-resolver."""
    from synthadoc.cli.main import app
    runner = CliRunner()
    result = runner.invoke(app, ["workflow", "run", "--help"])
    assert result.exit_code == 0
    assert "contradiction-resolver" in result.output.lower()


# ── contradiction-resolver help ───────────────────────────────────────────────

def test_workflow_run_contradiction_resolver_help():
    """contradiction-resolver subcommand shows --slug and --type without error.

    The output is stripped of ANSI escape codes before asserting: older rich
    versions insert colour codes between the leading dashes of each option name
    (``-\\x1b[...]-slug``), which breaks a plain ``in`` check.
    """
    from synthadoc.cli.main import app
    runner = CliRunner()
    result = runner.invoke(
        app, ["workflow", "run", "contradiction-resolver", "--help"]
    )
    assert result.exit_code == 0
    clean = _strip_ansi(result.output)
    assert "--slug" in clean
    assert "--type" in clean
    # New user-facing type names must appear in the help text
    assert "adversarial" in clean
    assert "source-conflict" in clean


# ── type translation (_TYPE_TO_SCOPE) ─────────────────────────────────────────

def test_type_to_scope_mapping():
    """_TYPE_TO_SCOPE translates user-facing names to internal agent tokens."""
    from synthadoc.cli.workflow import _TYPE_TO_SCOPE
    assert _TYPE_TO_SCOPE["adversarial"] == "gate"
    assert _TYPE_TO_SCOPE["source-conflict"] == "conflict"


def test_workflow_run_contradiction_resolver_calls_stream_query():
    """contradiction-resolver invocation calls _stream_query with the right question."""
    from synthadoc.cli.main import app
    runner = CliRunner()

    with patch("synthadoc.cli.workflow._stream_query") as mock_sq, \
         patch("synthadoc.cli.workflow._resolve_wiki", return_value="test-wiki"):
        result = runner.invoke(app, [
            "workflow", "run", "contradiction-resolver",
            "-w", "test-wiki",
        ])
    assert mock_sq.called
    call_args = mock_sq.call_args
    question = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("question", "")
    assert "contradiction" in question.lower()


def test_workflow_run_contradiction_resolver_with_slug():
    """--slug flag is forwarded in the query string."""
    from synthadoc.cli.main import app
    runner = CliRunner()

    with patch("synthadoc.cli.workflow._stream_query") as mock_sq, \
         patch("synthadoc.cli.workflow._resolve_wiki", return_value="test-wiki"):
        runner.invoke(app, [
            "workflow", "run", "contradiction-resolver",
            "--slug", "alan-turing",
            "-w", "test-wiki",
        ])

    assert mock_sq.called
    call_args = mock_sq.call_args
    question = call_args[0][1] if len(call_args[0]) > 1 else ""
    assert "alan-turing" in question


def test_workflow_run_contradiction_resolver_type_adversarial():
    """--type adversarial translates to 'gate' in the query string."""
    from synthadoc.cli.main import app
    runner = CliRunner()

    with patch("synthadoc.cli.workflow._stream_query") as mock_sq, \
         patch("synthadoc.cli.workflow._resolve_wiki", return_value="test-wiki"):
        runner.invoke(app, [
            "workflow", "run", "contradiction-resolver",
            "--type", "adversarial",
            "-w", "test-wiki",
        ])

    assert mock_sq.called
    question = mock_sq.call_args[0][1] if len(mock_sq.call_args[0]) > 1 else ""
    assert "--type gate" in question


def test_workflow_run_contradiction_resolver_type_source_conflict():
    """--type source-conflict translates to 'conflict' in the query string."""
    from synthadoc.cli.main import app
    runner = CliRunner()

    with patch("synthadoc.cli.workflow._stream_query") as mock_sq, \
         patch("synthadoc.cli.workflow._resolve_wiki", return_value="test-wiki"):
        runner.invoke(app, [
            "workflow", "run", "contradiction-resolver",
            "--type", "source-conflict",
            "-w", "test-wiki",
        ])

    assert mock_sq.called
    question = mock_sq.call_args[0][1] if len(mock_sq.call_args[0]) > 1 else ""
    assert "--type conflict" in question


def test_workflow_run_contradiction_resolver_no_type_omits_scope():
    """Omitting --type sends no --type token (defaults to all contradicted pages)."""
    from synthadoc.cli.main import app
    runner = CliRunner()

    with patch("synthadoc.cli.workflow._stream_query") as mock_sq, \
         patch("synthadoc.cli.workflow._resolve_wiki", return_value="test-wiki"):
        runner.invoke(app, [
            "workflow", "run", "contradiction-resolver",
            "-w", "test-wiki",
        ])

    assert mock_sq.called
    question = mock_sq.call_args[0][1] if len(mock_sq.call_args[0]) > 1 else ""
    assert "--type" not in question


# ── workflow RE routing ────────────────────────────────────────────────────────

def test_workflow_re_matches_contradiction_resolver():
    """_WORKFLOW_RE in query.py must route contradiction resolver to long timeout."""
    import synthadoc.cli.query as q
    assert q._WORKFLOW_RE.search("run contradiction resolver")
    assert q._WORKFLOW_RE.search("fix contradicted pages")
    assert q._WORKFLOW_RE.search("resolve contradictions")
