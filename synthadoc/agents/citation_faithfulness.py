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
from synthadoc.storage.wiki import LifecycleState

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


_VALID_VERDICTS = frozenset({"supported", "drift", "hallucination"})

_SYSTEM_PROMPT = """\
You are auditing citation faithfulness for a knowledge-base page.

For each numbered citation below, classify faithfulness as exactly one of:
  "supported"     — source lines clearly support the claim
  "drift"         — claim overstates, extrapolates from, or partially misrepresents the source
  "hallucination" — source lines do not support or directly contradict the claim

Respond with a JSON object only, no commentary or markdown fences:
{"results": [{"index": 1, "verdict": "supported", "reason": "one sentence"}, ...]}

Every citation must appear in results. Keep each reason to one sentence (≤120 chars).\
"""


def _build_user_message(slug: str, checks: list[CitationToCheck]) -> str:
    lines = [f"=== PAGE: {slug} ===", ""]
    for i, c in enumerate(checks, start=1):
        lines.append(f'{i}. Claim: "{c.claim_text}"')
        lines.append(f"   Source ({c.source_file}:{c.line_start}-{c.line_end}):")
        lines.append('   """')
        lines.append(f"   {c.source_lines}")
        lines.append('   """')
        lines.append("")
    return "\n".join(lines)


async def check_page_faithfulness(
    slug: str,
    checks: list[CitationToCheck],
    provider: LLMProvider,
) -> list[FaithfulnessResult]:
    """Send all citations for one page in a single LLM call.

    Returns one FaithfulnessResult per citation in the same order as checks.
    On JSON parse failure, returns all as skipped with reason='LLM parse error'.
    On missing index, emits skipped with reason='LLM omitted citation'.
    Unknown verdict strings are treated as skipped.
    """
    user_msg = _build_user_message(slug, checks)
    try:
        response = await provider.complete(
            messages=[Message(role="user", content=user_msg)],
            system=_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=2048,
        )
    except Exception as exc:
        reason = f"LLM error: {str(exc)[:80]}"
        return [
            FaithfulnessResult(
                slug=slug,
                citation_marker=c.citation_marker,
                verdict="skipped",
                reason=reason,
            )
            for c in checks
        ]

    try:
        parsed = json.loads(response.text)
        raw_results: list[dict] = parsed.get("results", [])
    except (json.JSONDecodeError, AttributeError, TypeError):
        return [
            FaithfulnessResult(
                slug=slug,
                citation_marker=c.citation_marker,
                verdict="skipped",
                reason="LLM parse error",
            )
            for c in checks
        ]

    # Index results by 1-based index
    by_index: dict[int, dict] = {r.get("index", -1): r for r in raw_results}

    results: list[FaithfulnessResult] = []
    for i, c in enumerate(checks, start=1):
        entry = by_index.get(i)
        if entry is None:
            results.append(FaithfulnessResult(
                slug=slug,
                citation_marker=c.citation_marker,
                verdict="skipped",
                reason="LLM omitted citation",
            ))
            continue
        verdict = entry.get("verdict", "")
        if verdict not in _VALID_VERDICTS:
            verdict = "skipped"
        reason = str(entry.get("reason", ""))[:150]
        results.append(FaithfulnessResult(
            slug=slug,
            citation_marker=c.citation_marker,
            verdict=verdict,
            reason=reason,
        ))
    return results


def collect_checks_for_pages(
    wiki_root: Path,
    store: "WikiStorage",
    page_slug: str | None = None,
) -> "dict[str, list[CitationToCheck]]":
    """Collect citation checks across active pages without any LLM calls.

    Used by the CLI and the HTTP dry-run endpoint to estimate cost before
    submitting a faithfulness audit job.  Returns a mapping of slug →
    list[CitationToCheck] for every active page that has at least one citation.

    Args:
        wiki_root: Root of the wiki (parent of the ``wiki/`` directory).
        store:     Open WikiStorage instance.
        page_slug: If given, restrict to that one page; otherwise all active pages.
    """
    extracted_dir = wiki_root / ".synthadoc" / "extracted"
    pages_with_checks: dict[str, list[CitationToCheck]] = {}

    slugs = [page_slug] if page_slug is not None else store.all_slugs()
    for slug in slugs:
        page = store.read_page(slug)
        if page is None or page.status != LifecycleState.ACTIVE:
            continue
        checks, _ = extract_citations_for_check(slug, page, extracted_dir)
        if checks:
            pages_with_checks[slug] = checks
    return pages_with_checks


def estimate_faithfulness_tokens(
    pages_with_checks: dict[str, list[CitationToCheck]],
) -> int:
    """Estimate total prompt tokens before any LLM calls are made.

    Formula: Σ_pages(200 + Σ_citations_in_page * 150)
    """
    total = 0
    for checks in pages_with_checks.values():
        total += 200 + len(checks) * 150
    return total


async def run_faithfulness_audit(
    wiki_root: Path,
    store: "WikiStorage",
    provider: LLMProvider,
    page_slug_filter: str | None = None,
) -> list[FaithfulnessResult]:
    """Top-level entry point for the faithfulness audit.

    1. Iterate active pages (or one slug if page_slug_filter is set).
    2. Extract citations; emit skipped immediately for missing sidecars.
    3. Call check_page_faithfulness per page (one LLM call per page).
    4. Return all FaithfulnessResult objects.

    Note: CostGuard is NOT called here — the CLI path calls it before
    invoking this function; the HTTP path uses a separate dry_run call.
    """
    extracted_dir = wiki_root / ".synthadoc" / "extracted"
    all_results: list[FaithfulnessResult] = []

    if page_slug_filter is not None:
        slugs_to_check = [page_slug_filter]
    else:
        slugs_to_check = store.all_slugs()

    for slug in slugs_to_check:
        page = store.read_page(slug)
        if page is None or page.status != LifecycleState.ACTIVE:
            continue

        checks, skipped = extract_citations_for_check(slug, page, extracted_dir)
        all_results.extend(skipped)

        if not checks:
            continue

        page_results = await check_page_faithfulness(slug, checks, provider)
        all_results.extend(page_results)

    return all_results
