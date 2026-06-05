# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from synthadoc.agents.action_agent import ActionAgent, _format_schedule_list
from synthadoc.agents.lint_agent import LintStateSummary
from synthadoc.providers.base import CompletionResponse


def _make_agent(tmp_path, extraction_json: str):
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=CompletionResponse(
        text=extraction_json, input_tokens=10, output_tokens=5,
    ))
    orch = MagicMock()
    orch.lint = AsyncMock(return_value="job-lint-001")
    orch.ingest = AsyncMock(return_value="job-ingest-001")
    orch._queue = MagicMock()
    orch._queue.enqueue = AsyncMock(return_value="job-scaffold-001")
    orch._store = MagicMock()
    orch._bump_epoch = MagicMock()
    return ActionAgent(provider=provider, orchestrator=orch, wiki_root=tmp_path)


# ── detect ────────────────────────────────────────────────────────────────────

def test_detect_run_lint(tmp_path):
    agent = _make_agent(tmp_path, "{}")
    assert agent.detect("Run a full lint check") is True

def test_detect_run_lint_with_flags(tmp_path):
    agent = _make_agent(tmp_path, "{}")
    assert agent.detect("Run lint with auto-resolve enabled") is True

def test_detect_ingest_url(tmp_path):
    agent = _make_agent(tmp_path, "{}")
    assert agent.detect("Ingest https://example.com/article") is True

def test_detect_scaffold(tmp_path):
    agent = _make_agent(tmp_path, "{}")
    assert agent.detect("Rebuild the wiki scaffold") is True

def test_detect_schedule_add(tmp_path):
    agent = _make_agent(tmp_path, "{}")
    assert agent.detect("Schedule a daily ingest at 6 AM") is True

def test_detect_schedule_list(tmp_path):
    agent = _make_agent(tmp_path, "{}")
    assert agent.detect("Show my scheduled tasks") is True

def test_detect_schedule_add_via_scheduler_noun(tmp_path):
    agent = _make_agent(tmp_path, "{}")
    assert agent.detect("please add a scaffold task to synthadoc scheduler and run it at 7 PM on every Saturday") is True

def test_detect_schedule_add_via_create(tmp_path):
    agent = _make_agent(tmp_path, "{}")
    assert agent.detect("Create a scheduled ingest job for every Monday at 9 AM") is True

def test_detect_schedule_add_via_register(tmp_path):
    agent = _make_agent(tmp_path, "{}")
    assert agent.detect("Register a weekly scaffold in the schedule") is True

def test_detect_schedule_add_chinese_mixed(tmp_path):
    agent = _make_agent(tmp_path, "{}")
    assert agent.detect("请在 Synthadoc 调度器scheduler 添加一个 scaffold 任务，并使其在每周六晚上 7 点运行") is True

def test_detect_schedule_add_chinese_operation_first(tmp_path):
    agent = _make_agent(tmp_path, "{}")
    assert agent.detect("scaffold 任务 每天晚上 scheduler 自动运行") is True

def test_detect_lifecycle_activate(tmp_path):
    agent = _make_agent(tmp_path, "{}")
    assert agent.detect("Activate page grace-hopper") is True

def test_detect_generic_question_returns_false(tmp_path):
    agent = _make_agent(tmp_path, "{}")
    assert agent.detect("What topics does this wiki cover?") is False

def test_detect_how_question_returns_false(tmp_path):
    agent = _make_agent(tmp_path, "{}")
    assert agent.detect("How do I run a lint check?") is False

def test_detect_reingest_question_returns_false(tmp_path):
    agent = _make_agent(tmp_path, "{}")
    assert agent.detect("How do I re-ingest with --force?") is False

def test_detect_ingest_url_still_true(tmp_path):
    agent = _make_agent(tmp_path, "{}")
    assert agent.detect("Ingest https://example.com/article") is True


# ── lint dispatch ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lint_action_enqueues_job(tmp_path):
    extraction = '{"action": "lint", "params": {"scope": "all", "auto_resolve": false}}'
    agent = _make_agent(tmp_path, extraction)
    result = await agent.run("Run a full lint check")
    assert result is not None
    assert result.success is True
    assert result.job_id == "job-lint-001"
    assert "job-lint-001" in result.message

