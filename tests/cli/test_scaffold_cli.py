# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from synthadoc.cli.main import app

runner = CliRunner()


def _make_get_mock(domain: str = "Robotics", job_id: str = "abc-123",
                   final_status: str = "completed", categories: int = 3):
    """Return a get mock: /config → domain, /jobs/{id} → completed job."""
    completed_job = {"status": final_status, "result": {"categories_updated": categories},
                     "error": None}
    def _get(wiki, path, **kw):
        if path == "/config":
            return {"domain": domain}
        if path.startswith("/jobs/"):
            return completed_job
        return {}
    return MagicMock(side_effect=_get)


def _invoke_scaffold(wiki: str = "my-wiki", get_mock=None, post_mock=None):
    with patch("synthadoc.cli._http.get", get_mock), \
         patch("synthadoc.cli._http.post", post_mock), \
         patch("synthadoc.cli._wiki.resolve_wiki", return_value=wiki), \
         patch("time.sleep"):  # skip the 2-second poll delay
        return runner.invoke(app, ["scaffold", "--wiki", wiki])


def test_scaffold_queues_job_on_server():
    """scaffold_cmd posts to /jobs/scaffold and exits zero."""
    get_mock = _make_get_mock(domain="Robotics", job_id="job-xyz")
    post_mock = MagicMock(return_value={"job_id": "job-xyz"})
    result = _invoke_scaffold(get_mock=get_mock, post_mock=post_mock)

    assert result.exit_code == 0, result.output
    post_mock.assert_called_once()
    call_args = post_mock.call_args
    assert call_args[0][1] == "/jobs/scaffold"
    assert call_args[0][2]["domain"] == "Robotics"


def test_scaffold_shows_completion_summary():
    """scaffold_cmd prints index/AGENTS/purpose updated and category count."""
    get_mock = _make_get_mock(categories=7)
    post_mock = MagicMock(return_value={"job_id": "job-1"})
    result = _invoke_scaffold(get_mock=get_mock, post_mock=post_mock)

    assert result.exit_code == 0, result.output
    assert "index.md" in result.output
    assert "AGENTS.md" in result.output
    assert "purpose.md" in result.output
    assert "7" in result.output


def test_scaffold_uses_domain_from_server_config():
    """scaffold_cmd reads domain from GET /config, not the local filesystem."""
    get_mock = _make_get_mock(domain="AI Research")
    post_mock = MagicMock(return_value={"job_id": "job-2"})
    result = _invoke_scaffold(get_mock=get_mock, post_mock=post_mock)

    assert result.exit_code == 0, result.output
    assert "AI Research" in result.output


def test_scaffold_exits_nonzero_when_server_unreachable():
    """scaffold_cmd exits non-zero when GET /config fails."""
    get_mock = MagicMock(side_effect=Exception("Connection refused"))
    post_mock = MagicMock()
    result = _invoke_scaffold(get_mock=get_mock, post_mock=post_mock)

    assert result.exit_code != 0
    post_mock.assert_not_called()


def test_scaffold_exits_nonzero_when_enqueue_fails():
    """scaffold_cmd exits non-zero when POST /jobs/scaffold raises."""
    get_mock = _make_get_mock()
    post_mock = MagicMock(side_effect=Exception("Server error"))
    result = _invoke_scaffold(get_mock=get_mock, post_mock=post_mock)

    assert result.exit_code != 0


def test_scaffold_exits_nonzero_when_job_fails():
    """scaffold_cmd exits non-zero when the job ends in failed status."""
    get_mock = _make_get_mock(final_status="failed")
    # Patch error field too
    def _get(wiki, path, **kw):
        if path == "/config":
            return {"domain": "Robotics"}
        return {"status": "failed", "result": None, "error": "LLM timeout"}
    get_mock = MagicMock(side_effect=_get)
    post_mock = MagicMock(return_value={"job_id": "job-3"})
    result = _invoke_scaffold(get_mock=get_mock, post_mock=post_mock)

    assert result.exit_code != 0
    assert "LLM timeout" in result.output


def test_scaffold_exits_gracefully_when_poll_drops():
    """scaffold_cmd catches connection errors during status polling and prints monitor hint."""
    def _get(wiki, path, **kw):
        if path == "/config":
            return {"domain": "Robotics"}
        raise Exception("Connection dropped")
    get_mock = MagicMock(side_effect=_get)
    post_mock = MagicMock(return_value={"job_id": "job-poll-err"})
    result = _invoke_scaffold(get_mock=get_mock, post_mock=post_mock)

    assert result.exit_code == 0
    assert "Monitor progress" in result.output
