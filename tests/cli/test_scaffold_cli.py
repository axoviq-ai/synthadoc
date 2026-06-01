# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from synthadoc.cli.main import app

runner = CliRunner()


def _mock_http(domain: str = "Robotics", job_id: str = "abc-123"):
    """Return (get_mock, post_mock) pre-configured for scaffold tests."""
    get_mock = MagicMock(return_value={"domain": domain})
    post_mock = MagicMock(return_value={"job_id": job_id})
    return get_mock, post_mock


def _invoke_scaffold(wiki: str = "my-wiki", get_mock=None, post_mock=None):
    with patch("synthadoc.cli._http.get", get_mock), \
         patch("synthadoc.cli._http.post", post_mock), \
         patch("synthadoc.cli._wiki.resolve_wiki", return_value=wiki):
        return runner.invoke(app, ["scaffold", "--wiki", wiki])


def test_scaffold_queues_job_on_server():
    """scaffold_cmd posts to /jobs/scaffold and exits zero."""
    get_mock, post_mock = _mock_http(domain="Robotics", job_id="job-xyz")
    result = _invoke_scaffold(get_mock=get_mock, post_mock=post_mock)

    assert result.exit_code == 0, result.output
    post_mock.assert_called_once()
    call_args = post_mock.call_args
    assert call_args[0][1] == "/jobs/scaffold"
    assert call_args[0][2]["domain"] == "Robotics"


def test_scaffold_shows_job_id_in_output():
    """scaffold_cmd prints the returned job_id."""
    get_mock, post_mock = _mock_http(job_id="job-xyz-456")
    result = _invoke_scaffold(get_mock=get_mock, post_mock=post_mock)

    assert result.exit_code == 0, result.output
    assert "job-xyz-456" in result.output


def test_scaffold_uses_domain_from_server_config():
    """scaffold_cmd reads domain from GET /config, not the local filesystem."""
    get_mock, post_mock = _mock_http(domain="AI Research")
    result = _invoke_scaffold(get_mock=get_mock, post_mock=post_mock)

    assert result.exit_code == 0, result.output
    assert "AI Research" in result.output


def test_scaffold_exits_nonzero_when_server_unreachable():
    """scaffold_cmd exits non-zero when the server cannot be reached."""
    get_mock = MagicMock(side_effect=Exception("Connection refused"))
    post_mock = MagicMock()
    result = _invoke_scaffold(get_mock=get_mock, post_mock=post_mock)

    assert result.exit_code != 0
    post_mock.assert_not_called()


def test_scaffold_exits_nonzero_when_enqueue_fails():
    """scaffold_cmd exits non-zero when POST /jobs/scaffold raises."""
    get_mock, _ = _mock_http()
    post_mock = MagicMock(side_effect=Exception("Server error"))
    result = _invoke_scaffold(get_mock=get_mock, post_mock=post_mock)

    assert result.exit_code != 0
