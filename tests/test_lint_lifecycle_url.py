# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from synthadoc.storage.wiki import WikiStorage, WikiPage, SourceRef
from synthadoc.storage.log import AuditDB


def _url_page(url: str, status: str = "active") -> WikiPage:
    return WikiPage(
        title="Test", tags=[], content="# Test\n\nContent.",
        status=status, confidence="medium",
        sources=[SourceRef(file=url, hash="", size=0, ingested="2026-05-24")],
    )


async def _make_db(tmp_path):
    db = AuditDB(tmp_path / ".synthadoc" / "audit.db")
    await db.init()
    return db


@pytest.mark.asyncio
async def test_url_archived_on_404(tmp_path):
    from synthadoc.agents.lint_agent import LintAgent
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir(parents=True)
    store = WikiStorage(wiki_dir)
    store.write_page("test-page", _url_page("https://example.com/gone"))
    db = await _make_db(tmp_path)
    agent = LintAgent(AsyncMock(), store, log_writer=MagicMock(), audit_db=db, wiki_root=tmp_path)

    with patch.object(agent, "_is_url_unavailable", new=AsyncMock(return_value=True)):
        await agent.lint(scope="all", adversarial=False, check_url_availability=True)

    page = store.read_page("test-page")
    assert page.status == "archived"


@pytest.mark.asyncio
async def test_url_not_archived_on_200(tmp_path):
    from synthadoc.agents.lint_agent import LintAgent
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir(parents=True)
    store = WikiStorage(wiki_dir)
    store.write_page("test-page", _url_page("https://example.com/present"))
    db = await _make_db(tmp_path)
    agent = LintAgent(AsyncMock(), store, log_writer=MagicMock(), audit_db=db, wiki_root=tmp_path)

    with patch.object(agent, "_is_url_unavailable", new=AsyncMock(return_value=False)):
        await agent.lint(scope="all", adversarial=False, check_url_availability=True)

    page = store.read_page("test-page")
    assert page.status != "archived"


@pytest.mark.asyncio
async def test_url_not_archived_when_flag_off(tmp_path):
    from synthadoc.agents.lint_agent import LintAgent
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir(parents=True)
    store = WikiStorage(wiki_dir)
    store.write_page("test-page", _url_page("https://example.com/gone"))
    db = await _make_db(tmp_path)
    agent = LintAgent(AsyncMock(), store, log_writer=MagicMock(), audit_db=db, wiki_root=tmp_path)

    with patch.object(agent, "_is_url_unavailable", new=AsyncMock(return_value=True)):
        await agent.lint(scope="all", adversarial=False, check_url_availability=False)

    page = store.read_page("test-page")
    assert page.status != "archived"  # flag off → no check


@pytest.mark.asyncio
async def test_url_stale_on_old_ingest(tmp_path):
    from synthadoc.agents.lint_agent import LintAgent
    from datetime import datetime, timezone, timedelta
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir(parents=True)
    store = WikiStorage(wiki_dir)
    url = "https://example.com/article"
    store.write_page("test-page", _url_page(url))
    db = await _make_db(tmp_path)
    old_ts = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    # Insert ingest record with old timestamp
    import aiosqlite
    async with aiosqlite.connect(db._path) as conn:
        await conn.execute(
            "INSERT INTO ingests (source_hash,source_size,source_path,wiki_page,tokens,cost_usd,ingested_at)"
            " VALUES (?,?,?,?,?,?,?)",
            ("abc123", 100, url, "test-page", 0, 0.0, old_ts)
        )
        await conn.commit()

    cfg = MagicMock()
    cfg.audit.url_staleness_days = 30
    cfg.audit.lifecycle_retention_days = 0
    cfg.lint.check_url_availability = False
    agent = LintAgent(AsyncMock(), store, log_writer=MagicMock(), audit_db=db, wiki_root=tmp_path, cfg=cfg)

    await agent.lint(scope="all", adversarial=False, check_url_availability=False)
    page = store.read_page("test-page")
    assert page.status == "stale"


@pytest.mark.asyncio
async def test_url_not_stale_when_recent(tmp_path):
    from synthadoc.agents.lint_agent import LintAgent
    from datetime import datetime, timezone, timedelta
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir(parents=True)
    store = WikiStorage(wiki_dir)
    url = "https://example.com/fresh"
    store.write_page("test-page", _url_page(url))
    db = await _make_db(tmp_path)
    recent_ts = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    import aiosqlite
    async with aiosqlite.connect(db._path) as conn:
        await conn.execute(
            "INSERT INTO ingests (source_hash,source_size,source_path,wiki_page,tokens,cost_usd,ingested_at)"
            " VALUES (?,?,?,?,?,?,?)",
            ("abc123", 100, url, "test-page", 0, 0.0, recent_ts)
        )
        await conn.commit()

    cfg = MagicMock()
    cfg.audit.url_staleness_days = 30
    cfg.audit.lifecycle_retention_days = 0
    cfg.lint.check_url_availability = False
    agent = LintAgent(AsyncMock(), store, log_writer=MagicMock(), audit_db=db, wiki_root=tmp_path, cfg=cfg)

    await agent.lint(scope="all", adversarial=False, check_url_availability=False)
    page = store.read_page("test-page")
    assert page.status != "stale"  # only 5 days old, threshold is 30
