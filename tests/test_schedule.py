# tests/test_schedule.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
#
# Platform markers:
#   pytest -m windows   — run only on Windows
#   pytest -m linux     — run only on Linux
#   pytest -m macos     — run only on macOS
#   pytest -m "not (windows or linux or macos)"  — cross-platform tests only
import platform
import pytest
from pathlib import Path
from synthadoc.storage.log import AuditDB
from synthadoc.core.scheduler import _cron_next_run, _schtasks_time_to_cron, Scheduler

windows = pytest.mark.skipif(platform.system() != "Windows", reason="Windows only")
linux   = pytest.mark.skipif(platform.system() != "Linux",   reason="Linux only")
macos   = pytest.mark.skipif(platform.system() != "Darwin",  reason="macOS only")
posix   = pytest.mark.skipif(platform.system() == "Windows", reason="POSIX only")


# ------------------------------------------------------------------
# Fix 1 helpers
# ------------------------------------------------------------------

def test_cron_next_run_returns_future_datetime():
    result = _cron_next_run("0 2 * * *")
    assert result != ""
    # Should be a date string like "2026-05-31 02:00"
    assert len(result) == 16
    assert ":" in result


def test_cron_next_run_invalid_returns_empty():
    assert _cron_next_run("not a cron") == ""


def test_schtasks_time_to_cron_am():
    assert _schtasks_time_to_cron("2:00:00 AM") == "0 2 * * *"


def test_schtasks_time_to_cron_pm():
    assert _schtasks_time_to_cron("11:30:00 PM") == "30 23 * * *"


def test_schtasks_time_to_cron_24h():
    assert _schtasks_time_to_cron("14:15:00") == "15 14 * * *"


def test_schtasks_time_to_cron_invalid_returns_empty():
    assert _schtasks_time_to_cron("garbage") == ""


def test_schedule_entry_defaults():
    from synthadoc.core.scheduler import ScheduleEntry
    e = ScheduleEntry(op="lint run", cron="0 2 * * *", wiki="mywiki")
    assert e.next_run == ""
    assert e.last_run == ""
    assert e.last_result == ""
    assert e.id.startswith("sched-")


def test_build_run_cmd_uses_schedule_run(tmp_path):
    sched = Scheduler(wiki="mywiki", wiki_root=str(tmp_path))
    cmd = sched._build_run_cmd("lint run")
    assert "schedule run" in cmd
    assert '--op "lint run"' in cmd
    assert "-w mywiki" in cmd


def test_build_crontab_line_uses_schedule_run(tmp_path):
    sched = Scheduler(wiki="mywiki", wiki_root=str(tmp_path))
    line = sched._build_crontab_line("lint run", "0 2 * * *", "sched-abc")
    assert "schedule run" in line
    assert "0 2 * * *" in line
    assert "sched-abc" in line


def test_build_schtasks_args_uses_schedule_run(tmp_path):
    sched = Scheduler(wiki="mywiki", wiki_root=str(tmp_path))
    args = sched._build_schtasks_args("lint run", "0 2 * * *", "sched-abc")
    tr_idx = args.index("/TR")
    cmd = args[tr_idx + 1]
    assert "schedule run" in cmd
    assert '--op "lint run"' in cmd


# ------------------------------------------------------------------
# Fix 3 — AuditDB scheduled_runs
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_scheduled_run_start(tmp_path):
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.record_scheduled_run_start("run-abc", "lint run", "mywiki")
    runs = await db.list_scheduled_runs()
    assert len(runs) == 1
    assert runs[0]["run_id"] == "run-abc"
    assert runs[0]["op"] == "lint run"
    assert runs[0]["status"] == "running"
    assert runs[0]["finished_at"] is None


@pytest.mark.asyncio
async def test_record_scheduled_run_finish_success(tmp_path):
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.record_scheduled_run_start("run-xyz", "lint run", "mywiki")
    await db.record_scheduled_run_finish("run-xyz", "success", 42.5)
    runs = await db.list_scheduled_runs()
    r = runs[0]
    assert r["status"] == "success"
    assert r["duration_s"] == 42.5
    assert r["error"] is None
    assert r["finished_at"] is not None


@pytest.mark.asyncio
async def test_record_scheduled_run_finish_failed(tmp_path):
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.record_scheduled_run_start("run-fail", "lint run", "mywiki")
    await db.record_scheduled_run_finish("run-fail", "failed", 3.2, "exit code 1")
    runs = await db.list_scheduled_runs()
    r = runs[0]
    assert r["status"] == "failed"
    assert r["error"] == "exit code 1"


