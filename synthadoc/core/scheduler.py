# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import platform
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


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
    _TAG_PREFIX = "# synthadoc:"

    def __init__(self, wiki: str, wiki_root: str) -> None:
        self._wiki = wiki
        self._wiki_root = wiki_root

    def add(self, op: str, cron: str) -> str:
        entry_id = f"sched-{uuid.uuid4().hex[:8]}"
        self._register_os_task(op=op, cron=cron, entry_id=entry_id)
        return entry_id

    def list(self) -> list[ScheduleEntry]:
        return self._list_os_tasks()

    def remove(self, entry_id: str) -> None:
        self._remove_os_task(entry_id)

    def apply(self, jobs: list[ScheduleEntry]) -> list[str]:
        return [self.add(op=j.op, cron=j.cron) for j in jobs]

    # ------------------------------------------------------------------
    # OS task registration
    # ------------------------------------------------------------------

    def _register_os_task(self, op: str, cron: str, entry_id: str) -> None:
        if platform.system() == "Windows":
            args = self._build_schtasks_args(op=op, cron=cron, entry_id=entry_id)
            subprocess.run(["schtasks"] + args, check=True)
        else:
            self._add_crontab_entry(op=op, cron=cron, entry_id=entry_id)

    def _build_run_cmd(self, op: str) -> str:
        return f'synthadoc -w {self._wiki} schedule run --op "{op}"'

    def _build_crontab_line(self, op: str, cron: str, entry_id: str) -> str:
        cmd = self._build_run_cmd(op)
        return f"{cron} {cmd} {self._TAG_PREFIX}{entry_id}"

    def _add_crontab_entry(self, op: str, cron: str, entry_id: str) -> None:
        current = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        existing = current.stdout if current.returncode == 0 else ""
        new_line = self._build_crontab_line(op=op, cron=cron, entry_id=entry_id)
        updated = existing.rstrip("\n") + "\n" + new_line + "\n"
        subprocess.run(["crontab", "-"], input=updated, text=True, check=True)

    def _build_schtasks_args(self, op: str, cron: str, entry_id: str) -> list[str]:
        parts = cron.split()
        minute, hour = parts[0], parts[1]
        cmd = self._build_run_cmd(op)
        return [
            "/Create", "/F",
            "/TN", f"synthadoc-{entry_id}",
            "/TR", cmd,
            "/SC", "DAILY",
            "/ST", f"{int(hour):02d}:{int(minute):02d}",
        ]

    # ------------------------------------------------------------------
    # OS task listing
    # ------------------------------------------------------------------

    def _list_os_tasks(self) -> list[ScheduleEntry]:
        if platform.system() == "Windows":
            return self._list_schtasks()
        return self._list_crontab()

    def _list_crontab(self) -> list[ScheduleEntry]:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        entries = []
        for line in result.stdout.splitlines():
            if self._TAG_PREFIX not in line:
                continue
            entry_id = line.split(self._TAG_PREFIX)[-1].strip()
            parts = line.split()
            cron = " ".join(parts[:5])
            op_parts = parts[5:]
            tag = self._TAG_PREFIX.strip()
            op = " ".join(p for p in op_parts if not p.startswith(tag))
            next_run = _cron_next_run(cron)
            entries.append(ScheduleEntry(
                id=entry_id, op=op.strip(), cron=cron,
                wiki=self._wiki, next_run=next_run,
            ))
        return entries

    def _list_schtasks(self) -> list[ScheduleEntry]:
        result = subprocess.run(
            ["schtasks", "/Query", "/FO", "LIST", "/V"],
            capture_output=True, text=True,
        )
        entries = []
        current: dict = {}

        def _flush(d: dict) -> None:
            if "id" in d and "op" in d:
                result_raw = d.get("last_result", "")
                last_result = (
                    "success" if result_raw == "0"
                    else ("N/A" if result_raw in ("", "267011") else f"failed ({result_raw})")
                )
                cron = d.get("cron", "")
                next_run = d.get("next_run", "")
                if next_run in ("N/A", ""):
                    next_run = _cron_next_run(cron)
                entries.append(ScheduleEntry(
                    id=d["id"],
                    op=d["op"],
                    cron=cron,
                    wiki=self._wiki,
                    next_run=next_run,
                    last_run=d.get("last_run", ""),
                    last_result=last_result,
                ))

        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if line.startswith("TaskName:"):
                _flush(current)
                current = (
                    {"id": line.split("synthadoc-")[-1].strip()}
                    if "synthadoc-" in line else {}
                )
            elif current:
                if line.startswith("Task To Run:"):
                    current["op"] = line.split(":", 1)[-1].strip()
                elif line.startswith("Next Run Time:"):
                    current["next_run"] = line.split(":", 1)[-1].strip()
                elif line.startswith("Last Run Time:"):
                    val = line.split(":", 1)[-1].strip()
                    current["last_run"] = "" if val == "N/A" else val
                elif line.startswith("Last Result:"):
                    current["last_result"] = line.split(":", 1)[-1].strip()
                elif line.startswith("Start Time:"):
                    time_str = line.split(":", 1)[-1].strip()
                    current["cron"] = _schtasks_time_to_cron(time_str)

        _flush(current)
        return entries

    # ------------------------------------------------------------------
    # OS task removal
    # ------------------------------------------------------------------

    def _remove_os_task(self, entry_id: str) -> None:
        if platform.system() == "Windows":
            subprocess.run(
                ["schtasks", "/Delete", "/TN", f"synthadoc-{entry_id}", "/F"],
                check=True,
            )
        else:
            result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            lines = [ln for ln in result.stdout.splitlines()
                     if f"{self._TAG_PREFIX}{entry_id}" not in ln]
            subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n",
                           text=True, check=True)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _cron_next_run(cron: str) -> str:
    """Return the next scheduled datetime string for a cron expression, or ''."""
    try:
        from croniter import croniter
        it = croniter(cron, datetime.now(timezone.utc))
        return it.get_next(datetime).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def _schtasks_time_to_cron(time_str: str) -> str:
    """Convert a schtasks Start Time string (e.g. '2:00:00 AM') to a cron expression."""
    for fmt in ("%I:%M:%S %p", "%H:%M:%S", "%I:%M %p", "%H:%M"):
        try:
            t = datetime.strptime(time_str.strip(), fmt)
            return f"{t.minute} {t.hour} * * *"
        except ValueError:
            continue
    return ""