@pytest.mark.asyncio
async def test_lint_auto_resolve_flag_passed(tmp_path):
    extraction = '{"action": "lint", "params": {"scope": "contradictions", "auto_resolve": true}}'
    agent = _make_agent(tmp_path, extraction)
    result = await agent.run("Run lint on contradictions with auto-resolve")
    agent._orch.lint.assert_called_once_with(scope="contradictions", auto_resolve=True)
    assert result.success is True


# ── ingest dispatch ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_action_enqueues_job(tmp_path):
    extraction = '{"action": "ingest", "params": {"source": "https://example.com/doc", "force": false}}'
    agent = _make_agent(tmp_path, extraction)
    result = await agent.run("Ingest https://example.com/doc")
    assert result is not None
    assert result.success is True
    assert "job-ingest-001" in result.message

@pytest.mark.asyncio
async def test_ingest_missing_source_returns_error(tmp_path):
    extraction = '{"action": "ingest", "params": {}}'
    agent = _make_agent(tmp_path, extraction)
    result = await agent.run("Ingest")
    assert result is not None
    assert result.success is False


# ── scaffold dispatch ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scaffold_action_enqueues_job(tmp_path):
    extraction = '{"action": "scaffold", "params": {"domain": ""}}'
    agent = _make_agent(tmp_path, extraction)
    result = await agent.run("Rebuild the wiki scaffold")
    assert result is not None
    assert result.success is True
    assert "job-scaffold-001" in result.message


# ── schedule dispatch ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_schedule_add(tmp_path):
    extraction = ('{"action": "schedule_add", "params": {'
                  '"op": "ingest --batch sources/", "cron": "0 6 * * *",'
                  '"schedule_description": "daily at 6 AM"}}')
    agent = _make_agent(tmp_path, extraction)
    result = await agent.run("Schedule a daily ingest at 6 AM")
    assert result is not None
    assert result.success is True
    assert "0 6 * * *" in result.message

@pytest.mark.asyncio
async def test_schedule_list_empty(tmp_path):
    extraction = '{"action": "schedule_list", "params": {}}'
    agent = _make_agent(tmp_path, extraction)
    result = await agent.run("Show my scheduled tasks")
    assert result is not None
    assert result.success is True
    assert "none" in result.message.lower() or "scheduled" in result.message.lower()


# ── lint_report dispatch ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lint_report_action_all_clear(tmp_path):
    extraction = '{"action": "lint_report", "params": {}}'
    agent = _make_agent(tmp_path, extraction)
    with patch("synthadoc.agents.lint_agent.read_current_lint_state") as mock_rcs:
        mock_rcs.return_value = LintStateSummary(contradicted=[], orphans=[], adv_pages=[])
        result = await agent.run("please run synthadoc lint report")
    assert result is not None
    assert result.success is True
    assert "all clear" in result.message.lower()


@pytest.mark.asyncio
async def test_lint_report_action_with_issues(tmp_path):
    extraction = '{"action": "lint_report", "params": {}}'
    agent = _make_agent(tmp_path, extraction)
    with patch("synthadoc.agents.lint_agent.read_current_lint_state") as mock_rcs:
        mock_rcs.return_value = LintStateSummary(
            contradicted=["page-a"],
            orphans=["page-b"],
            adv_pages=[{"slug": "page-c", "warnings": [{"claim": "x", "concern": "y"}]}],
        )
        result = await agent.run("please run synthadoc lint report")
    assert result is not None
    assert result.success is True
    assert "page-a" in result.message
    assert "page-b" in result.message
    assert "page-c" in result.message


# ── none action ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_none_action_returns_none(tmp_path):
    extraction = '{"action": "none", "params": {}}'
    agent = _make_agent(tmp_path, extraction)
    result = await agent.run("What is the capital of France?")
    assert result is None


# ── schedule_history dispatch ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_schedule_history_no_audit_db(tmp_path):
    """Returns graceful message when audit.db doesn't exist yet."""
    extraction = '{"action": "schedule_history", "params": {}}'
    agent = _make_agent(tmp_path, extraction)
    result = await agent.run("show scheduler history")
    assert result is not None
    assert result.success is True
    assert "no scheduled run history" in result.message.lower()


