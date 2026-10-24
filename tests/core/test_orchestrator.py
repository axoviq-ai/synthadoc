# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from synthadoc.core.orchestrator import Orchestrator
from synthadoc.config import load_config


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    """Build a minimal HTTPStatusError for testing."""
    request = httpx.Request("GET", "https://example.com/page")
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    return httpx.HTTPStatusError(
        message=f"{status_code}", request=request, response=response
    )


@pytest.mark.asyncio
async def test_orchestrator_init_creates_dbs(tmp_wiki):
    async with Orchestrator(wiki_root=tmp_wiki, config=load_config()):
        assert (tmp_wiki / ".synthadoc" / "jobs.db").exists()
        assert (tmp_wiki / ".synthadoc" / "audit.db").exists()
        assert (tmp_wiki / ".synthadoc" / "cache.db").exists()


@pytest.mark.asyncio
async def test_orchestrator_ingest_returns_job_id(tmp_wiki):
    async with Orchestrator(wiki_root=tmp_wiki, config=load_config()) as orch:
        source = tmp_wiki / "raw_sources" / "test.md"
        source.write_text("# Test\nContent.", encoding="utf-8")
        with patch.object(orch, "_run_ingest", new=AsyncMock()):
            job_id = await orch.ingest(str(source))
        assert job_id


@pytest.mark.asyncio
async def test_run_ingest_http_404_skips_job(tmp_wiki):
    """A 404 response must skip the job immediately with no retry and no exception raised."""
    async with Orchestrator(wiki_root=tmp_wiki, config=load_config()) as orch:
        job_id = await orch._queue.enqueue("ingest", {"source": "https://example.com/gone", "force": False})

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=_http_status_error(404))
        with patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
             patch("synthadoc.agents.ingest_agent.IngestAgent", return_value=mock_agent):
            # Must NOT raise — the worker loop must continue cleanly
            await orch._run_ingest(job_id, "https://example.com/gone", auto_confirm=True)

        from synthadoc.core.queue import JobStatus
        jobs = await orch._queue.list_jobs(status=JobStatus.SKIPPED)
        assert any(j.id == job_id for j in jobs)


@pytest.mark.asyncio
async def test_run_ingest_llm_skip_marks_job_skipped(tmp_wiki):
    """When IngestAgent returns result.skipped=True the job must be SKIPPED, not COMPLETED."""
    from synthadoc.agents.ingest_agent import IngestResult

    async with Orchestrator(wiki_root=tmp_wiki, config=load_config()) as orch:
        job_id = await orch._queue.enqueue("ingest", {"source": "https://example.com/oos", "force": False})

        skipped_result = IngestResult(source="https://example.com/oos", skipped=True, skip_reason="out of scope (purpose.md)")
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=skipped_result)
        with patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
             patch("synthadoc.agents.ingest_agent.IngestAgent", return_value=mock_agent):
            await orch._run_ingest(job_id, "https://example.com/oos", auto_confirm=True)

        from synthadoc.core.queue import JobStatus
        skipped = await orch._queue.list_jobs(status=JobStatus.SKIPPED)
        completed = await orch._queue.list_jobs(status=JobStatus.COMPLETED)
        assert any(j.id == job_id for j in skipped), "LLM-skipped job must have SKIPPED status"
        assert not any(j.id == job_id for j in completed), "LLM-skipped job must not be COMPLETED"


@pytest.mark.asyncio
async def test_run_ingest_http_5xx_retries_job(tmp_wiki):
    """A 5xx response must re-queue the job for retry (PENDING), not skip it."""
    async with Orchestrator(wiki_root=tmp_wiki, config=load_config()) as orch:
        job_id = await orch._queue.enqueue("ingest", {"source": "https://example.com/flaky", "force": False})

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=_http_status_error(503))
        with patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
             patch("synthadoc.agents.ingest_agent.IngestAgent", return_value=mock_agent):
            await orch._run_ingest(job_id, "https://example.com/flaky", auto_confirm=True)

        from synthadoc.core.queue import JobStatus
        # fail() with retries remaining → status becomes PENDING again (re-queued for retry)
        pending_jobs = await orch._queue.list_jobs(status=JobStatus.PENDING)
        skipped_jobs = await orch._queue.list_jobs(status=JobStatus.SKIPPED)
        assert any(j.id == job_id for j in pending_jobs), "5xx job should be re-queued for retry"
        assert not any(j.id == job_id for j in skipped_jobs), "5xx job must not be skipped"


def _vector_orch(tmp_wiki, mode):
    from synthadoc.core.orchestrator import Orchestrator
    from synthadoc.config import Config, AgentsConfig, AgentConfig, SearchConfig

    wiki_dir = tmp_wiki / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    (wiki_dir / "test-page.md").write_text(
        "---\ntitle: Test\ntags: []\nstatus: active\n"
        "confidence: high\ncreated: '2026-01-01'\nsources: []\n---\nContent here.",
        encoding="utf-8",
    )
    cfg = Config(
        agents=AgentsConfig(default=AgentConfig(provider="gemini", model="gemini-2.0-flash")),
        search=SearchConfig(vector=mode),
    )
    return Orchestrator(wiki_root=tmp_wiki, config=cfg)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [True, "auto"])
