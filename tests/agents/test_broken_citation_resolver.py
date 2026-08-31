# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for find_broken_citation_refs and tool_apply_citation_fixes."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from synthadoc.agents.lint_agent import find_broken_citation_refs
from synthadoc.storage.wiki import WikiPage, SourceRef


def _make_store(pages: dict[str, WikiPage]) -> MagicMock:
    store = MagicMock()
    store.list_pages.return_value = list(pages.keys())
    store.read_page.side_effect = lambda slug: pages.get(slug)
    return store


def _source(filename: str) -> SourceRef:
    return SourceRef(file=filename, hash="abc", size=100, ingested="2026-01-01")


# ──────────────────────────────────────────────────────────────
# Tests 1-6: find_broken_citation_refs
# ──────────────────────────────────────────────────────────────

def test_find_broken_citation_refs_detects_broken_ref(tmp_path):
    """broken_ref: citation filename not in page's sources[]."""
    page = WikiPage(
        title="Test", tags=[], content="A claim.^[missing.txt:1-5]",
        status="active", confidence="high",
        sources=[_source("bio.txt")],
    )
    store = _make_store({"my-page": page})
    result = find_broken_citation_refs(store, tmp_path)
    assert "my-page" in result
    assert result["my-page"][0]["reason"] == "broken_ref"
    assert result["my-page"][0]["citation"] == "^[missing.txt:1-5]"


def test_find_broken_citation_refs_detects_malformed(tmp_path):
    """malformed: ^[bio.txt] missing L-L range."""
    page = WikiPage(
        title="T", tags=[], content="Claim.^[bio.txt]",
        status="active", confidence="high",
        sources=[_source("bio.txt")],
    )
    store = _make_store({"p": page})
    result = find_broken_citation_refs(store, tmp_path)
    assert "p" in result
    assert result["p"][0]["reason"] == "malformed"


def test_find_broken_citation_refs_detects_out_of_range(tmp_path):
    """out_of_range: line_end exceeds file length."""
    extracted = tmp_path / ".synthadoc" / "extracted"
    extracted.mkdir(parents=True)
    (extracted / "bio.txt").write_text("line1\nline2\nline3\n", encoding="utf-8")
    page = WikiPage(
        title="T", tags=[], content="Claim.^[bio.txt:1-9999]",
        status="active", confidence="high",
        sources=[_source(str(tmp_path / "bio.txt"))],
    )
    store = _make_store({"p": page})
    result = find_broken_citation_refs(store, extracted)
    assert "p" in result
    assert result["p"][0]["reason"] == "out_of_range"


def test_find_broken_citation_refs_clean_page_returns_empty(tmp_path):
    """Page with a valid, in-range citation returns no issues."""
    extracted = tmp_path / ".synthadoc" / "extracted"
    extracted.mkdir(parents=True)
    lines = "\n".join(f"line{i}" for i in range(1, 101))
    (extracted / "bio.txt").write_text(lines, encoding="utf-8")
    page = WikiPage(
        title="T", tags=[], content="Claim.^[bio.txt:1-5]",
        status="active", confidence="high",
        sources=[_source(str(tmp_path / "bio.txt"))],
    )
    store = _make_store({"p": page})
    result = find_broken_citation_refs(store, extracted)
    assert result == {}


def test_find_broken_citation_refs_only_active_pages(tmp_path):
    """Stale and draft pages are NOT scanned."""
    stale = WikiPage(
        title="Stale", tags=[], content="Claim.^[missing.txt:1-5]",
        status="stale", confidence="low", sources=[],
    )
    draft = WikiPage(
        title="Draft", tags=[], content="Claim.^[gone.txt:1-5]",
        status="draft", confidence="low", sources=[],
    )
    store = _make_store({"stale-page": stale, "draft-page": draft})
    result = find_broken_citation_refs(store, tmp_path)
    assert result == {}


def test_find_broken_citation_refs_slug_filter(tmp_path):
    """slugs= parameter limits scan to specific pages."""
    good = WikiPage(
        title="Good", tags=[], content="Clean content, no citations.",
        status="active", confidence="high", sources=[],
    )
    bad = WikiPage(
        title="Bad", tags=[], content="Claim.^[gone.txt:1-5]",
        status="active", confidence="high", sources=[],
    )
    store = _make_store({"good": good, "bad": bad})
    result = find_broken_citation_refs(store, tmp_path, slugs=["good"])
    assert result == {}
    result2 = find_broken_citation_refs(store, tmp_path, slugs=["bad"])
    assert "bad" in result2


