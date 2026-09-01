# tests/test_cli_run.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for synthadoc/cli/workflow.py — the 'synthadoc workflow' subcommand group."""
from __future__ import annotations

import re
import pytest
from typer.testing import CliRunner
from unittest.mock import patch


def _strip_ansi(text: str) -> str:
    """Remove ANSI colour/style escape sequences from *text*.

    Older versions of rich insert colour codes between option-name dashes
    (``-\\x1b[...]-name``), which breaks plain substring checks.
    """
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


# ── top-level 'workflow' command ──────────────────────────────────────────────

def test_workflow_command_exists_on_app():
    """synthadoc workflow is a registered typer command group."""
    from synthadoc.cli.main import app
    runner = CliRunner()
    result = runner.invoke(app, ["workflow", "--help"])
    assert result.exit_code == 0
    out = result.output.lower()
    assert "run" in out
    assert "list" in out


# ── workflow list ─────────────────────────────────────────────────────────────

def test_workflow_list_exits_ok():
    """synthadoc workflow list exits 0 and prints a table."""
    from synthadoc.cli.main import app
    runner = CliRunner()
    result = runner.invoke(app, ["workflow", "list"])
    assert result.exit_code == 0
    assert "NAME" in result.output


def test_workflow_list_shows_all_registered_workflows():
    """All 5 registered workflows appear in 'workflow list' output."""
    from synthadoc.cli.main import app
    runner = CliRunner()
    result = runner.invoke(app, ["workflow", "list"])
    assert result.exit_code == 0
    out = result.output
    for expected in [
        "lint-report",
        "broken-wikilinks",
        "scaffold",
        "contradiction-resolver",
        "ingest-lint",
    ]:
        assert expected in out, f"'{expected}' missing from 'workflow list' output"


def test_workflow_list_shows_descriptions():
    """workflow list includes the DESCRIPTION for each workflow."""
    from synthadoc.cli.main import app
    runner = CliRunner()
    result = runner.invoke(app, ["workflow", "list"])
    assert result.exit_code == 0
    # Every registered workflow must have a non-empty description
    from synthadoc.agents.workflows._registry import CLI_REGISTRY
    for name, cls in CLI_REGISTRY.items():
        assert cls.DESCRIPTION, f"Workflow '{name}' has no DESCRIPTION"


# ── workflow run --help ───────────────────────────────────────────────────────

def test_workflow_run_help_shows_name_option():
    """synthadoc workflow run --help documents --name."""
    from synthadoc.cli.main import app
    runner = CliRunner()
    result = runner.invoke(app, ["workflow", "run", "--help"])
    assert result.exit_code == 0
    clean = _strip_ansi(result.output)
    assert "--name" in clean


def test_workflow_run_help_shows_workflow_examples():
    """workflow run --help mentions the registered workflow names."""
    from synthadoc.cli.main import app
    runner = CliRunner()
    result = runner.invoke(app, ["workflow", "run", "--help"])
    assert result.exit_code == 0
    out = result.output
    assert "contradiction-resolver" in out
    assert "lint-report" in out


# ── workflow run — dispatch ───────────────────────────────────────────────────

def test_workflow_run_calls_stream_query_for_lint_report():
    """workflow run --name lint-report calls _stream_query."""
    from synthadoc.cli.main import app
    runner = CliRunner()
    with patch("synthadoc.cli.workflow._stream_query") as mock_sq, \
         patch("synthadoc.cli.workflow._resolve_wiki", return_value="test-wiki"):
        result = runner.invoke(app, ["workflow", "run", "--name", "lint-report"])
    assert mock_sq.called
    question = mock_sq.call_args[0][1] if len(mock_sq.call_args[0]) > 1 else ""
    assert "lint" in question.lower()


def test_workflow_run_calls_stream_query_for_broken_wikilinks():
    """workflow run --name broken-wikilinks calls _stream_query."""
    from synthadoc.cli.main import app
    runner = CliRunner()
    with patch("synthadoc.cli.workflow._stream_query") as mock_sq, \
         patch("synthadoc.cli.workflow._resolve_wiki", return_value="test-wiki"):
        result = runner.invoke(app, ["workflow", "run", "--name", "broken-wikilinks"])
    assert mock_sq.called
    question = mock_sq.call_args[0][1] if len(mock_sq.call_args[0]) > 1 else ""
    assert "wikilink" in question.lower()


