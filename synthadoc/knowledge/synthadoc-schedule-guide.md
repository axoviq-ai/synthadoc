---
title: Synthadoc Schedule Guide
keywords: [schedule, scheduled, recurring, cron, scheduler, remove, delete, unschedule, add, list, automate, job, task, weekly, daily, nightly, schedule history, job history]
---

# Synthadoc Schedule Guide

The `synthadoc schedule` commands register recurring operations with the OS scheduler (crontab on macOS/Linux, Task Scheduler on Windows). No background daemon is required — the OS fires the job, which runs `synthadoc serve` internally.

---

## Add a scheduled job

```bash
synthadoc schedule add --op "<operation>" --cron "<cron-expression>"
```

Examples:

```bash
# Scaffold every Sunday at 11 PM
synthadoc schedule add --op "scaffold" --cron "0 23 * * 0"

# Lint run every night at 9 PM
synthadoc schedule add --op "lint run" --cron "0 21 * * *"

# Batch ingest every night at 2 AM
synthadoc schedule add --op "ingest --batch raw_sources/" --cron "0 2 * * *"

# Scaffold every Saturday at 7 PM
synthadoc schedule add --op "scaffold" --cron "0 19 * * 6"
```

**Common cron expressions:**

| Schedule | Cron |
|---|---|
| Every night at 9 PM | `0 21 * * *` |
| Every Sunday at 11 PM | `0 23 * * 0` |
| Every Saturday at 7 PM | `0 19 * * 6` |
| Daily at 6 AM | `0 6 * * *` |
| Every weekday at 9 AM | `0 9 * * 1-5` |
| Every hour | `0 * * * *` |

From the web chat UI, you can use natural language — no cron syntax required:

```
Schedule scaffold every Sunday at 11 PM
Schedule lint run every night at 9 PM
```

---

## List scheduled jobs

```bash
synthadoc schedule list
```

Shows all registered jobs with ID, cron expression, next run time, last run time, and last result.

---

## Remove a scheduled job

```bash
synthadoc schedule remove <schedule-id>
```

Replace `<schedule-id>` with the ID shown by `synthadoc schedule list`. Example:

```bash
synthadoc schedule list
# → sched-a3f1b2c4   0 23 * * 0   2026-06-08 23:00   —   scaffold

synthadoc schedule remove sched-a3f1b2c4
# → Removed: sched-a3f1b2c4
```

---

## View run history

```bash
synthadoc schedule history
```

Shows recent scheduled runs — run ID, operation, start time, duration, and status (`success` or `failed`). Failed runs include the error message so you can diagnose without checking log files.

---

## Apply jobs from config.toml

You can declare schedules in `<wiki-root>/.synthadoc/config.toml` and register them all at once:

```toml
[[schedule.jobs]]
op   = "ingest --batch raw_sources/"
cron = "0 2 * * *"

[[schedule.jobs]]
op   = "lint run"
cron = "0 21 * * *"

[[schedule.jobs]]
op   = "scaffold"
cron = "0 23 * * 0"
```

```bash
synthadoc schedule apply
```

---

## Notes

- If the machine is asleep or the server is down when a job fires, the run is skipped — check `synthadoc schedule history` for missed runs and re-run manually with `synthadoc schedule run --op "<operation>"`.
- Each `-w <wiki>` flag (or active wiki set via `synthadoc use`) determines which wiki the scheduled job targets.
