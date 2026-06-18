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
        "synthadoc_ingest", "synthadoc_lint",
        "synthadoc_search", "synthadoc_status",
        "synthadoc_read_page", "synthadoc_write_page", "synthadoc_lifecycle", "synthadoc_jobs",
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
    mock_report = MagicMock()
    mock_report.contradictions_found = 2
    mock_report.orphan_slugs = ["orphan-page"]
    with patch("synthadoc.core.orchestrator.Orchestrator.lint",
               new=AsyncMock(return_value=mock_report)):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_lint", {"scope": "all"}, convert_result=False
        )
    assert result["contradictions_found"] == 2
    assert "orphan-page" in result["orphans"]


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
