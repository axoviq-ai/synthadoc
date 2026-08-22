# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Live integration tests for the citation faithfulness audit.

These tests make real LLM API calls. They are skipped when ANTHROPIC_API_KEY
is not set in the environment. Each test creates a temporary wiki with
known-good and known-bad citations, runs the audit, and asserts on verdicts.

The tmp_path fixture guarantees cleanup even on assertion failure.
"""
from __future__ import annotations

import asyncio
import os
import pytest

SKIP_REASON = "ANTHROPIC_API_KEY not set — skipping live faithfulness tests"

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason=SKIP_REASON,
)


@pytest.fixture
def faith_wiki(tmp_path):
    """Create a minimal wiki with known ground-truth citations."""
    extracted = tmp_path / ".synthadoc" / "extracted"
    extracted.mkdir(parents=True)
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()

    # Source 1: accurate historical facts
    (extracted / "good-source.txt").write_text(
        "Line 1: The transistor was first demonstrated at Bell Labs on December 23, 1947.\n"
        "Line 2: Walter Brattain and John Bardeen were the inventors.\n"
        "Line 3: The demonstration used a point-contact germanium device.\n",
        encoding="utf-8",
    )

    # Source 2: says commercialisation was slow — contradicts "immediate success"
    (extracted / "bad-source.txt").write_text(
        "Line 1: The transistor took many years to achieve commercial viability.\n"
        "Line 2: Initial reception from Bell Labs management was lukewarm.\n"
        "Line 3: Commercialization did not begin until the early 1950s.\n",
        encoding="utf-8",
    )

    # Page 1: all citations faithful
    (wiki_dir / "clean-page.md").write_text(
        "---\nstatus: active\nsources:\n  - file: good-source.txt\n  hash: ''\n  size: 0\n  ingested: ''\n---\n\n"
        "The transistor was first demonstrated at Bell Labs in December 1947."
        "^[good-source.txt:1-3]\n",
        encoding="utf-8",
    )

    # Page 2: one faithful, one hallucination
    (wiki_dir / "dirty-page.md").write_text(
        "---\nstatus: active\nsources:\n"
        "  - file: good-source.txt\n    hash: ''\n    size: 0\n    ingested: ''\n"
        "  - file: bad-source.txt\n    hash: ''\n    size: 0\n    ingested: ''\n---\n\n"
        "The transistor was invented at Bell Labs by Brattain and Bardeen."
        "^[good-source.txt:1-3]\n\n"
        "The transistor achieved immediate commercial success after its debut."
        "^[bad-source.txt:1-3]\n",
        encoding="utf-8",
    )

    yield tmp_path
    # tmp_path cleanup is automatic


def _make_store_and_provider(faith_wiki):
    from synthadoc.storage.wiki import WikiStorage
    from synthadoc.providers import make_provider
    from synthadoc.config import load_config

    store = WikiStorage(faith_wiki / "wiki")
    # Use a minimal config pointing to the real API
    cfg = load_config()
    provider = make_provider("query", cfg)
    return store, provider


def test_faithfulness_clean_page(faith_wiki):
    """All citations on clean-page should be 'supported'."""
    from synthadoc.agents.citation_faithfulness import run_faithfulness_audit
    store, provider = _make_store_and_provider(faith_wiki)
    results = asyncio.run(
        run_faithfulness_audit(faith_wiki, store, provider, page_slug_filter="clean-page")
    )
    assert len(results) > 0
    assert all(r.verdict == "supported" for r in results if r.slug == "clean-page"), \
        f"Expected all supported, got: {[(r.citation_marker, r.verdict) for r in results]}"


def test_faithfulness_dirty_page(faith_wiki):
    """dirty-page: one supported, one hallucination (source contradicts claim)."""
    from synthadoc.agents.citation_faithfulness import run_faithfulness_audit
    store, provider = _make_store_and_provider(faith_wiki)
    results = asyncio.run(
        run_faithfulness_audit(faith_wiki, store, provider, page_slug_filter="dirty-page")
    )
    verdicts = {r.citation_marker: r.verdict for r in results}
    assert verdicts.get("^[good-source.txt:1-3]") == "supported", \
        f"Expected supported, got: {verdicts}"
    assert verdicts.get("^[bad-source.txt:1-3]") in ("hallucination", "drift"), \
        f"Expected hallucination or drift, got: {verdicts}"


def test_faithfulness_full_audit(faith_wiki):
    """Full audit across both pages returns results for both slugs."""
    from synthadoc.agents.citation_faithfulness import run_faithfulness_audit
    store, provider = _make_store_and_provider(faith_wiki)
    results = asyncio.run(
        run_faithfulness_audit(faith_wiki, store, provider, page_slug_filter=None)
    )
    slugs = {r.slug for r in results}
    assert "clean-page" in slugs, f"Expected clean-page in results, got: {slugs}"
    assert "dirty-page" in slugs, f"Expected dirty-page in results, got: {slugs}"
