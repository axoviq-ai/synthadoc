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


def test_lifecycle_log_shows_events_table():
    """lifecycle log must display a formatted table when events are returned."""
    events = [
        {
            "slug": "alan-turing",
            "from_state": "draft",
            "to_state": "active",
            "triggered_by": "user",
            "timestamp": "2026-06-02T10:00:00",
            "reason": "reviewed",
        }
    ]
    with patch("synthadoc.cli.lifecycle.get") as mock_get, \
         patch("synthadoc.cli.lifecycle.resolve_wiki", return_value="test-wiki"):
        mock_get.return_value = {"events": events, "total": 1}
        result = runner.invoke(app, ["lifecycle", "log", "-w", "test-wiki"])
    assert result.exit_code == 0
    assert "alan-turing" in result.output
    assert "active" in result.output
    assert "reviewed" in result.output


def test_lifecycle_log_with_slug_and_state_filter():
    """lifecycle log --slug and --state must be forwarded as query params."""
    with patch("synthadoc.cli.lifecycle.get") as mock_get, \
         patch("synthadoc.cli.lifecycle.resolve_wiki", return_value="test-wiki"):
        mock_get.return_value = {"events": [], "total": 0}
        result = runner.invoke(app, [
            "lifecycle", "log", "alan-turing", "-w", "test-wiki",
            "--state", "active",
        ])
    assert result.exit_code == 0
    _, kwargs = mock_get.call_args
    assert kwargs.get("slug") == "alan-turing"
    assert kwargs.get("to_state") == "active"


def test_lifecycle_transition_error_exits():
    """_transition_cmd must print an error and exit(1) when ok is False."""
    with patch("synthadoc.cli.lifecycle.post") as mock_post, \
         patch("synthadoc.cli.lifecycle.resolve_wiki", return_value="test-wiki"):
        mock_post.return_value = {"ok": False, "detail": "invalid transition"}
        result = runner.invoke(app, [
            "lifecycle", "activate", "bad-page",
            "-w", "test-wiki", "--reason", "test"
        ])
    assert result.exit_code != 0
