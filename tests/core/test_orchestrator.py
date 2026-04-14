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
    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    await orch.init()
    assert (tmp_wiki / ".synthadoc" / "jobs.db").exists()
    assert (tmp_wiki / ".synthadoc" / "audit.db").exists()
    assert (tmp_wiki / ".synthadoc" / "cache.db").exists()


@pytest.mark.asyncio
async def test_orchestrator_ingest_returns_job_id(tmp_wiki):
    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    await orch.init()
    source = tmp_wiki / "raw_sources" / "test.md"
    source.write_text("# Test\nContent.", encoding="utf-8")
    with patch.object(orch, "_run_ingest", new=AsyncMock()):
        job_id = await orch.ingest(str(source))
    assert job_id


@pytest.mark.asyncio
async def test_run_ingest_http_404_skips_job(tmp_wiki):
    """A 404 response must skip the job immediately with no retry and no exception raised."""
    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    await orch.init()
    job_id = await orch._queue.enqueue("ingest", {"source": "https://example.com/gone", "force": False})

    mock_agent = MagicMock()
    mock_agent.ingest = AsyncMock(side_effect=_http_status_error(404))
    with patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
         patch("synthadoc.agents.ingest_agent.IngestAgent", return_value=mock_agent):
        # Must NOT raise — the worker loop must continue cleanly
        await orch._run_ingest(job_id, "https://example.com/gone", auto_confirm=True)

    from synthadoc.core.queue import JobStatus
    jobs = await orch._queue.list_jobs(status=JobStatus.SKIPPED)
    assert any(j.id == job_id for j in jobs)


@pytest.mark.asyncio
async def test_run_ingest_http_5xx_retries_job(tmp_wiki):
    """A 5xx response must re-queue the job for retry (PENDING), not skip it."""
    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    await orch.init()
    job_id = await orch._queue.enqueue("ingest", {"source": "https://example.com/flaky", "force": False})

    mock_agent = MagicMock()
    mock_agent.ingest = AsyncMock(side_effect=_http_status_error(503))
    with patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
         patch("synthadoc.agents.ingest_agent.IngestAgent", return_value=mock_agent):
        await orch._run_ingest(job_id, "https://example.com/flaky", auto_confirm=True)

    from synthadoc.core.queue import JobStatus
    # fail() with retries remaining → status becomes PENDING again (re-queued for retry)
    pending_jobs = await orch._queue.list_jobs(status=JobStatus.PENDING)
    skipped_jobs = await orch._queue.list_jobs(status=JobStatus.SKIPPED)
    assert any(j.id == job_id for j in pending_jobs), "5xx job should be re-queued for retry"
    assert not any(j.id == job_id for j in skipped_jobs), "5xx job must not be skipped"
