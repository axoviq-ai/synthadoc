# tests/test_schedule.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import json
import pytest
from datetime import datetime
from pathlib import Path
from synthadoc.storage.log import AuditDB
from synthadoc.core.scheduler import (
    Scheduler, ScheduleEntry, _cron_next_run, _matches_cron, _format_run_ts,
    _truncate_output,
)


# ------------------------------------------------------------------
# _cron_next_run helpers
# ------------------------------------------------------------------

def test_cron_next_run_returns_future_datetime():
    result = _cron_next_run("0 2 * * *")
    assert result != ""
    assert len(result) == 16
    assert ":" in result


def test_cron_next_run_invalid_returns_empty():
    assert _cron_next_run("not a cron") == ""


# ------------------------------------------------------------------
# _format_run_ts
# ------------------------------------------------------------------

def test_format_run_ts_converts_utc_iso_to_local():
    # UTC ISO string — must come back as YYYY-MM-DD HH:MM (16 chars, no tz suffix)
    result = _format_run_ts("2026-05-31T03:04:00.014163+00:00")
    assert len(result) == 16
    assert "T" not in result
    assert "+" not in result


def test_format_run_ts_naive_iso_passthrough():
    result = _format_run_ts("2026-05-30T22:04:00")
    assert result == "2026-05-30 22:04"


def test_format_run_ts_empty_returns_empty():
    assert _format_run_ts("") == ""


def test_format_run_ts_invalid_returns_original():
    assert _format_run_ts("not-a-date") == "not-a-date"


# ------------------------------------------------------------------
# _matches_cron
# ------------------------------------------------------------------

def test_matches_cron_true_at_scheduled_time():
    # 0 2 * * * fires at 02:00 on any day
    dt = datetime(2026, 5, 31, 2, 0, 0)
    assert _matches_cron("0 2 * * *", dt) is True


def test_matches_cron_false_at_wrong_minute():
    dt = datetime(2026, 5, 31, 2, 1, 0)
    assert _matches_cron("0 2 * * *", dt) is False


def test_matches_cron_false_at_wrong_hour():
    dt = datetime(2026, 5, 31, 3, 0, 0)
    assert _matches_cron("0 2 * * *", dt) is False


def test_matches_cron_invalid_returns_false():
    assert _matches_cron("not a cron", datetime.now()) is False


# ------------------------------------------------------------------
# ScheduleEntry defaults
# ------------------------------------------------------------------

def test_schedule_entry_defaults():
    e = ScheduleEntry(op="lint run", cron="0 2 * * *", wiki="mywiki")
    assert e.next_run == ""
    assert e.last_run == ""
    assert e.last_result == ""
    assert e.id.startswith("sched-")


# ------------------------------------------------------------------
# Scheduler — JSON storage
# ------------------------------------------------------------------

def test_scheduler_add_creates_json_entry(tmp_path):
    sched = Scheduler(wiki="mywiki", wiki_root=str(tmp_path))
    entry_id = sched.add(op="lint run", cron="0 2 * * *")
    assert entry_id.startswith("sched-")
    data = json.loads((tmp_path / ".synthadoc" / "schedules.json").read_text())
    assert len(data) == 1
    assert data[0]["id"] == entry_id
    assert data[0]["op"] == "lint run"
    assert data[0]["cron"] == "0 2 * * *"


def test_scheduler_add_multiple_entries(tmp_path):
    sched = Scheduler(wiki="mywiki", wiki_root=str(tmp_path))
    id1 = sched.add(op="lint run", cron="0 2 * * *")
    id2 = sched.add(op="scaffold", cron="0 3 * * 0")
    data = json.loads((tmp_path / ".synthadoc" / "schedules.json").read_text())
    assert len(data) == 2
    assert {d["id"] for d in data} == {id1, id2}


def test_scheduler_remove_deletes_entry(tmp_path):
    sched = Scheduler(wiki="mywiki", wiki_root=str(tmp_path))
    id1 = sched.add(op="lint run", cron="0 2 * * *")
    id2 = sched.add(op="scaffold", cron="0 3 * * 0")
    sched.remove(id1)
    data = json.loads((tmp_path / ".synthadoc" / "schedules.json").read_text())
    assert len(data) == 1
    assert data[0]["id"] == id2


def test_scheduler_remove_nonexistent_is_noop(tmp_path):
    sched = Scheduler(wiki="mywiki", wiki_root=str(tmp_path))
    sched.add(op="lint run", cron="0 2 * * *")
    sched.remove("sched-doesnotexist")
    data = json.loads((tmp_path / ".synthadoc" / "schedules.json").read_text())
    assert len(data) == 1


