# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Fixture ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_orch(tmp_wiki):
    """Return an Orchestrator wired to tmp_wiki paths (not yet init'd — tests mock methods)."""
    from synthadoc.core.orchestrator import Orchestrator
    from synthadoc.config import load_config
    cfg = load_config(project_config=tmp_wiki / ".synthadoc" / "config.toml")
    orch = Orchestrator(wiki_root=tmp_wiki, config=cfg)
    return orch


# ── Existing tools (updated for new signature) ────────────────────────────────

def test_mcp_server_has_required_tools(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(mock_orch)
    tool_names = [t.name for t in mcp._tool_manager.list_tools()]
    for expected in (
        "synthadoc_ingest", "synthadoc_lint", "synthadoc_lint_report",
        "synthadoc_search", "synthadoc_status", "synthadoc_list_pages",
        "synthadoc_read_page", "synthadoc_write_page", "synthadoc_lifecycle", "synthadoc_jobs",
        "synthadoc_context", "synthadoc_export",
    ):
        assert expected in tool_names
    assert "synthadoc_query" not in tool_names



@pytest.mark.asyncio
async def test_mcp_ingest_tool_returns_job_id(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(mock_orch)
    with patch("synthadoc.core.orchestrator.Orchestrator.ingest",
               new=AsyncMock(return_value="job-xyz")):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_ingest", {"source": "paper.pdf"}, convert_result=False
        )
    assert result["job_id"] == "job-xyz"


@pytest.mark.asyncio
async def test_mcp_lint_tool_returns_result(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(mock_orch)
    with patch("synthadoc.core.orchestrator.Orchestrator.lint",
               new=AsyncMock(return_value="job-lint-abc")):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_lint", {"scope": "all"}, convert_result=False
        )
    assert result["job_id"] == "job-lint-abc"
    assert result["scope"] == "all"


@pytest.mark.asyncio
async def test_mcp_lint_report_tool_returns_state(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    from synthadoc.agents.lint_agent import LintStateSummary
    mcp = create_mcp_server(mock_orch)
    fake_state = LintStateSummary(
        contradicted=["page-a"],
        orphans=["page-b"],
        adv_pages=[{"slug": "page-c", "warnings": [{"msg": "w1"}, {"msg": "w2"}]}],
    )
    with patch("synthadoc.agents.lint_agent.read_current_lint_state", return_value=fake_state):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_lint_report", {}, convert_result=False
        )
    assert result["contradicted"] == ["page-a"]
    assert result["orphans"] == ["page-b"]
    assert result["adversarial_warnings"] == 2
    assert result["adversarial_pages"] == ["page-c"]


@pytest.mark.asyncio
async def test_mcp_search_tool_returns_results(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(mock_orch)
    mock_hit = MagicMock()
    mock_hit.slug = "test-page"
    mock_hit.score = 0.9
    mock_hit.title = "Test Page"
    mock_hit.snippet = "test excerpt"
    with patch("synthadoc.storage.search.HybridSearch.bm25_search",
               return_value=[mock_hit]):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_search", {"terms": "test query"}, convert_result=False
        )
    assert len(result["results"]) == 1
    assert result["results"][0]["slug"] == "test-page"


@pytest.mark.asyncio
async def test_mcp_status_tool_returns_page_count(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(mock_orch)
    with patch("synthadoc.storage.wiki.WikiStorage.list_pages",
               return_value=["page-1", "page-2"]):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_status", {}, convert_result=False
        )
    assert result["pages"] == 2
    # wiki field must be the directory name, not the full path
    assert result["wiki"] == mock_orch._root.name
    assert "\\" not in result["wiki"]
    assert "/" not in result["wiki"]


# ── New tool: synthadoc_read_page ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mcp_read_page_returns_content(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    from synthadoc.storage.wiki import WikiPage
    mcp = create_mcp_server(mock_orch)
    fake_page = WikiPage(
        title="Grace Hopper",
        tags=["biography", "cobol"],
        content="## Overview\nGrace Hopper invented COBOL.",
        status="active",
        confidence="high",
        sources=[],
        type="person",
    )
    with patch("synthadoc.storage.wiki.WikiStorage.read_page", return_value=fake_page):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_read_page", {"slug": "grace-hopper"}, convert_result=False
        )
    assert result["slug"] == "grace-hopper"
    assert result["title"] == "Grace Hopper"
    assert "COBOL" in result["content"]
    assert result["status"] == "active"
    assert result["type"] == "person"
    assert "biography" in result["tags"]
    assert result["lint_warnings"] == []
    assert result["sources"] == []


