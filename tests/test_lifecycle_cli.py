# tests/test_lifecycle_cli.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from typer.testing import CliRunner
from unittest.mock import patch
from synthadoc.cli.main import app
from synthadoc.storage.wiki import LifecycleState

runner = CliRunner()


def test_lifecycle_activate_requires_reason():
    """activate without --reason must fail."""
    with patch("synthadoc.cli.lifecycle.post") as mock_post, \
         patch("synthadoc.cli.lifecycle.resolve_wiki", return_value="test-wiki"):
        result = runner.invoke(app, ["lifecycle", "activate", "alan-turing", "-w", "test-wiki"])
        assert result.exit_code != 0


def test_lifecycle_activate_calls_transition():
    with patch("synthadoc.cli.lifecycle.post") as mock_post, \
         patch("synthadoc.cli.lifecycle.resolve_wiki", return_value="test-wiki"):
        mock_post.return_value = {"ok": True, "from_state": "draft", "to_state": "active"}
        result = runner.invoke(app, [
            "lifecycle", "activate", "alan-turing",
            "-w", "test-wiki", "--reason", "reviewed"
        ])
        assert result.exit_code == 0
        mock_post.assert_called_once()
        call_body = mock_post.call_args[0][2]
        assert call_body["to_state"] == LifecycleState.ACTIVE
        assert call_body["slug"] == "alan-turing"


def test_lifecycle_archive_calls_transition():
    with patch("synthadoc.cli.lifecycle.post") as mock_post, \
         patch("synthadoc.cli.lifecycle.resolve_wiki", return_value="test-wiki"):
        mock_post.return_value = {"ok": True, "from_state": "active", "to_state": "archived"}
        result = runner.invoke(app, [
            "lifecycle", "archive", "alan-turing",
            "-w", "test-wiki", "--reason", "source superseded"
        ])
        assert result.exit_code == 0
        call_body = mock_post.call_args[0][2]
        assert call_body["to_state"] == LifecycleState.ARCHIVED


def test_lifecycle_restore_calls_transition():
    with patch("synthadoc.cli.lifecycle.post") as mock_post, \
         patch("synthadoc.cli.lifecycle.resolve_wiki", return_value="test-wiki"):
        mock_post.return_value = {"ok": True, "from_state": "archived", "to_state": "draft"}
        result = runner.invoke(app, [
            "lifecycle", "restore", "alan-turing",
            "-w", "test-wiki", "--reason", "reinstated"
        ])
        assert result.exit_code == 0
        call_body = mock_post.call_args[0][2]
        assert call_body["to_state"] == LifecycleState.DRAFT


def test_lifecycle_log_calls_events():
    with patch("synthadoc.cli.lifecycle.get") as mock_get, \
         patch("synthadoc.cli.lifecycle.resolve_wiki", return_value="test-wiki"):
        mock_get.return_value = {"events": [], "total": 0}
        result = runner.invoke(app, ["lifecycle", "log", "-w", "test-wiki"])
        assert result.exit_code == 0
        mock_get.assert_called_once()