async def test_init_with_vectors_syncs_embeddings_in_background(tmp_wiki, mode):
    """init() opens embeddings.db and embeds existing pages in the background."""
    import numpy as np
    from unittest.mock import patch

    orch = _vector_orch(tmp_wiki, mode)
    fake = lambda texts: np.ones((len(texts), 4), dtype=np.float32) / 2
    with patch.dict("sys.modules", {"fastembed": MagicMock()}), \
         patch.object(orch._search, "_embed_texts", side_effect=fake):
        await orch.init()
        await orch._search.wait_for_embedding_sync()
    try:
        assert await orch._search._vector_store.text_hashes() != {}
        assert "test-page" in orch._search._page_slugs
    finally:
        await orch.close()


@pytest.mark.asyncio
async def test_init_without_vectors_never_embeds(tmp_wiki):
    from unittest.mock import patch

    orch = _vector_orch(tmp_wiki, False)
    with patch.object(orch._search, "_embed_texts") as embed:
        await orch.init()
        await orch._search.wait_for_embedding_sync()
    await orch.close()
    embed.assert_not_called()
    assert orch._search._vector_store is None


@pytest.mark.asyncio
async def test_wiki_epoch_increments_on_successful_ingest(tmp_wiki):
    """_wiki_epoch must increment after a successful ingest job."""
    from synthadoc.core.orchestrator import Orchestrator
    from synthadoc.agents.ingest_agent import IngestResult
    async with Orchestrator(wiki_root=tmp_wiki) as orch:
        assert orch._wiki_epoch == 0

        job_id = await orch._queue.enqueue("ingest", {"source": "http://example.com", "force": False})
        mock_result = IngestResult(
            source="http://example.com",
            pages_created=["new-page"],
            pages_updated=[],
            pages_flagged=[],
            tokens_used=10,
            input_tokens=8,
            output_tokens=2,
            cost_usd=0.0,
            skipped=False,
            skip_reason="",
            child_sources=[],
        )
        with patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
             patch("synthadoc.agents.ingest_agent.IngestAgent.run", new=AsyncMock(return_value=mock_result)):
            await orch._run_ingest(job_id, source="http://example.com", auto_confirm=True)

        assert orch._wiki_epoch == 1


@pytest.mark.asyncio
async def test_wiki_epoch_does_not_increment_on_skipped_ingest(tmp_wiki):
    """_wiki_epoch must NOT increment when ingest is skipped."""
    from synthadoc.core.orchestrator import Orchestrator
    from synthadoc.agents.ingest_agent import IngestResult
    async with Orchestrator(wiki_root=tmp_wiki) as orch:
        job_id = await orch._queue.enqueue("ingest", {"source": "http://example.com", "force": False})
        mock_result = IngestResult(
            source="http://example.com",
            pages_created=[],
            pages_updated=[],
            pages_flagged=[],
            tokens_used=0,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            skipped=True,
            skip_reason="already cached",
            child_sources=[],
        )
        with patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
             patch("synthadoc.agents.ingest_agent.IngestAgent.run", new=AsyncMock(return_value=mock_result)):
            await orch._run_ingest(job_id, source="http://example.com", auto_confirm=True)

        assert orch._wiki_epoch == 0


@pytest.mark.asyncio
async def test_run_lint_passes_adversarial_false(tmp_wiki):
    """_run_lint() passes adversarial=False to LintAgent.run() when requested."""
    from synthadoc.config import load_config
    from synthadoc.core.orchestrator import Orchestrator
    from synthadoc.agents.lint_agent import LintReport

    cfg = load_config()
    orch = Orchestrator(wiki_root=tmp_wiki, config=cfg)

    # Create a LintReport-like object with all required fields
    lint_report = LintReport(
        adversarial_warnings=[],
    )

    captured_kwargs = {}

    async def fake_lint(self, **kwargs):
        captured_kwargs.update(kwargs)
        return lint_report

    # Mock LintAgent.lint, make_provider, and queue methods
    with patch("synthadoc.agents.lint_agent.LintAgent.run", new=fake_lint), \
         patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
         patch.object(orch, "_queue") as mock_queue:
        mock_queue.complete = AsyncMock()
        mock_queue.fail = AsyncMock()
        mock_queue.fail_permanent = AsyncMock()
        await orch._run_lint("job-1", adversarial=False)

    assert captured_kwargs.get("adversarial") is False