@pytest.mark.asyncio
async def test_mcp_read_page_includes_sources(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    from synthadoc.storage.wiki import WikiPage, SourceRef
    mcp = create_mcp_server(mock_orch)
    fake_page = WikiPage(
        title="Backprop",
        tags=[],
        content="Backpropagation content.",
        status="active",
        confidence="high",
        sources=[SourceRef(file="backprop.pdf", hash="abc", size=100, ingested="2026-06-01")],
    )
    with patch("synthadoc.storage.wiki.WikiStorage.read_page", return_value=fake_page):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_read_page", {"slug": "backprop"}, convert_result=False
        )
    assert len(result["sources"]) == 1
    assert result["sources"][0]["file"] == "backprop.pdf"
    assert result["sources"][0]["ingested"] == "2026-06-01"


@pytest.mark.asyncio
async def test_mcp_list_pages_returns_all(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    from synthadoc.storage.wiki import WikiPage, SourceRef
    mcp = create_mcp_server(mock_orch)
    pages = {
        "page-a": WikiPage(title="Page A", tags=[], content="", status="active",
                           confidence="high", sources=[SourceRef("a.pdf","h",1,"2026-01-01")]),
        "page-b": WikiPage(title="Page B", tags=[], content="", status="draft",
                           confidence="low", sources=[]),
    }
    with patch("synthadoc.storage.wiki.WikiStorage.list_pages", return_value=list(pages)), \
         patch("synthadoc.storage.wiki.WikiStorage.read_page", side_effect=lambda s: pages.get(s)):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_list_pages", {}, convert_result=False
        )
    assert result["total"] == 2
    slugs = [p["slug"] for p in result["pages"]]
    assert "page-a" in slugs and "page-b" in slugs
    page_a = next(p for p in result["pages"] if p["slug"] == "page-a")
    assert page_a["has_sources"] is True
    page_b = next(p for p in result["pages"] if p["slug"] == "page-b")
    assert page_b["has_sources"] is False


@pytest.mark.asyncio
async def test_mcp_list_pages_filters_by_status(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    from synthadoc.storage.wiki import WikiPage
    mcp = create_mcp_server(mock_orch)
    pages = {
        "page-a": WikiPage(title="A", tags=[], content="", status="active",
                           confidence="high", sources=[]),
        "page-b": WikiPage(title="B", tags=[], content="", status="draft",
                           confidence="low", sources=[]),
    }
    with patch("synthadoc.storage.wiki.WikiStorage.list_pages", return_value=list(pages)), \
         patch("synthadoc.storage.wiki.WikiStorage.read_page", side_effect=lambda s: pages.get(s)):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_list_pages", {"status": "active"}, convert_result=False
        )
    assert result["total"] == 1
    assert result["pages"][0]["slug"] == "page-a"


