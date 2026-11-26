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


# Lock helpers that must never be held across an await. A module that adds a lock of
# the same kind (for example a cross-process secret-store lock) registers its name here.
_GUARDED_LOCKS = ("page_lock",)


def awaits_under_locks(lock_names, paths) -> list[str]:
    """``path:line`` of every ``await`` / ``async for`` / ``async with`` inside a
    ``with <...lock_name...>`` block in the given files."""
    found: list[str] = []
    for path in paths:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.With):
                continue
            if not any(name in ast.unparse(item.context_expr)
                       for item in node.items for name in lock_names):
                continue
            for stmt in node.body:
                for inner in ast.walk(stmt):
                    if isinstance(inner, (ast.Await, ast.AsyncFor, ast.AsyncWith)):
                        found.append(f"{Path(path).name}:{inner.lineno}")
    return found


def test_no_await_inside_a_guarded_lock_block():
    """Static guard: fails when a new ``await`` lands inside ``with ...page_lock(...)``."""
    assert awaits_under_locks(_GUARDED_LOCKS, sorted(_PKG.rglob("*.py"))) == []


def test_the_guard_flags_an_await_under_a_lock(tmp_path):
    """The scanner itself works, for any lock name it is given."""
    bad = tmp_path / "bad.py"
    source = [
        'async def f(store, other):',
        "    with store.page_lock('a'):",
        '        await other()',
        "    with store.secret_lock('b'):",
        '        await other()',
        "    with store.page_lock('c'):",
        '        other()',
    ]
    bad.write_text(chr(10).join(source), encoding="utf-8")
    assert awaits_under_locks(("page_lock",), [bad]) == ["bad.py:3"]
    assert awaits_under_locks(("page_lock", "secret_lock"), [bad]) == ["bad.py:3", "bad.py:5"]


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


def _provider(decision: str, cited: str | None = None) -> AsyncMock:
    """Answer each pass with its own kind of response. ``cited`` is what the citation
    pass returns (the annotated section); without it that pass gets the decision JSON,
    which ingest rejects and falls back to the unannotated section."""
    entity = CompletionResponse(
        text='{"entities":["Alan Turing"],"concepts":[],"tags":["history"]}',
        input_tokens=10, output_tokens=10)

    async def complete(*, messages, **_kwargs):
        prompt = messages[0].content
        if "citation annotator" in prompt and cited is not None:
            return CompletionResponse(text=cited, input_tokens=10, output_tokens=10)
        if "Decide how to handle" in prompt:
            return CompletionResponse(text=decision, input_tokens=10, output_tokens=10)
        return entity

    provider = AsyncMock()
    provider.complete.side_effect = complete
    return provider


async def _agent(tmp_wiki: Path, decision: str, cited: str | None = None,
                 status: str = "active"):
    from synthadoc.core.cache import CacheManager
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("alan-turing", WikiPage(
        title="Alan Turing", tags=["biography"], content="# Alan Turing\n\nMathematician.",
        status=status, confidence="high", sources=[], created="2026-01-01"))
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    agent = IngestAgent(
        provider=_provider(decision, cited), store=store,
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
                      '"update_content":"## Enigma\\n\\nNew detail."}',
            cited="## Enigma\n\nNew detail. ^[enigma.md:1-1]")
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
            assert "^[enigma.md:1-1]" in page.content, "the annotated section was not merged"
            assert "^[enigma.md:1-1]" in page.content, "the annotated section was not merged"
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


def test_an_update_that_never_settles_fails_the_job(tmp_wiki):
    """Intended: if the page's state keeps flipping while the section is annotated,
    ingest stops after three attempts and raises, so the job fails and can be retried."""
    async def scenario() -> None:
        store, _audit, agent, source = await _agent(
            tmp_wiki, '{"action":"update","target":"alan-turing","new_slug":"",'
                      '"update_content":"## Enigma\\n\\nNew detail."}',
            status="contradicted")
        original = agent._annotate_citations

        async def flip(*args, **kwargs):
            def toggle(page) -> None:
                page.status = "active" if page.status == "contradicted" else "contradicted"
            store.update_page("alan-turing", toggle)   # changes the rebuild decision
            return await original(*args, **kwargs)

        agent._annotate_citations = flip
        try:
            with pytest.raises(RuntimeError, match="kept changing state"):
                await agent.run(str(source), force=True)
        finally:
            await agent._cache.close()

    _run_with_watchdog(scenario)
