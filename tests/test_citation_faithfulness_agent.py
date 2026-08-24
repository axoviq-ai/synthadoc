# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

from synthadoc.agents.citation_faithfulness_agent import (
    CitationToCheck,
    FaithfulnessResult,
    extract_citations_for_check,
)
from synthadoc.storage.wiki import WikiPage, SourceRef


def _make_page(content: str, sources: list[str] | None = None) -> WikiPage:
    srcs = [SourceRef(file=f, hash="", size=0, ingested="") for f in (sources or [])]
    return WikiPage(
        title="T", tags=[], content=content, status="active",
        confidence="high", sources=srcs,
    )


# ── Extraction tests ────────────────────────────────────────────────────────

def test_extract_file_source(tmp_path):
    """Local .txt sidecar → correct CitationToCheck returned."""
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    (extracted / "bell-labs.txt").write_text(
        "Line 1: Transistor demonstrated December 1947.\n"
        "Line 2: Brattain and Bardeen invented it.\n"
        "Line 3: At Bell Labs.\n",
        encoding="utf-8",
    )
    content = "The transistor was invented at Bell Labs.^[bell-labs.txt:1-3]\n"
    page = _make_page(content, sources=["bell-labs.txt"])
    checks, skipped = extract_citations_for_check("my-page", page, extracted)
    assert len(skipped) == 0
    assert len(checks) == 1
    c = checks[0]
    assert c.citation_marker == "^[bell-labs.txt:1-3]"
    assert c.source_file == "bell-labs.txt"
    assert c.line_start == 1
    assert c.line_end == 3
    assert "Bell Labs" in c.claim_text
    assert "Transistor demonstrated" in c.source_lines


def test_extract_url_source_stem_fallback(tmp_path):
    """Sidecar without extension resolved via stem + '.txt' fallback."""
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    # File is stored as "bell-labs.txt" but citation uses "bell-labs"
    (extracted / "bell-labs.txt").write_text("Line 1: Bell Labs invented transistor.\n", encoding="utf-8")
    content = "Transistor invented at Bell Labs.^[bell-labs:1-1]\n"
    page = _make_page(content, sources=["bell-labs"])
    checks, skipped = extract_citations_for_check("slug", page, extracted)
    assert len(skipped) == 0
    assert checks[0].source_lines.startswith("Line 1:")


def test_extract_exact_match_preferred_over_stem(tmp_path):
    """When both exact and stem+'.txt' exist, exact match is used."""
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    (extracted / "report").write_text("exact match content\n", encoding="utf-8")
    (extracted / "report.txt").write_text("stem fallback content\n", encoding="utf-8")
    content = "Claim.^[report:1-1]\n"
    page = _make_page(content, sources=["report"])
    checks, skipped = extract_citations_for_check("slug", page, extracted)
    assert "exact match" in checks[0].source_lines


def test_extract_skips_missing_sidecar(tmp_path):
    """Missing .txt sidecar → immediate skipped FaithfulnessResult."""
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    content = "Some claim.^[missing-source.txt:1-2]\n"
    page = _make_page(content, sources=["missing-source.txt"])
    checks, skipped = extract_citations_for_check("slug", page, extracted)
    assert len(checks) == 0
    assert len(skipped) == 1
    assert skipped[0].verdict == "skipped"
    assert skipped[0].reason == "source unavailable"
    assert skipped[0].citation_marker == "^[missing-source.txt:1-2]"
    assert skipped[0].slug == "slug"


def test_extract_claim_sentence_boundary(tmp_path):
    """Claim text trimmed to nearest sentence boundary."""
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    (extracted / "src.txt").write_text("Line 1: content\n", encoding="utf-8")
    # Two sentences before the marker; should take the last sentence only
    content = "First sentence is here. The transistor was demonstrated at Bell Labs.^[src.txt:1-1]\n"
    page = _make_page(content, sources=["src.txt"])
    checks, _ = extract_citations_for_check("slug", page, extracted)
    claim = checks[0].claim_text
    # Should start at the sentence boundary (after ". ")
    assert claim.startswith("The transistor")
    assert "First sentence" not in claim


def test_extract_claim_no_boundary_within_400(tmp_path):
    """Falls back to full 400-char window when no sentence boundary found."""
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    (extracted / "src.txt").write_text("Line 1: data\n", encoding="utf-8")
    # 500 chars without any sentence boundary
    long_claim = "x" * 500
    content = f"{long_claim}^[src.txt:1-1]\n"
    page = _make_page(content, sources=["src.txt"])
    checks, _ = extract_citations_for_check("slug", page, extracted)
    assert len(checks[0].claim_text) == 400


def test_extract_multiple_markers_same_sentence(tmp_path):
    """Adjacent markers get distinct, non-overlapping claim windows."""
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    (extracted / "a.txt").write_text("Line 1: A content\n", encoding="utf-8")
    (extracted / "b.txt").write_text("Line 1: B content\n", encoding="utf-8")
    content = "First claim here.^[a.txt:1-1] Second claim here.^[b.txt:1-1]\n"
    page = _make_page(content, sources=["a.txt", "b.txt"])
    checks, _ = extract_citations_for_check("slug", page, extracted)
    assert len(checks) == 2
    # Each claim belongs to its respective marker
    assert checks[0].source_file == "a.txt"
    assert checks[1].source_file == "b.txt"
    # Windows must not overlap
    assert checks[0].claim_text != checks[1].claim_text
    assert "Second claim" not in checks[0].claim_text
    assert "First claim" not in checks[1].claim_text


