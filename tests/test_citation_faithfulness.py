# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

from synthadoc.agents.citation_faithfulness import (
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
