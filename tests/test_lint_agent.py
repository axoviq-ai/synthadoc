# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for LintAgent truncation warnings (Task 5)."""
import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from synthadoc.agents.lint_agent import LintAgent
from synthadoc.storage.wiki import WikiStorage, WikiPage, SourceRef, LifecycleState


def make_page(sources=None, content="# Test\n\nContent.", status=LifecycleState.ACTIVE):
    """Helper to create a WikiPage."""
    return WikiPage(
        title="Test",
        tags=[],
        content=content,
        status=status,
        confidence="medium",
        sources=sources or [],
    )


def make_store(tmp_path, pages_dict):
    """Helper to create a WikiStorage and populate it with pages."""
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    store = WikiStorage(wiki_dir)
    for slug, page in pages_dict.items():
        store.write_page(slug, page)
    return store


def mock_provider():
    """Create a mock LLM provider."""
    provider = AsyncMock()
    return provider


def mock_log_writer():
    """Create a mock log writer."""
    log = MagicMock()
    log.log_lint = MagicMock()
    return log


async def test_lint_warns_truncated_source(tmp_path):
    """lint emits a WARN for pages with truncated=True sources."""
    page = make_page(sources=[SourceRef(
        file="papers/big.pdf", hash="x", size=90000, ingested="2026-01-01", truncated=True
    )])
    store = make_store(tmp_path, {"quantum-computing": page})
    agent = LintAgent(mock_provider(), store, mock_log_writer())
    report = await agent.lint(scope="all", adversarial=False, lifecycle=False)
    warns = [w for w in report.warnings if "truncated" in w.lower()]
    assert len(warns) >= 1
    assert "papers/big.pdf" in warns[0]
    assert "--max-source-chars" in warns[0]


async def test_lint_no_warn_when_not_truncated(tmp_path):
    """lint does not emit a WARN for pages with truncated=False sources."""
    page = make_page(sources=[SourceRef(
        file="papers/small.pdf", hash="x", size=1000, ingested="2026-01-01", truncated=False
    )])
    store = make_store(tmp_path, {"quantum-computing": page})
    agent = LintAgent(mock_provider(), store, mock_log_writer())
    report = await agent.lint(scope="all", adversarial=False, lifecycle=False)
    warns = [w for w in report.warnings if "truncated" in w.lower()]
    assert len(warns) == 0