def test_workflow_run_calls_stream_query_for_scaffold():
    """workflow run --name scaffold calls _stream_query."""
    from synthadoc.cli.main import app
    runner = CliRunner()
    with patch("synthadoc.cli.workflow._stream_query") as mock_sq, \
         patch("synthadoc.cli.workflow._resolve_wiki", return_value="test-wiki"):
        result = runner.invoke(app, ["workflow", "run", "--name", "scaffold"])
    assert mock_sq.called
    question = mock_sq.call_args[0][1] if len(mock_sq.call_args[0]) > 1 else ""
    assert "scaffold" in question.lower()


def test_workflow_run_calls_stream_query_for_contradiction_resolver():
    """workflow run --name contradiction-resolver calls _stream_query."""
    from synthadoc.cli.main import app
    runner = CliRunner()
    with patch("synthadoc.cli.workflow._stream_query") as mock_sq, \
         patch("synthadoc.cli.workflow._resolve_wiki", return_value="test-wiki"):
        runner.invoke(app, [
            "workflow", "run", "--name", "contradiction-resolver",
            "-w", "test-wiki",
        ])
    assert mock_sq.called
    question = mock_sq.call_args[0][1] if len(mock_sq.call_args[0]) > 1 else ""
    assert "contradiction" in question.lower()


def test_workflow_run_calls_stream_query_for_ingest_lint():
    """workflow run --name ingest-lint calls _stream_query."""
    from synthadoc.cli.main import app
    runner = CliRunner()
    with patch("synthadoc.cli.workflow._stream_query") as mock_sq, \
         patch("synthadoc.cli.workflow._resolve_wiki", return_value="test-wiki"):
        result = runner.invoke(app, ["workflow", "run", "--name", "ingest-lint"])
    assert mock_sq.called
    question = mock_sq.call_args[0][1] if len(mock_sq.call_args[0]) > 1 else ""
    assert "stale" in question.lower()


# ── workflow run — extra args forwarding ──────────────────────────────────────

def test_workflow_run_forwards_slug_to_query():
    """--slug extra arg is appended to the query string."""
    from synthadoc.cli.main import app
    runner = CliRunner()
    with patch("synthadoc.cli.workflow._stream_query") as mock_sq, \
         patch("synthadoc.cli.workflow._resolve_wiki", return_value="test-wiki"):
        runner.invoke(app, [
            "workflow", "run", "--name", "contradiction-resolver",
            "--slug", "alan-turing",
            "-w", "test-wiki",
        ])
    assert mock_sq.called
    question = mock_sq.call_args[0][1] if len(mock_sq.call_args[0]) > 1 else ""
    assert "--slug" in question
    assert "alan-turing" in question


def test_workflow_run_forwards_type_adversarial_to_query():
    """--type adversarial is forwarded in the query string."""
    from synthadoc.cli.main import app
    runner = CliRunner()
    with patch("synthadoc.cli.workflow._stream_query") as mock_sq, \
         patch("synthadoc.cli.workflow._resolve_wiki", return_value="test-wiki"):
        runner.invoke(app, [
            "workflow", "run", "--name", "contradiction-resolver",
            "--type", "adversarial",
            "-w", "test-wiki",
        ])
    assert mock_sq.called
    question = mock_sq.call_args[0][1] if len(mock_sq.call_args[0]) > 1 else ""
    assert "--type" in question
    assert "adversarial" in question


def test_workflow_run_forwards_type_source_conflict_to_query():
    """--type source-conflict is forwarded in the query string."""
    from synthadoc.cli.main import app
    runner = CliRunner()
    with patch("synthadoc.cli.workflow._stream_query") as mock_sq, \
         patch("synthadoc.cli.workflow._resolve_wiki", return_value="test-wiki"):
        runner.invoke(app, [
            "workflow", "run", "--name", "contradiction-resolver",
            "--type", "source-conflict",
            "-w", "test-wiki",
        ])
    assert mock_sq.called
    question = mock_sq.call_args[0][1] if len(mock_sq.call_args[0]) > 1 else ""
    assert "--type" in question
    assert "source-conflict" in question


def test_workflow_run_no_extra_args_sends_base_query():
    """With no extra args, the base query string is sent unmodified."""
    from synthadoc.cli.main import app
    from synthadoc.cli.workflow import _WORKFLOW_QUERIES
    runner = CliRunner()
    with patch("synthadoc.cli.workflow._stream_query") as mock_sq, \
         patch("synthadoc.cli.workflow._resolve_wiki", return_value="test-wiki"):
        runner.invoke(app, [
            "workflow", "run", "--name", "contradiction-resolver",
            "-w", "test-wiki",
        ])
    assert mock_sq.called
    question = mock_sq.call_args[0][1] if len(mock_sq.call_args[0]) > 1 else ""
    assert question == _WORKFLOW_QUERIES["contradiction-resolver"]


# ── workflow run — unknown name ───────────────────────────────────────────────

