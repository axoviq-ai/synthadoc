# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from synthadoc.core.scheduler import Scheduler, ScheduleEntry, _run_scheduled_job


def test_schedule_entry_parses_cron():
    entry = ScheduleEntry(op="lint", cron="0 3 * * 0", wiki="research")
    assert entry.op == "lint"
    assert entry.cron == "0 3 * * 0"


def test_apply_returns_ids(tmp_path):
    sched = Scheduler(wiki="my-wiki", wiki_root=str(tmp_path))
    jobs = [
        ScheduleEntry(op="lint run", cron="0 2 * * *", wiki="my-wiki"),
        ScheduleEntry(op="ingest run", cron="0 3 * * *", wiki="my-wiki"),
    ]
    ids = sched.apply(jobs)
    assert len(ids) == 2
    assert all(i.startswith("sched-") for i in ids)


def test_scheduler_apply_from_config(tmp_path):
    """schedule apply registers all jobs declared in config.toml."""
    from synthadoc.config import load_config
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        '[agents]\ndefault = { provider = "anthropic", model = "claude-opus-4-6" }\n'
        '[[schedule.jobs]]\nop = "lint"\ncron = "0 3 * * 0"\n'
        '[[schedule.jobs]]\nop = "ingest --batch raw_sources/"\ncron = "0 2 * * *"\n'
    )
    cfg = load_config(project_config=cfg_file)
    assert len(cfg.schedule.jobs) == 2
    assert cfg.schedule.jobs[0].op == "lint"
    assert cfg.schedule.jobs[1].cron == "0 2 * * *"


# ------------------------------------------------------------------
# _run_scheduled_job — subprocess timeout and outcome recording
# ------------------------------------------------------------------

async def test_run_scheduled_job_timeout_kills_proc(tmp_path):
    """Hanging subprocess: TimeoutError kills the process and records 'failed'."""
    audit_db = AsyncMock()

    async def _hang():
        await asyncio.sleep(9999)

    mock_proc = MagicMock()
    mock_proc.kill = MagicMock()
    mock_proc.communicate = _hang

    entry = {"id": "sched-test-timeout", "op": "lint"}

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        await _run_scheduled_job(entry, "test-wiki", tmp_path, audit_db, job_timeout_seconds=0.05)

    mock_proc.kill.assert_called_once()
    call = audit_db.record_scheduled_run_finish.call_args
    assert call.args[1] == "failed"
    assert "timed out" in call.args[3]


async def test_run_scheduled_job_success(tmp_path):
    """Subprocess exits 0: audit records 'success'."""
    audit_db = AsyncMock()

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"all good", b""))

    entry = {"id": "sched-test-ok", "op": "lint"}

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        await _run_scheduled_job(entry, "test-wiki", tmp_path, audit_db, job_timeout_seconds=30)

    call = audit_db.record_scheduled_run_finish.call_args
    assert call.args[1] == "success"


async def test_run_scheduled_job_nonzero_exit(tmp_path):
    """Subprocess exits non-zero: audit records 'failed' with exit code message."""
    audit_db = AsyncMock()

    mock_proc = MagicMock()
    mock_proc.returncode = 2
    mock_proc.communicate = AsyncMock(return_value=(b"", b"something failed"))

    entry = {"id": "sched-test-fail", "op": "ingest"}

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        await _run_scheduled_job(entry, "test-wiki", tmp_path, audit_db, job_timeout_seconds=30)

    call = audit_db.record_scheduled_run_finish.call_args
    assert call.args[1] == "failed"
    assert "exit code 2" in call.args[3]


def test_save_raw_is_atomic(tmp_path):
    """_save_raw writes via a .tmp sibling then renames — no partial file on failure."""
    sched = Scheduler(wiki="test", wiki_root=str(tmp_path))
    sched.add("ingest", "0 2 * * *")

    # The .tmp file must not be left behind after a successful write
    tmp_file = sched._path.with_suffix(".tmp")
    assert not tmp_file.exists()

    # The target file must be valid JSON and contain the entry
    import json
    data = json.loads(sched._path.read_text())
    assert len(data) == 1
    assert data[0]["op"] == "ingest"


def test_save_raw_uses_unix_line_endings(tmp_path):
    """_save_raw must pass newline="\\n" to write_text regardless of platform.

    A binary-mode read catches the symptom on Windows; the write_text spy
    catches a missing newline= argument on Linux/Mac where Python never
    produces CRLF anyway (so the byte check alone would always pass there).
    """
    import pathlib
    from unittest.mock import patch, call

    real_write_text = pathlib.Path.write_text
    calls: list = []

    def spy(self, data, *args, **kwargs):
        calls.append((args, kwargs))
        return real_write_text(self, data, *args, **kwargs)

    sched = Scheduler(wiki="test", wiki_root=str(tmp_path))
    with patch.object(pathlib.Path, "write_text", spy):
        sched.add("ingest", "0 2 * * *")

    # Verify newline="\n" was passed on every write_text call
    for _, kwargs in calls:
        assert kwargs.get("newline") == "\n", "write_text called without newline='\\n'"
    # Also verify the on-disk bytes contain no CRLF
    assert b"\r\n" not in sched._path.read_bytes()
