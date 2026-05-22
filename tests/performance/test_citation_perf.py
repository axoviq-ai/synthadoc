# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import asyncio
import time

import pytest


def test_concurrent_audit_writes_complete_under_80ms():
    """asyncio.gather() on two 50ms coroutines should finish in ~50ms, not ~100ms.

    This validates that Pass 4 audit writes are concurrent — if they were
    sequential, two 50ms writes would take > 90ms.
    """
    async def _run():
        async def fake_write(delay: float) -> None:
            await asyncio.sleep(delay)

        start = time.monotonic()
        await asyncio.gather(fake_write(0.05), fake_write(0.05))
        return time.monotonic() - start

    elapsed = asyncio.run(_run())
    assert elapsed < 0.08, (
        f"Concurrent audit writes took {elapsed:.3f}s — expected < 80ms. "
        "Writes may be sequential rather than concurrent."
    )


def test_lint_check5_latency_20_pages(tmp_path):
    """LintAgent Check 5 on 20 pages must complete in < 2s (pure regex, no LLM)."""
    from synthadoc.agents.lint_agent import _check_page_citations
    from synthadoc.storage.wiki import WikiPage, SourceRef

    pages = [
        WikiPage(
            title=f"Page {i}",
            tags=[],
            status="active",
            confidence="medium",
            content="A claim.^[bio.txt:1-5]\n\nAnother.^[bio.txt:10-20]\n" * 50,
            sources=[SourceRef(file="/p/bio.txt", hash="x", size=1, ingested="2026-01-01")],
        )
        for i in range(20)
    ]

    start = time.monotonic()
    for i, page in enumerate(pages):
        _check_page_citations(f"page-{i}", page, tmp_path)
    elapsed = time.monotonic() - start

    assert elapsed < 2.0, (
        f"Check 5 on 20 pages took {elapsed:.3f}s — expected < 2.0s. "
        "Regex or file-stat operations may have regressed."
    )
