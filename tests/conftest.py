# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from pathlib import Path


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
    return tmp_path


@pytest.fixture
async def cache(tmp_wiki: Path):
    """CacheManager bound to tmp_wiki, auto-closed after each test."""
    from synthadoc.core.cache import CacheManager
    c = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await c.init()
    yield c
    await c.close()
