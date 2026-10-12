# tests/test_lint_lifecycle.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from synthadoc.storage.wiki import WikiStorage, WikiPage, SourceRef, LifecycleState
from synthadoc.storage.log import AuditDB


def _make_log():
    log = MagicMock()
    log.log_lint = MagicMock()
    return log


def _write_page(store, slug, status="draft", source_file="src.txt"):
    page = WikiPage(
        title=slug.replace("-", " ").title(), tags=[], content=f"# {slug}\n\nContent.",
        status=status, confidence="medium",
        sources=[SourceRef(file=source_file, hash="", size=0, ingested="2026-05-23")],
    )
    store.write_page(slug, page)
    return page


async def _make_db(path):
    db = AuditDB(path / ".synthadoc" / "audit.db")
    await db.init()
    return db


async def test_draft_promoted_to_active_on_clean_lint(tmp_path):
    from synthadoc.agents.lint_agent import LintAgent
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir(parents=True)
    store = WikiStorage(wiki_dir)
    _write_page(store, "alan-turing", status=LifecycleState.DRAFT)
    db = await _make_db(tmp_path)
    agent = LintAgent(AsyncMock(), store, _make_log(), audit_db=db, wiki_root=tmp_path)
    await agent.run(scope="all", adversarial=False)
    page = store.read_page("alan-turing")
    assert page is not None
    assert page.status == LifecycleState.ACTIVE
    state = await db.get_page_state("alan-turing")
    assert state is not None
    assert state["state"] == LifecycleState.ACTIVE
    events, _ = await db.get_lifecycle_events(slug="alan-turing")
    assert any(e["to_state"] == LifecycleState.ACTIVE for e in events)


async def test_stale_detection_on_hash_mismatch(tmp_path):
    from synthadoc.agents.lint_agent import LintAgent
    wiki_dir = tmp_path / "wiki"
    raw_dir = tmp_path / "raw_sources"
    wiki_dir.mkdir(parents=True)
    raw_dir.mkdir()
    src = raw_dir / "source.txt"
    src.write_text("original content", encoding="utf-8")
    store = WikiStorage(wiki_dir)
    page = WikiPage(
        title="Test", tags=[], content="# Test\n\nContent.", status=LifecycleState.ACTIVE,
        confidence="medium",
        sources=[SourceRef(file="source.txt", hash="", size=0, ingested="2026-05-23")],
    )
    store.write_page("test-page", page)
    db = await _make_db(tmp_path)
    # Record ingest with old hash (different from current file content)
    old_hash = "oldhash123abc"
    await db.record_ingest(old_hash, 100, str(raw_dir / "source.txt"), "test-page", 0, 0.0)
    # Now source file has different content → different hash on disk
    src.write_text("updated content", encoding="utf-8")
    agent = LintAgent(AsyncMock(), store, _make_log(), audit_db=db, wiki_root=tmp_path)
    await agent.run(scope="all", adversarial=False)
    page = store.read_page("test-page")
    assert page is not None
    assert page.status == LifecycleState.STALE
    events, _ = await db.get_lifecycle_events(slug="test-page")
    assert any(e["to_state"] == LifecycleState.STALE for e in events)


async def test_archived_detection_on_missing_source(tmp_path):
    from synthadoc.agents.lint_agent import LintAgent
    wiki_dir = tmp_path / "wiki"
    raw_dir = tmp_path / "raw_sources"
    wiki_dir.mkdir(parents=True)
    raw_dir.mkdir()
    store = WikiStorage(wiki_dir)
    page = WikiPage(
        title="Test", tags=[], content="# Test\n\nContent.", status=LifecycleState.ACTIVE,
        confidence="medium",
        sources=[SourceRef(file="gone.txt", hash="", size=0, ingested="2026-05-23")],
    )
    store.write_page("test-page", page)
    db = await _make_db(tmp_path)
    agent = LintAgent(AsyncMock(), store, _make_log(), audit_db=db, wiki_root=tmp_path)
    await agent.run(scope="all", adversarial=False)
    page = store.read_page("test-page")
    assert page is not None
    assert page.status == LifecycleState.ARCHIVED
    events, _ = await db.get_lifecycle_events(slug="test-page")
    assert any(e["to_state"] == LifecycleState.ARCHIVED for e in events)


async def test_no_lifecycle_flag_skips_checks(tmp_path):
    from synthadoc.agents.lint_agent import LintAgent
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir(parents=True)
    store = WikiStorage(wiki_dir)
    _write_page(store, "alan-turing", status=LifecycleState.DRAFT)
    db = await _make_db(tmp_path)
    agent = LintAgent(AsyncMock(), store, _make_log(), audit_db=db, wiki_root=tmp_path)
    await agent.run(scope="all", adversarial=False, lifecycle=False)
    page = store.read_page("alan-turing")
    assert page is not None
    assert page.status == LifecycleState.DRAFT  # unchanged


