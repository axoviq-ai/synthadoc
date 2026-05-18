# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from pathlib import Path
from unittest.mock import patch
from typer.testing import CliRunner
from synthadoc.cli.main import app

runner = CliRunner()


def test_jobs_list_empty(tmp_path):
    with patch("synthadoc.cli.jobs.get", return_value=[]):
        result = runner.invoke(app, ["jobs", "list", "--wiki", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "No jobs" in result.output


def test_jobs_list_shows_entries(tmp_path):
    mock_jobs = [
        {"id": "job-001", "status": "pending", "operation": "ingest",
         "created_at": "2026-05-17 10:00:00"},
    ]
    with patch("synthadoc.cli.jobs.get", return_value=mock_jobs):
        result = runner.invoke(app, ["jobs", "list", "--wiki", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "job-001" in result.output


def test_jobs_status_shows_result_fields(tmp_path):
    """jobs status displays all optional result fields when present."""
    mock_job = {
        "id": "job-001", "status": "completed", "operation": "ingest",
        "created_at": "2026-05-17 10:00:00", "error": None,
        "result": {
            "pages_created": ["page-1"],
            "pages_updated": ["page-2"],
            "pages_flagged": ["page-3"],
            "skip_reason": "out of scope",
            "tokens_used": 500,
        },
    }
    with patch("synthadoc.cli.jobs.get", return_value=mock_job):
        result = runner.invoke(app, ["jobs", "status", "job-001", "--wiki", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "page-1" in result.output
    assert "page-2" in result.output
    assert "page-3" in result.output
    assert "out of scope" in result.output
    assert "500" in result.output


def test_jobs_cancel_with_yes_skips_confirmation(tmp_path):
    """jobs cancel --yes bypasses confirmation and reports cancelled count."""
    with patch("synthadoc.cli._http.post", return_value={"cancelled": 3}):
        result = runner.invoke(app, ["jobs", "cancel", "--yes", "--wiki", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "3" in result.output


def test_jobs_list_passes_sort_params_to_api(tmp_path):
    """--sort and --order are forwarded as query params."""
    mock_jobs = [
        {"id": "j1", "status": "completed", "operation": "ingest", "created_at": "2026-01-02 00:00:00"},
        {"id": "j2", "status": "pending", "operation": "lint", "created_at": "2026-01-01 00:00:00"},
    ]
    with patch("synthadoc.cli.jobs.get", return_value=mock_jobs) as mock_get:
        result = runner.invoke(app, [
            "jobs", "list", "--sort", "operation", "--order", "desc", "--wiki", str(tmp_path)
        ])
    assert result.exit_code == 0, result.output
    call_kwargs = mock_get.call_args
    assert call_kwargs.kwargs.get("sort") == "operation" or "operation" in str(call_kwargs)
    assert call_kwargs.kwargs.get("order") == "desc" or "desc" in str(call_kwargs)


def test_jobs_list_default_sort_is_created_at_asc(tmp_path):
    """Default --sort is created_at and default --order is asc."""
    with patch("synthadoc.cli.jobs.get", return_value=[]) as mock_get:
        runner.invoke(app, ["jobs", "list", "--wiki", str(tmp_path)])
    call_kwargs = mock_get.call_args
    assert call_kwargs.kwargs.get("sort") == "created_at" or "created_at" in str(call_kwargs)
    assert call_kwargs.kwargs.get("order") == "asc" or ("asc" in str(call_kwargs) and "desc" not in str(call_kwargs))
