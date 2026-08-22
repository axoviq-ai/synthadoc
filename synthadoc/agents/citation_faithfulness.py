# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Citation faithfulness audit agent.

Verifies whether each claim's text is supported by the cited source lines.
Unlike structural citation lint (which validates reference integrity),
this agent checks semantic faithfulness via LLM evaluation.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from synthadoc.agents.citations import CITATION_RE
from synthadoc.providers.base import LLMProvider, Message

if TYPE_CHECKING:
    from synthadoc.storage.wiki import WikiPage, WikiStorage

# Maximum characters of claim text to extract backward from a citation marker.
_CLAIM_MAX_CHARS = 400

# Sentence boundary: one of .?! followed by whitespace, or double newline.
_SENTENCE_END_RE = re.compile(r'[.?!]\s|\n\n')


@dataclass
class CitationToCheck:
    """One citation extracted from a page body, ready for LLM evaluation."""
    citation_marker: str   # e.g. "^[bell-labs.txt:23-25]"
    claim_text: str        # text preceding the marker (≤400 chars, trimmed to sentence boundary)
    source_lines: str      # content of lines L1–L2 from the sidecar .txt file
    source_file: str       # e.g. "bell-labs.txt"
    line_start: int
    line_end: int


@dataclass
class FaithfulnessResult:
    """LLM verdict for one citation."""
    slug: str
    citation_marker: str
    verdict: str           # "supported" | "drift" | "hallucination" | "skipped"
    reason: str


def _resolve_sidecar(filename: str, extracted_dir: Path) -> Path | None:
    """Two-step sidecar resolution identical to LintAgent Check 5.

    1. exact filename match
    2. stem + '.txt' fallback
    """
    exact = extracted_dir / filename
    if exact.exists():
        return exact
    stem_txt = extracted_dir / (Path(filename).stem + ".txt")
    if stem_txt.exists():
        return stem_txt
    return None


def _extract_claim_text(body: str, marker_start: int, prev_end: int) -> str:
    """Extract claim text preceding a citation marker.

    Scans backward from marker_start (bounded by prev_end, the end position
    of the previous marker or 0). Returns at most _CLAIM_MAX_CHARS characters,
    trimmed to the nearest sentence boundary (last sentence only).
    """
    window_start = max(prev_end, marker_start - _CLAIM_MAX_CHARS)
    window = body[window_start:marker_start]

    # Find the last sentence boundary in the window
    last_match = None
    for m in _SENTENCE_END_RE.finditer(window):
        last_match = m

    if last_match is not None:
        return window[last_match.end():].strip()
    return window.strip()


def extract_citations_for_check(
    slug: str,
    page: "WikiPage",
    extracted_dir: Path,
) -> tuple[list[CitationToCheck], list[FaithfulnessResult]]:
    """Parse every ^[file:L1-L2] in the page body.

    Returns:
        checks  — citations ready for LLM evaluation
        skipped — citations emitted immediately (missing sidecar)
    """
    body = page.content or ""
    checks: list[CitationToCheck] = []
    skipped: list[FaithfulnessResult] = []
    prev_marker_end = 0

    for m in CITATION_RE.finditer(body):
        filename = m.group(1)
        line_start = int(m.group(2))
        line_end = int(m.group(3))
        marker = m.group(0)
        marker_start = m.start()
        marker_end = m.end()

        # Resolve sidecar
        sidecar = _resolve_sidecar(filename, extracted_dir)
        if sidecar is None:
            skipped.append(FaithfulnessResult(
                slug=slug,
                citation_marker=marker,
                verdict="skipped",
                reason="source unavailable",
            ))
            prev_marker_end = marker_end
            continue

        # Read source lines (1-indexed)
        lines = sidecar.read_text(encoding="utf-8").splitlines()
        source_lines = "\n".join(lines[line_start - 1: line_end])

        # Extract claim text
        claim_text = _extract_claim_text(body, marker_start, prev_marker_end)

        checks.append(CitationToCheck(
            citation_marker=marker,
            claim_text=claim_text,
            source_lines=source_lines,
            source_file=filename,
            line_start=line_start,
            line_end=line_end,
        ))
        prev_marker_end = marker_end

    return checks, skipped
