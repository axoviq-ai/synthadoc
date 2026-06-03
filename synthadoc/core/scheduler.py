# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from synthadoc.storage.log import AuditDB

logger = logging.getLogger("synthadoc.scheduler")


@dataclass
class ScheduleEntry:
    op: str
    cron: str
    wiki: str
    id: str = field(default_factory=lambda: f"sched-{uuid.uuid4().hex[:8]}")
    next_run: str = ""
    last_run: str = ""
    last_result: str = ""


class Scheduler:
    def __init__(self, wiki: str, wiki_root: str) -> None:
        self._wiki = wiki
        self._wiki_root = Path(wiki_root)
        self._path = self._wiki_root / ".synthadoc" / "schedules.json"

    def add(self, op: str, cron: str) -> str:
        entry_id = f"sched-{uuid.uuid4().hex[:8]}"
        entries = self._load_raw()
        entries.append({"id": entry_id, "op": op, "cron": cron, "wiki": self._wiki})
        self._save_raw(entries)
        return entry_id

    def remove(self, entry_id: str) -> None:
        self._save_raw([e for e in self._load_raw() if e["id"] != entry_id])

    def list(self) -> list[ScheduleEntry]:
        raw = self._load_raw()
        last_runs = self._fetch_last_runs()
        result = []
        for e in raw:
            cron = e.get("cron", "")
            lr = last_runs.get(e["id"], {})
            result.append(ScheduleEntry(
                id=e["id"],
                op=e["op"],
                cron=cron,
                wiki=e.get("wiki", self._wiki),
                next_run=_cron_next_run(cron),
                last_run=_format_run_ts(lr.get("started_at", "")),
                last_result=lr.get("status", ""),
            ))
        return result

    def apply(self, jobs: list[ScheduleEntry]) -> list[str]:
        return [self.add(op=j.op, cron=j.cron) for j in jobs]

    # ------------------------------------------------------------------
    # Internal storage
    # ------------------------------------------------------------------

    def _load_raw(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def _save_raw(self, entries: list[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    def _fetch_last_runs(self) -> dict[str, dict]:
        from synthadoc.storage.log import AuditDB
        db = AuditDB(self._wiki_root / ".synthadoc" / "audit.db")

        async def _query():
            await db.init()
            return await db.get_last_run_per_entry()

        coro = _query()
        try:
            return asyncio.run(coro)
        except Exception:
            coro.close()
            return {}


# ------------------------------------------------------------------
# Server-side scheduler loop — runs inside synthadoc serve
# ------------------------------------------------------------------

async def run_scheduler_loop(wiki: str, wiki_root: Path, audit_db: "AuditDB") -> None:
    """Asyncio background task: fire scheduled jobs at their cron times."""
    while True:
        now = datetime.now()
        sleep_secs = max(1.0, 60.0 - now.second - now.microsecond / 1_000_000)
        await asyncio.sleep(sleep_secs)

        now = datetime.now()
        try:
            sched = Scheduler(wiki=wiki, wiki_root=str(wiki_root))
            for entry in sched._load_raw():
                if _matches_cron(entry.get("cron", ""), now):
                    asyncio.create_task(
                        _run_scheduled_job(entry, wiki, wiki_root, audit_db)
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("scheduler loop error: %s", exc)


async def _run_scheduled_job(
    entry: dict, wiki: str, wiki_root: Path, audit_db: "AuditDB"
) -> None:
    """Execute one scheduled job and record the result in the audit DB."""
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    op = entry["op"]
    entry_id = entry["id"]

    await audit_db.record_scheduled_run_start(run_id, op, wiki, entry_id)
    logger.info("[schedule] %s  %s  starting", run_id, op)

    t0 = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "synthadoc", "-w", wiki,
            *op.split(),
            cwd=str(wiki_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        stdout, stderr = await proc.communicate()
        duration = time.monotonic() - t0
        out = _truncate_output(stdout.decode(errors="replace").strip() if stdout else "")

        if proc.returncode == 0:
            await audit_db.record_scheduled_run_finish(run_id, "success", duration, output=out)
            logger.info("[schedule] %s  %s  %.1fs  success", run_id, op, duration)
        else:
            err = f"exit code {proc.returncode}"
            if stderr:
                err += f": {stderr.decode(errors='replace').strip()[:300]}"
            await audit_db.record_scheduled_run_finish(run_id, "failed", duration, err, out)
            logger.warning("[schedule] %s  %s  %.1fs  failed (%s)", run_id, op, duration, err)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        duration = time.monotonic() - t0
        await audit_db.record_scheduled_run_finish(run_id, "failed", duration, str(exc))
        logger.error("[schedule] %s  %s  failed: %s", run_id, op, exc)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

_OUTPUT_LIMIT = 500


def _truncate_output(text: str) -> str:
    if len(text) <= _OUTPUT_LIMIT:
        return text
    return text[:_OUTPUT_LIMIT] + "…"


def _cron_next_run(cron: str) -> str:
    """Return the next scheduled datetime string for a cron expression, or ''."""
    try:
        from croniter import croniter
        it = croniter(cron, datetime.now())
        return it.get_next(datetime).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def _format_run_ts(ts: str) -> str:
    """Convert a stored UTC ISO timestamp to local YYYY-MM-DD HH:MM, or '' on error."""
    if not ts:
        return ""
    try:
        from datetime import timezone
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ts


def _matches_cron(cron: str, dt: datetime) -> bool:
    """Return True if dt (at minute precision) matches the cron expression."""
    try:
        from croniter import croniter
        return croniter.match(cron, dt)
    except Exception:
        return False