# ── LLM evaluation tests ─────────────────────────────────────────────────────

import asyncio
import json as _json

from synthadoc.agents.citation_faithfulness_agent import (
    FaithfulnessAuditAgent,
    check_page_faithfulness,
    estimate_faithfulness_tokens,
)


def _make_check(marker="^[src.txt:1-2]", claim="claim", source="source", src_file="src.txt"):
    return CitationToCheck(
        citation_marker=marker,
        claim_text=claim,
        source_lines=source,
        source_file=src_file,
        line_start=1,
        line_end=2,
    )


def _mock_provider(json_response: str):
    from synthadoc.providers.base import CompletionResponse
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=CompletionResponse(
        text=json_response, input_tokens=100, output_tokens=50,
    ))
    return provider


def test_check_page_all_supported():
    checks = [_make_check("^[a.txt:1-1]"), _make_check("^[b.txt:1-1]")]
    resp = _json.dumps({"results": [
        {"index": 1, "verdict": "supported", "reason": "clear support"},
        {"index": 2, "verdict": "supported", "reason": "matches source"},
    ]})
    provider = _mock_provider(resp)
    results = asyncio.run(check_page_faithfulness("slug", checks, provider))
    assert len(results) == 2
    assert all(r.verdict == "supported" for r in results)


def test_check_page_drift():
    checks = [_make_check("^[src.txt:1-2]")]
    resp = _json.dumps({"results": [
        {"index": 1, "verdict": "drift", "reason": "claim overstates scope"}
    ]})
    provider = _mock_provider(resp)
    results = asyncio.run(check_page_faithfulness("slug", checks, provider))
    assert results[0].verdict == "drift"
    assert results[0].reason == "claim overstates scope"


def test_check_page_hallucination():
    checks = [_make_check("^[src.txt:1-2]")]
    resp = _json.dumps({"results": [
        {"index": 1, "verdict": "hallucination", "reason": "source contradicts claim"}
    ]})
    provider = _mock_provider(resp)
    results = asyncio.run(check_page_faithfulness("slug", checks, provider))
    assert results[0].verdict == "hallucination"
    assert results[0].citation_marker == "^[src.txt:1-2]"


def test_check_page_malformed_json():
    """Garbage LLM response → all citations skipped with 'LLM parse error'."""
    checks = [_make_check("^[a.txt:1-1]"), _make_check("^[b.txt:1-1]")]
    provider = _mock_provider("this is not json at all")
    results = asyncio.run(check_page_faithfulness("slug", checks, provider))
    assert len(results) == 2
    assert all(r.verdict == "skipped" for r in results)
    assert all(r.reason == "LLM parse error" for r in results)


def test_check_page_missing_index():
    """LLM omits a citation index → that citation skipped."""
    checks = [_make_check("^[a.txt:1-1]"), _make_check("^[b.txt:1-1]")]
    # Only returns index 1, omits index 2
    resp = _json.dumps({"results": [
        {"index": 1, "verdict": "supported", "reason": "ok"}
    ]})
    provider = _mock_provider(resp)
    results = asyncio.run(check_page_faithfulness("slug", checks, provider))
    assert results[0].verdict == "supported"
    assert results[1].verdict == "skipped"
    assert results[1].reason == "LLM omitted citation"


def test_check_page_unknown_verdict():
    """Unknown verdict string from LLM → that citation skipped."""
    checks = [_make_check("^[a.txt:1-1]")]
    resp = _json.dumps({"results": [
        {"index": 1, "verdict": "uncertain", "reason": "not sure"}
    ]})
    provider = _mock_provider(resp)
    results = asyncio.run(check_page_faithfulness("slug", checks, provider))
    assert results[0].verdict == "skipped"


def test_estimate_tokens_formula():
    """200 per page + 150 per citation."""
    pages = {
        "page-a": [_make_check(), _make_check()],   # 200 + 2*150 = 500
        "page-b": [_make_check()],                   # 200 + 1*150 = 350
    }
    total = estimate_faithfulness_tokens(pages)
    assert total == 850


# ── run_faithfulness_audit tests ─────────────────────────────────────────────

def _make_wiki_storage(tmp_path, pages: dict[str, tuple[str, list[str]]]):
    """Helper: create wiki files and return WikiStorage.
    pages = {slug: (content, source_files)}
    """
    from synthadoc.storage.wiki import WikiStorage
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    for slug, (content, sources) in pages.items():
        src_refs = "\n".join(f"  - file: {s}" for s in sources)
        (wiki_dir / f"{slug}.md").write_text(
            f"---\nstatus: active\nsources:\n{src_refs}\n---\n\n{content}\n",
            encoding="utf-8",
        )
    return WikiStorage(wiki_dir)