@pytest.mark.asyncio
async def test_mcp_context_tool_returns_pack(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    from synthadoc.agents.context_agent import ContextPack, ContextPage
    mcp = create_mcp_server(mock_orch)
    fake_pack = ContextPack(
        goal="early neural networks",
        token_budget=4000,
        tokens_used=120,
        pages=[ContextPage(slug="perceptron", relevance=0.9, excerpt="The perceptron...",
                           source="perceptron.pdf", confidence="high", tags=[], estimated_tokens=120)],
        omitted=[],
    )
    with patch("synthadoc.providers.make_provider", return_value=MagicMock()), \
         patch("synthadoc.agents.context_agent.ContextAgent.build",
               new=AsyncMock(return_value=fake_pack)):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_context", {"goal": "early neural networks", "token_budget": 10000},
            convert_result=False
        )
    assert result["goal"] == "early neural networks"
    assert result["tokens_used"] == 120
    assert len(result["pages"]) == 1
    assert result["pages"][0]["slug"] == "perceptron"


@pytest.mark.asyncio
async def test_mcp_export_tool_okf_uses_default_path(mock_orch, tmp_path):
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(mock_orch)
    fake_files = {"index.md": "# Index", "wiki/page.md": "Content."}
    with patch("synthadoc.agents.export_agent.ExportAgent.export",
               new=AsyncMock(return_value=fake_files)):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_export", {"format": "okf"},
            convert_result=False
        )
    assert result["format"] == "okf"
    assert "output_path" in result
    assert "okf" in result["output_path"]
    assert result["files_written"] == 2


@pytest.mark.asyncio
async def test_mcp_export_tool_okf_writes_folder(mock_orch, tmp_path):
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(mock_orch)
    fake_files = {
        "index.md": "# Index",
        "wiki/perceptron.md": "---\ntitle: Perceptron\n---\nContent.",
    }
    out_dir = str(tmp_path / "okf-export")
    with patch("synthadoc.agents.export_agent.ExportAgent.export",
               new=AsyncMock(return_value=fake_files)):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_export", {"format": "okf", "output_path": out_dir},
            convert_result=False
        )
    assert result["format"] == "okf"
    assert result["files_written"] == 2
    assert (tmp_path / "okf-export" / "index.md").exists()
    assert (tmp_path / "okf-export" / "wiki" / "perceptron.md").exists()


@pytest.mark.asyncio
async def test_mcp_export_tool_llms_txt_inline(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(mock_orch)
    with patch("synthadoc.agents.export_agent.ExportAgent.export",
               new=AsyncMock(return_value="# Wiki\nPage content.")):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_export", {"format": "llms.txt"},
            convert_result=False
        )
    assert result["format"] == "llms.txt"
    assert "content" in result
    assert "Wiki" in result["content"]


@pytest.mark.asyncio
async def test_mcp_export_tool_invalid_format_returns_error(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(mock_orch)
    result = await mcp._tool_manager.call_tool(
        "synthadoc_export", {"format": "unsupported"},
        convert_result=False
    )
    assert "error" in result
    assert "unsupported" in result["error"]


@pytest.mark.asyncio
async def test_mcp_read_page_not_found_returns_error(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(mock_orch)
    with patch("synthadoc.storage.wiki.WikiStorage.read_page", return_value=None):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_read_page", {"slug": "missing-page"}, convert_result=False
        )
    assert "error" in result
    assert result["slug"] == "missing-page"


# ── New tool: synthadoc_write_page ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_mcp_write_page_updates_content(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    from synthadoc.storage.wiki import WikiPage
    mcp = create_mcp_server(mock_orch)
    fake_page = WikiPage(
        title="Grace Hopper", tags=[], content="old content",
        status="contradicted", confidence="high", sources=[],
        contradiction_note="old note",
    )
    with patch("synthadoc.storage.wiki.WikiStorage.read_page", return_value=fake_page), \
         patch("synthadoc.storage.wiki.WikiStorage.write_page") as mock_write:
        result = await mcp._tool_manager.call_tool(
            "synthadoc_write_page",
            {"slug": "grace-hopper", "content": "new content", "title": "Grace Hopper (revised)"},
            convert_result=False,
        )
    assert result["slug"] == "grace-hopper"
    assert result["title"] == "Grace Hopper (revised)"
    assert result["status"] == "contradicted"  # unchanged — use synthadoc_lifecycle for that
    assert fake_page.content == "new content"
    assert fake_page.contradiction_note is None  # cleared on write
    mock_write.assert_called_once()


@pytest.mark.asyncio
async def test_mcp_write_page_not_found_returns_error(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(mock_orch)
    with patch("synthadoc.storage.wiki.WikiStorage.read_page", return_value=None):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_write_page",
            {"slug": "missing", "content": "anything"},
            convert_result=False,
        )
    assert result == {"error": "page not found", "slug": "missing"}


@pytest.mark.asyncio
async def test_mcp_write_page_rejects_empty_content(mock_orch):
    """synthadoc_write_page with empty or whitespace-only content must return an error."""
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(mock_orch)
    for bad in ("", "   "):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_write_page",
            {"slug": "some-page", "content": bad},
            convert_result=False,
        )
        assert result == {"error": "content must not be empty"}


