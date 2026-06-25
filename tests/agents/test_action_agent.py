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
        inst.get_lifecycle_summary = AsyncMock(return_value=counts)
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

def test_fmt_job_ts_none():
    from synthadoc.agents.action_agent import ActionAgent
    assert ActionAgent._fmt_job_ts(None) == "—"

def test_fmt_job_ts_invalid():
    from synthadoc.agents.action_agent import ActionAgent
    assert ActionAgent._fmt_job_ts("not-a-date") == "not-a-date"

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
