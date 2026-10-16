# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for ContentHealthResolverWorkflow.run_for_cli_provider."""
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from synthadoc.agents.workflows._base import WorkflowContext
from synthadoc.agents.workflows.content_health_resolver import ContentHealthResolverWorkflow
from synthadoc.providers.base import CompletionResponse
from synthadoc.storage.wiki import LifecycleState, WikiPage, WikiStorage


def _make_ctx(store):
    ctx = MagicMock(spec=WorkflowContext)
    ctx.store = store
    ctx.audit_db = MagicMock()
    ctx.audit_db.snapshot_if_changed = AsyncMock(return_value=True)
    ctx.audit_db.list_page_snapshots = AsyncMock(return_value=[{"index": 1, "id": 42}])
    ctx.bump_epoch = MagicMock()
    ctx.is_cli_provider = True
    return ctx


_CLEAN_CONTENT = "# Page\n\n## Introduction\n\n" + " ".join(["word"] * 60) + "\n"
_DUPED_CONTENT = "# Page\n\n## Intro\nOld.\n\n## Intro\nDup.\n"


def _make_page(slug, with_issues=False):
    issues = []
    if with_issues:
        issues = [{"type": "duplicate_section", "severity": "critical",
                   "location": "## Intro", "description": "Appears 3 times"}]
    content = _DUPED_CONTENT if with_issues else _CLEAN_CONTENT
    return WikiPage(title=slug.title(), tags=[], content=content,
                    status=LifecycleState.ACTIVE, confidence="", sources=[],
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
    provider.complete = AsyncMock(
        return_value=CompletionResponse(text=fixed_content, input_tokens=0, output_tokens=0)
    )

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


# ── list / roll back intents on the CLI-provider path ────────────────────────

_FIX_RECORD = {"slug": "turing", "snapshot_id": 42, "snapshot_index_before": 1,
               "timestamp": "2026-10-11T14:00:00Z", "issues_fixed": ["duplicate_section x2"]}


async def _run_cli(wf, ctx, question, provider):
    """Run the CLI-provider path; fail if it opens a confirm gate."""
    confirm = AsyncMock(return_value={"confirmed": True})
    with patch("synthadoc.agents.workflows.content_health_resolver.tool_confirm", new=confirm):
        events = [e async for e in wf.run_for_cli_provider(ctx, question=question, provider=provider)]
    confirm.assert_not_called()
    provider.complete.assert_not_called()
    return events


def _fixed_page(slug):
    page = _make_page(slug)
    page.content = "# Page\n\n## Intro\n" + " ".join(["word"] * 60) + "\n"
    page.content_health_fix_record = dict(_FIX_RECORD, slug=slug)
    return page


@pytest.mark.asyncio
@pytest.mark.parametrize("question", [
    "list content health fixes",
    "run content health resolver list",   # synthadoc workflow run --name content-health list
])
async def test_cli_provider_list_shows_fix_history(tmp_path, question):
    store = WikiStorage(tmp_path / "wiki")
    store.write_page("turing", _fixed_page("turing"))
    store.write_page("hopper", _make_page("hopper", with_issues=True))  # flagged, must not be fixed
    ctx = _make_ctx(store)
    provider = MagicMock()
    provider.complete = AsyncMock()

    events = await _run_cli(ContentHealthResolverWorkflow(), ctx, question, provider)

    text = events[-1]["data"]["text"]
    assert events[-1]["event"] == "final_text"
    assert "turing" in text and "2026-10-11T14:00:00Z" in text
    assert "hopper" not in text


@pytest.mark.asyncio
async def test_cli_provider_list_empty(tmp_path):
    store = WikiStorage(tmp_path / "wiki")
    store.write_page("hopper", _make_page("hopper", with_issues=True))
    ctx = _make_ctx(store)
    provider = MagicMock()
    provider.complete = AsyncMock()

    events = await _run_cli(ContentHealthResolverWorkflow(), ctx, "list content health fixes", provider)

    assert events[-1]["data"]["text"] == "No content health fixes have been recorded yet."


@pytest.mark.asyncio
@pytest.mark.parametrize("question", [
    "roll back turing",
    "run content health resolver roll back turing",   # CLI form
    "rollback turing.",
])
async def test_cli_provider_rollback_restores_snapshot(tmp_path, question):
    original = "# Page\n\n## Intro\nOld.\n\n## Intro\nDup.\n"
    store = WikiStorage(tmp_path / "wiki")
    store.write_page("turing", _fixed_page("turing"))
    store.write_page("hopper", _make_page("hopper", with_issues=True))  # flagged, must not be fixed
    ctx = _make_ctx(store)
    ctx.audit_db.get_snapshot_by_index = AsyncMock(
        return_value={"index": 1, "id": 42, "content_snapshot": original})
    provider = MagicMock()
    provider.complete = AsyncMock()

    events = await _run_cli(ContentHealthResolverWorkflow(), ctx, question, provider)

    assert "rolled back to snapshot #1" in events[-1]["data"]["text"]
    restored = store.read_page("turing")
    assert restored.content.strip() == original.strip()
    assert restored.content_health_fix_record is None
    assert restored.content_health_issues  # original duplicate flagged again
    assert store.read_page("hopper").content_health_fix_record is None


@pytest.mark.asyncio
async def test_cli_provider_rollback_unknown_page_reports_error(tmp_path):
    store = WikiStorage(tmp_path / "wiki")
    store.write_page("hopper", _make_page("hopper", with_issues=True))
    ctx = _make_ctx(store)
    provider = MagicMock()
    provider.complete = AsyncMock()

    events = await _run_cli(ContentHealthResolverWorkflow(), ctx, "roll back hopper", provider)

    assert "No content health fix recorded for 'hopper'" in events[-1]["data"]["text"]


@pytest.mark.asyncio
async def test_cli_provider_bare_rollback_lists_fixes(tmp_path):
    store = WikiStorage(tmp_path / "wiki")
    store.write_page("turing", _fixed_page("turing"))
    ctx = _make_ctx(store)
    provider = MagicMock()
    provider.complete = AsyncMock()

    events = await _run_cli(ContentHealthResolverWorkflow(), ctx, "roll back", provider)

    text = events[-1]["data"]["text"]
    assert "turing" in text
    assert "roll back <slug>" in text


@pytest.mark.parametrize("question, expected", [
    ("list content health fixes", ("list", None)),
    ("run content health resolver list", ("list", None)),
    ("roll back alan-turing", ("rollback", "alan-turing")),
    ("run content health resolver roll back alan-turing.", ("rollback", "alan-turing")),
    ("roll back", ("rollback", None)),
    ("run content health resolver", ("fix", None)),
    ("run content health resolver --slug alan-turing", ("fix", None)),
])
def test_parse_intent_shared_by_both_paths(question, expected):
    assert ContentHealthResolverWorkflow._parse_intent(question) == expected
