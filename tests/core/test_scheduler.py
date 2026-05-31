# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from synthadoc.core.scheduler import Scheduler, ScheduleEntry


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