# ──────────────────────────────────────────────────────────────
# Tests 7-8: tool_apply_citation_fixes
# ──────────────────────────────────────────────────────────────

from synthadoc.agents.workflows._tools import tool_apply_citation_fixes
from synthadoc.agents.workflows._base import WorkflowContext


def _make_ctx_for_tool(pages: dict[str, WikiPage]) -> WorkflowContext:
    """Create a minimal WorkflowContext with a mock store, for tool tests."""
    from contextlib import contextmanager

    async def _noop(e, d):
        pass

    store = _make_store(pages)

    @contextmanager
    def _noop_lock(slug):
        yield

    store.page_lock.side_effect = _noop_lock
    store.write_page.return_value = None

    return WorkflowContext(
        session_id="s1",
        wiki_root=Path("/wiki"),
        queue=None,
        store=store,
        audit_db=None,
        send_sse_event=_noop,
        confirm_registry={},
        confirm_result_registry={},
    )


@pytest.mark.asyncio
async def test_apply_citation_fixes_replace(tmp_path):
    """tool_apply_citation_fixes replaces old marker with new marker."""
    content = "A claim.^[old.txt:1-5] More content."
    page = WikiPage(
        title="P", tags=[], content=content,
        status="active", confidence="high", sources=[],
    )
    ctx = _make_ctx_for_tool({"my-page": page})
    result = await tool_apply_citation_fixes(
        ctx,
        page_slug="my-page",
        fixes=[{"old_citation": "^[old.txt:1-5]", "new_citation": "^[new.txt:1-5]"}],
    )
    assert result["status"] == "success"
    assert result["changes"] == 1
    # Verify the page was written with the corrected content
    call_args = ctx.store.write_page.call_args
    written_page: WikiPage = call_args[0][1]
    assert "^[new.txt:1-5]" in written_page.content
    assert "^[old.txt:1-5]" not in written_page.content


@pytest.mark.asyncio
async def test_apply_citation_fixes_remove(tmp_path):
    """new_citation=null removes the marker, keeping surrounding prose."""
    content = "A claim.^[old.txt:1-5] More prose."
    page = WikiPage(
        title="P", tags=[], content=content,
        status="active", confidence="high", sources=[],
    )
    ctx = _make_ctx_for_tool({"my-page": page})
    result = await tool_apply_citation_fixes(
        ctx,
        page_slug="my-page",
        fixes=[{"old_citation": "^[old.txt:1-5]", "new_citation": None}],
    )
    assert result["status"] == "success"
    assert result["changes"] == 1
    call_args = ctx.store.write_page.call_args
    written_page: WikiPage = call_args[0][1]
    assert "^[old.txt:1-5]" not in written_page.content
    # Surrounding prose must survive
    assert "A claim." in written_page.content
    assert "More prose." in written_page.content


@pytest.mark.asyncio
async def test_find_broken_citations_inactive_slug_returns_empty(tmp_path):
    """Single-page mode with inactive slug returns empty pages list, not a full scan."""
    from contextlib import contextmanager

    from synthadoc.agents.workflows._tools import tool_find_broken_citations

    active_page = WikiPage(
        title="Active", tags=[], content="Claim.^[missing.txt:1-5]",
        status="active", confidence="high", sources=[],
    )
    inactive_page = WikiPage(
        title="Stale", tags=[], content="Claim.^[also-missing.txt:1-5]",
        status="stale", confidence="high", sources=[],
    )

    store = _make_store({"active-page": active_page, "inactive-page": inactive_page})

    @contextmanager
    def _noop_lock(slug):
        yield

    store.page_lock.side_effect = _noop_lock
    store.page_exists.return_value = True

    async def _noop(e, d):
        pass

    audit_db = MagicMock()
    # Only "active-page" is active
    audit_db.get_live_page_states = AsyncMock(return_value=[
        {"slug": "active-page", "state": "active"},
        {"slug": "inactive-page", "state": "stale"},
    ])

    ctx = WorkflowContext(
        session_id="s1",
        wiki_root=tmp_path,
        queue=None,
        store=store,
        audit_db=audit_db,
        send_sse_event=_noop,
        confirm_registry={},
        confirm_result_registry={},
    )

    # Request the INACTIVE slug in single-page mode
    result = await tool_find_broken_citations(ctx, page_slug="inactive-page")
    assert result["total_issues"] == 0
    assert result["pages"] == []
    assert result["scanned"] == 0, "Inactive slug should scan 0 pages, not trigger full-wiki scan"
