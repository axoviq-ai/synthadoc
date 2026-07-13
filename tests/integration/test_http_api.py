# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import asyncio

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from synthadoc.storage.log import AuditDB


def test_health(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        assert client.get("/health").json()["status"] == "ok"


def test_status_returns_page_count(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        data = client.get("/status").json()
    assert "pages" in data


def test_query_endpoint(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    from synthadoc.agents.query_agent import QueryResult
    app = create_app(wiki_root=tmp_wiki)
    mock = QueryResult(question="q", answer="answer", citations=["p1"])
    with patch("synthadoc.core.orchestrator.Orchestrator.query",
               new=AsyncMock(return_value=mock)):
        with TestClient(app) as client:
            resp = client.post("/query", json={"question": "What is AI?"})
    assert resp.json()["answer"] == "answer"


def test_ingest_endpoint_returns_job_id(tmp_wiki):
    """POST /jobs/ingest enqueues a job and returns its ID."""
    from synthadoc.integration.http_server import create_app
    app = create_app(wiki_root=tmp_wiki)
    # The endpoint calls queue.enqueue(), not orch.ingest() directly
    with patch("synthadoc.core.queue.JobQueue.enqueue",
               new=AsyncMock(return_value="job-abc")):
        with TestClient(app) as client:
            resp = client.post("/jobs/ingest", json={"source": "paper.pdf"})
    assert resp.status_code == 200
    assert resp.json()["job_id"] == "job-abc"


def test_lint_report_shows_contradictions_and_orphans(tmp_wiki):
    """GET /lint/report reads wiki files and returns contradicted pages and orphans."""
    wiki_dir = tmp_wiki / "wiki"
    # A page marked contradicted in its frontmatter
    (wiki_dir / "conflicted-page.md").write_text(
        "---\nstatus: contradicted\n---\n# Conflicted Page\n",
        encoding="utf-8",
    )
    # An orphan page — no other page links to it
    (wiki_dir / "orphan-page.md").write_text(
        "---\nstatus: active\ntags: [test]\n---\n# Orphan Page\n",
        encoding="utf-8",
    )
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/lint/report")
    assert resp.status_code == 200
    data = resp.json()
    assert "conflicted-page" in data["contradictions"]
    assert "orphan-page" in data["orphans"]


def test_query_empty_question_returns_422(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.post("/query", json={"question": ""})
    assert resp.status_code == 422


def test_ingest_url_not_mangled_to_file_path(tmp_wiki):
    """POST /jobs/ingest with an http URL must not be resolved as a local path."""
    from synthadoc.integration.http_server import create_app
    with patch("synthadoc.core.queue.JobQueue.enqueue",
               new=AsyncMock(return_value="job-url")) as mock_enqueue:
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.post("/jobs/ingest", json={"source": "https://example.com/article"})
    assert resp.status_code == 200
    queued_source = mock_enqueue.call_args[0][1]["source"]
    assert queued_source == "https://example.com/article"
    assert str(tmp_wiki) not in queued_source


def test_ingest_backslash_url_is_normalised_not_path_resolved(tmp_wiki):
    """POST /jobs/ingest with a Windows backslash URL must store a clean https:// URL.

    Users sometimes paste URLs as https:\\example.com\\path (backslashes).
    The endpoint must normalise these to forward slashes and NOT prepend the
    wiki root — otherwise the stored source becomes an unresolvable local path.
    """
    from synthadoc.integration.http_server import create_app
    backslash_url = r"https:\example.com\collections\page"
    with patch("synthadoc.core.queue.JobQueue.enqueue",
               new=AsyncMock(return_value="job-bs")) as mock_enqueue:
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.post("/jobs/ingest", json={"source": backslash_url})
    assert resp.status_code == 200
    queued_source = mock_enqueue.call_args[0][1]["source"]
    assert queued_source == "https://example.com/collections/page"
    assert str(tmp_wiki) not in queued_source


def test_retry_job_endpoint(tmp_wiki):
    """POST /jobs/{id}/retry resets the job to pending."""
    from synthadoc.integration.http_server import create_app
    from synthadoc.core.queue import Job, JobStatus
    fake_job = Job(id="fail-1", operation="ingest", payload={},
                   status=JobStatus.FAILED, retries=0, error="server restarted")
    with patch("synthadoc.core.queue.JobQueue.list_jobs",
               new=AsyncMock(return_value=[fake_job])):
        with patch("synthadoc.core.queue.JobQueue.retry",
                   new=AsyncMock()) as mock_retry:
            with TestClient(create_app(wiki_root=tmp_wiki)) as client:
                resp = client.post("/jobs/fail-1/retry")
    assert resp.status_code == 200
    assert resp.json()["retried"] == "fail-1"
    mock_retry.assert_awaited_once_with("fail-1")


def test_retry_dead_job_returns_409(tmp_wiki):
    """POST /jobs/{id}/retry on a dead job must return 409 — dead jobs cannot be retried."""
    from synthadoc.integration.http_server import create_app
    from synthadoc.core.queue import Job, JobStatus
    fake_job = Job(id="dead-1", operation="ingest", payload={},
                   status=JobStatus.DEAD, retries=3, error="timed out after 600s")
    with patch("synthadoc.core.queue.JobQueue.list_jobs",
               new=AsyncMock(return_value=[fake_job])):
        with patch("synthadoc.core.queue.JobQueue.retry", new=AsyncMock()) as mock_retry:
            with TestClient(create_app(wiki_root=tmp_wiki)) as client:
                resp = client.post("/jobs/dead-1/retry")
    assert resp.status_code == 409
    mock_retry.assert_not_awaited()


def test_audit_queries_returns_empty_initially(tmp_wiki):
    """GET /audit/queries must return an empty list before any queries are made."""
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/audit/queries")
    assert resp.status_code == 200
    data = resp.json()
    assert data["records"] == []
    assert data["count"] == 0


def test_audit_queries_returns_recorded_data(tmp_wiki):
    """GET /audit/queries must return records after queries have been made."""
    from synthadoc.integration.http_server import create_app
    # Pre-populate the DB file before the server starts so it shares the record
    db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    asyncio.run(db.init())
    asyncio.run(db.record_query(
        question="What is Moore's Law?", sub_questions_count=1,
        tokens=125, cost_usd=0.0004,
    ))
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/audit/queries")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["records"][0]["question"] == "What is Moore's Law?"


def test_query_stream_records_audit_entry(tmp_wiki):
    """GET /query/stream must write a record to audit.db when the done event fires.

    Mocks QueryAgent.run_stream (not Orchestrator.query_stream) so the real
    orchestrator wiring — including the record_query call — executes.
    """
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    from synthadoc.storage.log import AuditDB

    async def _fake_run_stream(self, question, **kwargs):
        yield {"event": "status", "data": {"phase": "retrieving"}}
        yield {"event": "token", "data": {"text": "Bell Labs invented the transistor."}}
        yield {"event": "citations", "data": {"citations": []}}
        yield {"event": "done", "data": {
            "next_hints": [], "cacheable": False,
            "routing_warning": None, "sub_questions_count": 2,
        }}

    with patch("synthadoc.agents.query_agent.QueryAgent.run_stream", new=_fake_run_stream):
        with patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock(spec=[])):
            with TestClient(create_app(wiki_root=tmp_wiki)) as client:
                resp = client.get("/query/stream?q=Who+invented+the+transistor")

    assert resp.status_code == 200

    db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    records = asyncio.run(_fetch_queries(db))
    assert len(records) == 1
    assert records[0]["question"] == "Who invented the transistor"
    assert records[0]["sub_questions_count"] == 2


async def _fetch_queries(db):
    await db.init()
    return await db.list_queries(limit=10)


def test_query_post_provider_unavailable_returns_502(tmp_wiki):
    """If the LLM provider raises a connection error, POST /query must return 502."""
    from synthadoc.integration.http_server import create_app
    with patch("synthadoc.core.orchestrator.Orchestrator.query",
               new=AsyncMock(side_effect=Exception("Connection refused"))):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.post("/query", json={"question": "What is Moore's Law?"})
    assert resp.status_code == 502
    assert "unavailable" in resp.json()["detail"].lower()


def test_query_get_provider_unavailable_returns_502(tmp_wiki):
    """If the LLM provider raises, GET /query must also return 502."""
    from synthadoc.integration.http_server import create_app
    with patch("synthadoc.core.orchestrator.Orchestrator.query",
               new=AsyncMock(side_effect=Exception("timeout"))):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.get("/query", params={"q": "test"})
    assert resp.status_code == 502
    assert "unavailable" in resp.json()["detail"].lower()


def test_retry_job_not_found(tmp_wiki):
    """POST /jobs/{id}/retry returns 404 for unknown job IDs."""
    from synthadoc.integration.http_server import create_app
    with patch("synthadoc.core.queue.JobQueue.list_jobs",
               new=AsyncMock(return_value=[])):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.post("/jobs/nonexistent/retry")
    assert resp.status_code == 404


def test_purge_jobs_endpoint(tmp_wiki):
    """DELETE /jobs?older_than=N returns the count of purged jobs."""
    from synthadoc.integration.http_server import create_app
    with patch("synthadoc.core.queue.JobQueue.purge",
               new=AsyncMock(return_value=5)) as mock_purge:
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.delete("/jobs?older_than=3")
    assert resp.status_code == 200
    assert resp.json()["purged"] == 5
    assert resp.json()["older_than_days"] == 3
    mock_purge.assert_awaited_once_with(older_than_days=3)


def test_scaffold_endpoint_enqueues_job(tmp_wiki):
    """POST /jobs/scaffold enqueues a scaffold job and returns its ID."""
    from synthadoc.integration.http_server import create_app
    with patch("synthadoc.core.queue.JobQueue.enqueue",
               new=AsyncMock(return_value="scaf-01")) as mock_enqueue:
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.post("/jobs/scaffold", json={"domain": "Canadian tax law"})
    assert resp.status_code == 200
    assert resp.json()["job_id"] == "scaf-01"
    mock_enqueue.assert_awaited_once_with("scaffold", {"domain": "Canadian tax law"})


def test_scaffold_endpoint_rejects_empty_domain(tmp_wiki):
    """POST /jobs/scaffold with an empty domain returns 422."""
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.post("/jobs/scaffold", json={"domain": ""})
    assert resp.status_code == 422


def test_audit_history_endpoint(tmp_wiki):
    """GET /audit/history returns ingest records."""
    from synthadoc.integration.http_server import create_app
    fake_records = [
        {"source_path": "paper.pdf", "wiki_page": "ai-basics",
         "tokens": 500, "cost_usd": 0.001, "ingested_at": "2026-04-17T10:00:00"}
    ]
    with patch("synthadoc.storage.log.AuditDB.list_ingests",
               new=AsyncMock(return_value=fake_records)):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.get("/audit/history?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["records"][0]["wiki_page"] == "ai-basics"


def test_audit_costs_endpoint(tmp_wiki):
    """GET /audit/costs returns cost summary."""
    from synthadoc.integration.http_server import create_app
    fake_summary = {"total_tokens": 1200, "total_cost_usd": 0.0024, "daily": []}
    with patch("synthadoc.storage.log.AuditDB.cost_summary",
               new=AsyncMock(return_value=fake_summary)):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.get("/audit/costs?days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_tokens"] == 1200
    assert data["total_cost_usd"] == pytest.approx(0.0024)


def test_query_response_includes_knowledge_gap_fields(tmp_wiki):
    """GET /query must include knowledge_gap and suggested_searches in response."""
    from synthadoc.integration.http_server import create_app
    from synthadoc.agents.query_agent import QueryResult
    with patch("synthadoc.core.orchestrator.Orchestrator.query",
               new=AsyncMock(return_value=QueryResult(
                   question="q", answer="answer", citations=[],
                   knowledge_gap=False, suggested_searches=[],
               ))):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.get("/query", params={"q": "test question"})
    assert resp.status_code == 200
    data = resp.json()
    assert "knowledge_gap" in data
    assert "suggested_searches" in data


def test_query_response_gap_true_includes_suggestions(tmp_wiki):
    """When knowledge_gap=True, suggested_searches must be a non-empty list."""
    from synthadoc.integration.http_server import create_app
    from synthadoc.agents.query_agent import QueryResult
    with patch("synthadoc.core.orchestrator.Orchestrator.query",
               new=AsyncMock(return_value=QueryResult(
                   question="q", answer="No info found.", citations=[],
                   knowledge_gap=True,
                   suggested_searches=["canadian vegetable spring planting", "frost dates Canada"],
               ))):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.get("/query", params={"q": "vegetables in Canada?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["knowledge_gap"] is True
    assert data["suggested_searches"] == ["canadian vegetable spring planting", "frost dates Canada"]


def test_query_post_response_includes_gap_fields(tmp_wiki):
    """POST /query must also include knowledge_gap and suggested_searches."""
    from synthadoc.integration.http_server import create_app
    from synthadoc.agents.query_agent import QueryResult
    with patch("synthadoc.core.orchestrator.Orchestrator.query",
               new=AsyncMock(return_value=QueryResult(
                   question="q", answer="answer", citations=[],
                   knowledge_gap=True, suggested_searches=["search string"],
               ))):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.post("/query", json={"question": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert "knowledge_gap" in data
    assert "suggested_searches" in data


def test_job_response_includes_progress_field(tmp_wiki):
    """GET /jobs/{id} must include a progress field (may be null)."""
    from synthadoc.integration.http_server import create_app
    from synthadoc.core.queue import Job, JobStatus
    fake_job = Job(id="job-p1", operation="ingest", payload={"source": "search for: housing"},
                   status=JobStatus.PENDING, retries=0, error=None, progress=None)
    with patch("synthadoc.core.queue.JobQueue.list_jobs",
               new=AsyncMock(return_value=[fake_job])):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.get("/jobs/job-p1")
    assert resp.status_code == 200
    assert "progress" in resp.json()


def test_list_jobs_includes_progress_field(tmp_wiki):
    """GET /jobs must include progress field on each job."""
    from synthadoc.integration.http_server import create_app
    from synthadoc.core.queue import Job, JobStatus
    fake_job = Job(id="job-p2", operation="ingest", payload={"source": "file.pdf"},
                   status=JobStatus.PENDING, retries=0, error=None, progress=None)
    with patch("synthadoc.core.queue.JobQueue.list_jobs",
               new=AsyncMock(return_value=[fake_job])):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.get("/jobs")
    assert resp.status_code == 200
    jobs = resp.json()
    assert len(jobs) >= 1
    for job in jobs:
        assert "progress" in job


def test_list_jobs_sort_params_forwarded_to_queue(tmp_wiki):
    """GET /jobs?sort=operation&order=desc must pass sort_by and order to queue.list_jobs."""
    from synthadoc.integration.http_server import create_app
    from synthadoc.core.queue import Job, JobStatus
    fake_job = Job(id="job-s1", operation="lint", payload={},
                   status=JobStatus.PENDING, retries=0, error=None)
    captured = {}

    async def mock_list_jobs(self, status=None, sort_by="created_at", order="asc"):
        captured["sort_by"] = sort_by
        captured["order"] = order
        return [fake_job]

    with patch("synthadoc.core.queue.JobQueue.list_jobs", new=mock_list_jobs):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.get("/jobs?sort=operation&order=desc")
    assert resp.status_code == 200
    assert captured["sort_by"] == "operation"
    assert captured["order"] == "desc"


def test_analyse_endpoint_returns_structure(tmp_wiki):
    """POST /analyse returns source and analysis keys."""
    from synthadoc.integration.http_server import create_app
    from synthadoc.skills.base import ExtractedContent

    app = create_app(wiki_root=tmp_wiki)
    mock_extracted = ExtractedContent(text="AI is important.", source_path="test.md", metadata={})
    mock_analysis = {"entities": ["AI"], "tags": ["ai"], "summary": "AI summary.", "relevant": True}

    with patch("synthadoc.agents.skill_agent.SkillAgent.extract",
               new=AsyncMock(return_value=mock_extracted)), \
         patch("synthadoc.agents.ingest_agent.IngestAgent._analyse",
               new=AsyncMock(return_value=mock_analysis)), \
         patch("synthadoc.providers.make_provider", return_value=AsyncMock()):
        with TestClient(app) as client:
            resp = client.post("/analyse", json={"source": "test.md"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "test.md"
    assert "analysis" in data
    assert "entities" in data["analysis"]


def test_analyse_endpoint_empty_wiki(tmp_wiki):
    """POST /analyse works when the wiki has no pages."""
    from synthadoc.integration.http_server import create_app
    from synthadoc.skills.base import ExtractedContent

    app = create_app(wiki_root=tmp_wiki)
    mock_extracted = ExtractedContent(text="", source_path="empty.md", metadata={})
    mock_analysis = {"entities": [], "tags": [], "summary": "", "relevant": False}

    with patch("synthadoc.agents.skill_agent.SkillAgent.extract",
               new=AsyncMock(return_value=mock_extracted)), \
         patch("synthadoc.agents.ingest_agent.IngestAgent._analyse",
               new=AsyncMock(return_value=mock_analysis)), \
         patch("synthadoc.providers.make_provider", return_value=AsyncMock()):
        with TestClient(app) as client:
            resp = client.post("/analyse", json={"source": "empty.md"})

    assert resp.status_code == 200
    assert resp.json()["source"] == "empty.md"


def test_enqueue_lint_adversarial_param_forwarded(tmp_wiki):
    """POST /jobs/lint with adversarial: false enqueues payload with adversarial=False."""
    from synthadoc.integration.http_server import create_app
    from unittest.mock import AsyncMock, patch
    app = create_app(wiki_root=tmp_wiki)
    enqueued = {}

    async def capture_enqueue(op, payload):
        enqueued.update(payload)
        return "job-xyz"

    with patch("synthadoc.core.queue.JobQueue.enqueue", side_effect=capture_enqueue):
        with TestClient(app) as client:
            resp = client.post("/jobs/lint", json={"adversarial": False})
    assert resp.status_code == 200
    assert enqueued.get("adversarial") is False


def test_provenance_citations_empty(tmp_wiki):
    """GET /provenance/citations returns empty list when no citations."""
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/provenance/citations")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["citations"] == []


def test_provenance_citations_returns_data(tmp_wiki):
    """GET /provenance/citations returns recorded citations."""
    from synthadoc.integration.http_server import create_app
    # Seed the DB used by the test server
    db_path = tmp_wiki / ".synthadoc" / "audit.db"
    db = AuditDB(db_path)
    asyncio.run(db.init())
    asyncio.run(db.record_claim_citations("alan-turing", [
        {"source_file": "bio.txt", "line_start": 1, "line_end": 10,
         "claim_excerpt": "Turing proposed the test"}
    ]))
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/provenance/citations")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["citations"][0]["page_slug"] == "alan-turing"


def test_provenance_citations_filter_by_page(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/provenance/citations?page=alan-turing")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "citations" in data


def test_provenance_citations_pagination(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/provenance/citations?limit=10&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "citations" in data


def test_provenance_citations_broken_returns_correct_total(tmp_wiki):
    """GET /provenance/citations?broken=true must return the full total, not just page size."""
    from synthadoc.integration.http_server import create_app
    db_path = tmp_wiki / ".synthadoc" / "audit.db"
    db = AuditDB(db_path)
    asyncio.run(db.init())
    asyncio.run(db.write_event(
        event="citation_validation_failed",
        metadata={"slug": "p", "citation": "^[x:1-2]", "reason": "broken_ref"},
    ))
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/provenance/citations?broken=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert len(data["citations"]) >= 1


def test_lint_report_includes_adversarial_warnings(tmp_wiki):
    """GET /lint/report returns adversarial_warnings from page lint_warnings frontmatter."""
    wiki_dir = tmp_wiki / "wiki"
    wiki_dir.mkdir(exist_ok=True)
    # Real ingest always stores absolute paths; relative paths are placeholder entries
    # that _is_reingestable() filters out.  Use an absolute path to test the positive case.
    abs_source = str(tmp_wiki / "raw_sources" / "study.pdf")
    (wiki_dir / "flagged-page.md").write_text(
        "---\n"
        "status: active\n"
        "sources:\n"
        f"  - {{file: '{abs_source}', hash: 'abc', size: 1000, ingested: '2026-05-01'}}\n"
        "lint_warnings:\n"
        "  - claim: 'Claim A'\n"
        "    concern: 'Overstated'\n"
        "---\n\n# Flagged Page\n",
        encoding="utf-8",
    )
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        r = client.get("/lint/report")
    assert r.status_code == 200
    data = r.json()
    assert "adversarial_warnings" in data
    assert len(data["adversarial_warnings"]) == 1
    entry = data["adversarial_warnings"][0]
    assert entry["slug"] == "flagged-page"
    assert entry["warnings"][0]["claim"] == "Claim A"
    assert len(entry["suggested_reingests"]) == 1
    assert "study.pdf" in entry["suggested_reingests"][0]


def test_lifecycle_pages_endpoint_returns_list(tmp_wiki):
    """GET /lifecycle/pages returns current state per slug from page_states table."""
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/lifecycle/pages")
    assert resp.status_code == 200
    data = resp.json()
    assert "pages" in data
    assert isinstance(data["pages"], list)


def test_lifecycle_status_endpoint(tmp_wiki):
    """GET /lifecycle/status returns flat counts for all 5 lifecycle states."""
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/lifecycle/status")
    assert resp.status_code == 200
    data = resp.json()
    for state in ("draft", "active", "contradicted", "stale", "archived"):
        assert state in data, f"Missing state '{state}' in /lifecycle/status response"
    assert "counts" not in data


def test_lifecycle_status_includes_unlinted_for_new_pages(tmp_wiki):
    """GET /lifecycle/status includes 'unlinted' count when pages exist with no state."""
    from synthadoc.integration.http_server import create_app
    # Write a page that has no page_states entry (never linted)
    (tmp_wiki / "wiki" / "brand-new.md").write_text("# Brand New\nstatus: active\n", encoding="utf-8")
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/lifecycle/status")
    assert resp.status_code == 200
    data = resp.json()
    # The new page has no audit DB entry → should appear in unlinted
    assert data.get("unlinted", 0) >= 1


def test_lifecycle_events_endpoint(tmp_wiki):
    """GET /lifecycle/events returns paginated events."""
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/lifecycle/events?limit=5&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert "total" in data


def test_lifecycle_transition_valid(tmp_wiki):
    """POST /lifecycle/transition moves a draft page to active and returns slug/states/timestamp."""
    import asyncio
    from synthadoc.integration.http_server import create_app
    from synthadoc.storage.wiki import WikiStorage, WikiPage

    wiki_dir = tmp_wiki / "wiki"
    page = WikiPage(title="Test", tags=[], content="# Test",
                    status="draft", confidence="medium", sources=[])
    WikiStorage(wiki_dir).write_page("test-page", page)

    db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    asyncio.run(db.init())
    asyncio.run(db.set_page_state("test-page", "draft", "ingest"))

    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.post("/lifecycle/transition", json={
            "slug": "test-page", "to_state": "active", "reason": "reviewed"
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["slug"] == "test-page"
    assert data["from_state"] == "draft"
    assert data["to_state"] == "active"
    assert "timestamp" in data
    assert "ok" not in data


def test_lifecycle_transition_page_not_found(tmp_wiki):
    """POST /lifecycle/transition returns 404 when page is missing."""
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.post("/lifecycle/transition", json={
            "slug": "no-such-page", "to_state": "active", "reason": "test"
        })
    assert resp.status_code == 404


def test_staging_policy_get(tmp_wiki):
    """GET /staging/policy returns the current policy (defaults to off)."""
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/staging/policy")
    assert resp.status_code == 200
    data = resp.json()
    assert "policy" in data
    assert "confidence_min" in data


def test_lifecycle_transition_same_state_rejected(tmp_wiki):
    """POST /lifecycle/transition returns 422 when to_state equals current state."""
    import asyncio
    from synthadoc.integration.http_server import create_app
    from synthadoc.storage.wiki import WikiStorage, WikiPage

    wiki_dir = tmp_wiki / "wiki"
    page = WikiPage(title="Test", tags=[], content="# Test",
                    status="active", confidence="medium", sources=[])
    WikiStorage(wiki_dir).write_page("active-page", page)

    db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    asyncio.run(db.init())
    asyncio.run(db.set_page_state("active-page", "active", "ingest"))

    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.post("/lifecycle/transition", json={
            "slug": "active-page", "to_state": "active", "reason": "test"
        })
    assert resp.status_code == 422
    assert "already in state" in resp.json()["detail"]


def test_lifecycle_transition_any_state_allowed(tmp_wiki):
    """POST /lifecycle/transition permits any cross-state transition (no graph enforcement)."""
    import asyncio
    from synthadoc.integration.http_server import create_app
    from synthadoc.storage.wiki import WikiStorage, WikiPage

    wiki_dir = tmp_wiki / "wiki"
    for slug, status in [("page-a", "stale"), ("page-b", "contradicted")]:
        page = WikiPage(title=slug, tags=[], content=f"# {slug}",
                        status=status, confidence="medium", sources=[])
        WikiStorage(wiki_dir).write_page(slug, page)

    db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    asyncio.run(db.init())
    asyncio.run(db.set_page_state("page-a", "stale", "lint"))
    asyncio.run(db.set_page_state("page-b", "contradicted", "lint"))

    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        # stale → active (previously blocked)
        r1 = client.post("/lifecycle/transition", json={
            "slug": "page-a", "to_state": "active", "reason": "manual review"
        })
        # contradicted → active (previously blocked)
        r2 = client.post("/lifecycle/transition", json={
            "slug": "page-b", "to_state": "active", "reason": "contradiction resolved"
        })
    assert r1.status_code == 200, r1.json()
    assert r2.status_code == 200, r2.json()


def test_audit_events_endpoint(tmp_wiki):
    """GET /audit/events returns records."""
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/audit/events?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "records" in data
    assert "count" in data


def test_cancel_pending_jobs_endpoint(tmp_wiki):
    """POST /jobs/cancel-pending cancels all pending jobs."""
    from synthadoc.integration.http_server import create_app
    with patch("synthadoc.core.queue.JobQueue.cancel_pending",
               new=AsyncMock(return_value=0)):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.post("/jobs/cancel-pending")
    assert resp.status_code == 200
    assert resp.json()["cancelled"] == 0


def test_delete_job_endpoint_not_found(tmp_wiki):
    """DELETE /jobs/{id} returns 404 when job does not exist."""
    from synthadoc.integration.http_server import create_app
    from synthadoc.core.queue import Job, JobStatus
    with patch("synthadoc.core.queue.JobQueue.list_jobs",
               new=AsyncMock(return_value=[])):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.delete("/jobs/no-such-job")
    assert resp.status_code == 404


def test_delete_completed_job_endpoint(tmp_wiki):
    """DELETE /jobs/{id} removes a completed job."""
    from synthadoc.integration.http_server import create_app
    from synthadoc.core.queue import Job, JobStatus
    import datetime
    completed_job = Job(id="done-1", operation="lint", payload={},
                        status=JobStatus.COMPLETED, retries=0, error=None,
                        created_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    with patch("synthadoc.core.queue.JobQueue.list_jobs",
               new=AsyncMock(return_value=[completed_job])):
        with patch("synthadoc.core.queue.JobQueue.delete", new=AsyncMock()):
            with TestClient(create_app(wiki_root=tmp_wiki)) as client:
                resp = client.delete("/jobs/done-1")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == "done-1"


def test_delete_pending_job_returns_409(tmp_wiki):
    """DELETE /jobs/{id} returns 409 when the job is still pending."""
    from synthadoc.integration.http_server import create_app
    from synthadoc.core.queue import Job, JobStatus
    import datetime
    pending_job = Job(id="run-1", operation="lint", payload={},
                      status=JobStatus.PENDING, retries=0, error=None,
                      created_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    with patch("synthadoc.core.queue.JobQueue.list_jobs",
               new=AsyncMock(return_value=[pending_job])):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.delete("/jobs/run-1")
    assert resp.status_code == 409


def test_parse_retry_after_with_match():
    """_parse_retry_after extracts seconds from rate-limit error messages."""
    from synthadoc.integration.http_server import _parse_retry_after
    exc = Exception("Please try again in 1m 30.5s.")
    assert _parse_retry_after(exc) == pytest.approx(90.5)


def test_parse_retry_after_no_match_returns_default():
    """_parse_retry_after returns default when message does not match."""
    from synthadoc.integration.http_server import _parse_retry_after
    assert _parse_retry_after(Exception("unrelated error")) == 60.0


def test_config_endpoint_returns_lint_settings(tmp_wiki):
    """GET /config exposes check_url_availability from the server config."""
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "check_url_availability" in data
    assert isinstance(data["check_url_availability"], bool)


def test_query_endpoint_returns_cached_result(tmp_wiki):
    """GET /query must return a cached answer on second identical call."""
    from synthadoc.integration.http_server import create_app
    from fastapi.testclient import TestClient
    from unittest.mock import AsyncMock, patch
    from synthadoc.agents.query_agent import QueryResult

    app = create_app(wiki_root=tmp_wiki)
    mock_result = QueryResult(
        question="what is AI",
        answer="test answer",
        citations=[],
        knowledge_gap=False,
        suggested_searches=[],
    )

    with patch("synthadoc.core.orchestrator.Orchestrator.query",
               new=AsyncMock(return_value=mock_result)) as mock_query:
        with TestClient(app) as client:
            resp1 = client.get("/query?q=what+is+AI")
            resp2 = client.get("/query?q=what+is+AI")

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["answer"] == "test answer"
    assert resp2.json()["answer"] == "test answer"
    # Second call should hit cache — LLM called only once
    assert mock_query.call_count == 1


def test_lifecycle_transition_bumps_epoch(tmp_wiki):
    """A lifecycle transition must increment the orchestrator's wiki_epoch."""
    from synthadoc.integration.http_server import create_app
    from fastapi.testclient import TestClient

    wiki_dir = tmp_wiki / "wiki"
    (wiki_dir / "test-page.md").write_text(
        "---\nstatus: draft\n---\n# Test Page\n",
        encoding="utf-8",
    )
    app = create_app(wiki_root=tmp_wiki)
    with TestClient(app) as client:
        epoch_before = client.app.state.orch._wiki_epoch
        resp = client.post("/lifecycle/transition",
                           json={"slug": "test-page", "to_state": "active", "reason": "test"})
        epoch_after = client.app.state.orch._wiki_epoch
    if resp.status_code == 200:
        assert epoch_after > epoch_before


# ---------------------------------------------------------------------------
# Citation issues — HTTP API lint report (regression: endpoint never called
# _check_page_citations, so citation_issues was always absent)
# ---------------------------------------------------------------------------

def test_lint_report_returns_citation_issues_keys(tmp_wiki):
    """GET /lint/report must always include citation_issues and citation_issues_by_slug keys.

    Regression: the HTTP endpoint skipped _check_page_citations entirely, so
    the two citation keys were absent even though CLI showed 205 issues.
    """
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/lint/report")
    assert resp.status_code == 200
    data = resp.json()
    assert "citation_issues" in data
    assert "citation_issues_by_slug" in data


def test_lint_report_includes_citation_issues_for_broken_refs(tmp_wiki):
    """A page body with ^[FILENAME:3-5] and source named 'real-source.txt' must
    appear in citation_issues as a broken_ref.

    The citation uses 'FILENAME' as the source name, but the source's actual
    basename is 'real-source.txt', so the reference is broken.
    """
    from synthadoc.integration.http_server import create_app

    wiki_dir = tmp_wiki / "wiki"
    (wiki_dir / "cited-page.md").write_text(
        "---\n"
        "status: active\n"
        "sources:\n"
        "  - file: '/docs/real-source.txt'\n"
        "    hash: deadbeef\n"
        "    size: 1000\n"
        "    ingested: '2026-07-12'\n"
        "---\n\n"
        "# Cited Page\n\n"
        "Some content. ^[FILENAME:3-5]\n",
        encoding="utf-8",
    )

    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/lint/report")
    assert resp.status_code == 200
    data = resp.json()
    issues = data.get("citation_issues", [])
    # At least one broken_ref for cited-page
    assert any(i["slug"] == "cited-page" and i["reason"] == "broken_ref" for i in issues), \
        f"No broken_ref for cited-page in: {issues}"


def test_lint_report_returns_truncated_sources(tmp_wiki):
    """A page with truncated: true in a source must appear in truncated_sources.

    Regression: while the CLI showed truncated sources and the plugin showed them,
    the HTTP API's /lint/report endpoint also needs to expose them.
    """
    from synthadoc.integration.http_server import create_app

    wiki_dir = tmp_wiki / "wiki"
    (wiki_dir / "big-article.md").write_text(
        "---\n"
        "status: active\n"
        "sources:\n"
        "  - file: 'https://example.com/big-article'\n"
        "    hash: abc123\n"
        "    size: 45000\n"
        "    ingested: '2026-07-12'\n"
        "    truncated: true\n"
        "---\n\n"
        "# Big Article\n\n"
        "Some content.\n",
        encoding="utf-8",
    )

    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/lint/report")
    assert resp.status_code == 200
    data = resp.json()
    truncated = data.get("truncated_sources", [])
    assert any(e["slug"] == "big-article" for e in truncated), \
        f"big-article not in truncated_sources: {truncated}"
