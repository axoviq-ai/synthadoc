# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
import typer


# ── _StreakGuard unit tests ────────────────────────────────────────────────────

def test_streak_guard_does_not_raise_before_threshold():
    from synthadoc.cli.lint import _StreakGuard
    guard = _StreakGuard(max_streak=3)
    guard.failure()
    guard.failure()  # 2 consecutive — still below threshold


def test_streak_guard_raises_exit_at_threshold():
    from synthadoc.cli.lint import _StreakGuard
    guard = _StreakGuard(max_streak=3, message="giving up")
    guard.failure()
    guard.failure()
    with pytest.raises(typer.Exit):
        guard.failure()  # 3rd consecutive — should exit


def test_streak_guard_success_resets_count():
    from synthadoc.cli.lint import _StreakGuard
    guard = _StreakGuard(max_streak=3)
    guard.failure()
    guard.failure()
    guard.success()   # reset
    guard.failure()   # only 1 consecutive after reset — no exit
    guard.failure()   # 2 consecutive — still fine


def test_streak_guard_raises_again_after_reset_if_threshold_hit():
    from synthadoc.cli.lint import _StreakGuard
    guard = _StreakGuard(max_streak=2)
    guard.failure()
    guard.success()
    guard.failure()
    with pytest.raises(typer.Exit):
        guard.failure()  # 2nd consecutive after reset — exit


def test_streak_guard_exit_is_code_1():
    from synthadoc.cli.lint import _StreakGuard
    guard = _StreakGuard(max_streak=1)
    with pytest.raises(typer.Exit) as exc_info:
        guard.failure()
    assert exc_info.value.exit_code == 1


def test_streak_guard_custom_message_printed(capsys):
    from synthadoc.cli.lint import _StreakGuard
    guard = _StreakGuard(max_streak=1, message="custom: server gone")
    with pytest.raises(typer.Exit):
        guard.failure()
    captured = capsys.readouterr()
    assert "custom: server gone" in captured.err


# ── _poll_job_progress integration tests ─────────────────────────────────────

def _make_job_resp(status: str, message: str = "") -> dict:
    return {"status": status, "progress": {"message": message}}


def test_poll_job_progress_returns_completed_on_success():
    from synthadoc.cli.lint import _poll_job_progress
    responses = [
        _make_job_resp("running", "phase 1"),
        _make_job_resp("running", "phase 2"),
        _make_job_resp("completed", "done"),
    ]
    with patch("synthadoc.cli.lint.get", side_effect=responses), \
         patch("time.sleep"):
        result = _poll_job_progress("my-wiki", "job-abc")
    assert result == "completed"


def test_poll_job_progress_exits_after_max_streak_server_errors():
    from synthadoc.cli.lint import _poll_job_progress, _POLL_MAX_STREAK
    with patch("synthadoc.cli.lint.get", side_effect=ConnectionError("refused")), \
         patch("time.sleep"):
        with pytest.raises(typer.Exit) as exc_info:
            _poll_job_progress("my-wiki", "job-abc")
    assert exc_info.value.exit_code == 1


def test_poll_job_progress_recovers_after_transient_errors():
    from synthadoc.cli.lint import _poll_job_progress, _POLL_MAX_STREAK
    # Fewer failures than the threshold, then a success
    errors = [ConnectionError("refused")] * (_POLL_MAX_STREAK - 1)
    responses = errors + [_make_job_resp("completed")]
    with patch("synthadoc.cli.lint.get", side_effect=responses), \
         patch("time.sleep"):
        result = _poll_job_progress("my-wiki", "job-abc")
    assert result == "completed"