def test_run_audit_filters_non_active(tmp_path):
    """Pages with status != 'active' are excluded."""
    extracted = tmp_path / ".synthadoc" / "extracted"
    extracted.mkdir(parents=True)
    (extracted / "src.txt").write_text("Line 1: content\n", encoding="utf-8")

    store = _make_wiki_storage(tmp_path, {
        "active-page":   ("Active page claim.^[src.txt:1-1]\n", ["src.txt"]),
    })
    # Manually write a non-active page
    wiki_dir = tmp_path / "wiki"
    (wiki_dir / "draft-page.md").write_text(
        "---\nstatus: draft\nsources:\n  - file: src.txt\n---\n\n"
        "Draft claim.^[src.txt:1-1]\n",
        encoding="utf-8",
    )

    provider = _mock_provider(_json.dumps({"results": [
        {"index": 1, "verdict": "supported", "reason": "ok"}
    ]}))
    agent = FaithfulnessAuditAgent(provider, tmp_path, store)
    results = asyncio.run(agent.run())
    slugs = {r.slug for r in results}
    assert "active-page" in slugs
    assert "draft-page" not in slugs


def test_run_audit_page_slug_filter(tmp_path):
    """page_slug argument limits audit to one page."""
    extracted = tmp_path / ".synthadoc" / "extracted"
    extracted.mkdir(parents=True)
    (extracted / "src.txt").write_text("Line 1: content\n", encoding="utf-8")

    store = _make_wiki_storage(tmp_path, {
        "page-a": ("Claim A.^[src.txt:1-1]\n", ["src.txt"]),
        "page-b": ("Claim B.^[src.txt:1-1]\n", ["src.txt"]),
    })
    provider = _mock_provider(_json.dumps({"results": [
        {"index": 1, "verdict": "supported", "reason": "ok"}
    ]}))
    agent = FaithfulnessAuditAgent(provider, tmp_path, store)
    results = asyncio.run(agent.run(page_slug="page-a"))
    slugs = {r.slug for r in results}
    assert "page-a" in slugs
    assert "page-b" not in slugs


def test_run_audit_skips_pages_with_no_citations(tmp_path):
    """Pages with no ^[...] markers → absent from results."""
    extracted = tmp_path / ".synthadoc" / "extracted"
    extracted.mkdir(parents=True)

    store = _make_wiki_storage(tmp_path, {
        "no-citations": ("This page has no citation markers at all.\n", []),
    })
    provider = _mock_provider(_json.dumps({"results": []}))
    agent = FaithfulnessAuditAgent(provider, tmp_path, store)
    results = asyncio.run(agent.run())
    assert len(results) == 0
    # Provider should NOT have been called (no LLM calls for pages without citations)
    provider.complete.assert_not_called()


def test_check_page_top_level_array_response():
    """LLM returns a top-level JSON array instead of object → all skipped."""
    checks = [
        CitationToCheck(
            citation_marker="^[src.txt:1-2]",
            claim_text="claim",
            source_lines="line 1\nline 2",
            source_file="src.txt",
            line_start=1,
            line_end=2,
        )
    ]
    provider = _mock_provider('[{"index": 1, "verdict": "supported", "reason": "ok"}]')
    results = asyncio.run(check_page_faithfulness("pg", checks, provider))
    assert len(results) == 1
    assert results[0].verdict == "skipped"
    assert "LLM parse error" in results[0].reason


def test_run_audit_nonexistent_slug_filter(tmp_path):
    """page_slug naming a missing slug returns empty list without calling provider."""
    extracted = tmp_path / ".synthadoc" / "extracted"
    extracted.mkdir(parents=True)
    store = _make_wiki_storage(tmp_path, {})
    provider = _mock_provider(_json.dumps({"results": []}))
    agent = FaithfulnessAuditAgent(provider, tmp_path, store)
    results = asyncio.run(agent.run(page_slug="no-such-page"))
    assert results == []
    provider.complete.assert_not_called()


# ── FaithfulnessAuditAgent class tests ──────────────────────────────────────

def test_faithfulness_audit_agent_is_base_agent():
    """FaithfulnessAuditAgent inherits from BaseAgent."""
    from synthadoc.agents._base import BaseAgent
    assert issubclass(FaithfulnessAuditAgent, BaseAgent)


def test_faithfulness_audit_agent_stores_dependencies(tmp_path):
    """Constructor binds provider, wiki_root, store, and cfg."""
    from unittest.mock import MagicMock
    from synthadoc.agents.citation_faithfulness_agent import FaithfulnessAuditAgent
    provider = MagicMock()
    store = MagicMock()
    cfg = MagicMock()
    agent = FaithfulnessAuditAgent(provider, tmp_path, store, cfg=cfg)
    assert agent._provider is provider
    assert agent._wiki_root == tmp_path
    assert agent._store is store
    assert agent._cfg is cfg


def test_faithfulness_audit_agent_cfg_defaults_to_none(tmp_path):
    """cfg is optional and defaults to None."""
    from unittest.mock import MagicMock
    provider = MagicMock()
    store = MagicMock()
    agent = FaithfulnessAuditAgent(provider, tmp_path, store)
    assert agent._cfg is None
