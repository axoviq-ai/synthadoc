# tests/test_lint_agent_scoped.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for LintAgent.run(scope='slug') — scoped single-page re-lint."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from synthadoc.agents.lint_agent import LintAgent, LintReport
from synthadoc.storage.wiki import WikiPage, WikiStorage, LifecycleState


def _make_store(tmp_path: Path, pages: dict[str, WikiPage]) -> WikiStorage:
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    store = WikiStorage(wiki_dir)
    for slug, page in pages.items():
        store.write_page(slug, page)
    return store


def _page(status=LifecycleState.CONTRADICTED, warnings=None, note=None):
    return WikiPage(
        title="Test", tags=[], content="Some content",
        status=status, confidence="high", sources=[],
        lint_warnings=warnings or [],
        contradiction_note=note,
    )


def _agent(store, provider=None, adv_provider=None):
    return LintAgent(
        provider=provider or AsyncMock(),
        adversarial_provider=adv_provider,
        store=store,
    )


@pytest.mark.asyncio
async def test_scope_slug_returns_empty_report_when_page_missing(tmp_path):
    store = _make_store(tmp_path, {})
    agent = _agent(store)
    report = await agent.run(scope="slug", slug="ghost", adversarial=False, lifecycle=False)
    assert isinstance(report, LintReport)
    assert report.contradictions_found == 0


@pytest.mark.asyncio
async def test_scope_slug_no_warnings_no_note_returns_zero(tmp_path):
    store = _make_store(tmp_path, {"target": _page(warnings=[], note=None)})
    agent = _agent(store)
    report = await agent.run(scope="slug", slug="target", adversarial=False, lifecycle=False)
    assert report.contradictions_found == 0


@pytest.mark.asyncio
async def test_scope_slug_contradiction_note_counts(tmp_path):
    store = _make_store(tmp_path, {
        "target": _page(note="Source A says X; source B says Y")
    })
    agent = _agent(store)
    report = await agent.run(scope="slug", slug="target", adversarial=False, lifecycle=False)
    assert report.contradictions_found == 1


@pytest.mark.asyncio
async def test_scope_slug_skips_full_wiki_scan(tmp_path):
    """scope=slug must not touch other pages."""
    pages = {
        "target": _page(note="conflict"),
        "other": _page(note="also conflicted"),
    }
    store = _make_store(tmp_path, pages)
    agent = _agent(store)
    report = await agent.run(scope="slug", slug="target", adversarial=False, lifecycle=False)
    # Only the target page counts — not the other
    assert report.contradictions_found == 1


@pytest.mark.asyncio
async def test_scope_slug_adversarial_pass_updates_lint_warnings(tmp_path):
    """When adversarial=True, the adversarial pass runs and updates page.lint_warnings."""
    page = _page()
    store = _make_store(tmp_path, {"target": page})

    adv_provider = AsyncMock()
    adv_response = MagicMock()
    adv_response.text = '[{"claim": "c1", "concern": "dubious"}]'
    adv_response.total_tokens = 50
    adv_provider.complete = AsyncMock(return_value=adv_response)

    agent = _agent(store, adv_provider=adv_provider)
    report = await agent.run(scope="slug", slug="target", adversarial=True, lifecycle=False)

    updated = store.read_page("target")
    assert updated is not None
    # adversarial provider was called
    assert adv_provider.complete.called


@pytest.mark.asyncio
async def test_scope_slug_does_not_demote_contradicted_page_via_gate(tmp_path):
    """A CONTRADICTED page must remain CONTRADICTED after scoped lint — gate does not re-fire."""
    page = _page(status=LifecycleState.CONTRADICTED)
    store = _make_store(tmp_path, {"target": page})

    adv_provider = AsyncMock()
    adv_response = MagicMock()
    adv_response.text = '[{"claim": "x", "concern": "bad"}]'
    adv_response.total_tokens = 30
    adv_provider.complete = AsyncMock(return_value=adv_response)

    cfg = MagicMock()
    cfg.lint.adversarial_gate_threshold = 1  # would demote ACTIVE, but not CONTRADICTED
    cfg.lint.adversarial_concurrency = 1

    agent = LintAgent(
        provider=AsyncMock(),
        adversarial_provider=adv_provider,
        store=store,
        cfg=cfg,
    )
    await agent.run(scope="slug", slug="target", adversarial=True, lifecycle=False)
    updated = store.read_page("target")
    assert updated.status == LifecycleState.CONTRADICTED  # unchanged


@pytest.mark.asyncio
async def test_scope_slug_skips_lint_skip_slugs(tmp_path):
    """System slugs (index, overview, etc.) are silently skipped."""
    from synthadoc.agents.lint_agent import LINT_SKIP_SLUGS
    a_skip_slug = next(iter(LINT_SKIP_SLUGS))
    pages = {a_skip_slug: _page()}
    store = _make_store(tmp_path, pages)
    agent = _agent(store)
    report = await agent.run(scope="slug", slug=a_skip_slug, adversarial=False, lifecycle=False)
    assert report.contradictions_found == 0


@pytest.mark.asyncio
async def test_scope_slug_missing_slug_param_returns_empty(tmp_path):
    """scope='slug' without a slug → empty report, no error."""
    store = _make_store(tmp_path, {"p": _page()})
    agent = _agent(store)
    report = await agent.run(scope="slug", slug=None, adversarial=False, lifecycle=False)
    assert report.contradictions_found == 0


def test_lint_config_has_resolver_timeout():
    """LintConfig must define contradiction_resolver_timeout_seconds."""
    from synthadoc.config import LintConfig
    cfg = LintConfig()
    assert cfg.contradiction_resolver_timeout_seconds == 3600