def test_scheduler_list_returns_entries_with_next_run(tmp_path):
    sched = Scheduler(wiki="mywiki", wiki_root=str(tmp_path))
    sched.add(op="lint run", cron="0 2 * * *")
    entries = sched.list()
    assert len(entries) == 1
    e = entries[0]
    assert e.op == "lint run"
    assert e.cron == "0 2 * * *"
    assert e.next_run != ""   # computed by croniter


def test_scheduler_list_empty_without_file(tmp_path):
    sched = Scheduler(wiki="mywiki", wiki_root=str(tmp_path))
    assert sched.list() == []


def test_scheduler_apply_adds_all_jobs(tmp_path):
    sched = Scheduler(wiki="mywiki", wiki_root=str(tmp_path))
    jobs = [
        ScheduleEntry(op="lint run", cron="0 2 * * *", wiki="mywiki"),
        ScheduleEntry(op="scaffold", cron="0 3 * * 0", wiki="mywiki"),
    ]
    ids = sched.apply(jobs)
    assert len(ids) == 2
    data = json.loads((tmp_path / ".synthadoc" / "schedules.json").read_text())
    assert len(data) == 2


# ------------------------------------------------------------------
# AuditDB scheduled_runs
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_scheduled_run_start(tmp_path):
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.record_scheduled_run_start("run-abc", "lint run", "mywiki", "sched-001")
    runs = await db.list_scheduled_runs()
    assert len(runs) == 1
    assert runs[0]["run_id"] == "run-abc"
    assert runs[0]["entry_id"] == "sched-001"
    assert runs[0]["op"] == "lint run"
    assert runs[0]["status"] == "running"
    assert runs[0]["finished_at"] is None


@pytest.mark.asyncio
async def test_record_scheduled_run_finish_success(tmp_path):
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.record_scheduled_run_start("run-xyz", "lint run", "mywiki", "sched-001")
    await db.record_scheduled_run_finish("run-xyz", "success", 42.5,
                                         output="Checked 42 pages. 0 issues.")
    runs = await db.list_scheduled_runs()
    r = runs[0]
    assert r["status"] == "success"
    assert r["duration_s"] == 42.5
    assert r["error"] is None
    assert r["finished_at"] is not None
    assert r["output"] == "Checked 42 pages. 0 issues."


@pytest.mark.asyncio
async def test_record_scheduled_run_finish_failed(tmp_path):
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.record_scheduled_run_start("run-fail", "lint run", "mywiki", "sched-001")
    await db.record_scheduled_run_finish("run-fail", "failed", 3.2, "exit code 1",
                                         output="partial stdout before crash")
    runs = await db.list_scheduled_runs()
    assert runs[0]["status"] == "failed"
    assert runs[0]["error"] == "exit code 1"
    assert runs[0]["output"] == "partial stdout before crash"


# ------------------------------------------------------------------
# _truncate_output
# ------------------------------------------------------------------

def test_truncate_output_short_passthrough():
    assert _truncate_output("short") == "short"


def test_truncate_output_empty():
    assert _truncate_output("") == ""


def test_truncate_output_at_limit_exact():
    text = "x" * 500
    assert _truncate_output(text) == text


def test_truncate_output_over_limit_appends_ellipsis():
    text = "x" * 501
    result = _truncate_output(text)
    assert result.endswith("…")
    assert len(result) == 501  # 500 chars + ellipsis


@pytest.mark.asyncio
async def test_list_scheduled_runs_ordered_desc(tmp_path):
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    for i in range(3):
        await db.record_scheduled_run_start(f"run-{i}", "lint run", "mywiki", f"sched-{i:03d}")
    runs = await db.list_scheduled_runs()
    assert runs[0]["run_id"] == "run-2"
    assert runs[-1]["run_id"] == "run-0"


@pytest.mark.asyncio
async def test_list_scheduled_runs_respects_limit(tmp_path):
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    for i in range(5):
        await db.record_scheduled_run_start(f"run-{i}", "lint run", "mywiki", f"sched-{i:03d}")
    runs = await db.list_scheduled_runs(limit=3)
    assert len(runs) == 3


@pytest.mark.asyncio
async def test_get_last_run_per_entry(tmp_path):
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    await db.record_scheduled_run_start("run-1", "lint run", "mywiki", "sched-aaa")
    await db.record_scheduled_run_finish("run-1", "success", 10.0)
    await db.record_scheduled_run_start("run-2", "lint run", "mywiki", "sched-aaa")
    await db.record_scheduled_run_finish("run-2", "failed", 1.0, "oops")
    await db.record_scheduled_run_start("run-3", "scaffold", "mywiki", "sched-bbb")
    await db.record_scheduled_run_finish("run-3", "success", 5.0)

    last = await db.get_last_run_per_entry()
    assert last["sched-aaa"]["status"] == "failed"   # most recent for aaa
    assert last["sched-bbb"]["status"] == "success"