# ── New tool: synthadoc_lifecycle ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mcp_lifecycle_transitions_page(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    from synthadoc.storage.wiki import WikiPage
    mcp = create_mcp_server(mock_orch)
    fake_page = WikiPage(
        title="Grace Hopper",
        tags=[],
        content="content",
        status="contradicted",
        confidence="high",
        sources=[],
    )
    with patch("synthadoc.storage.wiki.WikiStorage.read_page", return_value=fake_page), \
         patch("synthadoc.storage.wiki.WikiStorage.write_page") as mock_write, \
         patch("synthadoc.storage.log.AuditDB.set_page_state", new=AsyncMock()), \
         patch("synthadoc.storage.log.AuditDB.record_lifecycle_event", new=AsyncMock()):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_lifecycle",
            {"slug": "grace-hopper", "to_state": "active", "reason": "verified correct"},
            convert_result=False,
        )
    assert result["slug"] == "grace-hopper"
    assert result["from_state"] == "contradicted"
    assert result["to_state"] == "active"
    assert result["reason"] == "verified correct"
    assert "timestamp" in result
    # Verify the page object was actually mutated before write_page was called
    written_page = mock_write.call_args.args[1]
    assert written_page.status == "active"


@pytest.mark.asyncio
async def test_mcp_lifecycle_invalid_state_returns_error(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(mock_orch)
    with patch("synthadoc.storage.wiki.WikiStorage.read_page") as mock_read:
        result = await mcp._tool_manager.call_tool(
            "synthadoc_lifecycle",
            {"slug": "any-page", "to_state": "unknown_state", "reason": "test"},
            convert_result=False,
        )
        mock_read.assert_not_called()  # should fail before reading page
    assert "error" in result
    assert "unknown_state" in result["error"]


@pytest.mark.asyncio
async def test_mcp_lifecycle_blocked_transition_returns_error(mock_orch):
    """Transitions not in the allowed graph must return an error dict, not write the page."""
    from synthadoc.integration.mcp_server import create_mcp_server
    from synthadoc.storage.wiki import WikiPage
    mcp = create_mcp_server(mock_orch)
    # draft → contradicted is blocked (draft pages haven't been published yet)
    fake_page = WikiPage(
        title="Test Page", tags=[], content="content",
        status="draft", confidence="medium", sources=[],
    )
    with patch("synthadoc.storage.wiki.WikiStorage.read_page", return_value=fake_page), \
         patch("synthadoc.storage.wiki.WikiStorage.write_page") as mock_write:
        result = await mcp._tool_manager.call_tool(
            "synthadoc_lifecycle",
            {"slug": "test-page", "to_state": "contradicted", "reason": "blocked test"},
            convert_result=False,
        )
    assert "error" in result
    assert "not permitted" in result["error"]
    mock_write.assert_not_called()  # page must not be written on blocked transition


# ── New tool: synthadoc_jobs ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mcp_jobs_returns_all_jobs(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    from synthadoc.core.queue import Job, JobStatus
    mcp = create_mcp_server(mock_orch)
    fake_jobs = [
        Job(id="abc123", operation="ingest", payload={"source": "https://example.com"},
            status=JobStatus.COMPLETED, retries=0, error=None, created_at="2026-06-17T09:00:00"),
        Job(id="def456", operation="lint", payload={"scope": "all"},
            status=JobStatus.COMPLETED, retries=0, error=None, created_at="2026-06-17T09:01:00"),
    ]
    with patch("synthadoc.core.queue.JobQueue.list_jobs", new=AsyncMock(return_value=fake_jobs)):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_jobs", {"status": "all"}, convert_result=False
        )
    assert len(result["jobs"]) == 2
    assert result["jobs"][0]["id"] == "abc123"
    assert result["jobs"][0]["operation"] == "ingest"
    assert result["jobs"][0]["source"] == "https://example.com"
    assert "source" not in result["jobs"][1]  # lint jobs have no source


