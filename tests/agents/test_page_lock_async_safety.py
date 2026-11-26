# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Peter White / axoviq.com
"""A page lock must never be held across an ``await``.

``WikiStorage.page_lock`` is a thread lock. A task that awaits while holding it
leaves the lock taken while the event loop runs other tasks, and the first of
those that asks for the same slug blocks the whole loop, so the task holding the
lock can never resume: a deadlock. With one sequential worker it stays hidden;
concurrent HTTP writers next to the worker make it reachable.
"""
from __future__ import annotations

import ast
import asyncio
import itertools
import threading
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from synthadoc.agents.ingest_agent import IngestAgent
from synthadoc.providers.base import CompletionResponse
from synthadoc.storage.log import AuditDB, LogWriter
from synthadoc.storage.search import HybridSearch
from synthadoc.storage.wiki import WikiPage, WikiStorage

_PKG = Path(__file__).resolve().parents[2] / "synthadoc"
_HANG_SECONDS = 20


def _awaits_under_page_lock() -> list[str]:
    found: list[str] = []
    for path in sorted(_PKG.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.With):
                continue
            if not any("page_lock" in ast.unparse(item.context_expr) for item in node.items):
                continue
            for stmt in node.body:
                for inner in ast.walk(stmt):
                    if isinstance(inner, (ast.Await, ast.AsyncFor, ast.AsyncWith)):
                        found.append(f"{path.relative_to(_PKG.parent)}:{inner.lineno}")
    return found


def test_no_await_inside_a_page_lock_block():
    """Static guard: fails when a new ``await`` lands inside ``with ...page_lock(...)``."""
    assert _awaits_under_page_lock() == []


def _run_with_watchdog(coro_factory) -> None:
    """Run the scenario on its own loop in a thread so a blocked loop fails the test
    instead of hanging the suite."""
    errors: list[BaseException] = []

    def target() -> None:
        try:
            asyncio.run(coro_factory())
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(_HANG_SECONDS)
    assert not thread.is_alive(), "event loop is blocked: a page lock was held across an await"
    if errors:
        raise errors[0]


def _provider(decision: str) -> AsyncMock:
    entity = CompletionResponse(
        text='{"entities":["Alan Turing"],"concepts":[],"tags":["history"]}',
        input_tokens=10, output_tokens=10)
    decide = CompletionResponse(text=decision, input_tokens=10, output_tokens=10)
    provider = AsyncMock()
    provider.complete.side_effect = itertools.cycle([entity, decide])
    return provider


async def _agent(tmp_wiki: Path, decision: str):
    from synthadoc.core.cache import CacheManager
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("alan-turing", WikiPage(
        title="Alan Turing", tags=["biography"], content="# Alan Turing\n\nMathematician.",
        status="active", confidence="high", sources=[], created="2026-01-01"))
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    agent = IngestAgent(
        provider=_provider(decision), store=store,
        search=HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db"),
        log_writer=LogWriter(tmp_wiki / "wiki" / "log.md"), audit_db=audit,
        cache=cache, max_pages=15)
    source = tmp_wiki / "raw_sources" / "enigma.md"
    source.write_text("Turing helped break the Enigma cipher at Bletchley Park.", encoding="utf-8")
    return store, audit, agent, source


def _add_tag(store: WikiStorage) -> None:
    store.update_page("alan-turing", lambda page: setattr(page, "tags", [*page.tags, "concurrent"]))


def test_a_concurrent_writer_is_not_blocked_while_an_update_ingest_awaits(tmp_wiki):
    """The update branch awaits the citation pass (an LLM call). Another writer must
    be able to take the page lock in that window, and its change must survive."""
    async def scenario() -> None:
        store, _audit, agent, source = await _agent(
            tmp_wiki, '{"action":"update","target":"alan-turing","new_slug":"",'
                      '"update_content":"## Enigma\\n\\nNew detail."}')
        inside, release = asyncio.Event(), asyncio.Event()
        original = agent._annotate_citations

        async def slow(*args, **kwargs):
            inside.set()
            await release.wait()
            return await original(*args, **kwargs)

        agent._annotate_citations = slow

        async def other_writer() -> None:
            await inside.wait()
            _add_tag(store)            # blocks the loop if the ingest holds the lock
            release.set()

        try:
            await asyncio.gather(agent.run(str(source)), other_writer())
            page = store.read_page("alan-turing")
            assert "concurrent" in page.tags, "the concurrent change was overwritten"
            assert "Enigma" in page.content
        finally:
            await agent._cache.close()

    _run_with_watchdog(scenario)


def test_a_concurrent_writer_is_not_blocked_while_a_flag_ingest_awaits_the_audit(tmp_wiki):
    async def scenario() -> None:
        store, audit, agent, source = await _agent(
            tmp_wiki, '{"action":"flag","target":"alan-turing","new_slug":"","update_content":""}')
        inside, release = asyncio.Event(), asyncio.Event()
        original = audit.set_page_state

        async def slow(*args, **kwargs):
            inside.set()
            await release.wait()
            return await original(*args, **kwargs)

        audit.set_page_state = slow

        async def other_writer() -> None:
            await inside.wait()
            _add_tag(store)
            release.set()

        try:
            await asyncio.gather(agent.run(str(source)), other_writer())
            page = store.read_page("alan-turing")
            assert page.status == "contradicted"
            assert "concurrent" in page.tags
        finally:
            await agent._cache.close()

    _run_with_watchdog(scenario)


def test_two_ingests_updating_the_same_page_both_land(tmp_wiki):
    """Two ingests that overlap on one page finish, and neither update is lost."""
    async def scenario() -> None:
        store, _audit, first, source_a = await _agent(
            tmp_wiki, '{"action":"update","target":"alan-turing","new_slug":"",'
                      '"update_content":"## Enigma\\n\\nFirst detail."}')
        source_b = tmp_wiki / "raw_sources" / "colossus.md"
        source_b.write_text("Colossus was built to read Lorenz traffic.", encoding="utf-8")
        second = IngestAgent(
            provider=_provider('{"action":"update","target":"alan-turing","new_slug":"",'
                               '"update_content":"## Colossus\\n\\nSecond detail."}'),
            store=store, search=first._search, log_writer=first._log,
            audit_db=first._audit, cache=first._cache, max_pages=15)
        try:
            await asyncio.gather(first.run(str(source_a)), second.run(str(source_b)))
            content = store.read_page("alan-turing").content
            assert "First detail" in content and "Second detail" in content
        finally:
            await first._cache.close()

    _run_with_watchdog(scenario)