async def test_scope_stale_detects_stale_pages(tmp_path):
    """--scope stale must mark pages as stale when source file hash changed."""
    from synthadoc.agents.lint_agent import LintAgent
    wiki_dir = tmp_path / "wiki"
    raw_dir = tmp_path / "raw_sources"
    wiki_dir.mkdir(parents=True)
    raw_dir.mkdir()
    src = raw_dir / "source.txt"
    src.write_text("original content", encoding="utf-8")
    store = WikiStorage(wiki_dir)
    page = WikiPage(
        title="Test", tags=[], content="# Test\n\nContent.", status=LifecycleState.ACTIVE,
        confidence="medium",
        sources=[SourceRef(file="source.txt", hash="", size=0, ingested="2026-05-23")],
    )
    store.write_page("test-page", page)
    db = await _make_db(tmp_path)
    await db.record_ingest("oldhash123abc", 100, str(raw_dir / "source.txt"), "test-page", 0, 0.0)
    src.write_text("updated content", encoding="utf-8")
    agent = LintAgent(AsyncMock(), store, _make_log(), audit_db=db, wiki_root=tmp_path)
    report = await agent.run(scope="stale", adversarial=False)
    page = store.read_page("test-page")
    assert page is not None
    assert page.status == LifecycleState.STALE
    assert report.lifecycle_stale == 1


async def test_scope_stale_does_not_promote_drafts(tmp_path):
    """--scope stale must not promote draft pages to active."""
    from synthadoc.agents.lint_agent import LintAgent
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir(parents=True)
    store = WikiStorage(wiki_dir)
    _write_page(store, "alan-turing", status=LifecycleState.DRAFT)
    db = await _make_db(tmp_path)
    agent = LintAgent(AsyncMock(), store, _make_log(), audit_db=db, wiki_root=tmp_path)
    await agent.run(scope="stale", adversarial=False)
    page = store.read_page("alan-turing")
    assert page is not None
    assert page.status == LifecycleState.DRAFT  # must remain draft


async def test_draft_promoted_when_source_file_prefixed_with_raw_sources(tmp_path):
    """Regression: src_ref.file stored as 'raw_sources/foo.pdf' must not be
    misidentified as missing, which would block draft→active promotion."""
    from synthadoc.agents.lint_agent import LintAgent
    wiki_dir = tmp_path / "wiki"
    raw_dir = tmp_path / "raw_sources"
    wiki_dir.mkdir(parents=True)
    raw_dir.mkdir()
    # File is at raw_sources/foo.pdf but frontmatter stores the full-prefix path
    (raw_dir / "foo.pdf").write_bytes(b"%PDF-1.4 dummy")
    store = WikiStorage(wiki_dir)
    page = WikiPage(
        title="Test", tags=[], content="# Test\n\nContent.", status=LifecycleState.DRAFT,
        confidence="medium",
        sources=[SourceRef(file="raw_sources/foo.pdf", hash="", size=0, ingested="2026-10-11")],
    )
    store.write_page("test-page", page)
    db = await _make_db(tmp_path)
    agent = LintAgent(AsyncMock(), store, _make_log(), audit_db=db, wiki_root=tmp_path)
    await agent.run(scope="all", adversarial=False)
    result = store.read_page("test-page")
    assert result is not None
    assert result.status == LifecycleState.ACTIVE, (
        f"Expected ACTIVE after lint but got {result.status!r}; "
        "raw_sources/ prefix in src_ref.file must not cause false 'missing source'"
    )


async def test_stale_page_promoted_after_reingest_when_source_prefixed(tmp_path):
    """Regression: STALE page with 'raw_sources/foo.pdf' source must reach ACTIVE
    after re-ingest sets it to DRAFT and lint runs (mirrors the Docker/serve bug)."""
    from synthadoc.agents.lint_agent import LintAgent
    wiki_dir = tmp_path / "wiki"
    raw_dir = tmp_path / "raw_sources"
    wiki_dir.mkdir(parents=True)
    raw_dir.mkdir()
    (raw_dir / "foo.pdf").write_bytes(b"%PDF-1.4 dummy")
    store = WikiStorage(wiki_dir)
    # Simulate state after re-ingest: page is DRAFT (ingest moved it from STALE→DRAFT)
    page = WikiPage(
        title="Test", tags=[], content="# Test\n\nContent.", status=LifecycleState.DRAFT,
        confidence="medium",
        sources=[SourceRef(file="raw_sources/foo.pdf", hash="", size=0, ingested="2026-10-11")],
    )
    store.write_page("test-page", page)
    db = await _make_db(tmp_path)
    await db.set_page_state("test-page", LifecycleState.DRAFT, "ingest")
    agent = LintAgent(AsyncMock(), store, _make_log(), audit_db=db, wiki_root=tmp_path)
    await agent.run(scope="all", adversarial=False)
    result = store.read_page("test-page")
    assert result is not None
    assert result.status == LifecycleState.ACTIVE, (
        f"Expected ACTIVE but got {result.status!r}; "
        "DRAFT page with raw_sources/-prefixed source must promote after re-ingest+lint"
    )