@pytest.mark.asyncio
async def test_schedule_history_with_runs(tmp_path):
    extraction = '{"action": "schedule_history", "params": {}}'
    agent = _make_agent(tmp_path, extraction)
    audit_path = tmp_path / ".synthadoc" / "audit.db"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.touch()
    mock_runs = [
        {"run_id": "r1", "op": "lint run", "started_at": "2026-06-04T09:00:00",
         "duration_s": 12.5, "status": "success", "error": None},
        {"run_id": "r2", "op": "ingest", "started_at": "2026-06-04T10:00:00",
         "duration_s": None, "status": "failed", "error": "timeout"},
    ]
    with patch("synthadoc.storage.log.AuditDB") as MockAudit:
        inst = AsyncMock()
        inst.init = AsyncMock()
        inst.list_scheduled_runs = AsyncMock(return_value=mock_runs)
        MockAudit.return_value = inst
        result = await agent.run("show scheduler history")
    assert result is not None
    assert result.success is True
    assert "r1" in result.message
    assert "lint run" in result.message
    assert "❌" in result.message  # failed run shows error icon


# ── wiki_status dispatch ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_wiki_status_no_audit_db(tmp_path):
    """Falls back to page count when audit.db absent."""
    extraction = '{"action": "wiki_status", "params": {}}'
    agent = _make_agent(tmp_path, extraction)
    agent._orch._store.list_pages.return_value = ["page-a", "page-b"]
    result = await agent.run("show wiki status")
    assert result is not None
    assert result.success is True
    assert "2 pages" in result.message


@pytest.mark.asyncio
async def test_wiki_status_with_audit_db(tmp_path):
    extraction = '{"action": "wiki_status", "params": {}}'
    agent = _make_agent(tmp_path, extraction)
    audit_path = tmp_path / ".synthadoc" / "audit.db"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.touch()
    counts = {"draft": 3, "active": 42, "stale": 5, "contradicted": 2, "archived": 1}
    with patch("synthadoc.storage.log.AuditDB") as MockAudit:
        inst = AsyncMock()
        inst.init = AsyncMock()
        inst.get_lifecycle_summary = AsyncMock(return_value=counts)
        MockAudit.return_value = inst
        result = await agent.run("show wiki status")
    assert result is not None
    assert result.success is True
    assert "active" in result.message
    assert "42" in result.message
    assert "53 pages" in result.message


# ── detect: orphan / contradiction / lint-report ──────────────────────────────

def test_detect_orphan_pages_query(tmp_path):
    agent = _make_agent(tmp_path, "{}")
    assert agent.detect("What pages in this wiki domain are orphan pages?") is True

def test_detect_show_contradictions(tmp_path):
    agent = _make_agent(tmp_path, "{}")
    assert agent.detect("list contradicted pages") is True

def test_detect_adversarial_pages(tmp_path):
    agent = _make_agent(tmp_path, "{}")
    assert agent.detect("are there any adversarial pages?") is True

def test_detect_lint_report(tmp_path):
    agent = _make_agent(tmp_path, "{}")
    assert agent.detect("show lint report") is True

def test_detect_wiki_status(tmp_path):
    agent = _make_agent(tmp_path, "{}")
    assert agent.detect("show synthadoc status") is True

def test_detect_what_contradictions(tmp_path):
    agent = _make_agent(tmp_path, "{}")
    assert agent.detect("what contradictions exist?") is True


# ── schedule_add lint normalisation ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_schedule_add_normalises_lint_op(tmp_path):
    """'lint' op is normalised to 'lint run' before saving."""
    extraction = ('{"action": "schedule_add", "params": {'
                  '"op": "lint", "cron": "0 21 * * *",'
                  '"schedule_description": "every night at 9 PM"}}')
    agent = _make_agent(tmp_path, extraction)
    result = await agent.run("Schedule lint run every night at 9 PM")
    assert result is not None
    assert result.success is True
    assert "lint run" in result.message


# ── format helper ─────────────────────────────────────────────────────────────

def test_format_schedule_list_empty():
    assert "none" in _format_schedule_list([]).lower()

def test_format_schedule_list_with_entries():
    entry = MagicMock()
    entry.id = "sched-abc"
    entry.op = "ingest --batch sources/"
    entry.cron = "0 6 * * *"
    entry.next_run = "2026-06-04 06:00"
    entry.last_result = "success"
    result = _format_schedule_list([entry])
    assert "sched-abc" in result
    assert "0 6 * * *" in result