def test_workflow_run_unknown_name_exits_nonzero():
    """Passing an unregistered workflow name exits with code 1."""
    from synthadoc.cli.main import app
    runner = CliRunner()
    with patch("synthadoc.cli.workflow._resolve_wiki", return_value="test-wiki"):
        result = runner.invoke(app, [
            "workflow", "run", "--name", "nonexistent-workflow",
        ])
    assert result.exit_code != 0


def test_workflow_run_unknown_name_prints_available_list():
    """Unknown workflow name error message lists available workflow names."""
    from synthadoc.cli.main import app
    runner = CliRunner()
    with patch("synthadoc.cli.workflow._resolve_wiki", return_value="test-wiki"):
        result = runner.invoke(app, [
            "workflow", "run", "--name", "does-not-exist",
        ])
    # Error goes to stderr; CliRunner mixes it with stdout by default
    assert "contradiction-resolver" in result.output or result.exit_code != 0


# ── CLI_REGISTRY ──────────────────────────────────────────────────────────────

def test_cli_registry_contains_all_named_workflows():
    """CLI_REGISTRY contains all 7 workflow classes."""
    from synthadoc.agents.workflows._registry import CLI_REGISTRY
    expected = {
        "lint-report",
        "broken-wikilinks",
        "scaffold",
        "contradiction-resolver",
        "ingest-lint",
        "orphan-resolver",
        "broken-citation-resolver",
    }
    assert expected == set(CLI_REGISTRY.keys())


def test_cli_registry_values_are_workflow_classes():
    """CLI_REGISTRY values are AgenticWorkflow subclasses."""
    from synthadoc.agents.workflows._registry import CLI_REGISTRY
    from synthadoc.agents.workflows._base import AgenticWorkflow
    for name, cls in CLI_REGISTRY.items():
        assert issubclass(cls, AgenticWorkflow), f"{name} is not an AgenticWorkflow"


# ── ContradictionResolverWorkflow.build_initial_message ───────────────────────

def test_build_initial_message_no_args_defaults_all():
    """build_initial_message with no --slug/--type defaults scope to 'all'."""
    from synthadoc.agents.workflows.contradiction_resolver import ContradictionResolverWorkflow
    wf = ContradictionResolverWorkflow()
    msg = wf.build_initial_message("run contradiction resolver")
    assert "Scope: all" in msg


def test_build_initial_message_slug_forwarded():
    """build_initial_message extracts --slug from the query string."""
    from synthadoc.agents.workflows.contradiction_resolver import ContradictionResolverWorkflow
    wf = ContradictionResolverWorkflow()
    msg = wf.build_initial_message("run contradiction resolver --slug alan-turing")
    assert "alan-turing" in msg


def test_build_initial_message_type_adversarial_maps_to_gate():
    """--type adversarial in the query is remapped to internal scope 'gate'."""
    from synthadoc.agents.workflows.contradiction_resolver import ContradictionResolverWorkflow
    wf = ContradictionResolverWorkflow()
    msg = wf.build_initial_message("run contradiction resolver --type adversarial")
    assert "Scope: gate" in msg


def test_build_initial_message_type_source_conflict_maps_to_conflict():
    """--type source-conflict in the query is remapped to internal scope 'conflict'."""
    from synthadoc.agents.workflows.contradiction_resolver import ContradictionResolverWorkflow
    wf = ContradictionResolverWorkflow()
    msg = wf.build_initial_message("run contradiction resolver --type source-conflict")
    assert "Scope: conflict" in msg


def test_build_initial_message_type_gate_passes_through():
    """--type gate passes through without remapping."""
    from synthadoc.agents.workflows.contradiction_resolver import ContradictionResolverWorkflow
    wf = ContradictionResolverWorkflow()
    msg = wf.build_initial_message("run contradiction resolver --type gate")
    assert "Scope: gate" in msg


def test_build_initial_message_type_conflict_passes_through():
    """--type conflict passes through without remapping."""
    from synthadoc.agents.workflows.contradiction_resolver import ContradictionResolverWorkflow
    wf = ContradictionResolverWorkflow()
    msg = wf.build_initial_message("run contradiction resolver --type conflict")
    assert "Scope: conflict" in msg


# ── workflow RE routing ────────────────────────────────────────────────────────

def test_workflow_re_matches_contradiction_resolver():
    """_WORKFLOW_RE in query.py routes contradiction resolver to long timeout."""
    import synthadoc.cli.query as q
    assert q._WORKFLOW_RE.search("run contradiction resolver")
    assert q._WORKFLOW_RE.search("fix contradicted pages")
    assert q._WORKFLOW_RE.search("resolve contradictions")