@pytest.mark.asyncio
async def test_mcp_jobs_filtered_by_status(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    from synthadoc.core.queue import Job, JobStatus
    mcp = create_mcp_server(mock_orch)
    fake_jobs = [
        Job(id="abc123", operation="ingest", payload={"source": "https://example.com"},
            status=JobStatus.COMPLETED, retries=0, error=None, created_at="2026-06-17T09:00:00"),
    ]
    with patch("synthadoc.core.queue.JobQueue.list_jobs",
               new=AsyncMock(return_value=fake_jobs)) as mock_list:
        result = await mcp._tool_manager.call_tool(
            "synthadoc_jobs", {"status": "completed"}, convert_result=False
        )
        from synthadoc.core.queue import JobStatus
        mock_list.assert_called_once_with(status=JobStatus.COMPLETED)
    assert len(result["jobs"]) == 1


@pytest.mark.asyncio
async def test_mcp_jobs_includes_error_for_failed(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    from synthadoc.core.queue import Job, JobStatus
    mcp = create_mcp_server(mock_orch)
    fake_jobs = [
        Job(id="ok123", operation="ingest", payload={"source": "https://good.com"},
            status=JobStatus.COMPLETED, retries=0, error=None, created_at="2026-06-17T09:00:00"),
        Job(id="skip456", operation="ingest", payload={"source": "https://blocked.com"},
            status=JobStatus.SKIPPED, retries=0,
            error="out of scope (purpose.md)", created_at="2026-06-17T09:01:00"),
    ]
    with patch("synthadoc.core.queue.JobQueue.list_jobs", new=AsyncMock(return_value=fake_jobs)):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_jobs", {"status": "all"}, convert_result=False
        )
    completed_job = next(j for j in result["jobs"] if j["id"] == "ok123")
    skipped_job = next(j for j in result["jobs"] if j["id"] == "skip456")
    assert "error" not in completed_job
    assert skipped_job["error"] == "out of scope (purpose.md)"


@pytest.mark.asyncio
async def test_mcp_lifecycle_page_not_found_returns_error(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(mock_orch)
    with patch("synthadoc.storage.wiki.WikiStorage.read_page", return_value=None):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_lifecycle",
            {"slug": "missing-page", "to_state": "active", "reason": "test"},
            convert_result=False,
        )
    assert result == {"error": "page not found", "slug": "missing-page"}


@pytest.mark.asyncio
async def test_mcp_jobs_invalid_status_returns_error(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(mock_orch)
    result = await mcp._tool_manager.call_tool(
        "synthadoc_jobs", {"status": "invalid_status"}, convert_result=False
    )
    assert "error" in result
    assert "invalid_status" in result["error"]


# ── Bug fixes: input validation ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mcp_ingest_empty_source_returns_error(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(mock_orch)
    with patch("synthadoc.core.orchestrator.Orchestrator.ingest",
               new=AsyncMock(return_value="job-xyz")) as mock_ingest:
        result = await mcp._tool_manager.call_tool(
            "synthadoc_ingest", {"source": ""}, convert_result=False
        )
    assert "error" in result
    mock_ingest.assert_not_called()


@pytest.mark.asyncio
async def test_mcp_ingest_calls_ingest_without_auto_confirm(mock_orch):
    """Regression: auto_confirm was incorrectly passed to Orchestrator.ingest()."""
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(mock_orch)
    with patch("synthadoc.core.orchestrator.Orchestrator.ingest",
               new=AsyncMock(return_value="job-abc")) as mock_ingest:
        result = await mcp._tool_manager.call_tool(
            "synthadoc_ingest", {"source": "paper.pdf"}, convert_result=False
        )
    mock_ingest.assert_called_once_with("paper.pdf", max_results=None, max_source_chars=None)
    assert result["job_id"] == "job-abc"


@pytest.mark.asyncio
async def test_mcp_list_pages_invalid_status_returns_error(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(mock_orch)
    result = await mcp._tool_manager.call_tool(
        "synthadoc_list_pages", {"status": "nonexistent_state"}, convert_result=False
    )
    assert "error" in result
    assert "nonexistent_state" in result["error"]


@pytest.mark.asyncio
async def test_mcp_lint_nonexistent_slug_returns_error(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(mock_orch)
    with patch("synthadoc.storage.wiki.WikiStorage.read_page", return_value=None), \
         patch("synthadoc.core.orchestrator.Orchestrator.lint",
               new=AsyncMock(return_value="job-lint")) as mock_lint:
        result = await mcp._tool_manager.call_tool(
            "synthadoc_lint", {"scope": "does-not-exist"}, convert_result=False
        )
    assert "error" in result
    assert result["error"] == "page not found"
    mock_lint.assert_not_called()


@pytest.mark.asyncio
async def test_mcp_lint_all_scope_skips_page_check(mock_orch):
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(mock_orch)
    with patch("synthadoc.core.orchestrator.Orchestrator.lint",
               new=AsyncMock(return_value="job-lint")) as mock_lint, \
         patch("synthadoc.storage.wiki.WikiStorage.read_page") as mock_read:
        result = await mcp._tool_manager.call_tool(
            "synthadoc_lint", {"scope": "all"}, convert_result=False
        )
    mock_read.assert_not_called()  # read_page must not be called for scope="all"
    mock_lint.assert_called_once_with(scope="all")
    assert result["job_id"] == "job-lint"


# ── Wiki name injection ───────────────────────────────────────────────────────

def test_mcp_tool_descriptions_include_wiki_name(tmp_path):
    from pathlib import Path
    from synthadoc.integration.mcp_server import create_mcp_server
    orch = MagicMock()
    orch._root = tmp_path / "history-of-computing"
    mcp = create_mcp_server(orch)
    for tool in mcp._tool_manager._tools.values():
        assert tool.description.startswith("Wiki: history-of-computing. "), (
            f"{tool.name} missing wiki prefix: {tool.description[:80]}"
        )


def test_mcp_tool_descriptions_no_prefix_without_path(tmp_path):
    from synthadoc.integration.mcp_server import create_mcp_server
    orch = MagicMock()
    orch._root = MagicMock()  # not a Path — no injection
    mcp = create_mcp_server(orch)
    for tool in mcp._tool_manager._tools.values():
        assert not tool.description.startswith("Wiki: "), (
            f"{tool.name} got unexpected wiki prefix: {tool.description[:80]}"
        )


# ── Integration: MCP mounted on HTTP app ─────────────────────────────────────

def test_mcp_mounted_on_http_app(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    app = create_app(wiki_root=tmp_wiki)
    # Check that a route exists at /mcp (Starlette mount)
    mounted_paths = [
        route.path for route in app.routes
        if hasattr(route, "path")
    ]
    assert "/mcp" in mounted_paths, f"MCP not mounted. Routes: {mounted_paths}"
