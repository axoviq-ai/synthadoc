# tests/test_export_agent.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from pathlib import Path
from synthadoc.storage.wiki import WikiStorage, WikiPage, SourceRef, LifecycleState
from synthadoc.agents.export_agent import ExportAgent, ExportOptions


def _make_store(tmp_path: Path) -> WikiStorage:
    store = WikiStorage(tmp_path / "wiki")
    return store


def _write_page(store, slug, title, status, content="", contradiction_note=None, tags=None):
    page = WikiPage(
        title=title, tags=tags or [], content=content, status=status,
        confidence="high", sources=[], created="2026-05-26T00:00:00",
        orphan=False, contradiction_note=contradiction_note,
    )
    store.write_page(slug, page)


def _agent(tmp_path, store):
    return ExportAgent(
        store=store,
        wiki_name="test-wiki",
        audit_db_path=tmp_path / ".synthadoc" / "audit.db",
        routing_path=tmp_path / "ROUTING.md",
    )


@pytest.mark.asyncio
async def test_llms_txt_active_in_pages_section(tmp_path):
    store = _make_store(tmp_path)
    _write_page(store, "ada-lovelace", "Ada Lovelace", LifecycleState.ACTIVE, "First programmer.")
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="llms.txt"))
    assert "## Pages" in result
    assert "[Ada Lovelace](ada-lovelace)" in result


@pytest.mark.asyncio
async def test_llms_txt_contradicted_in_needs_review(tmp_path):
    store = _make_store(tmp_path)
    _write_page(store, "eniac", "ENIAC", LifecycleState.CONTRADICTED,
                contradiction_note="disputed claim about first computer")
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="llms.txt"))
    assert "## Needs Review" in result
    assert "[ENIAC](eniac)" in result
    assert "contradicted" in result


@pytest.mark.asyncio
async def test_llms_txt_stale_in_needs_review(tmp_path):
    store = _make_store(tmp_path)
    _write_page(store, "vacuum-tubes", "Vacuum Tubes", LifecycleState.STALE)
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="llms.txt"))
    assert "## Needs Review" in result
    assert "stale" in result


@pytest.mark.asyncio
async def test_llms_txt_archived_omitted(tmp_path):
    store = _make_store(tmp_path)
    _write_page(store, "old-page", "Old Page", LifecycleState.ARCHIVED)
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="llms.txt"))
    assert "old-page" not in result


@pytest.mark.asyncio
async def test_llms_txt_status_active_filter_omits_review_section(tmp_path):
    store = _make_store(tmp_path)
    _write_page(store, "ada-lovelace", "Ada Lovelace", LifecycleState.ACTIVE, "First programmer.")
    _write_page(store, "eniac", "ENIAC", LifecycleState.CONTRADICTED)
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="llms.txt", status_filter="active"))
    assert "## Pages" in result
    assert "[Ada Lovelace]" in result
    assert "## Needs Review" not in result
    assert "eniac" not in result


@pytest.mark.asyncio
async def test_llms_full_txt_contains_page_content(tmp_path):
    store = _make_store(tmp_path)
    _write_page(store, "babbage", "Charles Babbage", LifecycleState.ACTIVE,
                content="Babbage designed the Difference Engine.^[babbage.txt:1-12]")
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="llms-full.txt"))
    assert "# Charles Babbage" in result
    assert "Babbage designed the Difference Engine.^[babbage.txt:1-12]" in result


@pytest.mark.asyncio
async def test_llms_full_txt_has_header_with_count(tmp_path):
    store = _make_store(tmp_path)
    _write_page(store, "p1", "Page One", LifecycleState.ACTIVE)
    _write_page(store, "p2", "Page Two", LifecycleState.ACTIVE)
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="llms-full.txt"))
    assert "2 active" in result


@pytest.mark.asyncio
async def test_empty_wiki_llms_txt(tmp_path):
    store = _make_store(tmp_path)
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="llms.txt"))
    assert "# test-wiki" in result


@pytest.mark.asyncio
async def test_empty_wiki_llms_full_txt(tmp_path):
    store = _make_store(tmp_path)
    agent = _agent(tmp_path, store)
    result = await agent.export(ExportOptions(format="llms-full.txt"))
    assert "# test-wiki" in result
