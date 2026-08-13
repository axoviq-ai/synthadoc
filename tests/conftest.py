# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import asyncio
import platform
import sqlite3
import sys
import pytest
from pathlib import Path


def pytest_collection_modifyitems(config, items):
    """Auto-deselect tests whose platform marker does not match the current OS."""
    _sys = sys.platform  # "win32", "linux", "darwin"
    remaining, deselected = [], []
    for item in items:
        skip = (
            (item.get_closest_marker("windows") and _sys != "win32")
            or (item.get_closest_marker("linux") and _sys != "linux")
            or (item.get_closest_marker("macos") and _sys != "darwin")
            or (item.get_closest_marker("posix") and _sys == "win32")
        )
        (deselected if skip else remaining).append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = remaining

# Detect whether the MCP package is properly installed.  Forks whose
# pyproject.toml pre-dates the mcp dependency may have no mcp package, or an
# old one that lacks mcp.server.fastmcp.  We detect this once at import time
# so the autouse fixture below is zero-cost when mcp is present.
try:
    from mcp.server.fastmcp import FastMCP as _FastMCP  # noqa: F401
    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False

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


@pytest.fixture(autouse=True)
def _disable_mcp_when_unavailable(monkeypatch):
    """Force enable_mcp=False in create_app when mcp.server.fastmcp is absent.

    Non-MCP tests (HTTP API, routing, SSE, …) don't exercise the MCP mount
    and must not fail just because the mcp package is missing or stale.
    MCP-specific tests guard themselves with pytest.importorskip.
    """
    if _MCP_AVAILABLE:
        return
    import synthadoc.integration.http_server as _hs
    _orig = _hs.create_app

    def _patched(wiki_root, *, enable_mcp=True, **kwargs):
        return _orig(wiki_root, enable_mcp=False, **kwargs)

    monkeypatch.setattr(_hs, "create_app", _patched)


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
    # audit.db is included: tests that call _fetch_live_wiki_data and expect ""
    # still pass because the function returns "" for an empty (data-less) DB, the
    # same result as for a missing file.
    for _db in ("jobs.db", "cache.db", "audit.db"):
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