@pytest.mark.asyncio
async def test_run_scaffold_excludes_meta_slugs_from_protected(tmp_wiki):
    """_run_scaffold() must not pass meta slugs (index, overview, purpose, dashboard, log)
    as protected_slugs — they must never appear as categorised content in the index."""
    from synthadoc.config import load_config
    from synthadoc.core.orchestrator import Orchestrator
    from synthadoc.agents.lint_agent import LINT_SKIP_SLUGS
    from synthadoc.agents.scaffold_agent import ScaffoldResult

    cfg = load_config()
    orch = Orchestrator(wiki_root=tmp_wiki, config=cfg)

    # Create a mix of meta and real pages on disk
    wiki_dir = tmp_wiki / "wiki"
    for slug in ["overview", "purpose", "index", "dashboard", "real-topic"]:
        (wiki_dir / f"{slug}.md").write_text(f"# {slug}\n", encoding="utf-8")

    captured_slugs: list[str] = []

    async def fake_scaffold(self, domain, protected_slugs=None, port=7070):
        captured_slugs.extend(protected_slugs or [])
        _agents = (
            "# AGENTS.md — Test Wiki\n\n## Domain Guidelines\n- Summarize.\n\n"
            "## Quick Reference\n| Action | Command |\n\n## Ingest\n\n## Query\n"
        )
        return ScaffoldResult(
            index_md=(
                f"---\ntitle: Index\nstatus: active\nconfidence: high\n"
                f"created: '2026-01-01'\n---\n\n# {domain} — Index\n\n"
                "## Topics\n\n- [[real-topic]]\n"
            ),
            agents_md=_agents,
            claude_md=_agents.replace("# AGENTS.md", "# CLAUDE.md", 1),
            gemini_md=_agents.replace("# AGENTS.md", "# GEMINI.md", 1),
            purpose_md=f"# Wiki Purpose — {domain}\n\n## Overview\n\nText.\n",
            dashboard_intro="A wiki.",
        )

    with patch("synthadoc.agents.scaffold_agent.ScaffoldAgent.run", new=fake_scaffold), \
         patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
         patch.object(orch, "_queue") as mock_queue:
        mock_queue.complete = AsyncMock()
        mock_queue.fail = AsyncMock()
        mock_queue.fail_permanent = AsyncMock()
        await orch._run_scaffold("job-1", "TestDomain")

    for meta in LINT_SKIP_SLUGS:
        assert meta not in captured_slugs, (
            f"Meta slug '{meta}' must be filtered out of protected_slugs passed to scaffold"
        )
    assert "real-topic" in captured_slugs


@pytest.mark.asyncio
async def test_run_scaffold_daily_quota_exhausted_fails_permanent(tmp_wiki):
    """DailyQuotaExhaustedException in _run_scaffold must permanently fail the job (no retry)."""
    from synthadoc.errors import DailyQuotaExhaustedException

    cfg = load_config()
    orch = Orchestrator(wiki_root=tmp_wiki, config=cfg)

    exc = DailyQuotaExhaustedException(provider="anthropic")

    with patch("synthadoc.agents.scaffold_agent.ScaffoldAgent.run", new=AsyncMock(side_effect=exc)), \
         patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
         patch.object(orch, "_queue") as mock_queue:
        mock_queue.fail_permanent = AsyncMock()
        mock_queue.fail = AsyncMock()
        await orch._run_scaffold("job-quota-daily", "TestDomain")

    mock_queue.fail_permanent.assert_awaited_once()
    mock_queue.fail.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_scaffold_coding_tool_quota_fails_permanent(tmp_wiki):
    """CodingToolQuotaExhaustedException in _run_scaffold must permanently fail the job (no retry)."""
    from synthadoc.errors import CodingToolQuotaExhaustedException

    cfg = load_config()
    orch = Orchestrator(wiki_root=tmp_wiki, config=cfg)

    exc = CodingToolQuotaExhaustedException("claude-code")

    with patch("synthadoc.agents.scaffold_agent.ScaffoldAgent.run", new=AsyncMock(side_effect=exc)), \
         patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
         patch.object(orch, "_queue") as mock_queue:
        mock_queue.fail_permanent = AsyncMock()
        mock_queue.fail = AsyncMock()
        await orch._run_scaffold("job-quota-coding", "TestDomain")

    mock_queue.fail_permanent.assert_awaited_once()
    mock_queue.fail.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_block_domain_writes_unix_line_endings(tmp_wiki):
    """blocked_domains.json must pass newline="\\n" to write_text regardless of platform.

    A binary-mode read catches the symptom on Windows; the write_text spy
    catches a missing newline= argument on Linux/Mac where Python never
    produces CRLF anyway (so the byte check alone would always pass there).
    """
    import pathlib
    from synthadoc.errors import DomainBlockedException

    real_write_text = pathlib.Path.write_text
    calls: list = []

    def spy(self, data, *args, **kwargs):
        calls.append((args, kwargs))
        return real_write_text(self, data, *args, **kwargs)

    cfg = load_config()
    async with Orchestrator(wiki_root=tmp_wiki, config=cfg) as orch:
        exc = DomainBlockedException(domain="evil.com", url="https://evil.com/p", status_code=403)
        with patch("pathlib.Path.write_text", spy):
            await orch._auto_block_domain(exc)

    blocked_path = tmp_wiki / ".synthadoc" / "blocked_domains.json"
    assert blocked_path.exists()
    # Verify newline="\n" was passed on every write_text call
    for _, kwargs in calls:
        assert kwargs.get("newline") == "\n", "write_text called without newline='\\n'"
    # Also verify the on-disk bytes contain no CRLF
    assert b"\r\n" not in blocked_path.read_bytes()
