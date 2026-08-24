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
