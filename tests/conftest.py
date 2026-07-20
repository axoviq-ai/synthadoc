# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import asyncio
import platform
import sqlite3
import pytest
from pathlib import Path

# ProactorEventLoop (Windows IOCP) deadlocks with aiosqlite's worker thread
# under load — observed in test_cache_read_latency_p99 and concurrent-reader
# tests.  Force SelectorEventLoop for all async tests on Windows.
# WindowsSelectorEventLoopPolicy is deprecated in Python 3.14+ (removal in
# 3.16); suppress the DeprecationWarning so test output stays clean.
if platform.system() == "Windows":
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture
def tmp_wiki(tmp_path: Path) -> Path:
    """Minimal wiki root with all required subdirectories."""
    (tmp_path / "wiki").mkdir()
    (tmp_path / "raw_sources").mkdir()
    (tmp_path / "hooks").mkdir()
    (tmp_path / "skills").mkdir()
    sd = tmp_path / ".synthadoc"
    sd.mkdir()
    (sd / "logs").mkdir()
    # Pre-create DB files synchronously so they exist before the asyncio event loop
    # starts.  On Windows CI, sqlite3.connect() on a brand-new file triggers an AV
    # scan; creating them here (outside the event loop) prevents that scan from
    # blocking aiosqlite threads during app startup and timing out long test suites.
    # audit.db is intentionally excluded — some tests assert on its absence.
    for _db in ("jobs.db", "cache.db"):
        with sqlite3.connect(sd / _db):
            pass
    return tmp_path


@pytest.fixture
async def cache(tmp_wiki: Path):
    """CacheManager bound to tmp_wiki, auto-closed after each test."""
    from synthadoc.core.cache import CacheManager
    c = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await c.init()
    yield c
    await c.close()
