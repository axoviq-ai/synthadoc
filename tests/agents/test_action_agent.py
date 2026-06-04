# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from synthadoc.agents.action_agent import ActionAgent, _format_schedule_list
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


# ── none action ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_none_action_returns_none(tmp_path):
    extraction = '{"action": "none", "params": {}}'
    agent = _make_agent(tmp_path, extraction)
    result = await agent.run("What is the capital of France?")
    assert result is None


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
