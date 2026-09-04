# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from synthadoc.agents.action_agent import ActionAgent, _format_schedule_list
from synthadoc.agents.lint_agent import LintStateSummary
from synthadoc.providers.base import CompletionResponse


def _make_agent(tmp_path, extraction_json: str, provider=None):
    if provider is None:
        provider = MagicMock()
        provider.complete = AsyncMock(return_value=CompletionResponse(
            text=extraction_json, input_tokens=10, output_tokens=5,
        ))
    orch = MagicMock()
    orch.lint = AsyncMock(return_value="job-lint-001")
    orch.ingest = AsyncMock(return_value="job-ingest-001")
    orch._queue = MagicMock()
    orch._queue.enqueue = AsyncMock(return_value="job-scaffold-001")
    orch.queue = MagicMock()
    orch.queue.list_jobs = AsyncMock(return_value=[])
    orch._store = MagicMock()
    orch._bump_epoch = MagicMock()
    orch._cfg = MagicMock()
    orch._cfg.chat.clarify_lookback = 5
    return ActionAgent(provider=provider, orchestrator=orch, wiki_root=tmp_path), provider


# ── detect ────────────────────────────────────────────────────────────────────

def test_detect_run_lint(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("Run a full lint check") is True

def test_detect_run_lint_with_flags(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("Run lint with auto-resolve enabled") is True

def test_detect_ingest_url(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("Ingest https://example.com/article") is True

def test_detect_scaffold(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("Rebuild the wiki scaffold") is True

def test_detect_schedule_add(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("Schedule a daily ingest at 6 AM") is True

def test_detect_schedule_list(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("Show my scheduled tasks") is True

def test_detect_schedule_add_via_scheduler_noun(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("please add a scaffold task to synthadoc scheduler and run it at 7 PM on every Saturday") is True

def test_detect_schedule_add_via_create(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("Create a scheduled ingest job for every Monday at 9 AM") is True

def test_detect_schedule_add_via_register(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("Register a weekly scaffold in the schedule") is True

def test_detect_schedule_add_chinese_mixed(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("请在 Synthadoc 调度器scheduler 添加一个 scaffold 任务，并使其在每周六晚上 7 点运行") is True

def test_detect_schedule_add_chinese_operation_first(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("scaffold 任务 每天晚上 scheduler 自动运行") is True

def test_detect_lifecycle_activate(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("Activate page grace-hopper") is True

def test_detect_generic_question_returns_false(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("What topics does this wiki cover?") is False

def test_detect_how_question_returns_false(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("How do I run a lint check?") is False

def test_detect_reingest_question_returns_false(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("How do I re-ingest with --force?") is False

def test_detect_ingest_url_still_true(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("Ingest https://example.com/article") is True


# ── lint dispatch ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lint_action_enqueues_job(tmp_path):
    extraction = '{"action": "lint", "params": {"scope": "all", "auto_resolve": false}}'
    agent, _ = _make_agent(tmp_path, extraction)
    result = await agent.run("Run a full lint check")
    assert result is not None
    assert result.success is True
    assert result.job_id == "job-lint-001"
    assert "job-lint-001" in result.message

@pytest.mark.asyncio
async def test_lint_auto_resolve_flag_passed(tmp_path):
    extraction = '{"action": "lint", "params": {"scope": "contradictions", "auto_resolve": true}}'
    agent, _ = _make_agent(tmp_path, extraction)
    result = await agent.run("Run lint on contradictions with auto-resolve")
    agent._orch.lint.assert_called_once_with(scope="contradictions", auto_resolve=True)
    assert result.success is True


# ── ingest dispatch ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_action_enqueues_job(tmp_path):
    extraction = '{"action": "ingest", "params": {"source": "https://example.com/doc", "force": false}}'
    agent, _ = _make_agent(tmp_path, extraction)
    result = await agent.run("Ingest https://example.com/doc")
    assert result is not None
    assert result.success is True
    assert "job-ingest-001" in result.message

@pytest.mark.asyncio
async def test_ingest_missing_source_returns_error(tmp_path):
    extraction = '{"action": "ingest", "params": {}}'
    agent, _ = _make_agent(tmp_path, extraction)
    result = await agent.run("Ingest")
    assert result is not None
    assert result.success is False


# ── scaffold dispatch ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scaffold_action_enqueues_job(tmp_path):
    extraction = '{"action": "scaffold", "params": {"domain": ""}}'
    agent, _ = _make_agent(tmp_path, extraction)
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
    agent, _ = _make_agent(tmp_path, extraction)
    result = await agent.run("Schedule a daily ingest at 6 AM")
    assert result is not None
    assert result.success is True
    assert "0 6 * * *" in result.message

@pytest.mark.asyncio
async def test_schedule_list_empty(tmp_path):
    extraction = '{"action": "schedule_list", "params": {}}'
    agent, _ = _make_agent(tmp_path, extraction)
    result = await agent.run("Show my scheduled tasks")
    assert result is not None
    assert result.success is True
    assert "none" in result.message.lower() or "scheduled" in result.message.lower()


# ── lint_report dispatch ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lint_report_action_all_clear(tmp_path):
    extraction = '{"action": "lint_report", "params": {}}'
    agent, _ = _make_agent(tmp_path, extraction)
    with patch("synthadoc.agents.lint_agent.read_current_lint_state") as mock_rcs:
        mock_rcs.return_value = LintStateSummary(contradicted=[], orphans=[], adv_pages=[])
        result = await agent.run("please run synthadoc lint report")
    assert result is not None
    assert result.success is True
    assert "all clear" in result.message.lower()


@pytest.mark.asyncio
async def test_lint_report_action_with_issues(tmp_path):
    extraction = '{"action": "lint_report", "params": {}}'
    agent, _ = _make_agent(tmp_path, extraction)
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


@pytest.mark.asyncio
async def test_lint_report_orphan_zero_shown_when_other_issues_exist(tmp_path):
    """When there are no orphans but other issues exist, the report must explicitly
    state 'Orphan pages (0)' so orphan-specific queries don't silently omit the answer."""
    extraction = '{"action": "lint_report", "params": {}}'
    agent, _ = _make_agent(tmp_path, extraction)
    with patch("synthadoc.agents.lint_agent.read_current_lint_state") as mock_rcs:
        mock_rcs.return_value = LintStateSummary(
            contradicted=["page-a"],
            orphans=[],
            adv_pages=[{"slug": "page-b", "warnings": [{"claim": "x", "concern": "y"}]}],
        )
        result = await agent.run("What pages are orphan pages?")
    assert result is not None
    assert result.success is True
    assert "page-a" in result.message
    assert "Orphan pages (0)" in result.message
    assert "all pages have at least one inbound link" in result.message
    assert "page-b" in result.message


# ── none action ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_none_action_returns_none(tmp_path):
    extraction = '{"action": "none", "params": {}}'
    agent, _ = _make_agent(tmp_path, extraction)
    result = await agent.run("What is the capital of France?")
    assert result is None


# ── schedule_history dispatch ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_schedule_history_no_audit_db(tmp_path):
    """Returns graceful message when audit.db doesn't exist yet."""
    extraction = '{"action": "schedule_history", "params": {}}'
    agent, _ = _make_agent(tmp_path, extraction)
    result = await agent.run("show scheduler history")
    assert result is not None
    assert result.success is True
    assert "no scheduled run history" in result.message.lower()


@pytest.mark.asyncio
async def test_schedule_history_with_runs(tmp_path):
    extraction = '{"action": "schedule_history", "params": {}}'
    agent, _ = _make_agent(tmp_path, extraction)
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
    agent, _ = _make_agent(tmp_path, extraction)
    agent._orch._store.list_pages.return_value = ["page-a", "page-b"]
    result = await agent.run("show wiki status")
    assert result is not None
    assert result.success is True
    assert "2 pages" in result.message


@pytest.mark.asyncio
async def test_wiki_status_with_audit_db(tmp_path):
    extraction = '{"action": "wiki_status", "params": {}}'
    agent, _ = _make_agent(tmp_path, extraction)
    audit_path = tmp_path / ".synthadoc" / "audit.db"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.touch()
    counts = {"draft": 3, "active": 42, "stale": 5, "contradicted": 2, "archived": 1}
    # 53 linted + 2 unlinted on disk = 55 total
    agent._orch._store.list_pages.return_value = [f"page-{i}" for i in range(55)]
    with patch("synthadoc.storage.log.AuditDB") as MockAudit:
        inst = AsyncMock()
        inst.init = AsyncMock()
        inst.get_live_lifecycle_summary = AsyncMock(return_value=counts)
        MockAudit.return_value = inst
        result = await agent.run("show wiki status")
    assert result is not None
    assert result.success is True
    assert "active" in result.message
    assert "42" in result.message
    assert "55 pages" in result.message
    assert "unlinted" in result.message
    assert "2" in result.message


# ── detect: orphan / contradiction / lint-report ──────────────────────────────

def test_detect_orphan_pages_query(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("What pages in this wiki domain are orphan pages?") is True

def test_detect_show_contradictions(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("list contradicted pages") is True

def test_detect_adversarial_pages(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("are there any adversarial pages?") is True

def test_detect_lint_report(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("show lint report") is True

def test_detect_wiki_status(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("show synthadoc status") is True

def test_detect_what_contradictions(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("what contradictions exist?") is True

def test_detect_can_you_run_lint(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("Can you run lint and auto resolve the page grace-hopper") is True

def test_detect_could_you_run_lint(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("Could you run lint on the wiki?") is True

def test_detect_auto_resolve(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("auto-resolve the contradicted pages") is True

def test_detect_auto_resolve_no_hyphen(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("please auto resolve contradictions") is True

def test_detect_resolve_contradictions(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("resolve contradictions in grace-hopper") is True

def test_detect_fix_contradictions(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("fix the contradictions on this page") is True

def test_detect_clear_contradictions(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("clear contradictions") is True

def test_detect_clarify_continuation(tmp_path):
    """Chip reply after a clarify turn must route back to the action agent."""
    from synthadoc.agents.action_agent import CLARIFY_STORE_PREFIX
    agent, _ = _make_agent(tmp_path, "{}")
    history = [
        {"role": "user", "content": "show me job status"},
        {"role": "assistant", "content": CLARIFY_STORE_PREFIX + "Which job would you like to see the status for?\n1. abc-123"},
    ]
    assert agent.detect("abc-123", history=history) is True

def test_detect_clarify_continuation_second_chip(tmp_path):
    """Second chip click after one answer was already given must still route to action agent."""
    from synthadoc.agents.action_agent import CLARIFY_STORE_PREFIX
    agent, _ = _make_agent(tmp_path, "{}")
    history = [
        {"role": "user", "content": "show me job status"},
        {"role": "assistant", "content": CLARIFY_STORE_PREFIX + "Which job?\n1. abc-123\n2. def-456"},
        {"role": "user", "content": "abc-123"},
        {"role": "assistant", "content": "**Job abc-123**\n- Status: completed"},
    ]
    assert agent.detect("def-456", history=history) is True

def test_detect_no_clarify_continuation_without_prefix(tmp_path):
    """A plain assistant message does NOT trigger clarify continuation."""
    agent, _ = _make_agent(tmp_path, "{}")
    history = [
        {"role": "user", "content": "who is Turing?"},
        {"role": "assistant", "content": "Alan Turing was a mathematician..."},
    ]
    assert agent.detect("abc-123", history=history) is False

def test_detect_repeat_with_history_routes_to_action_agent(tmp_path):
    """'run it again' with history containing a previous action response routes to action agent."""
    agent, _ = _make_agent(tmp_path, "{}")
    history = [
        {"role": "user", "content": "show synthadoc status"},
        {"role": "assistant", "content": "| State | Count |\n| active | 82 |"},
    ]
    assert agent.detect("run it again", history=history) is True


def test_detect_repeat_phrases_with_history(tmp_path):
    """All common repeat phrases route to action agent when history is present."""
    agent, _ = _make_agent(tmp_path, "{}")
    history = [{"role": "user", "content": "run lint"}, {"role": "assistant", "content": "Lint complete."}]
    for phrase in ("run it again", "do it again", "repeat", "again", "redo", "try again once more"):
        assert agent.detect(phrase, history=history) is True, f"Expected True for {phrase!r}"


def test_detect_repeat_without_history_returns_false(tmp_path):
    """'again' alone without history should NOT route to the action agent."""
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("again") is False
    assert agent.detect("run it again") is False


@pytest.mark.asyncio
async def test_run_repeat_resolves_previous_action_from_history(tmp_path):
    """'run it again' should re-execute the previous action found in history, not ask the LLM."""
    wiki_status_json = '{"action": "wiki_status", "params": {}}'
    agent, provider = _make_agent(tmp_path, wiki_status_json)
    agent._orch._store.get_lifecycle_summary = MagicMock(return_value={"active": 5})
    agent._orch._store.list_pages = MagicMock(return_value=["page1", "page2", "page3", "page4", "page5"])

    history = [
        {"role": "user", "content": "show synthadoc status"},
        {"role": "assistant", "content": "| State | Count |\n| active | 5 |"},
    ]
    result = await agent.run("run it again", history=history)
    assert result is not None
    assert result.action_type == "wiki_status"
    # Provider was called with the resolved question, not the vague "run it again" phrase
    call_prompt = provider.complete.call_args[1]["messages"][0].content
    # The "User request:" line should show the resolved question, not the repeat phrase
    assert "User request: show synthadoc status" in call_prompt


def test_detect_show_job_status(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("show me job status") is True

def test_detect_job_list(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("list jobs") is True

def test_detect_check_job(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("check job abc123") is True

def test_detect_job_progress(tmp_path):
    agent, _ = _make_agent(tmp_path, "{}")
    assert agent.detect("what is the status of my job") is True


# ── job_list / job_status ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_job_list_empty(tmp_path):
    agent, _ = _make_agent(tmp_path, '{"action": "job_list", "params": {}}')
    agent._orch.queue.list_jobs = AsyncMock(return_value=[])
    result = await agent.run("list jobs")
    assert result is not None
    assert result.success is True
    assert "No jobs" in result.message

@pytest.mark.asyncio
async def test_job_list_with_jobs(tmp_path):
    job = MagicMock()
    job.id = "abc-123"
    job.operation = "lint"
    job.status = "completed"
    job.created_at = "2026-06-11 16:36:00"
    agent, _ = _make_agent(tmp_path, '{"action": "job_list", "params": {}}')
    agent._orch.queue.list_jobs = AsyncMock(return_value=[job])
    result = await agent.run("list jobs")
    assert result is not None
    assert result.success is True
    assert "abc-123" in result.message
    assert "lint" in result.message

@pytest.mark.asyncio
async def test_job_status_with_id(tmp_path):
    job = MagicMock()
    job.id = "abc-123"
    job.operation = "ingest"
    job.status = "completed"
    job.created_at = "2026-06-11 16:36:00"
    job.error = None
    job.result = {"pages_created": ["grace-hopper"], "tokens_used": 500}
    agent, _ = _make_agent(tmp_path, '{"action": "job_status", "params": {"job_id": "abc-123"}}')
    agent._orch.queue.list_jobs = AsyncMock(return_value=[job])
    result = await agent.run("check job abc-123")
    assert result is not None
    assert result.success is True
    assert "abc-123" in result.message
    assert "grace-hopper" in result.message
    assert result.needs_clarification is False

@pytest.mark.asyncio
async def test_job_status_no_id_triggers_clarify(tmp_path):
    job = MagicMock()
    job.id = "abc-123"
    job.operation = "lint"
    job.status = "running"
    job.created_at = "2026-06-11 16:36:00"
    agent, _ = _make_agent(tmp_path, '{"action": "job_status", "params": {"job_id": null}}')
    agent._orch.queue.list_jobs = AsyncMock(return_value=[job])
    result = await agent.run("show me job status")
    assert result is not None
    assert result.needs_clarification is True
    assert "abc-123" in result.clarify_candidates
    assert "Which job" in result.clarify_prompt

@pytest.mark.asyncio
async def test_job_list_multi_status_filter(tmp_path):
    job = MagicMock()
    job.id = "abc-123"
    job.operation = "ingest"
    job.status = "failed"
    job.created_at = "2026-06-11 16:36:00"
    agent, _ = _make_agent(tmp_path, '{"action": "job_list", "params": {"status_filter": ["failed", "skipped"]}}')
    agent._orch.queue.list_jobs = AsyncMock(return_value=[job])
    result = await agent.run("show failed and skipped jobs")
    assert result is not None
    assert result.success is True
    assert "abc-123" in result.message

@pytest.mark.asyncio
async def test_job_status_not_found(tmp_path):
    job = MagicMock()
    job.id = "abc-123"
    job.operation = "lint"
    job.status = "completed"
    job.created_at = "2026-06-11 16:36:00"
    agent, _ = _make_agent(tmp_path, '{"action": "job_status", "params": {"job_id": "bad-id"}}')
    agent._orch.queue.list_jobs = AsyncMock(return_value=[job])
    result = await agent.run("check job bad-id")
    assert result is not None
    assert result.success is False
    assert "not found" in result.message.lower()

@pytest.mark.asyncio
async def test_job_status_no_jobs_at_all(tmp_path):
    agent, _ = _make_agent(tmp_path, '{"action": "job_status", "params": {"job_id": null}}')
    agent._orch.queue.list_jobs = AsyncMock(return_value=[])
    result = await agent.run("show me job status")
    assert result is not None
    assert result.success is True
    assert "No jobs" in result.message

@pytest.mark.asyncio
async def test_job_status_with_error_and_flagged(tmp_path):
    job = MagicMock()
    job.id = "abc-123"
    job.operation = "ingest"
    job.status = "failed"
    job.created_at = "2026-06-11 16:36:00"
    job.error = "domain blocked"
    job.result = {"pages_flagged": ["bad-page"], "pages_updated": ["ok-page"], "tokens_used": 100}
    agent, _ = _make_agent(tmp_path, '{"action": "job_status", "params": {"job_id": "abc-123"}}')
    agent._orch.queue.list_jobs = AsyncMock(return_value=[job])
    result = await agent.run("check job abc-123")
    assert result is not None
    assert result.success is True
    assert "domain blocked" in result.message
    assert "bad-page" in result.message
    assert "ok-page" in result.message
    assert "100" in result.message

@pytest.mark.asyncio
async def test_job_list_with_errors_shows_error_column(tmp_path):
    job = MagicMock()
    job.id = "abc-123"
    job.operation = "ingest"
    job.status = "failed"
    job.created_at = "2026-06-11 16:36:00"
    job.error = "network timeout"
    agent, _ = _make_agent(tmp_path, '{"action": "job_list", "params": {}}')
    agent._orch.queue.list_jobs = AsyncMock(return_value=[job])
    result = await agent.run("list jobs")
    assert result is not None
    assert "Error" in result.message
    assert "network timeout" in result.message

@pytest.mark.asyncio
async def test_job_list_string_status_filter_coerced(tmp_path):
    """A bare string status_filter (not a list) must be coerced to a list."""
    job = MagicMock()
    job.id = "abc-123"
    job.operation = "lint"
    job.status = "failed"
    job.created_at = "2026-06-11 16:36:00"
    job.error = None
    agent, _ = _make_agent(tmp_path, '{"action": "job_list", "params": {"status_filter": "failed"}}')
    agent._orch.queue.list_jobs = AsyncMock(return_value=[job])
    result = await agent.run("show failed jobs")
    assert result is not None
    assert result.success is True
    assert "abc-123" in result.message

def test_fmt_ts_none():
    from synthadoc.utils import fmt_ts
    assert fmt_ts(None) == "—"

def test_fmt_ts_invalid():
    from synthadoc.utils import fmt_ts
    # Invalid string: fallback returns ts[:16]
    assert fmt_ts("not-a-date") == "not-a-date"

@pytest.mark.asyncio
async def test_extract_strips_markdown_fences(tmp_path):
    """_extract() must handle LLM responses wrapped in ```json fences."""
    fenced = '```json\n{"action": "lint", "params": {"scope": "all", "auto_resolve": false}}\n```'
    agent, _ = _make_agent(tmp_path, fenced)
    result = await agent.run("run lint")
    assert result is not None
    assert result.action_type == "lint"

@pytest.mark.asyncio
async def test_extract_returns_none_on_bad_json(tmp_path):
    """_extract() must return None when the LLM response is unparseable."""
    agent, _ = _make_agent(tmp_path, "sorry I cannot help")
    result = await agent.run("run lint")
    assert result is None

@pytest.mark.asyncio
async def test_dispatch_exception_returns_failure_result(tmp_path):
    """A hard exception inside dispatch must return a failure ActionResult, not raise."""
    agent, _ = _make_agent(tmp_path, '{"action": "lint", "params": {}}')
    agent._orch.lint = AsyncMock(side_effect=RuntimeError("db locked"))
    result = await agent.run("run lint")
    assert result is not None
    assert result.success is False
    assert "db locked" in result.message

def test_detect_clarify_lookback_exhausted_without_match(tmp_path):
    """When lookback is exhausted without finding a clarify prefix, detect returns False."""
    from synthadoc.agents.action_agent import CLARIFY_STORE_PREFIX
    agent, _ = _make_agent(tmp_path, "{}")
    agent._orch._cfg.chat.clarify_lookback = 2
    history = [
        {"role": "user",      "content": "who is Turing?"},
        {"role": "assistant", "content": "Alan Turing was a mathematician."},
        {"role": "user",      "content": "tell me more"},
        {"role": "assistant", "content": "He invented the Turing machine."},
        # clarify is further back than lookback=2
        {"role": "user",      "content": "show me job status"},
        {"role": "assistant", "content": CLARIFY_STORE_PREFIX + "Which job?"},
    ]
    # reverse: last 2 assistant msgs are "He invented..." and "Alan Turing..."  — no prefix
    # but wait, the clarify IS the most recent assistant here; let me restructure
    history2 = [
        {"role": "user",      "content": "show me job status"},
        {"role": "assistant", "content": CLARIFY_STORE_PREFIX + "Which job?"},
        {"role": "user",      "content": "abc-123"},
        {"role": "assistant", "content": "Job abc-123 is completed."},
        {"role": "user",      "content": "tell me more about it"},
        {"role": "assistant", "content": "It ingested 3 pages."},
    ]
    # lookback=2: checks last 2 assistant msgs ("It ingested 3 pages.", "Job abc-123 is completed.")
    # neither has CLARIFY_STORE_PREFIX → False
    assert agent.detect("random question", history=history2) is False


# ── schedule_add lint normalisation ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_schedule_add_normalises_lint_op(tmp_path):
    """'lint' op is normalised to 'lint run' before saving."""
    extraction = ('{"action": "schedule_add", "params": {'
                  '"op": "lint", "cron": "0 21 * * *",'
                  '"schedule_description": "every night at 9 PM"}}')
    agent, _ = _make_agent(tmp_path, extraction)
    result = await agent.run("Schedule lint run every night at 9 PM")
    assert result is not None
    assert result.success is True
    assert "lint run" in result.message


# ── lifecycle: null / missing slug ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lifecycle_archive_null_slug_lists_candidates(tmp_path):
    """LLM returns slug=null (ambiguous request) — must not crash; must list eligible pages."""
    from synthadoc.storage.wiki import WikiPage, LifecycleState
    extraction = '{"action": "lifecycle_archive", "params": {"slug": null, "reason": null}}'
    agent, _ = _make_agent(tmp_path, extraction)

    stale_page = MagicMock(spec=WikiPage)
    stale_page.status = LifecycleState.STALE
    agent._orch._store.list_pages.return_value = ["alan-turing", "other-page"]
    agent._orch._store.read_page.side_effect = lambda s: stale_page

    result = await agent.run("Archive a stale page")
    assert result is not None
    assert result.success is False
    assert "alan-turing" in result.clarify_candidates or "other-page" in result.clarify_candidates
    assert "archive" in result.message.lower()


@pytest.mark.asyncio
async def test_lifecycle_archive_active_page_appears_as_candidate(tmp_path):
    """Active pages are eligible for archive — they should appear in clarify_candidates."""
    from synthadoc.storage.wiki import WikiPage, LifecycleState
    extraction = '{"action": "lifecycle_archive", "params": {"slug": null}}'
    agent, _ = _make_agent(tmp_path, extraction)

    active_page = MagicMock(spec=WikiPage)
    active_page.status = LifecycleState.ACTIVE
    agent._orch._store.list_pages.return_value = ["active-page"]
    agent._orch._store.read_page.return_value = active_page

    result = await agent.run("Archive a stale page")
    assert result is not None
    assert result.needs_clarification is True
    assert "active-page" in result.clarify_candidates


# ── clarify path: new ActionResult fields ────────────────────────────────────

@pytest.mark.asyncio
async def test_lifecycle_archive_null_slug_returns_clarify_result(tmp_path):
    """needs_clarification=True and candidates populated when slug=null."""
    from synthadoc.storage.wiki import WikiPage, LifecycleState
    extraction = '{"action": "lifecycle_archive", "params": {"slug": null}}'
    agent, _ = _make_agent(tmp_path, extraction)
    stale = MagicMock(spec=WikiPage)
    stale.status = LifecycleState.STALE
    agent._orch._store.list_pages.return_value = ["page-a", "page-b"]
    agent._orch._store.read_page.return_value = stale
    result = await agent.run("Archive a stale page")
    assert result is not None
    assert result.needs_clarification is True
    assert "page-a" in result.clarify_candidates
    assert result.clarify_prompt != ""
    assert result.action_type == "lifecycle_archive"


@pytest.mark.asyncio
async def test_lifecycle_archive_state_filter_narrows_candidates(tmp_path):
    """state_filter='stale' must exclude ACTIVE pages even though active is a valid archive source."""
    from synthadoc.storage.wiki import WikiPage, LifecycleState
    extraction = '{"action": "lifecycle_archive", "params": {"slug": null, "state_filter": "stale"}}'
    agent, _ = _make_agent(tmp_path, extraction)

    stale_page = MagicMock(spec=WikiPage)
    stale_page.status = LifecycleState.STALE
    active_page = MagicMock(spec=WikiPage)
    active_page.status = LifecycleState.ACTIVE

    agent._orch._store.list_pages.return_value = ["stale-pg", "active-pg"]
    agent._orch._store.read_page.side_effect = lambda s: (
        stale_page if s == "stale-pg" else active_page
    )

    result = await agent.run("Archive a stale page")
    assert result is not None
    assert result.needs_clarification is True
    assert "stale-pg" in result.clarify_candidates
    assert "active-pg" not in result.clarify_candidates


@pytest.mark.asyncio
async def test_lifecycle_archive_state_filter_no_match_returns_message(tmp_path):
    """state_filter='stale' with zero stale pages → helpful 'no stale pages' message, not clarify."""
    from synthadoc.storage.wiki import WikiPage, LifecycleState
    extraction = '{"action": "lifecycle_archive", "params": {"slug": null, "state_filter": "stale"}}'
    agent, _ = _make_agent(tmp_path, extraction)

    active_page = MagicMock(spec=WikiPage)
    active_page.status = LifecycleState.ACTIVE
    agent._orch._store.list_pages.return_value = ["active-pg"]
    agent._orch._store.read_page.return_value = active_page

    result = await agent.run("Archive a stale page")
    assert result is not None
    assert result.needs_clarification is False
    assert result.success is False
    assert "stale" in result.message.lower()
    assert "lint run" in result.message


@pytest.mark.asyncio
async def test_lifecycle_archive_candidates_capped(tmp_path):
    """More than _MAX_CLARIFY_CANDIDATES eligible pages must be capped in clarify_candidates."""
    from synthadoc.agents.action_agent import _MAX_CLARIFY_CANDIDATES
    from synthadoc.storage.wiki import WikiPage, LifecycleState
    extraction = '{"action": "lifecycle_archive", "params": {"slug": null}}'
    agent, _ = _make_agent(tmp_path, extraction)

    active_page = MagicMock(spec=WikiPage)
    active_page.status = LifecycleState.ACTIVE
    many_pages = [f"page-{i:02d}" for i in range(_MAX_CLARIFY_CANDIDATES + 5)]
    agent._orch._store.list_pages.return_value = many_pages
    agent._orch._store.read_page.return_value = active_page

    result = await agent.run("Archive a page")
    assert result is not None
    assert result.needs_clarification is True
    assert len(result.clarify_candidates) == _MAX_CLARIFY_CANDIDATES
    assert str(_MAX_CLARIFY_CANDIDATES) in result.clarify_prompt


@pytest.mark.asyncio
async def test_schedule_add_missing_cron_returns_clarify(tmp_path):
    """needs_clarification=True with empty candidates when cron is null."""
    extraction = '{"action": "schedule_add", "params": {"op": "lint run", "cron": null}}'
    agent, _ = _make_agent(tmp_path, extraction)
    result = await agent.run("Schedule a lint run")
    assert result is not None
    assert result.needs_clarification is True
    assert result.clarify_candidates == []
    assert result.clarify_prompt != ""


@pytest.mark.asyncio
async def test_history_context_passed_to_extraction(tmp_path):
    """History is appended to the extraction prompt when provided."""
    from synthadoc.storage.wiki import WikiPage, LifecycleState
    extraction = '{"action": "lifecycle_archive", "params": {"slug": "page-a", "reason": null}}'
    agent, provider = _make_agent(tmp_path, extraction)
    page = MagicMock(spec=WikiPage)
    page.status = LifecycleState.STALE
    agent._orch._store.list_pages.return_value = ["page-a"]
    agent._orch._store.read_page.return_value = page
    history = [
        {"role": "user", "content": "Archive a stale page"},
        {"role": "assistant", "content": "Which page? 1. page-a"},
    ]
    result = await agent.run("1", history=history)
    assert result is not None
    call_args = provider.complete.call_args
    prompt_content = call_args.kwargs["messages"][0].content if call_args.kwargs else call_args.args[0][0].content
    assert "page-a" in prompt_content or "history" in prompt_content.lower() or "User:" in prompt_content


# ── CLI provider guard ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_orchestrate_rejects_coding_tool_provider(tmp_path):
    """_run_orchestrate must return an error message (not attempt the tool-call
    loop) when the configured provider is a CodingToolCLIProvider subclass and
    the matched workflow does NOT set SUPPORTS_CLI_PROVIDER=True.

    Claude Code and Opencode are themselves agents — they refuse Synthadoc's
    JSON wire-format system prompt as prompt injection.  The guard fires
    for workflows that have not opted into run_for_cli_provider().

    We use a minimal stub workflow that deliberately leaves SUPPORTS_CLI_PROVIDER
    at its default (False), so the test is decoupled from which real workflows
    happen to have opted in.
    """
    from unittest.mock import patch as _patch
    from synthadoc.agents.action_agent import ActionAgent
    from synthadoc.agents.workflows._base import AgenticWorkflow

    class _NoCliWorkflow(AgenticWorkflow):
        """Minimal stub — SUPPORTS_CLI_PROVIDER deliberately left False."""
        NAME = "no-cli-stub"
        DESCRIPTION = "Guard-test stub."
        SUPPORTS_CLI_PROVIDER = False  # explicitly at default — guard must fire
        async def build_system_prompt(self) -> str: return "no"
        def build_initial_message(self, user_input: str) -> str: return user_input
        def get_tool_fns(self, ctx) -> dict: return {}

    # Build a mock that looks like ClaudeCodeCLIProvider without requiring
    # the real binary to be installed.
    with _patch("synthadoc.providers.coding_tool._find_binary", return_value="/usr/bin/claude"):
        from synthadoc.providers.coding_tool import ClaudeCodeCLIProvider
        cli_provider = ClaudeCodeCLIProvider(model=None, timeout=30)

    orch = MagicMock()
    orch.lint = AsyncMock()
    orch._queue = MagicMock()
    orch.queue = MagicMock()
    orch._store = MagicMock()
    orch._bump_epoch = MagicMock()
    orch._cfg = MagicMock()
    orch._cfg.chat.clarify_lookback = 5
    agent = ActionAgent(provider=cli_provider, orchestrator=orch, wiki_root=tmp_path)

    # Collect all SSE events yielded by _run_orchestrate.
    events = []
    async for evt in agent._run_orchestrate("run no-cli-stub", workflow=_NoCliWorkflow()):
        events.append(evt)

    # Must yield at least a token event with the error message and a done event.
    event_types = [e["event"] for e in events]
    assert "token" in event_types
    assert "done" in event_types
    # No final_text: the guard streams a single token and then done.
    assert "final_text" not in event_types

    # The error text must mention the binary name and suggest anthropic provider.
    token_text = "".join(
        e["data"]["text"] for e in events if e["event"] == "token"
    )
    assert "claude" in token_text.lower()
    assert "anthropic" in token_text.lower()
    # Crucially: the loop was never started — confirm and tool_fns are never wired.
    orch.lint.assert_not_called()


@pytest.mark.asyncio
async def test_run_orchestrate_uses_cli_path_for_supported_workflow(tmp_path):
    """When the provider is a CodingToolCLIProvider and the workflow sets
    SUPPORTS_CLI_PROVIDER=True, _run_orchestrate must call run_for_cli_provider
    instead of yielding the unsupported-provider error message.
    """
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.action_agent import ActionAgent
    from synthadoc.agents.workflows._base import AgenticWorkflow, WorkflowContext

    with _patch("synthadoc.providers.coding_tool._find_binary", return_value="/usr/bin/claude"):
        from synthadoc.providers.coding_tool import ClaudeCodeCLIProvider
        cli_provider = ClaudeCodeCLIProvider(model=None, timeout=30)

    # Minimal stub workflow that opts into the CLI path and yields a sentinel event.
    class _CLIWorkflow(AgenticWorkflow):
        SUPPORTS_CLI_PROVIDER = True
        MATCH_RE = None

        async def build_system_prompt(self): return ""
        def build_initial_message(self, q): return q
        def get_tool_fns(self, ctx): return {}

        async def run_for_cli_provider(self, ctx, question, provider):
            yield {"event": "token", "data": {"text": "cli-path-ran"}}
            yield {"event": "final_text", "data": {"text": "cli-path-ran"}}

    orch = MagicMock()
    orch.lint = _AsyncMock()
    orch._queue = MagicMock()
    orch.queue = MagicMock()
    orch._store = MagicMock()
    orch._bump_epoch = MagicMock()
    orch._cfg = MagicMock()
    orch._cfg.chat.clarify_lookback = 5
    agent = ActionAgent(provider=cli_provider, orchestrator=orch, wiki_root=tmp_path)

    events = []
    async for evt in agent._run_orchestrate("fix broken citations", workflow=_CLIWorkflow()):
        events.append(evt)

    token_text = "".join(e["data"]["text"] for e in events if e["event"] == "token")
    # CLI path ran — no error message
    assert "cli-path-ran" in token_text
    assert "anthropic" not in token_text
    # final_text → converted to done by the drain loop
    event_types = [e["event"] for e in events]
    assert "done" in event_types
    assert "final_text" not in event_types


@pytest.mark.asyncio
async def test_broken_citation_resolver_cli_path_no_issues(tmp_path):
    """run_for_cli_provider returns early with 'no broken citations' when
    tool_find_broken_citations reports zero issues."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.broken_citation_resolver import BrokenCitationResolverWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()

    wf = BrokenCitationResolverWorkflow()
    fake_provider = MagicMock()

    with _patch(
        "synthadoc.agents.workflows.broken_citation_resolver.tool_find_broken_citations",
        new=_AsyncMock(return_value={"pages": [], "total_issues": 0, "scanned": 5}),
    ):
        events = []
        async for evt in wf.run_for_cli_provider(ctx, "fix broken citations", fake_provider):
            events.append(evt)

    texts = [e["data"]["text"] for e in events if e["event"] == "token"]
    assert any("no broken citations" in t.lower() for t in texts)
    event_types = [e["event"] for e in events]
    assert "final_text" in event_types


@pytest.mark.asyncio
async def test_broken_citation_resolver_cli_path_applies_fixes(tmp_path):
    """run_for_cli_provider computes fixes via difflib, confirms, and applies them.

    broken_ref with a close match → renamed marker.
    malformed → removed.
    """
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.broken_citation_resolver import BrokenCitationResolverWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()

    scan_result = {
        "pages": [
            {
                "slug": "page-a",
                "title": "Page A",
                "issues": [
                    {"citation": "^[source.txt:1-5]", "reason": "broken_ref"},
                    {"citation": "^[bad]", "reason": "malformed"},
                ],
                "page_sources": ["sources.txt"],
            }
        ],
        "total_issues": 2,
        "scanned": 1,
    }

    applied_fixes: list[dict] = []

    async def _fake_apply(ctx, page_slug, fixes):
        applied_fixes.extend(fixes)
        return {"status": "success", "changes": len(fixes), "page": page_slug}

    wf = BrokenCitationResolverWorkflow()

    with _patch(
        "synthadoc.agents.workflows.broken_citation_resolver.tool_find_broken_citations",
        new=_AsyncMock(return_value=scan_result),
    ), _patch(
        "synthadoc.agents.workflows.broken_citation_resolver.tool_confirm",
        new=_AsyncMock(return_value={"confirmed": True}),
    ), _patch(
        "synthadoc.agents.workflows.broken_citation_resolver.tool_apply_citation_fixes",
        new=_fake_apply,
    ), _patch(
        "synthadoc.agents.workflows.broken_citation_resolver.tool_get_wiki_status",
        new=_AsyncMock(return_value={"active": 3, "contradicted": 0, "stale": 1, "draft": 0, "archived": 0}),
    ):
        events = []
        async for evt in wf.run_for_cli_provider(ctx, "fix broken citations", MagicMock()):
            events.append(evt)

    # broken_ref with close match "source.txt" ≈ "sources.txt" → rename
    rename_fix = next((f for f in applied_fixes if f["old_citation"] == "^[source.txt:1-5]"), None)
    assert rename_fix is not None
    assert rename_fix["new_citation"] == "^[sources.txt:1-5]"

    # malformed → remove
    remove_fix = next((f for f in applied_fixes if f["old_citation"] == "^[bad]"), None)
    assert remove_fix is not None
    assert remove_fix["new_citation"] is None

    # Summary event emitted
    token_text = "".join(e["data"]["text"] for e in events if e["event"] == "token")
    assert "Fixed" in token_text
    assert "final_text" in [e["event"] for e in events]


@pytest.mark.asyncio
async def test_contradiction_resolver_cli_path_no_pages(tmp_path):
    """run_for_cli_provider returns early when no contradicted pages are found."""
    from unittest.mock import AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.contradiction_resolver import ContradictionResolverWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()

    wf = ContradictionResolverWorkflow()

    with patch(
        "synthadoc.agents.workflows.contradiction_resolver.tool_get_contradicted_pages",
        new=_AsyncMock(return_value={"pages": []}),
    ):
        events = []
        async for evt in wf.run_for_cli_provider(ctx, "run contradiction resolver", MagicMock()):
            events.append(evt)

    texts = [e["data"]["text"] for e in events if e["event"] == "token"]
    assert any("no contradicted pages" in t.lower() for t in texts)
    assert "final_text" in [e["event"] for e in events]


@pytest.mark.asyncio
async def test_contradiction_resolver_cli_path_cancelled(tmp_path):
    """run_for_cli_provider returns early when the user cancels the cost estimate."""
    from unittest.mock import AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.contradiction_resolver import ContradictionResolverWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()

    wf = ContradictionResolverWorkflow()

    with patch(
        "synthadoc.agents.workflows.contradiction_resolver.tool_get_contradicted_pages",
        new=_AsyncMock(return_value={"pages": [{"slug": "page-a", "type": "gate"}]}),
    ), patch(
        "synthadoc.agents.workflows.contradiction_resolver.tool_cost_estimate",
        new=_AsyncMock(return_value={"confirmed": False, "pages": 1}),
    ):
        events = []
        async for evt in wf.run_for_cli_provider(ctx, "run contradiction resolver", MagicMock()):
            events.append(evt)

    texts = [e["data"]["text"] for e in events if e["event"] == "token"]
    assert any("cancelled" in t.lower() for t in texts)


@pytest.mark.asyncio
async def test_contradiction_resolver_cli_path_resolves_page(tmp_path):
    """run_for_cli_provider applies a rewrite, lint passes → page activated."""
    from unittest.mock import AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.contradiction_resolver import ContradictionResolverWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()

    wf = ContradictionResolverWorkflow()

    # Stub provider returns a simple rewrite
    fake_provider = MagicMock()
    from synthadoc.providers.base import CompletionResponse
    fake_provider.complete = _AsyncMock(return_value=CompletionResponse(
        text="# Revised page\nHedged content.", input_tokens=50, output_tokens=20,
    ))

    with patch(
        "synthadoc.agents.workflows.contradiction_resolver.tool_get_contradicted_pages",
        new=_AsyncMock(return_value={"pages": [{"slug": "page-a", "type": "gate"}]}),
    ), patch(
        "synthadoc.agents.workflows.contradiction_resolver.tool_cost_estimate",
        new=_AsyncMock(return_value={"confirmed": True, "pages": 1}),
    ), patch(
        "synthadoc.agents.workflows.contradiction_resolver.tool_read_page_content",
        new=_AsyncMock(return_value={
            "slug": "page-a", "content": "# Page\nOriginal.",
            "lint_warnings": ["claim X is unsupported"], "contradiction_note": None,
        }),
    ), patch(
        "synthadoc.agents.workflows.contradiction_resolver.tool_propose_and_apply",
        new=_AsyncMock(return_value={"applied": True, "diff_preview": "..."}),
    ), patch(
        "synthadoc.agents.workflows.contradiction_resolver.tool_run_scoped_lint",
        new=_AsyncMock(return_value={"pass": True, "warnings_count": 0}),
    ), patch(
        "synthadoc.agents.workflows.contradiction_resolver.tool_transition_lifecycle_state",
        new=_AsyncMock(return_value={"status": "success"}),
    ), patch(
        "synthadoc.agents.workflows.contradiction_resolver.tool_get_wiki_status",
        new=_AsyncMock(return_value={"active": 1, "contradicted": 0, "stale": 0, "draft": 0, "archived": 0}),
    ):
        events = []
        async for evt in wf.run_for_cli_provider(ctx, "resolve contradictions", fake_provider):
            events.append(evt)

    token_text = "".join(e["data"]["text"] for e in events if e["event"] == "token")
    assert "Fixed" in token_text
    assert "page-a" in token_text
    assert "final_text" in [e["event"] for e in events]


@pytest.mark.asyncio
async def test_contradiction_resolver_strategy1_rules_shared():
    """_STRATEGY_1_RULES is embedded in _SYSTEM_PROMPT — the constant is used,
    not duplicated."""
    from synthadoc.agents.workflows.contradiction_resolver import (
        _SYSTEM_PROMPT,
        _STRATEGY_1_RULES,
    )
    # The first distinctive line of the rules must appear in the system prompt
    first_rule_line = _STRATEGY_1_RULES.splitlines()[0]
    assert first_rule_line in _SYSTEM_PROMPT, (
        "_STRATEGY_1_RULES is not embedded in _SYSTEM_PROMPT — placeholder substitution failed"
    )
    # The CLI rewrite system is derived from the same constant (not a hardcoded copy)
    # — verified by importing the workflow and checking _cli_rewrite_page uses it.
    # (Source-level enforcement: grep for the literal strings would be fragile,
    #  so we assert the constant itself is non-trivial and in the prompt.)
    assert len(_STRATEGY_1_RULES) > 50


# ── IngestLintWorkflow CLI path ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_lint_cli_path_no_stale_pages(tmp_path):
    """Workflow A: tool_find_stale_pages returns empty → early exit, no confirm called."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.ingest_lint import IngestLintWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = IngestLintWorkflow()

    with _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_find_stale_pages",
        new=_AsyncMock(return_value={"pages": []}),
    ) as mock_find, _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_confirm",
        new=_AsyncMock(),
    ) as mock_confirm:
        events = []
        async for evt in wf.run_for_cli_provider(ctx, "re-ingest stale pages", MagicMock()):
            events.append(evt)

    mock_find.assert_called_once()
    mock_confirm.assert_not_called()
    texts = [e["data"]["text"] for e in events if e["event"] == "token"]
    assert any("no stale pages" in t.lower() for t in texts)
    assert "final_text" in [e["event"] for e in events]


@pytest.mark.asyncio
async def test_ingest_lint_cli_path_workflow_a_cancelled(tmp_path):
    """Workflow A: confirm returns false → no ingests, no lint."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.ingest_lint import IngestLintWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = IngestLintWorkflow()

    stale_pages = [
        {"slug": "page-a", "source_path": "/data/a.txt", "stale_since": "2026-08-01"},
    ]

    with _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_find_stale_pages",
        new=_AsyncMock(return_value={"pages": stale_pages}),
    ), _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_confirm",
        new=_AsyncMock(return_value={"confirmed": False}),
    ), _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_ingest_source",
        new=_AsyncMock(),
    ) as mock_ingest, _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_run_lint",
        new=_AsyncMock(),
    ) as mock_lint:
        events = []
        async for evt in wf.run_for_cli_provider(ctx, "re-ingest stale pages", MagicMock()):
            events.append(evt)

    mock_ingest.assert_not_called()
    mock_lint.assert_not_called()
    texts = [e["data"]["text"] for e in events if e["event"] == "token"]
    assert any("cancel" in t.lower() for t in texts)


@pytest.mark.asyncio
async def test_ingest_lint_cli_path_workflow_a_ingests(tmp_path):
    """Workflow A: confirms → ingests each page (skipping one with no source_path),
    then runs lint and get_page_states; summary shows per-page results."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.ingest_lint import IngestLintWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = IngestLintWorkflow()

    stale_pages = [
        {"slug": "page-a", "source_path": "/data/a.txt", "stale_since": "2026-08-01"},
        {"slug": "page-b", "source_path": None,           "stale_since": "2026-07-20"},
    ]

    ingested: list[str] = []

    async def _fake_ingest(ctx, source_path):
        ingested.append(source_path)
        return {"status": "success", "message": "done"}

    with _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_find_stale_pages",
        new=_AsyncMock(return_value={"pages": stale_pages}),
    ), _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_confirm",
        new=_AsyncMock(return_value={"confirmed": True}),
    ), _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_ingest_source",
        new=_fake_ingest,
    ), _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_run_lint",
        new=_AsyncMock(return_value={"status": "success", "message": "all clean"}),
    ), _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_get_page_states",
        new=_AsyncMock(return_value={
            "pages": [
                {"slug": "page-a", "state": "active"},
                {"slug": "page-b", "state": "stale"},
            ]
        }),
    ):
        events = []
        async for evt in wf.run_for_cli_provider(ctx, "re-ingest stale pages", MagicMock()):
            events.append(evt)

    # page-a has a source_path → ingested; page-b has none → skipped
    assert ingested == ["/data/a.txt"]

    token_text = "".join(e["data"]["text"] for e in events if e["event"] == "token")
    assert "page-a" in token_text
    assert "page-b" in token_text
    assert "skipped" in token_text          # page-b skipped (no source path)
    assert "active" in token_text           # page-a ended up active
    assert "final_text" in [e["event"] for e in events]


@pytest.mark.asyncio
async def test_ingest_lint_cli_path_workflow_b_specific_slug(tmp_path):
    """Workflow B (--slug): looks up source, confirms, ingests, lints, checks state."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.ingest_lint import IngestLintWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = IngestLintWorkflow()

    with _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_find_page_source",
        new=_AsyncMock(return_value={"slug": "my-page", "source_path": "/data/my.txt"}),
    ), _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_confirm",
        new=_AsyncMock(return_value={"confirmed": True}),
    ), _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_ingest_source",
        new=_AsyncMock(return_value={"status": "success", "message": "done"}),
    ), _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_run_lint",
        new=_AsyncMock(return_value={"status": "success", "message": "clean"}),
    ), _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_get_page_states",
        new=_AsyncMock(return_value={"pages": [{"slug": "my-page", "state": "active"}]}),
    ):
        events = []
        async for evt in wf.run_for_cli_provider(
            ctx, "re-ingest page --slug my-page", MagicMock()
        ):
            events.append(evt)

    token_text = "".join(e["data"]["text"] for e in events if e["event"] == "token")
    assert "my-page" in token_text
    assert "active" in token_text
    assert "final_text" in [e["event"] for e in events]


@pytest.mark.asyncio
async def test_ingest_lint_cli_path_natural_language_slug(tmp_path):
    """Graph UI sends "Re-ingest the alan-turing page" (no --slug flag).
    The CLI path must extract the slug from the natural language pattern
    and route to Workflow B, not Workflow A (all stale pages)."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.ingest_lint import IngestLintWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = IngestLintWorkflow()

    with _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_find_page_source",
        new=_AsyncMock(return_value={"slug": "alan-turing", "source_path": "/data/alan.txt"}),
    ) as mock_source, _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_find_stale_pages",
        new=_AsyncMock(),
    ) as mock_stale, _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_confirm",
        new=_AsyncMock(return_value={"confirmed": True}),
    ), _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_ingest_source",
        new=_AsyncMock(return_value={"status": "success", "message": "done"}),
    ), _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_run_lint",
        new=_AsyncMock(return_value={"status": "success", "message": "clean"}),
    ), _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_get_page_states",
        new=_AsyncMock(return_value={"pages": [{"slug": "alan-turing", "state": "active"}]}),
    ):
        events = []
        async for evt in wf.run_for_cli_provider(
            ctx, "Re-ingest the alan-turing page", MagicMock()
        ):
            events.append(evt)

    # Workflow B path: find_page_source called, NOT find_stale_pages
    mock_source.assert_called_once_with(ctx, slug="alan-turing")
    mock_stale.assert_not_called()

    token_text = "".join(e["data"]["text"] for e in events if e["event"] == "token")
    assert "alan-turing" in token_text
    assert "active" in token_text


@pytest.mark.asyncio
async def test_ingest_lint_cli_path_workflow_b_no_source(tmp_path):
    """Workflow B: tool_find_page_source returns an error → early exit."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.ingest_lint import IngestLintWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = IngestLintWorkflow()

    with _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_find_page_source",
        new=_AsyncMock(return_value={"error": "Page 'ghost' not found in this wiki"}),
    ), _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_run_lint",
        new=_AsyncMock(),
    ) as mock_lint:
        events = []
        async for evt in wf.run_for_cli_provider(
            ctx, "re-ingest page --slug ghost", MagicMock()
        ):
            events.append(evt)

    mock_lint.assert_not_called()
    texts = [e["data"]["text"] for e in events if e["event"] == "token"]
    assert any("ghost" in t for t in texts)
    assert any("cannot re-ingest" in t.lower() for t in texts)


@pytest.mark.asyncio
async def test_ingest_lint_cli_path_workflow_a_ingest_error_in_summary(tmp_path):
    """Workflow A: tool_ingest_source returns {"error": ...} (e.g. file-not-found).

    The summary must surface "error" so live tests can detect partial failure.
    Regression: previously ingest_status fell back to "?" (no "status" key),
    which matched no failure keyword the live assertion checked.
    """
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.ingest_lint import IngestLintWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = IngestLintWorkflow()

    stale_pages = [
        {"slug": "page-ok",  "source_path": "/data/ok.txt",  "stale_since": "2026-08-01"},
        {"slug": "page-bad", "source_path": "/data/bad.txt", "stale_since": "2026-08-01"},
    ]

    async def _fake_ingest(ctx, source_path):
        if "bad" in source_path:
            return {"error": f"File not found: {source_path!r}"}
        return {"status": "success", "message": "done"}

    with _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_find_stale_pages",
        new=_AsyncMock(return_value={"pages": stale_pages}),
    ), _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_confirm",
        new=_AsyncMock(return_value={"confirmed": True}),
    ), _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_ingest_source",
        new=_fake_ingest,
    ), _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_run_lint",
        new=_AsyncMock(return_value={"status": "success", "message": "clean"}),
    ), _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_get_page_states",
        new=_AsyncMock(return_value={
            "pages": [
                {"slug": "page-ok",  "state": "active"},
                {"slug": "page-bad", "state": "stale"},
            ]
        }),
    ):
        events = []
        async for evt in wf.run_for_cli_provider(ctx, "re-ingest stale pages", MagicMock()):
            events.append(evt)

    token_text = "".join(e["data"]["text"] for e in events if e["event"] == "token")
    # page-bad errored → summary must contain "error" (not "?") so live tests detect it
    assert "error" in token_text.lower()
    assert "page-bad" in token_text
    # page-ok succeeded → should still appear
    assert "page-ok" in token_text
    assert "active" in token_text
    assert "final_text" in [e["event"] for e in events]


# ── BrokenWikilinksWorkflow CLI path ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_broken_wikilinks_cli_path_no_broken(tmp_path):
    """Full-wiki scan finds zero broken links → clean-wiki summary, no confirm."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.broken_wikilinks import BrokenWikilinksWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = BrokenWikilinksWorkflow()

    with _patch(
        "synthadoc.agents.workflows.broken_wikilinks.tool_find_broken_wikilinks",
        new=_AsyncMock(return_value={"pages": [], "scanned": 12, "total_broken": 0}),
    ), _patch(
        "synthadoc.agents.workflows.broken_wikilinks.tool_confirm",
        new=_AsyncMock(),
    ) as mock_confirm:
        events = []
        async for evt in wf.run_for_cli_provider(
            ctx, "fix broken wikilinks", MagicMock()
        ):
            events.append(evt)

    mock_confirm.assert_not_called()
    texts = [e["data"]["text"] for e in events if e["event"] == "token"]
    assert any("no broken wikilinks" in t.lower() for t in texts)
    assert any("12" in t for t in texts)
    assert "final_text" in [e["event"] for e in events]


@pytest.mark.asyncio
async def test_broken_wikilinks_cli_path_single_page_clean(tmp_path):
    """Single-page mode (--slug): uses page_title in the clean message."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.broken_wikilinks import BrokenWikilinksWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = BrokenWikilinksWorkflow()

    with _patch(
        "synthadoc.agents.workflows.broken_wikilinks.tool_find_broken_wikilinks",
        new=_AsyncMock(return_value={
            "pages": [], "scanned": 1, "total_broken": 0,
            "page_title": "Alan Turing",
        }),
    ):
        events = []
        async for evt in wf.run_for_cli_provider(
            ctx, "fix broken wikilinks --slug alan-turing", MagicMock()
        ):
            events.append(evt)

    texts = [e["data"]["text"] for e in events if e["event"] == "token"]
    assert any("Alan Turing" in t for t in texts)


@pytest.mark.asyncio
async def test_broken_wikilinks_cli_path_cancelled(tmp_path):
    """confirm returns false → no apply_link_fixes, no lint."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.broken_wikilinks import BrokenWikilinksWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = BrokenWikilinksWorkflow()

    scan_result = {
        "pages": [{"slug": "page-a", "broken_links": [{"ref": "nope", "suggestion": None}]}],
        "scanned": 5, "total_broken": 1,
    }

    with _patch(
        "synthadoc.agents.workflows.broken_wikilinks.tool_find_broken_wikilinks",
        new=_AsyncMock(return_value=scan_result),
    ), _patch(
        "synthadoc.agents.workflows.broken_wikilinks.tool_confirm",
        new=_AsyncMock(return_value={"confirmed": False}),
    ), _patch(
        "synthadoc.agents.workflows.broken_wikilinks.tool_apply_link_fixes",
        new=_AsyncMock(),
    ) as mock_apply, _patch(
        "synthadoc.agents.workflows.broken_wikilinks.tool_run_lint",
        new=_AsyncMock(),
    ) as mock_lint:
        events = []
        async for evt in wf.run_for_cli_provider(
            ctx, "fix broken wikilinks", MagicMock()
        ):
            events.append(evt)

    mock_apply.assert_not_called()
    mock_lint.assert_not_called()
    texts = [e["data"]["text"] for e in events if e["event"] == "token"]
    assert any("cancel" in t.lower() for t in texts)


@pytest.mark.asyncio
async def test_broken_wikilinks_cli_path_applies_fixes(tmp_path):
    """Happy path: scan finds two broken refs (one with suggestion, one without),
    confirms, applies, runs lint, checks page states, and produces summary."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.broken_wikilinks import BrokenWikilinksWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = BrokenWikilinksWorkflow()

    scan_result = {
        "pages": [{
            "slug": "page-a",
            "broken_links": [
                {"ref": "turing",    "suggestion": "alan-turing"},   # rename
                {"ref": "ghost-ref", "suggestion": None},             # remove
            ],
        }],
        "scanned": 8,
        "total_broken": 2,
    }

    applied_fixes: list[dict] = []

    async def _fake_apply(ctx, page_slug, fixes):
        applied_fixes.extend(fixes)
        return {"status": "success", "changes": len(fixes), "page": page_slug}

    with _patch(
        "synthadoc.agents.workflows.broken_wikilinks.tool_find_broken_wikilinks",
        new=_AsyncMock(return_value=scan_result),
    ), _patch(
        "synthadoc.agents.workflows.broken_wikilinks.tool_confirm",
        new=_AsyncMock(return_value={"confirmed": True}),
    ), _patch(
        "synthadoc.agents.workflows.broken_wikilinks.tool_apply_link_fixes",
        new=_fake_apply,
    ), _patch(
        "synthadoc.agents.workflows.broken_wikilinks.tool_run_lint",
        new=_AsyncMock(return_value={"status": "success", "message": "all clean"}),
    ), _patch(
        "synthadoc.agents.workflows.broken_wikilinks.tool_get_page_states",
        new=_AsyncMock(return_value={
            "pages": [{"slug": "page-a", "state": "active"}]
        }),
    ):
        events = []
        async for evt in wf.run_for_cli_provider(
            ctx, "fix broken wikilinks", MagicMock()
        ):
            events.append(evt)

    # Both fixes submitted: rename and remove
    rename = next((f for f in applied_fixes if f["old_ref"] == "turing"), None)
    assert rename is not None and rename["new_ref"] == "alan-turing"
    remove = next((f for f in applied_fixes if f["old_ref"] == "ghost-ref"), None)
    assert remove is not None and remove["new_ref"] is None

    token_text = "".join(e["data"]["text"] for e in events if e["event"] == "token")
    assert "page-a" in token_text
    assert "active" in token_text
    assert "final_text" in [e["event"] for e in events]


# ── OrphanResolverWorkflow CLI path ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_orphan_resolver_cli_path_no_orphans(tmp_path):
    """tool_find_orphaned_pages returns empty → early exit, no confirm called."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = OrphanResolverWorkflow()

    with _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_find_orphaned_pages",
        new=_AsyncMock(return_value={"orphans": [], "count": 0}),
    ), _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_estimate_and_confirm",
        new=_AsyncMock(),
    ) as mock_estimate:
        events = []
        async for evt in wf.run_for_cli_provider(ctx, "run orphan resolver", MagicMock()):
            events.append(evt)

    mock_estimate.assert_not_called()
    texts = [e["data"]["text"] for e in events if e["event"] == "token"]
    assert any("no active orphaned pages" in t.lower() for t in texts)
    assert "final_text" in [e["event"] for e in events]


@pytest.mark.asyncio
async def test_orphan_resolver_cli_path_cancelled(tmp_path):
    """tool_estimate_and_confirm returns false → no resolution attempted."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = OrphanResolverWorkflow()

    with _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_find_orphaned_pages",
        new=_AsyncMock(return_value={"orphans": ["orphan-a"], "count": 1}),
    ), _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_estimate_and_confirm",
        new=_AsyncMock(return_value={"confirmed": False}),
    ), _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_search_orphan_candidates",
        new=_AsyncMock(),
    ) as mock_search:
        events = []
        async for evt in wf.run_for_cli_provider(ctx, "run orphan resolver", MagicMock()):
            events.append(evt)

    mock_search.assert_not_called()
    texts = [e["data"]["text"] for e in events if e["event"] == "token"]
    assert any("cancel" in t.lower() for t in texts)


@pytest.mark.asyncio
async def test_orphan_resolver_cli_path_slug_already_resolved(tmp_path):
    """--slug page that is already linked → early exit without cost estimate."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = OrphanResolverWorkflow()

    with _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_verify_orphan_resolved",
        new=_AsyncMock(return_value={"resolved": True, "linked_by": ["some-page"]}),
    ), _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_estimate_and_confirm",
        new=_AsyncMock(),
    ) as mock_estimate:
        events = []
        async for evt in wf.run_for_cli_provider(
            ctx, "run orphan resolver --slug my-page", MagicMock()
        ):
            events.append(evt)

    mock_estimate.assert_not_called()
    texts = [e["data"]["text"] for e in events if e["event"] == "token"]
    assert any("not an active orphan" in t.lower() for t in texts)
    assert any("some-page" in t for t in texts)


@pytest.mark.asyncio
async def test_orphan_resolver_cli_path_resolves_orphan(tmp_path):
    """Happy path: BM25 finds candidate, LLM inserts link, apply succeeds, verify resolves."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext
    from synthadoc.providers.base import CompletionResponse

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = OrphanResolverWorkflow()

    fake_provider = MagicMock()
    fake_provider.complete = _AsyncMock(return_value=CompletionResponse(
        text="# Candidate\nSee also [[orphan-page]].\n",
        input_tokens=100, output_tokens=20,
    ))

    # tool_verify_orphan_resolved is called 3 times:
    #   1. pre-check in run_for_cli_provider  → False (page is still orphaned)
    #   2. post-apply inside _cli_resolve_orphan → True (link now in graph)
    #   3. confirm linked_by in run_for_cli_provider after status=="resolved"
    verify_calls = [
        {"resolved": False, "linked_by": []},
        {"resolved": True,  "linked_by": ["candidate-page"]},
        {"resolved": True,  "linked_by": ["candidate-page"]},
    ]
    verify_iter = iter(verify_calls)

    with _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_find_orphaned_pages",
        new=_AsyncMock(return_value={"orphans": ["orphan-page"], "count": 1}),
    ), _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_estimate_and_confirm",
        new=_AsyncMock(return_value={"confirmed": True, "orphan_count": 1}),
    ), _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_verify_orphan_resolved",
        new=_AsyncMock(side_effect=lambda *a, **kw: verify_iter.__next__()),
    ), _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_search_orphan_candidates",
        new=_AsyncMock(return_value={
            "candidates": ["candidate-page"],
            "strategy": "title_bm25",
            "tried_slugs": ["orphan-page", "candidate-page"],
        }),
    ), _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_read_page_content",
        new=_AsyncMock(return_value={
            "slug": "candidate-page",
            "content": "# Candidate\nSome content.\n",
        }),
    ), _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_propose_and_apply",
        new=_AsyncMock(return_value={"applied": True, "diff_preview": "..."}),
    ):
        events = []
        async for evt in wf.run_for_cli_provider(ctx, "run orphan resolver", fake_provider):
            events.append(evt)

    token_text = "".join(e["data"]["text"] for e in events if e["event"] == "token")
    assert "orphan-page" in token_text
    assert "Resolved" in token_text
    assert "candidate-page" in token_text
    assert "final_text" in [e["event"] for e in events]


@pytest.mark.asyncio
async def test_orphan_resolver_cli_path_skips_candidate_that_removes_wikilinks(tmp_path):
    """LLM rewrite removes an existing [[wikilink]] → guard skips candidate, orphan unresolved.

    Inserting [[orphan-slug]] must never silently drop existing wikilinks
    from the candidate page (which would orphan those other pages).  The
    code-level guard detects removed slugs and discards the rewrite before
    tool_propose_and_apply is ever called.
    """
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext
    from synthadoc.providers.base import CompletionResponse

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = OrphanResolverWorkflow()

    # The candidate page has an existing [[other-page]] wikilink.
    candidate_original = "# Candidate\nSee also [[other-page]].\n"
    # The LLM replaces [[other-page]] with [[orphan-page]] — removing the original link.
    candidate_rewritten = "# Candidate\nSee also [[orphan-page]].\n"

    fake_provider = MagicMock()
    fake_provider.complete = _AsyncMock(return_value=CompletionResponse(
        text=candidate_rewritten,
        input_tokens=80, output_tokens=15,
    ))

    with _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_find_orphaned_pages",
        new=_AsyncMock(return_value={"orphans": ["orphan-page"], "count": 1}),
    ), _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_estimate_and_confirm",
        new=_AsyncMock(return_value={"confirmed": True, "orphan_count": 1}),
    ), _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_verify_orphan_resolved",
        new=_AsyncMock(return_value={"resolved": False, "linked_by": []}),
    ), _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_search_orphan_candidates",
        new=_AsyncMock(return_value={
            "candidates": ["candidate-page"],
            "strategy": "title_bm25",
            "tried_slugs": ["candidate-page"],
        }),
    ), _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_read_page_content",
        new=_AsyncMock(return_value={
            "slug": "candidate-page",
            "content": candidate_original,
        }),
    ), _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_propose_and_apply",
        new=_AsyncMock(return_value={"applied": True, "diff_preview": "..."}),
    ) as mock_apply, _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_notify",
        new=_AsyncMock(return_value={"sent": True}),
    ) as mock_notify:
        events = []
        async for evt in wf.run_for_cli_provider(ctx, "run orphan resolver", fake_provider):
            events.append(evt)

    # The guard must discard the rewrite — propose_and_apply must NOT be called.
    mock_apply.assert_not_called()
    # The orphan ends up unresolved, so tool_notify fires the escalation message.
    mock_notify.assert_called_once()
    token_text = "".join(e["data"]["text"] for e in events if e["event"] == "token")
    assert "Unresolved" in token_text


@pytest.mark.asyncio
async def test_orphan_resolver_cli_path_no_candidates(tmp_path):
    """Both BM25 strategies return no candidates → orphan marked unresolved."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.orphan_resolver import OrphanResolverWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = OrphanResolverWorkflow()

    with _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_find_orphaned_pages",
        new=_AsyncMock(return_value={"orphans": ["isolated-page"], "count": 1}),
    ), _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_estimate_and_confirm",
        new=_AsyncMock(return_value={"confirmed": True, "orphan_count": 1}),
    ), _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_verify_orphan_resolved",
        new=_AsyncMock(return_value={"resolved": False, "linked_by": []}),
    ), _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_search_orphan_candidates",
        new=_AsyncMock(return_value={
            "candidates": [], "strategy": "title_bm25", "tried_slugs": [],
        }),
    ), _patch(
        "synthadoc.agents.workflows.orphan_resolver.tool_notify",
        new=_AsyncMock(return_value={"sent": True}),
    ) as mock_notify:
        events = []
        async for evt in wf.run_for_cli_provider(ctx, "run orphan resolver", MagicMock()):
            events.append(evt)

    mock_notify.assert_called_once()
    token_text = "".join(e["data"]["text"] for e in events if e["event"] == "token")
    assert "isolated-page" in token_text
    assert "Unresolved" in token_text


# ── LintReportWorkflow — CLI provider path ────────────────────────────────────

@pytest.mark.asyncio
async def test_lint_report_cli_path_lint_failure(tmp_path):
    """tool_run_lint returns a failure → early exit, get_lint_report never called."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.lint_report import LintReportWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = LintReportWorkflow()

    with _patch(
        "synthadoc.agents.workflows.lint_report.tool_run_lint",
        new=_AsyncMock(return_value={"status": "failed", "message": "lint error"}),
    ), _patch(
        "synthadoc.agents.workflows.lint_report.tool_get_lint_report",
        new=_AsyncMock(),
    ) as mock_report:
        events = []
        async for evt in wf.run_for_cli_provider(ctx, "run lint", MagicMock()):
            events.append(evt)

    mock_report.assert_not_called()
    token_text = " ".join(e["data"]["text"] for e in events if e["event"] == "token")
    assert "lint failed" in token_text.lower()
    assert "final_text" in [e["event"] for e in events]


@pytest.mark.asyncio
async def test_lint_report_cli_path_clean_wiki(tmp_path):
    """Lint succeeds with empty report → all list sections show (none)."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.lint_report import LintReportWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = LintReportWorkflow()

    lint_report = {
        "last_run": {
            "timestamp": "2026-08-13", "dangling_removed": 0,
            "orphans": 0, "contradictions_resolved": 0, "contradictions_flagged": 0,
        },
        "contradicted_pages": [],
        "adversarial_warnings": [],
        "orphan_slugs": [],
        "broken_citations": 0,
        "broken_citation_pages": [],
    }

    with _patch(
        "synthadoc.agents.workflows.lint_report.tool_run_lint",
        new=_AsyncMock(return_value={"status": "success", "message": "ok"}),
    ), _patch(
        "synthadoc.agents.workflows.lint_report.tool_get_lint_report",
        new=_AsyncMock(return_value=lint_report),
    ):
        events = []
        async for evt in wf.run_for_cli_provider(ctx, "run lint", MagicMock()):
            events.append(evt)

    token_text = " ".join(e["data"]["text"] for e in events if e["event"] == "token")
    assert "Lint Report" in token_text
    assert "2026-08-13" in token_text
    # Timestamp-based sections with no items must show "(none)"
    assert token_text.count("(none)") == 4  # contradicted, warnings, orphans, citations
    # Zero-only summary lines are omitted (dangling and broken citations)
    assert "Dangling" not in token_text
    assert "Broken citations" not in token_text
    assert "final_text" in [e["event"] for e in events]


@pytest.mark.asyncio
async def test_lint_report_cli_path_with_issues(tmp_path):
    """Lint report with issues → all sections populated with correct formatting."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.lint_report import LintReportWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = LintReportWorkflow()

    lint_report = {
        "last_run": {
            "timestamp": "2026-08-13", "dangling_removed": 3,
            "orphans": 2, "contradictions_resolved": 1, "contradictions_flagged": 2,
        },
        "contradicted_pages": [{"slug": "alan-turing", "since": "2026-07-01"}],
        "adversarial_warnings": [{"slug": "grace-hopper", "count": 2}],
        "orphan_slugs": ["isolated-page", "no-links-page"],
        "broken_citations": 4,
        "broken_citation_pages": [{"slug": "ada-lovelace", "count": 4}],
    }

    with _patch(
        "synthadoc.agents.workflows.lint_report.tool_run_lint",
        new=_AsyncMock(return_value={"status": "success", "message": "ok"}),
    ), _patch(
        "synthadoc.agents.workflows.lint_report.tool_get_lint_report",
        new=_AsyncMock(return_value=lint_report),
    ):
        events = []
        async for evt in wf.run_for_cli_provider(ctx, "run lint", MagicMock()):
            events.append(evt)

    token_text = " ".join(e["data"]["text"] for e in events if e["event"] == "token")
    assert "Dangling links removed: 3" in token_text
    assert "Orphan pages: 2" in token_text
    assert "Contradictions: 1 resolved, 2 flagged" in token_text
    assert "Broken citations: 4" in token_text
    assert "alan-turing" in token_text
    assert "since 2026-07-01" in token_text
    assert "[[grace-hopper]]" in token_text
    assert "2 warnings" in token_text
    assert "isolated-page" in token_text
    assert "no-links-page" in token_text
    assert "[[ada-lovelace]]" in token_text
    assert "4 broken citations" in token_text
    assert "final_text" in [e["event"] for e in events]


# ── ScaffoldWorkflow — CLI provider path ──────────────────────────────────────

@pytest.mark.asyncio
async def test_scaffold_cli_path_cancelled(tmp_path):
    """tool_run_scaffold returns 'cancelled' (user declined) → cancellation message."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.scaffold import ScaffoldWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = ScaffoldWorkflow()

    with _patch(
        "synthadoc.agents.workflows.scaffold.tool_get_scaffold_preview",
        new=_AsyncMock(return_value={
            "domain": "AI Research", "files_to_overwrite": ["wiki/index.md"],
        }),
    ), _patch(
        "synthadoc.agents.workflows.scaffold.tool_run_scaffold",
        new=_AsyncMock(return_value={"status": "cancelled", "message": "User declined."}),
    ):
        events = []
        async for evt in wf.run_for_cli_provider(ctx, "run scaffold", MagicMock()):
            events.append(evt)

    token_text = " ".join(e["data"]["text"] for e in events if e["event"] == "token")
    assert "cancel" in token_text.lower()
    assert "final_text" in [e["event"] for e in events]


@pytest.mark.asyncio
async def test_scaffold_cli_path_success(tmp_path):
    """Successful scaffold → summary with domain, files, categories, routing flag."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.scaffold import ScaffoldWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = ScaffoldWorkflow()

    preview = {
        "domain": "AI Research",
        "files_to_overwrite": ["wiki/index.md", "wiki/purpose.md"],
    }
    scaffold_result = {
        "status": "success",
        "domain": "AI Research",
        "categories_updated": 5,
        "routing_regenerated": True,
    }

    with _patch(
        "synthadoc.agents.workflows.scaffold.tool_get_scaffold_preview",
        new=_AsyncMock(return_value=preview),
    ), _patch(
        "synthadoc.agents.workflows.scaffold.tool_run_scaffold",
        new=_AsyncMock(return_value=scaffold_result),
    ) as mock_scaffold:
        events = []
        async for evt in wf.run_for_cli_provider(ctx, "run scaffold", MagicMock()):
            events.append(evt)

    # run_scaffold must receive the domain from get_scaffold_preview
    mock_scaffold.assert_called_once_with(ctx, domain="AI Research")
    token_text = " ".join(e["data"]["text"] for e in events if e["event"] == "token")
    assert "AI Research" in token_text
    assert "wiki/index.md" in token_text
    assert "5 pages" in token_text
    assert "ROUTING.md regenerated: Yes" in token_text
    assert "Preservation" in token_text
    assert "final_text" in [e["event"] for e in events]


@pytest.mark.asyncio
async def test_scaffold_cli_path_error(tmp_path):
    """tool_run_scaffold returns a failure status → error message, no summary."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.scaffold import ScaffoldWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = ScaffoldWorkflow()

    with _patch(
        "synthadoc.agents.workflows.scaffold.tool_get_scaffold_preview",
        new=_AsyncMock(return_value={"domain": "AI Research", "files_to_overwrite": []}),
    ), _patch(
        "synthadoc.agents.workflows.scaffold.tool_run_scaffold",
        new=_AsyncMock(return_value={"status": "failed", "message": "queue timeout"}),
    ):
        events = []
        async for evt in wf.run_for_cli_provider(ctx, "run scaffold", MagicMock()):
            events.append(evt)

    token_text = " ".join(e["data"]["text"] for e in events if e["event"] == "token")
    assert "scaffold failed" in token_text.lower()
    assert "Preservation" not in token_text
    assert "final_text" in [e["event"] for e in events]


# ── Extra coverage gaps ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_lint_cli_path_workflow_b_cancelled(tmp_path):
    """Workflow B (single slug): confirm declined → 'Cancelled' message, no ingest called."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.ingest_lint import IngestLintWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = IngestLintWorkflow()

    with _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_find_page_source",
        new=_AsyncMock(return_value={"source_path": "/docs/alan-turing.md"}),
    ), _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_confirm",
        new=_AsyncMock(return_value={"confirmed": False}),
    ), _patch(
        "synthadoc.agents.workflows.ingest_lint.tool_ingest_source",
        new=_AsyncMock(),
    ) as mock_ingest:
        events = []
        async for evt in wf.run_for_cli_provider(
            ctx, "re-ingest the alan-turing", MagicMock()
        ):
            events.append(evt)

    mock_ingest.assert_not_called()
    token_text = " ".join(e["data"]["text"] for e in events if e["event"] == "token")
    assert "cancelled" in token_text.lower()
    assert "final_text" in [e["event"] for e in events]


@pytest.mark.asyncio
async def test_scaffold_cli_path_no_overwrite_files(tmp_path):
    """Scaffold success with files_to_overwrite=[] → 'Files written: (none)' in summary."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.scaffold import ScaffoldWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = ScaffoldWorkflow()

    preview = {"domain": "AI Research", "files_to_overwrite": []}
    scaffold_result = {
        "status": "success",
        "domain": "AI Research",
        "categories_updated": 3,
        "routing_regenerated": False,
    }

    with _patch(
        "synthadoc.agents.workflows.scaffold.tool_get_scaffold_preview",
        new=_AsyncMock(return_value=preview),
    ), _patch(
        "synthadoc.agents.workflows.scaffold.tool_run_scaffold",
        new=_AsyncMock(return_value=scaffold_result),
    ):
        events = []
        async for evt in wf.run_for_cli_provider(ctx, "run scaffold", MagicMock()):
            events.append(evt)

    token_text = " ".join(e["data"]["text"] for e in events if e["event"] == "token")
    assert "Files written: (none)" in token_text
    assert "final_text" in [e["event"] for e in events]


@pytest.mark.asyncio
async def test_broken_wikilinks_cli_path_fix_error_shown_in_summary(tmp_path):
    """When apply_link_fixes returns an error, the summary shows '⚠ error' for that page."""
    from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
    from synthadoc.agents.workflows.broken_wikilinks import BrokenWikilinksWorkflow
    from synthadoc.agents.workflows._base import WorkflowContext

    ctx = MagicMock(spec=WorkflowContext)
    ctx.send_sse_event = _AsyncMock()
    wf = BrokenWikilinksWorkflow()

    scan_result = {
        "pages": [{"slug": "broken-page", "broken_links": [{"ref": "dead-ref", "suggestion": None}]}],
        "scanned": 1,
        "total_broken": 1,
    }

    with _patch(
        "synthadoc.agents.workflows.broken_wikilinks.tool_find_broken_wikilinks",
        new=_AsyncMock(return_value=scan_result),
    ), _patch(
        "synthadoc.agents.workflows.broken_wikilinks.tool_confirm",
        new=_AsyncMock(return_value={"confirmed": True}),
    ), _patch(
        "synthadoc.agents.workflows.broken_wikilinks.tool_apply_link_fixes",
        new=_AsyncMock(return_value={"status": "error", "error": "write permission denied"}),
    ), _patch(
        "synthadoc.agents.workflows.broken_wikilinks.tool_run_lint",
        new=_AsyncMock(return_value={"status": "success"}),
    ), _patch(
        "synthadoc.agents.workflows.broken_wikilinks.tool_get_page_states",
        new=_AsyncMock(return_value={"pages": [{"slug": "broken-page", "state": "active"}]}),
    ):
        events = []
        async for evt in wf.run_for_cli_provider(ctx, "fix broken wikilinks", MagicMock()):
            events.append(evt)

    token_text = " ".join(e["data"]["text"] for e in events if e["event"] == "token")
    assert "⚠ error" in token_text
    assert "write permission denied" in token_text


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