@pytest.mark.asyncio
async def test_list_scheduled_runs_ordered_desc(tmp_path):
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.record_scheduled_run_start("run-1", "lint run", "mywiki")
    await db.record_scheduled_run_start("run-2", "lint run", "mywiki")
    await db.record_scheduled_run_start("run-3", "lint run", "mywiki")
    runs = await db.list_scheduled_runs()
    assert runs[0]["run_id"] == "run-3"  # most recent first
    assert runs[-1]["run_id"] == "run-1"


@pytest.mark.asyncio
async def test_list_scheduled_runs_respects_limit(tmp_path):
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    for i in range(5):
        await db.record_scheduled_run_start(f"run-{i}", "lint run", "mywiki")
    runs = await db.list_scheduled_runs(limit=3)
    assert len(runs) == 3


# ------------------------------------------------------------------
# Platform-specific: Windows (schtasks)
# Run with: pytest -m windows
# ------------------------------------------------------------------

@windows
def test_windows_build_schtasks_args_daily(tmp_path):
    sched = Scheduler(wiki="mywiki", wiki_root=str(tmp_path))
    args = sched._build_schtasks_args("lint run", "0 2 * * *", "sched-test")
    assert "/SC" in args
    sc_idx = args.index("/SC")
    assert args[sc_idx + 1] == "DAILY"
    st_idx = args.index("/ST")
    assert args[st_idx + 1] == "02:00"


@windows
def test_windows_schtasks_time_roundtrip():
    assert _schtasks_time_to_cron("2:00:00 AM") == "0 2 * * *"
    assert _schtasks_time_to_cron("11:45:00 PM") == "45 23 * * *"
    assert _schtasks_time_to_cron("12:00:00 AM") == "0 0 * * *"


@windows
def test_windows_list_schtasks_parses_next_run(tmp_path, monkeypatch):
    """_list_schtasks parses Next Run Time and Last Result from schtasks output."""
    import subprocess
    fake_output = (
        "TaskName:                             \\synthadoc-sched-abc123\n"
        "Next Run Time:                        5/31/2026 2:00:00 AM\n"
        "Last Run Time:                        5/30/2026 2:00:00 AM\n"
        "Last Result:                          0\n"
        "Task To Run:                          synthadoc -w mywiki schedule run --op \"lint run\"\n"
        "Start Time:                           2:00:00 AM\n"
    )
    mock_result = type("R", (), {"stdout": fake_output, "returncode": 0})()
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)
    sched = Scheduler(wiki="mywiki", wiki_root=str(tmp_path))
    entries = sched._list_schtasks()
    assert len(entries) == 1
    e = entries[0]
    assert e.id == "sched-abc123"
    assert e.next_run == "5/31/2026 2:00:00 AM"
    assert e.last_run == "5/30/2026 2:00:00 AM"
    assert e.last_result == "success"
    assert e.cron == "0 2 * * *"


# ------------------------------------------------------------------
# Platform-specific: Linux / macOS (crontab)
# Run with: pytest -m posix
# ------------------------------------------------------------------

@posix
def test_posix_crontab_line_format(tmp_path):
    sched = Scheduler(wiki="mywiki", wiki_root=str(tmp_path))
    line = sched._build_crontab_line("lint run", "0 2 * * *", "sched-abc")
    assert line.startswith("0 2 * * *")
    assert 'schedule run --op "lint run"' in line
    assert "# synthadoc:sched-abc" in line


@posix
def test_posix_list_crontab_parses_next_run(tmp_path, monkeypatch):
    """_list_crontab parses entry and computes next_run via croniter."""
    import subprocess
    fake_crontab = (
        '0 2 * * * synthadoc -w mywiki schedule run --op "lint run" # synthadoc:sched-xyz\n'
    )
    mock_result = type("R", (), {"stdout": fake_crontab, "returncode": 0})()
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)
    sched = Scheduler(wiki="mywiki", wiki_root=str(tmp_path))
    entries = sched._list_crontab()
    assert len(entries) == 1
    e = entries[0]
    assert e.id == "sched-xyz"
    assert e.cron == "0 2 * * *"
    assert e.next_run != ""  # croniter computed a future datetime
    assert e.last_run == ""  # not available in crontab
    assert e.last_result == ""  # not available in crontab


@posix
def test_posix_cron_next_run_is_future():
    from datetime import datetime, timezone
    result = _cron_next_run("0 2 * * *")
    assert result != ""
    dt = datetime.strptime(result, "%Y-%m-%d %H:%M")
    # next run must be in the future relative to now
    assert dt >= datetime.now().replace(second=0, microsecond=0)
