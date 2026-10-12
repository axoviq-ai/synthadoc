# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for ContentHealthResolverWorkflow.run_for_cli_provider."""
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from synthadoc.agents.workflows._base import WorkflowContext
from synthadoc.agents.workflows.content_health_resolver import ContentHealthResolverWorkflow
from synthadoc.storage.wiki import WikiPage, WikiStorage


def _make_ctx(store):
    ctx = MagicMock(spec=WorkflowContext)
    ctx.store = store
    ctx.audit_db = MagicMock()
    ctx.audit_db.snapshot_if_changed = AsyncMock(return_value=True)
    ctx.audit_db.list_page_snapshots = AsyncMock(return_value=[{"index": 1, "id": 42}])
    ctx.bump_epoch = MagicMock()
    ctx.is_cli_provider = True
    return ctx


def _make_page(slug, with_issues=False):
    issues = []
    if with_issues:
        issues = [{"type": "duplicate_section", "severity": "critical",
                   "location": "## Intro", "description": "Appears 3 times"}]
    return WikiPage(title=slug.title(), tags=[], content="# Page\n\n## Intro\nOld.\n\n## Intro\nDup.\n",
                    status="active", confidence="", sources=[],
                    content_health_issues=issues)


@pytest.mark.asyncio
async def test_cli_provider_no_issues_exits_cleanly(tmp_path):
    store = WikiStorage(tmp_path / "wiki")
    store.write_page("clean", _make_page("clean", with_issues=False))
    ctx = _make_ctx(store)
    provider = MagicMock()

    wf = ContentHealthResolverWorkflow()
    events = []
    async for event in wf.run_for_cli_provider(ctx, question="run content health", provider=provider):
        events.append(event)

    final = [e for e in events if e.get("event") == "final_text"]
    assert final
    assert "no" in final[-1]["data"]["text"].lower()


@pytest.mark.asyncio
async def test_cli_provider_user_approves_fix(tmp_path):
    store = WikiStorage(tmp_path / "wiki")
    store.write_page("turing", _make_page("turing", with_issues=True))
    ctx = _make_ctx(store)

    fixed_content = "# Page\n\n## Intro\n" + " ".join(["word"] * 60) + "\n"
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=fixed_content)

    wf = ContentHealthResolverWorkflow()
    events = []
    with patch(
        "synthadoc.agents.workflows.content_health_resolver.tool_confirm",
        new=AsyncMock(return_value={"confirmed": True}),
    ):
        async for event in wf.run_for_cli_provider(ctx, question="run content health", provider=provider):
            events.append(event)

    loaded = store.read_page("turing")
    assert loaded.content_health_fix_record is not None
