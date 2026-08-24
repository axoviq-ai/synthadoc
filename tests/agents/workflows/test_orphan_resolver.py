# tests/agents/workflows/test_orphan_resolver.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
"""Unit tests for the orphan-resolver workflow and its domain tools."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from synthadoc.agents.workflows._base import WorkflowContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(store=None, search=None, audit_db=None, queue=None):
    events = []

    async def _send(e, d):
        events.append({"event": e, "data": d})

    ctx = WorkflowContext(
        session_id="test-session",
        wiki_root=Path("/wiki"),
        queue=queue,
        store=store,
        audit_db=audit_db,
        send_sse_event=_send,
        confirm_registry={},
        confirm_result_registry={},
        search=search,
    )
    return ctx, events


# ---------------------------------------------------------------------------
# Task 2: WorkflowContext.search field
# ---------------------------------------------------------------------------

def test_workflow_context_search_field():
    """WorkflowContext accepts a search= kwarg and exposes it."""
    mock_search = MagicMock()
    ctx, _ = _make_ctx(search=mock_search)
    assert ctx.search is mock_search


def test_workflow_context_search_field_defaults_none():
    """WorkflowContext.search defaults to None when omitted."""
    events = []

    async def _send(e, d):
        events.append({"event": e, "data": d})

    ctx = WorkflowContext(
        session_id="s",
        wiki_root=Path("/wiki"),
        queue=None,
        store=None,
        audit_db=None,
        send_sse_event=_send,
        confirm_registry={},
        confirm_result_registry={},
    )
    assert ctx.search is None


# ---------------------------------------------------------------------------
# Task 3: tool_find_orphaned_pages + tool_verify_orphan_resolved
# ---------------------------------------------------------------------------

def _make_wiki_store(pages: dict[str, tuple[str, str]]) -> MagicMock:
    """Build a mock WikiStorage from {slug: (status, content)} pairs."""
    store = MagicMock()
    page_slugs = list(pages.keys())
    store.list_pages.return_value = page_slugs

    def _read(slug):
        if slug not in pages:
            return None
        status, content = pages[slug]
        p = MagicMock()
        p.status = status
        p.content = content
        p.orphan = False
        return p

    store.read_page.side_effect = _read
    return store


async def test_find_orphaned_pages_empty():
    """No active pages → empty orphans list."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_find_orphaned_pages
    store = _make_wiki_store({})
    ctx, _ = _make_ctx(store=store)
    result = await tool_find_orphaned_pages(ctx)
    assert result == {"orphans": [], "count": 0}


async def test_find_orphaned_pages_returns_slugs():
    """Page with no inbound links is returned as orphan; page with link is not."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_find_orphaned_pages
    store = _make_wiki_store({
        "alpha": ("active", "This page mentions [[beta]]."),
        "beta":  ("active", "No links here."),
        "gamma": ("active", "Links to [[alpha]]."),
    })
    ctx, _ = _make_ctx(store=store)
    result = await tool_find_orphaned_pages(ctx)
    # gamma links to alpha, alpha links to beta — only beta has no inbound link
    # Wait: alpha→beta, gamma→alpha. beta has inbound from alpha. gamma has inbound from none.
    # Correct: gamma is orphan (no page links to gamma), beta is not orphan (alpha links to beta)
    # Actually: referenced = {beta, alpha}. Not referenced = {gamma}.
    assert "gamma" in result["orphans"]
    assert "beta" not in result["orphans"]
    assert result["count"] == len(result["orphans"])


async def test_find_orphaned_pages_excludes_non_active():
    """Draft and archived pages are not included in orphan check."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_find_orphaned_pages
    store = _make_wiki_store({
        "active-page": ("active", "No links."),
        "draft-page":  ("draft", "No links."),
        "archived":    ("archived", "No links."),
    })
    ctx, _ = _make_ctx(store=store)
    result = await tool_find_orphaned_pages(ctx)
    slugs = result["orphans"]
    assert "draft-page" not in slugs
    assert "archived" not in slugs


async def test_verify_orphan_resolved_true():
    """Orphan is resolved when another page now links to it."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_verify_orphan_resolved
    store = _make_wiki_store({
        "orphan-page": ("active", "Content."),
        "linker":      ("active", "See [[orphan-page]] for details."),
    })
    ctx, _ = _make_ctx(store=store)
    result = await tool_verify_orphan_resolved(ctx, "orphan-page")
    assert result["resolved"] is True
    assert "linker" in result["linked_by"]


async def test_verify_orphan_resolved_false():
    """Orphan is still unresolved when no page links to it."""
    from synthadoc.agents.workflows.tools.orphan_resolver_tools import tool_verify_orphan_resolved
    store = _make_wiki_store({
        "orphan-page": ("active", "Content."),
        "other":       ("active", "Nothing relevant."),
    })
    ctx, _ = _make_ctx(store=store)
    result = await tool_verify_orphan_resolved(ctx, "orphan-page")
    assert result["resolved"] is False
    assert result["linked_by"] == []
