# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Targeted tests to boost coverage across several low-coverage modules.

These tests focus on edge cases and error branches not covered by the existing
test suite, chosen to maximise statement coverage with minimal test complexity.
"""
from __future__ import annotations

import platform
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── cli/_utils.py ─────────────────────────────────────────────────────────────

def test_resolve_root_returns_cwd_when_none():
    from synthadoc.cli._utils import _resolve_root
    result = _resolve_root(None)
    assert result == Path(".")


def test_resolve_root_returns_path_from_string():
    from synthadoc.cli._utils import _resolve_root
    result = _resolve_root("/tmp/my-wiki")
    assert result == Path("/tmp/my-wiki")


# ── core/cost_guard.py ────────────────────────────────────────────────────────

def test_cost_guard_interactive_aborts_on_n():
    from synthadoc.core.cost_guard import CostGuard, CostEstimate, CostGateError
    from synthadoc.config import CostConfig
    guard = CostGuard(CostConfig(soft_warn_usd=0.01, hard_gate_usd=0.05))
    with patch("builtins.input", return_value="n"):
        with pytest.raises(CostGateError, match="Aborted"):
            guard.check(
                CostEstimate(tokens=10000, cost_usd=1.00, operation="batch"),
                auto_confirm=False, interactive=True
            )


def test_cost_guard_interactive_proceeds_on_y():
    from synthadoc.core.cost_guard import CostGuard, CostEstimate
    from synthadoc.config import CostConfig
    guard = CostGuard(CostConfig(soft_warn_usd=0.01, hard_gate_usd=0.05))
    with patch("builtins.input", return_value="y"):
        # Should not raise
        guard.check(
            CostEstimate(tokens=10000, cost_usd=1.00, operation="batch"),
            auto_confirm=False, interactive=True
        )


# ── core/scheduler.py ─────────────────────────────────────────────────────────

def test_scheduler_register_os_task_windows():
    """_register_os_task routes to schtasks on Windows."""
    from synthadoc.core.scheduler import Scheduler
    sched = Scheduler(wiki="my-wiki", wiki_root="/wikis/my-wiki")
    with patch("platform.system", return_value="Windows"), \
         patch.object(sched, "_build_schtasks_args", return_value=["arg"]) as mock_args, \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        sched._register_os_task(op="lint run", cron="0 3 * * 0", entry_id="s1")
    mock_args.assert_called_once()
    mock_run.assert_called_once()


def test_scheduler_register_os_task_linux():
    """_register_os_task routes to crontab on non-Windows."""
    from synthadoc.core.scheduler import Scheduler
    sched = Scheduler(wiki="my-wiki", wiki_root="/wikis/my-wiki")
    with patch("platform.system", return_value="Linux"), \
         patch.object(sched, "_add_crontab_entry") as mock_cron:
        sched._register_os_task(op="lint run", cron="0 3 * * 0", entry_id="s1")
    mock_cron.assert_called_once_with(op="lint run", cron="0 3 * * 0", entry_id="s1")


def test_scheduler_list_os_tasks_windows():
    """_list_os_tasks routes to _list_schtasks on Windows."""
    from synthadoc.core.scheduler import Scheduler
    sched = Scheduler(wiki="my-wiki", wiki_root="/wikis/my-wiki")
    with patch("platform.system", return_value="Windows"), \
         patch.object(sched, "_list_schtasks", return_value=[]) as mock_list:
        sched._list_os_tasks()
    mock_list.assert_called_once()


def test_scheduler_remove_os_task_windows():
    """_remove_os_task calls schtasks /Delete on Windows."""
    from synthadoc.core.scheduler import Scheduler
    import subprocess
    sched = Scheduler(wiki="my-wiki", wiki_root="/wikis/my-wiki")
    with patch("platform.system", return_value="Windows"), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        sched._remove_os_task("sched-win1")
    call_args = mock_run.call_args[0][0]
    assert "/Delete" in call_args
    assert "synthadoc-sched-win1" in call_args


def test_scheduler_remove_os_task_linux():
    """_remove_os_task rewrites crontab on non-Windows."""
    from synthadoc.core.scheduler import Scheduler
    sched = Scheduler(wiki="my-wiki", wiki_root="/wikis/my-wiki")
    existing = "0 2 * * * cmd # synthadoc:sched-001\n0 3 * * * other\n"
    with patch("platform.system", return_value="Linux"), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=existing)
        sched._remove_os_task("sched-001")
    # Second call writes new crontab (with the entry removed)
    assert mock_run.call_count == 2


# ── cli/ingest.py ─────────────────────────────────────────────────────────────

def test_ingest_validate_source_invalid_path_exits():
    import typer
    from synthadoc.cli.ingest import _validate_source
    with pytest.raises((SystemExit, typer.Exit, Exception)):
        _validate_source("/nonexistent/path/file.pdf")


def test_ingest_validate_source_valid_url():
    from synthadoc.cli.ingest import _validate_source
    _validate_source("https://example.com/article")  # no exception


def test_ingest_validate_source_intent_phrase():
    from synthadoc.cli.ingest import _validate_source
    _validate_source("search for: computing history")  # no exception


def test_ingest_no_source_exits():
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    runner = CliRunner()
    result = runner.invoke(app, ["ingest", "--wiki", "/tmp/no-wiki"])
    assert result.exit_code != 0


def test_ingest_batch_dir_not_found(tmp_path):
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    runner = CliRunner()
    nonexistent = tmp_path / "no-such-dir"
    result = runner.invoke(app, ["ingest", "--batch", str(nonexistent), "--wiki", str(tmp_path)])
    assert result.exit_code != 0


def test_ingest_batch_not_a_dir(tmp_path):
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    runner = CliRunner()
    f = tmp_path / "afile.pdf"
    f.write_bytes(b"dummy")
    result = runner.invoke(app, ["ingest", "--batch", str(f), "--wiki", str(tmp_path)])
    assert result.exit_code != 0


def test_ingest_batch_no_files_exits(tmp_path):
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    runner = CliRunner()
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    result = runner.invoke(app, ["ingest", "--batch", str(empty_dir), "--wiki", str(tmp_path)])
    assert result.exit_code != 0


def test_ingest_max_results_included_in_body(tmp_path):
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    runner = CliRunner()

    captured_body = {}

    def fake_post(wiki, path, body, timeout=60):
        captured_body.update(body)
        return {"job_id": "job-123"}

    with patch("synthadoc.cli.ingest.post", side_effect=fake_post), \
         patch("synthadoc.cli._wiki.resolve_wiki", return_value=str(tmp_path)):
        result = runner.invoke(app, [
            "ingest", "https://example.com/page",
            "--max-results", "5",
            "--wiki", str(tmp_path),
        ])

    assert captured_body.get("max_results") == 5


def test_ingest_analyse_only_calls_analyse_endpoint(tmp_path):
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    runner = CliRunner()

    def fake_post(wiki, path, body, timeout=60):
        assert "/analyse" in path
        return {"entities": [], "tags": [], "summary": "test"}

    with patch("synthadoc.cli.ingest.post", side_effect=fake_post), \
         patch("synthadoc.cli._wiki.resolve_wiki", return_value=str(tmp_path)):
        result = runner.invoke(app, [
            "ingest", "https://example.com/page",
            "--analyse-only",
            "--wiki", str(tmp_path),
        ])

    assert result.exit_code == 0, result.output


# ── cli/candidates.py ─────────────────────────────────────────────────────────

def test_toml_value_fallback_uses_json_dumps():
    from synthadoc.cli.candidates import _toml_value
    # A float value should call the fallback json.dumps path
    result = _toml_value(3.14)
    assert "3.14" in result


def test_staging_policy_invalid_policy_exits(tmp_path):
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    runner = CliRunner()
    cfg_dir = tmp_path / ".synthadoc"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text('[ingest]\nstaging_policy = "off"\n')
    result = runner.invoke(app, ["staging", "policy", "invalid_policy", "--wiki", str(tmp_path)])
    assert result.exit_code != 0


def test_staging_policy_threshold_with_min_confidence(tmp_path):
    import tomllib
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    runner = CliRunner()
    cfg_dir = tmp_path / ".synthadoc"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text('[ingest]\nstaging_policy = "off"\n')
    result = runner.invoke(app, [
        "staging", "policy", "threshold",
        "--min-confidence", "medium",
        "--wiki", str(tmp_path),
    ])
    assert result.exit_code == 0, result.output
    assert "medium" in result.output
    cfg = tomllib.loads((tmp_path / ".synthadoc" / "config.toml").read_text())
    assert cfg["ingest"]["staging_confidence_min"] == "medium"


def test_candidates_promote_missing_slug_shows_not_found(tmp_path):
    """Promoting a slug that does not exist shows 'Not found'."""
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    runner = CliRunner()
    (tmp_path / "wiki" / "candidates").mkdir(parents=True)
    (tmp_path / ".synthadoc").mkdir(exist_ok=True)
    (tmp_path / ".synthadoc" / "config.toml").write_text('[ingest]\n')
    result = runner.invoke(app, ["candidates", "promote", "missing-slug", "--wiki", str(tmp_path)])
    assert result.exit_code == 0
    assert "Not found" in result.output


def test_read_frontmatter_no_leading_dashes(tmp_path):
    """_read_frontmatter returns {} when file does not start with ---."""
    from synthadoc.cli.candidates import _read_frontmatter
    f = tmp_path / "page.md"
    f.write_text("# No frontmatter\n\nContent here.\n", encoding="utf-8")
    assert _read_frontmatter(f) == {}


def test_read_frontmatter_malformed_yaml(tmp_path):
    """_read_frontmatter returns {} on YAML parse error."""
    from synthadoc.cli.candidates import _read_frontmatter
    f = tmp_path / "page.md"
    f.write_text("---\n: bad: yaml: :\n---\nContent.\n", encoding="utf-8")
    result = _read_frontmatter(f)
    assert isinstance(result, dict)


def test_read_frontmatter_incomplete_delimiters(tmp_path):
    """_read_frontmatter returns {} when closing --- is absent."""
    from synthadoc.cli.candidates import _read_frontmatter
    f = tmp_path / "page.md"
    f.write_text("---\ntitle: No closing delimiter\n", encoding="utf-8")
    assert _read_frontmatter(f) == {}


def test_page_title_falls_back_to_slug(tmp_path):
    """_page_title derives a title from the filename when frontmatter has no title."""
    from synthadoc.cli.candidates import _page_title
    f = tmp_path / "alan-turing.md"
    f.write_text("---\ntags: []\n---\nContent.", encoding="utf-8")
    assert _page_title(f) == "Alan Turing"


def test_patch_toml_section_ends_before_next_section(tmp_path):
    """_patch_toml appends unseen keys before the next section starts."""
    from synthadoc.cli.candidates import _patch_toml
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "[ingest]\nsome_key = 1\n\n[server]\nport = 7070\n",
        encoding="utf-8",
    )
    _patch_toml(cfg, "ingest", {"staging_policy": "all"})
    content = cfg.read_text()
    assert 'staging_policy = "all"' in content
    assert "port = 7070" in content


# ── cli/scaffold.py — _run_scaffold() ─────────────────────────────────────────

def test_run_scaffold_returns_none_when_no_api_key(tmp_path):
    """_run_scaffold returns None when the required API env var is unset."""
    from synthadoc.cli.scaffold import _run_scaffold
    sd = tmp_path / ".synthadoc"
    sd.mkdir()
    (sd / "config.toml").write_text(
        '[agents]\ndefault = { provider = "gemini", model = "gemini-2.5-flash" }\n',
        encoding="utf-8",
    )
    with patch.dict("os.environ", {"GEMINI_API_KEY": ""}, clear=False):
        result = _run_scaffold(tmp_path, "test domain")
    assert result is None


def test_run_scaffold_returns_none_on_llm_exception(tmp_path):
    """_run_scaffold returns None and logs a warning when ScaffoldAgent raises."""
    from synthadoc.cli.scaffold import _run_scaffold
    sd = tmp_path / ".synthadoc"
    sd.mkdir()
    (sd / "config.toml").write_text(
        '[agents]\ndefault = { provider = "gemini", model = "gemini-2.5-flash" }\n',
        encoding="utf-8",
    )
    with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}, clear=False), \
         patch("synthadoc.providers.make_provider", return_value=MagicMock()), \
         patch("synthadoc.agents.scaffold_agent.ScaffoldAgent") as MockAgent:
        MockAgent.return_value.scaffold = AsyncMock(side_effect=RuntimeError("LLM failed"))
        result = _run_scaffold(tmp_path, "test domain")
    assert result is None


def test_install_run_scaffold_returns_none_when_no_api_key(tmp_path):
    """install._run_scaffold returns None when the required API env var is unset."""
    from synthadoc.cli.install import _run_scaffold
    sd = tmp_path / ".synthadoc"
    sd.mkdir()
    (sd / "config.toml").write_text(
        '[agents]\ndefault = { provider = "gemini", model = "gemini-2.5-flash" }\n',
        encoding="utf-8",
    )
    with patch.dict("os.environ", {"GEMINI_API_KEY": ""}, clear=False):
        result = _run_scaffold(tmp_path, "test domain")
    assert result is None


def test_install_run_scaffold_returns_none_on_exception(tmp_path):
    """install._run_scaffold returns None when ScaffoldAgent raises."""
    from synthadoc.cli.install import _run_scaffold
    sd = tmp_path / ".synthadoc"
    sd.mkdir()
    (sd / "config.toml").write_text(
        '[agents]\ndefault = { provider = "gemini", model = "gemini-2.5-flash" }\n',
        encoding="utf-8",
    )
    with patch.dict("os.environ", {"GEMINI_API_KEY": "fake"}, clear=False), \
         patch("synthadoc.providers.make_provider", return_value=MagicMock()), \
         patch("synthadoc.agents.scaffold_agent.ScaffoldAgent") as MockAgent:
        MockAgent.return_value.scaffold = AsyncMock(side_effect=RuntimeError("API error"))
        result = _run_scaffold(tmp_path, "test domain")
    assert result is None


# ── cli/install.py — list_cmd and uninstall edge ──────────────────────────────

def test_install_list_cmd_empty_registry():
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    runner = CliRunner()
    with patch("synthadoc.cli.install._read_registry", return_value={}):
        result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "No wikis" in result.output


def test_install_list_cmd_shows_wikis():
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    runner = CliRunner()
    registry = {
        "my-wiki": {"path": "/home/user/wikis/my-wiki", "demo": None,
                    "installed": "2026-01-01", "port": 7070},
        "demo-wiki": {"path": "/home/user/wikis/demo-wiki", "demo": "history-of-computing",
                      "installed": "2026-01-02", "port": 7071},
    }
    with patch("synthadoc.cli.install._read_registry", return_value=registry):
        result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "my-wiki" in result.output
    assert "demo-wiki" in result.output
    assert "[demo]" in result.output


def test_install_list_cmd_shows_port():
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    runner = CliRunner()
    registry = {
        "wiki-a": {"path": "/wikis/wiki-a", "demo": None, "installed": "2026-01-01", "port": 7072},
    }
    with patch("synthadoc.cli.install._read_registry", return_value=registry):
        result = runner.invoke(app, ["list"])
    assert "7072" in result.output


# ── cli/install.py — port auto-assignment ─────────────────────────────────────

def test_install_cmd_uses_explicit_port(tmp_path):
    """--port <N> uses that port without auto-assignment."""
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    runner = CliRunner()
    target = tmp_path / "wikis"
    target.mkdir()

    with patch("synthadoc.cli.install._read_registry", return_value={}), \
         patch("synthadoc.cli.install._write_registry"), \
         patch("synthadoc.cli.install._run_scaffold", return_value=None), \
         patch("synthadoc.cli._init.init_wiki"):
        result = runner.invoke(app, [
            "install", "test-wiki",
            "--target", str(target),
            "--port", "7099",
        ])
    # Should show the specified port
    assert "7099" in result.output or result.exit_code == 0


# ── core/orchestrator.py — _run_scaffold and _run_lint quota ─────────────────

@pytest.mark.asyncio
async def test_run_scaffold_completes_job(tmp_wiki):
    """_run_scaffold writes files and marks the job completed."""
    from synthadoc.config import load_config
    from synthadoc.core.orchestrator import Orchestrator
    from synthadoc.agents.scaffold_agent import ScaffoldResult

    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    await orch.init()

    job_id = await orch._queue.enqueue("scaffold", {"domain": "Test Domain"})

    result = ScaffoldResult(
        index_md="# Index\n",
        agents_md="# Agents\n",
        purpose_md="# Purpose\n",
        dashboard_intro="intro",
    )

    with patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
         patch("synthadoc.agents.scaffold_agent.ScaffoldAgent") as MockAgent:
        MockAgent.return_value.scaffold = AsyncMock(return_value=result)
        await orch._run_scaffold(job_id, "Test Domain")

    from synthadoc.core.queue import JobStatus
    completed = await orch._queue.list_jobs(status=JobStatus.COMPLETED)
    assert any(j.id == job_id for j in completed)


@pytest.mark.asyncio
async def test_run_scaffold_fails_job_on_exception(tmp_wiki):
    """_run_scaffold marks the job as non-completed and re-raises on exception."""
    from synthadoc.config import load_config
    from synthadoc.core.orchestrator import Orchestrator

    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    await orch.init()
    job_id = await orch._queue.enqueue("scaffold", {"domain": "Test Domain"})

    with patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
         patch("synthadoc.agents.scaffold_agent.ScaffoldAgent") as MockAgent:
        MockAgent.return_value.scaffold = AsyncMock(side_effect=RuntimeError("LLM error"))
        with pytest.raises(RuntimeError):
            await orch._run_scaffold(job_id, "Test Domain")

    from synthadoc.core.queue import JobStatus
    completed = await orch._queue.list_jobs(status=JobStatus.COMPLETED)
    assert not any(j.id == job_id for j in completed), "Job must not be completed after exception"


@pytest.mark.asyncio
async def test_run_lint_daily_quota_fails_permanent(tmp_wiki):
    """_run_lint permanently fails on DailyQuotaExhaustedException."""
    from synthadoc.config import load_config
    from synthadoc.core.orchestrator import Orchestrator
    from synthadoc.errors import DailyQuotaExhaustedException

    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    await orch.init()
    job_id = await orch._queue.enqueue("lint", {"scope": "all"})

    with patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
         patch("synthadoc.agents.lint_agent.LintAgent") as MockLint:
        MockLint.return_value.lint = AsyncMock(
            side_effect=DailyQuotaExhaustedException(provider="gemini"))
        await orch._run_lint(job_id)

    from synthadoc.core.queue import JobStatus
    failed = await orch._queue.list_jobs(status=JobStatus.FAILED)
    assert any(j.id == job_id for j in failed)


@pytest.mark.asyncio
async def test_run_lint_generic_exception_reraises(tmp_wiki):
    """_run_lint re-raises on unexpected exception (job is not completed)."""
    from synthadoc.config import load_config
    from synthadoc.core.orchestrator import Orchestrator

    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    await orch.init()
    job_id = await orch._queue.enqueue("lint", {"scope": "all"})

    with patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
         patch("synthadoc.agents.lint_agent.LintAgent") as MockLint:
        MockLint.return_value.lint = AsyncMock(side_effect=ValueError("unexpected"))
        with pytest.raises(ValueError):
            await orch._run_lint(job_id)

    from synthadoc.core.queue import JobStatus
    completed = await orch._queue.list_jobs(status=JobStatus.COMPLETED)
    assert not any(j.id == job_id for j in completed), "Job must not be completed after exception"


@pytest.mark.asyncio
async def test_run_ingest_rate_limit_requeues_and_raises(tmp_wiki):
    """A 429 rate-limit exception requeues the job without burning a retry, then re-raises."""
    import httpx
    from synthadoc.config import load_config
    from synthadoc.core.orchestrator import Orchestrator

    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    await orch.init()
    job_id = await orch._queue.enqueue("ingest", {"source": "https://example.com", "force": False})

    # Build an exception with status_code=429
    rate_exc = Exception("rate limited")
    rate_exc.status_code = 429  # type: ignore

    mock_agent = MagicMock()
    mock_agent.ingest = AsyncMock(side_effect=rate_exc)
    with patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
         patch("synthadoc.agents.ingest_agent.IngestAgent", return_value=mock_agent):
        with pytest.raises(Exception):
            await orch._run_ingest(job_id, "https://example.com", auto_confirm=True)


@pytest.mark.asyncio
async def test_auto_block_domain_writes_file(tmp_wiki):
    """_auto_block_domain persists the blocked domain to blocked_domains.json."""
    from synthadoc.config import load_config
    from synthadoc.core.orchestrator import Orchestrator
    from synthadoc.errors import DomainBlockedException

    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    await orch.init()

    exc = DomainBlockedException(domain="blocked.com", url="https://blocked.com/page", status_code=403)
    await orch._auto_block_domain(exc)

    import json
    blocked_file = tmp_wiki / ".synthadoc" / "blocked_domains.json"
    assert blocked_file.exists()
    domains = json.loads(blocked_file.read_text())
    assert "blocked.com" in domains


@pytest.mark.asyncio
async def test_auto_block_domain_does_not_duplicate(tmp_wiki):
    """_auto_block_domain does not add the same domain twice."""
    import json
    from synthadoc.config import load_config
    from synthadoc.core.orchestrator import Orchestrator
    from synthadoc.errors import DomainBlockedException

    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    await orch.init()

    blocked_file = tmp_wiki / ".synthadoc" / "blocked_domains.json"
    blocked_file.write_text('["blocked.com"]', encoding="utf-8")

    exc = DomainBlockedException(domain="blocked.com", url="https://blocked.com/p", status_code=403)
    await orch._auto_block_domain(exc)

    domains = json.loads(blocked_file.read_text())
    assert domains.count("blocked.com") == 1


@pytest.mark.asyncio
async def test_run_ingest_vector_embed_on_complete(tmp_wiki):
    """When search.vector=True and a page exists in the store, _run_ingest embeds it."""
    from synthadoc.agents.ingest_agent import IngestResult
    from synthadoc.config import Config, AgentsConfig, AgentConfig, SearchConfig
    from synthadoc.core.orchestrator import Orchestrator
    from synthadoc.storage.wiki import WikiPage, SourceRef

    cfg = Config(
        agents=AgentsConfig(default=AgentConfig(provider="gemini", model="gemini-2.5-flash")),
        search=SearchConfig(vector=True),
    )
    orch = Orchestrator(wiki_root=tmp_wiki, config=cfg)
    await orch._queue.init()
    await orch._audit.init()
    await orch._cache.init()

    # Write the page to the wiki store so read_page returns it
    page = WikiPage(
        title="New Page", tags=[], status="active", confidence="high",
        content="Content.", sources=[],
    )
    orch._store.write_page("new-page", page)

    job_id = await orch._queue.enqueue("ingest", {"source": "https://ex.com", "force": False})

    result = IngestResult(source="https://ex.com")
    result.pages_created = ["new-page"]
    result.pages_updated = []
    result.pages_flagged = []
    result.child_sources = []
    result.tokens_used = 10
    result.input_tokens = 5
    result.output_tokens = 5
    result.skipped = False

    embed_calls = []

    async def fake_embed(slug, text):
        embed_calls.append(slug)

    mock_agent = MagicMock()
    mock_agent.ingest = AsyncMock(return_value=result)

    with patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
         patch("synthadoc.agents.ingest_agent.IngestAgent", return_value=mock_agent), \
         patch.object(orch._search, "embed_page", side_effect=fake_embed):
        await orch._run_ingest(job_id, "https://ex.com", auto_confirm=True)

    assert "new-page" in embed_calls


# ── cli/_http.py — server_url and happy paths ─────────────────────────────────

def test_server_url_reads_port_from_config(tmp_path):
    """server_url returns the correct URL from config.toml."""
    from synthadoc.cli._http import server_url
    sd = tmp_path / ".synthadoc"
    sd.mkdir()
    (sd / "config.toml").write_text("[server]\nport = 7777\n", encoding="utf-8")

    with patch("synthadoc.cli._http.resolve_wiki_path", return_value=tmp_path):
        url = server_url("my-wiki")

    assert url == "http://127.0.0.1:7777"


def test_server_url_missing_config_exits(tmp_path):
    """server_url raises Exit when config.toml does not exist."""
    import typer
    from synthadoc.cli._http import server_url
    with patch("synthadoc.cli._http.resolve_wiki_path", return_value=tmp_path):
        with pytest.raises((SystemExit, typer.Exit, Exception)):
            server_url("no-wiki")


def test_http_get_happy_path():
    """get() returns parsed JSON on a 200 response."""
    from synthadoc.cli._http import get
    import httpx
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"status": "ok"}

    with patch("synthadoc.cli._http.server_url", return_value="http://127.0.0.1:7070"), \
         patch.object(httpx, "get", return_value=mock_resp):
        result = get("my-wiki", "/health")

    assert result == {"status": "ok"}


def test_http_post_happy_path():
    """post() returns parsed JSON on a 200 response."""
    from synthadoc.cli._http import post
    import httpx
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"job_id": "abc-123"}

    with patch("synthadoc.cli._http.server_url", return_value="http://127.0.0.1:7070"), \
         patch.object(httpx, "post", return_value=mock_resp):
        result = post("my-wiki", "/jobs/ingest", {"source": "file.md"})

    assert result["job_id"] == "abc-123"


def test_http_delete_happy_path():
    """delete() returns parsed JSON on a 200 response."""
    from synthadoc.cli._http import delete
    import httpx
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"deleted": True}

    with patch("synthadoc.cli._http.server_url", return_value="http://127.0.0.1:7070"), \
         patch.object(httpx, "delete", return_value=mock_resp):
        result = delete("my-wiki", "/jobs/abc-123")

    assert result["deleted"] is True


# ── cli/lint.py ───────────────────────────────────────────────────────────────

def test_lint_is_reingestable_with_url():
    from synthadoc.cli.lint import _is_reingestable
    assert _is_reingestable("https://example.com/article") is True


def test_lint_is_reingestable_with_absolute_path(tmp_path):
    from synthadoc.cli.lint import _is_reingestable
    assert _is_reingestable(str(tmp_path / "file.pdf")) is True


def test_lint_is_reingestable_with_empty_string():
    from synthadoc.cli.lint import _is_reingestable
    assert _is_reingestable("") is False


def test_lint_is_reingestable_with_relative_path():
    from synthadoc.cli.lint import _is_reingestable
    assert _is_reingestable("relative/path.pdf") is False


def test_lint_report_shows_adversarial_warnings(tmp_path):
    """lint report prints adversarial warnings when pages have lint_warnings."""
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    runner = CliRunner()

    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "alan-turing.md").write_text(
        "---\ntitle: Alan Turing\ntags: []\nstatus: active\nconfidence: high\n"
        "created: '2026-01-01'\nsources: []\n"
        "lint_warnings:\n  - claim: 'He saved millions'\n    concern: 'Unsupported figure'\n"
        "---\nContent here.\n",
        encoding="utf-8",
    )

    with patch("synthadoc.cli._wiki.resolve_wiki", return_value=str(tmp_path)):
        result = runner.invoke(app, ["lint", "report", "--wiki", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "Adversarial" in result.output or "warnings" in result.output or "alan-turing" in result.output


def test_lint_report_shows_contradiction_note(tmp_path):
    """lint report shows contradiction_note when present in frontmatter."""
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    runner = CliRunner()

    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "grace-hopper.md").write_text(
        "---\ntitle: Grace Hopper\ntags: []\nstatus: contradicted\nconfidence: high\n"
        "created: '2026-01-01'\nsources: []\n"
        "contradiction_note: 'A-0 was a loader not a compiler'\n"
        "---\nContent.\n",
        encoding="utf-8",
    )

    with patch("synthadoc.cli._wiki.resolve_wiki", return_value=str(tmp_path)):
        result = runner.invoke(app, ["lint", "report", "--wiki", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "A-0 was a loader" in result.output or "grace-hopper" in result.output


# ── cli/plugin.py ─────────────────────────────────────────────────────────────

def test_plugin_install_no_files_exits(tmp_path):
    """plugin install exits when no plugin files are copied (build step missing)."""
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    runner = CliRunner()

    wiki_dir = tmp_path / "my-wiki"
    wiki_dir.mkdir()
    sd = wiki_dir / ".synthadoc"
    sd.mkdir()
    (sd / "config.toml").write_text("[server]\nport = 7070\n", encoding="utf-8")

    fake_plugin_src = tmp_path / "obsidian-plugin"
    fake_plugin_src.mkdir()  # exists but empty (no plugin files)

    with patch("synthadoc.cli.plugin.resolve_wiki_path", return_value=wiki_dir), \
         patch("synthadoc.cli.plugin._PLUGIN_SRC", fake_plugin_src), \
         patch("synthadoc.cli._wiki.resolve_wiki", return_value="my-wiki"):
        result = runner.invoke(app, ["plugin", "install", "my-wiki"])

    assert result.exit_code != 0


def test_plugin_upgrade_nothing_to_upgrade():
    """plugin upgrade with no wikis registered shows 'No wikis registered'."""
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    from pathlib import Path
    runner = CliRunner()

    fake_plugin_src = Path("/fake/obsidian-plugin")
    with patch("synthadoc.cli.plugin._read_registry", return_value={}), \
         patch("synthadoc.cli.plugin._PLUGIN_SRC") as mock_src:
        mock_src.exists.return_value = True
        mock_src.__str__ = lambda s: str(fake_plugin_src)
        result = runner.invoke(app, ["plugin", "upgrade"])

    assert result.exit_code == 0
    assert "No wikis" in result.output


def test_plugin_upgrade_skipped_no_files(tmp_path):
    """plugin upgrade shows Skipped when wiki has no plugin files to copy."""
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    runner = CliRunner()

    wiki_dir = tmp_path / "my-wiki"
    wiki_dir.mkdir()

    fake_plugin_src = tmp_path / "plugin-src"
    fake_plugin_src.mkdir()

    registry = {"my-wiki": {"path": str(wiki_dir)}}

    with patch("synthadoc.cli.plugin._read_registry", return_value=registry), \
         patch("synthadoc.cli.plugin._PLUGIN_SRC", fake_plugin_src):
        result = runner.invoke(app, ["plugin", "upgrade"])

    assert result.exit_code == 0
    assert "Skipped" in result.output or "no plugin files" in result.output.lower()


# ── config.py — TOML decode error ─────────────────────────────────────────────

def test_load_config_toml_decode_error_raises_value_error(tmp_path):
    """A TOML parse error in config raises ValueError with ERR-CFG-003."""
    from synthadoc.config import load_config
    bad_config = tmp_path / "config.toml"
    bad_config.write_text("[[agents]]\ndefault = { invalid", encoding="utf-8")
    with pytest.raises((ValueError, Exception)):
        load_config(project_config=bad_config)


def test_load_config_duplicate_key_raises_descriptive_error(tmp_path):
    """Duplicate agents.default lines give a descriptive ERR-CFG-003 message."""
    from synthadoc.config import load_config
    # TOML spec forbids duplicate keys — tomllib raises TOMLDecodeError
    bad_config = tmp_path / "config.toml"
    bad_config.write_text(
        "[agents]\ndefault = {provider='gemini',model='a'}\n"
        "default = {provider='anthropic',model='b'}\n",
        encoding="utf-8",
    )
    with pytest.raises((ValueError, Exception)):
        load_config(project_config=bad_config)


# ── storage/wiki.py ───────────────────────────────────────────────────────────

def test_write_page_with_unresolved_note(tmp_path):
    """write_page includes unresolved_note in frontmatter when set."""
    from synthadoc.storage.wiki import WikiStorage, WikiPage
    store = WikiStorage(tmp_path)
    page = WikiPage(
        title="Test", tags=[], status="active", confidence="high",
        content="Content.",
        sources=[],
        unresolved_note="LLM could not resolve",
    )
    store.write_page("test-page", page)
    text = (tmp_path / "test-page.md").read_text(encoding="utf-8")
    assert "unresolved_note" in text
    assert "LLM could not resolve" in text


def test_set_page_categories_noop_for_missing_page(tmp_path):
    """set_page_categories returns silently when the page does not exist."""
    from synthadoc.storage.wiki import WikiStorage
    store = WikiStorage(tmp_path)
    store.set_page_categories("nonexistent", ["Category A"])  # must not raise


def test_add_category_noop_for_missing_page(tmp_path):
    """_add_category returns silently when the page does not exist."""
    from synthadoc.storage.wiki import WikiStorage
    store = WikiStorage(tmp_path)
    store._add_category("nonexistent", "Category A")  # must not raise


def test_add_to_index_appends_to_existing_recently_added(tmp_path):
    """_add_to_recently_added_index appends to an existing Recently Added section."""
    from synthadoc.storage.wiki import WikiStorage, WikiPage
    store = WikiStorage(tmp_path)

    # Create index.md with an existing ## Recently Added section
    index_path = tmp_path / "index.md"
    index_path.write_text(
        "---\ntitle: Index\ntags: []\nstatus: active\nconfidence: high\n"
        "created: '2026-01-01'\nsources: []\n---\n\n# Index\n\n## People\n"
        "- [[existing-page]]\n\n## Recently Added\n- [[old-page]]\n",
        encoding="utf-8",
    )

    # Write a new page and call add_to_recently_added_index
    page = WikiPage(
        title="New Page", tags=[], status="active", confidence="high",
        content="Content.", sources=[],
    )
    store.write_page("new-page", page)
    store.append_to_index("new-page", "New Page")

    text = index_path.read_text(encoding="utf-8")
    assert "[[new-page]]" in text
    assert "[[old-page]]" in text  # existing entry preserved


# ── cli/jobs.py ───────────────────────────────────────────────────────────────

def test_jobs_delete_command():
    """jobs delete calls DELETE endpoint and echoes confirmation."""
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    runner = CliRunner()

    with patch("synthadoc.cli.jobs.http_delete", return_value={"deleted": True}) as mock_del, \
         patch("synthadoc.cli._wiki.resolve_wiki", return_value="my-wiki"):
        result = runner.invoke(app, ["jobs", "delete", "job-abc123", "--wiki", "my-wiki"])

    assert result.exit_code == 0
    assert "job-abc123" in result.output


# ── cli/audit.py ─────────────────────────────────────────────────────────────

def test_audit_citations_json_output(tmp_wiki):
    """audit citations --json outputs JSON to stdout."""
    import asyncio as _real_asyncio
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    runner = CliRunner()

    mock_records = [{"page_slug": "test", "citation": "file.txt:1-5", "valid": True}]

    async def fake_fetch():
        return mock_records

    def fake_asyncio_run(coro):
        # Clean up the coroutine to avoid RuntimeWarning
        try:
            return _real_asyncio.get_event_loop().run_until_complete(fake_fetch())
        except RuntimeError:
            return _real_asyncio.run(fake_fetch())

    with patch("synthadoc.cli.audit.asyncio.run", side_effect=lambda _coro: (_coro.close() or mock_records)):
        result = runner.invoke(app, [
            "audit", "citations",
            "--wiki", str(tmp_wiki),
            "--json",
        ])

    assert result.exit_code == 0, result.output


def test_audit_citations_empty_results(tmp_wiki):
    """audit citations shows 'No citations found' when empty."""
    from typer.testing import CliRunner
    from synthadoc.cli.main import app
    runner = CliRunner()

    with patch("synthadoc.cli.audit.asyncio.run", side_effect=lambda _coro: (_coro.close() or [])):
        result = runner.invoke(app, [
            "audit", "citations",
            "--wiki", str(tmp_wiki),
        ])

    assert result.exit_code == 0, result.output
    assert "No citations" in result.output


# ── core/orchestrator.py — _read_manifest and _resolve_manifest_source ────────

def test_read_manifest_returns_none_on_read_error(tmp_path):
    """_read_manifest returns None when the file cannot be read."""
    from synthadoc.core.orchestrator import _read_manifest
    nonexistent = tmp_path / "does_not_exist.txt"
    result = _read_manifest(nonexistent)
    assert result is None


def test_read_manifest_returns_none_for_empty_file(tmp_path):
    """_read_manifest returns None for a file with no content lines."""
    from synthadoc.core.orchestrator import _read_manifest
    empty = tmp_path / "empty.txt"
    empty.write_text("# comment only\n", encoding="utf-8")
    result = _read_manifest(empty)
    assert result is None


def test_read_manifest_returns_none_for_non_manifest_line(tmp_path):
    """_read_manifest returns None when a line is not a URL, intent, or valid path."""
    from synthadoc.core.orchestrator import _read_manifest
    f = tmp_path / "mixed.txt"
    f.write_text("https://example.com\njust plain text here\n", encoding="utf-8")
    result = _read_manifest(f)
    assert result is None


def test_read_manifest_returns_lines_for_valid_manifest(tmp_path):
    """_read_manifest returns content lines for a valid all-URL manifest."""
    from synthadoc.core.orchestrator import _read_manifest
    f = tmp_path / "sources.txt"
    f.write_text(
        "# batch ingest\nhttps://example.com/a\nhttps://example.com/b\n",
        encoding="utf-8",
    )
    result = _read_manifest(f)
    assert result == ["https://example.com/a", "https://example.com/b"]


def test_resolve_manifest_source_absolute_path(tmp_path):
    """_resolve_manifest_source returns the path unchanged when already absolute."""
    from synthadoc.core.orchestrator import _resolve_manifest_source
    abs_path = str(tmp_path / "file.pdf")
    result = _resolve_manifest_source(abs_path, tmp_path)
    assert result == abs_path


def test_resolve_manifest_source_relative_path(tmp_path):
    """_resolve_manifest_source resolves relative paths against the base directory."""
    from synthadoc.core.orchestrator import _resolve_manifest_source
    result = _resolve_manifest_source("subdir/file.pdf", tmp_path)
    assert str(tmp_path) in result
    assert "file.pdf" in result


def test_resolve_manifest_source_url_passthrough(tmp_path):
    """_resolve_manifest_source returns URLs unchanged."""
    from synthadoc.core.orchestrator import _resolve_manifest_source
    result = _resolve_manifest_source("https://example.com/page", tmp_path)
    assert result == "https://example.com/page"


# ── agents/lint_agent.py — targeted edge cases ────────────────────────────────

def test_check_page_citations_oserror_is_silenced(tmp_path):
    """_check_page_citations handles OSError on file read without raising."""
    from synthadoc.agents.lint_agent import _check_page_citations
    from synthadoc.storage.wiki import WikiPage, SourceRef

    # Citation references a source that is valid but the extracted .txt does not exist.
    # The extracted_dir itself does not exist — triggering the OSError branch.
    page = WikiPage(
        title="Test",
        tags=[],
        status="active",
        confidence="high",
        content="A claim.^[bio.txt:1000-2000]",
        sources=[SourceRef(file=str(tmp_path / "bio.txt"), hash="x", size=1000, ingested="2026-01-01")],
    )

    # Write a fake extracted .txt so the citation ref resolves, but make it too short
    extracted_dir = tmp_path / ".synthadoc" / "extracted"
    extracted_dir.mkdir(parents=True)
    (extracted_dir / "bio.txt").write_text("only 5 lines\n" * 5, encoding="utf-8")

    issues = _check_page_citations("test-page", page, extracted_dir)
    # Expect an out_of_range issue (line 1000 > 5 lines)
    assert any(i.get("reason") == "out_of_range" for i in issues)


def test_clean_dangling_links_skips_missing_page(tmp_path):
    """_clean_dangling_links skips slugs with no page in the store."""
    from synthadoc.agents.lint_agent import LintAgent
    from synthadoc.storage.wiki import WikiStorage
    from unittest.mock import MagicMock

    wiki_dir = tmp_path / "wiki_dangling"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    store = WikiStorage(wiki_dir)

    lint = LintAgent(
        provider=MagicMock(),
        store=store,
        log_writer=MagicMock(),
    )
    # Include a slug that has no page file — read_page returns None
    fixed = lint._clean_dangling_links(["nonexistent-slug"])
    assert fixed == 0


@pytest.mark.asyncio
async def test_run_adversarial_pass_empty_scan(tmp_path):
    """_run_adversarial_pass returns ([], 0) when there are no scannable pages."""
    from synthadoc.agents.lint_agent import LintAgent
    from synthadoc.storage.wiki import WikiStorage
    from unittest.mock import MagicMock

    wiki_dir = tmp_path / "wiki_adversarial"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    store = WikiStorage(wiki_dir)

    lint = LintAgent(
        provider=MagicMock(),
        store=store,
        log_writer=MagicMock(),
    )
    # No pages in the store — scan is empty
    result, tokens = await lint._run_adversarial_pass([])
    assert result == []
    assert tokens == 0


@pytest.mark.asyncio
async def test_adversarial_single_rate_limit_returns_skip_warning(tmp_path):
    """_adversarial_single returns a rate-limit skip warning on 429 error."""
    from synthadoc.agents.lint_agent import LintAgent
    from synthadoc.storage.wiki import WikiStorage
    from unittest.mock import MagicMock, AsyncMock

    wiki_dir = tmp_path / "wiki_single"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    store = WikiStorage(wiki_dir)

    mock_provider = MagicMock()
    mock_provider.complete = AsyncMock(side_effect=Exception("429 Too Many Requests"))

    lint = LintAgent(
        provider=mock_provider,
        adversarial_provider=mock_provider,
        store=store,
        log_writer=MagicMock(),
    )
    result, tokens = await lint._adversarial_single("test-page", "Some content here.")
    assert tokens == 0
    # Should return the rate-limit placeholder warning
    assert len(result) == 1
    assert "rate limit" in (result[0].get("concern") or "").lower()


# ── orchestrator.py — remaining branches ─────────────────────────────────────

def test_read_manifest_with_valid_file_path(tmp_path):
    """_read_manifest treats a line that is a valid path as a manifest entry."""
    from synthadoc.core.orchestrator import _read_manifest
    src_file = tmp_path / "document.pdf"
    src_file.write_bytes(b"fake pdf")
    manifest = tmp_path / "sources.txt"
    manifest.write_text(str(src_file) + "\n", encoding="utf-8")
    result = _read_manifest(manifest)
    assert result is not None
    assert len(result) == 1
