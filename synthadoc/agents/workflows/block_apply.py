# Copyright (C) 2026 William Johnason / axoviq.com
"""
Block apply engine for scoped edit output.

Provides pure-logic helpers for applying a list of scoped edit blocks
(old_text / new_text pairs) to a page body with safety guards:
  - duplicate / no-match detection
  - overlap conflict detection
  - heading-mutation guard
  - sentence-loss guard (≥ 80 % retention required)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal


# ---------------------------------------------------------------------------
# normalize_whitespace
# ---------------------------------------------------------------------------

def normalize_whitespace(text: str) -> str:
    """Collapse runs of horizontal whitespace and normalise line endings.

    - ``\\r\\n`` and ``\\r`` → ``\\n``
    - Two or more spaces / tabs on the same line → single space
    """
    # Normalise line endings first
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse horizontal whitespace runs (spaces and tabs only, not newlines)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text


# ---------------------------------------------------------------------------
# _build_norm_to_raw_map
# ---------------------------------------------------------------------------

def _build_norm_to_raw_map(raw: str) -> list[int]:
    """Build a forward map from normalized-body positions to raw-body positions.

    Returns a list of length ``len(normalize_whitespace(raw)) + 1`` where
    ``result[i]`` is the index in *raw* that produced normalized character *i*.
    The sentinel entry ``result[len(norm)]`` equals ``len(raw)``.

    Used by :func:`apply_blocks` to recover the raw span corresponding to a
    matched position in the normalized body, so that the returned
    ``accumulated_body`` is never normalized.
    """
    mapping: list[int] = []
    i = 0
    n = len(raw)
    while i < n:
        c = raw[i]
        if c == '\r':
            # \r\n → single \n (consume both); bare \r → \n (consume one)
            mapping.append(i)
            if i + 1 < n and raw[i + 1] == '\n':
                i += 2
            else:
                i += 1
        elif c in ' \t':
            # Scan the full run of spaces/tabs; the run collapses to one space
            j = i
            while j < n and raw[j] in ' \t':
                j += 1
            mapping.append(i)  # the entire run maps to one normalized char
            i = j
        else:
            mapping.append(i)
            i += 1
    mapping.append(n)  # sentinel: maps len(norm) → len(raw)
    return mapping


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BlockResult:
    index: int
    old_text: str
    new_text: str
    status: Literal["applied", "rejected"]
    rejection_reason: Literal["no_match", "conflict", "heading_mutation", "sentence_loss"] | None = None


@dataclass
class ApplyResult:
    blocks: list[BlockResult] = field(default_factory=list)
    accumulated_body: str = ""
    applied_count: int = 0
    rejected_count: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_sentences(text: str) -> list[str]:
    """Return the non-empty sentence fragments from *text*.

    A sentence is any span that ends with ``.``, ``!``, or ``?``.
    We split on those punctuation characters (keeping the delimiter).
    """
    parts = re.split(r"(?<=[.!?])\s*", text)
    return [p.strip() for p in parts if p.strip()]


def _check_heading_mutation(old_text: str, new_text: str) -> bool:
    """Return True if a heading line present in *old_text* is absent / changed
    in *new_text* (i.e. the edit mutates a heading).
    """
    heading_re = re.compile(r"^#{1,6} .+", re.MULTILINE)
    old_headings = set(heading_re.findall(old_text))
    if not old_headings:
        return False
    new_headings = set(heading_re.findall(new_text))
    # Any heading from old that is not present verbatim in new_text is a mutation
    return bool(old_headings - new_headings)


def _check_sentence_loss(old_text: str, new_text: str, threshold: float = 0.8) -> bool:
    """Return True if *new_text* contains substantially fewer sentences than *old_text*.

    The guard fires when the sentence-count ratio (new / old) falls below
    *threshold*.  This prevents silent deletion of sentences while allowing
    legitimate single-sentence rewrites.

    Retention ratio = sentence_count(new_text) / sentence_count(old_text).
    """
    old_sentences = _extract_sentences(old_text)
    if not old_sentences:
        return False
    new_sentences = _extract_sentences(new_text)
    retention = len(new_sentences) / len(old_sentences)
    return retention < threshold


# ---------------------------------------------------------------------------
# apply_blocks
# ---------------------------------------------------------------------------

def apply_blocks(
    page_body: str,
    raw_blocks: list[dict],
    *,
    allow_heading_mutation: bool = False,
) -> ApplyResult:
    """Apply *raw_blocks* (list of ``{"old_text": …, "new_text": …}`` dicts)
    to *page_body* using the following pipeline:

    1. For each block, try an exact substring match in the raw body first; fall
       back to a normalized match (via :func:`normalize_whitespace`) and map the
       normalized position back to a raw span using
       :func:`_build_norm_to_raw_map`.  Empty or whitespace-only *old_text*
       values and blocks that find no match are marked ``no_match``.
    2. Sort matched blocks by their raw byte-start position.
    3. Scan adjacent pairs for overlapping raw spans → mark both ``conflict``.
    4. For each non-rejected block: heading-mutation guard (skipped when
       *allow_heading_mutation* is True), then sentence-loss guard.
    5. Apply remaining (non-rejected) blocks by splicing the **raw body** in
       *reverse position order* (rightmost first) so earlier offsets are not
       shifted.  ``normalize_whitespace`` is **never** applied to the returned
       ``accumulated_body`` — only matching uses normalization.

    *allow_heading_mutation* — set True for content-health fixes where heading
    removal/restructure is intentional (e.g. orphaned_heading, empty_section).
    Contradiction-resolver callers leave it False so the LLM cannot silently
    delete headings.
    """
    result = ApplyResult(accumulated_body=page_body)

    if not raw_blocks:
        return result

    norm_body = normalize_whitespace(page_body)
    norm_map: list[int] | None = None  # built lazily only if needed

    # ------------------------------------------------------------------
    # Step 1 — find positions (leftmost match), mark duplicates no_match
    # ------------------------------------------------------------------
    # pending: list of per-block dicts tracking match position and reason
    pending: list[dict] = []
    seen_raw_starts: set[int] = set()

    for idx, blk in enumerate(raw_blocks):
        raw_old = blk.get("old_text", "")
        raw_new = blk.get("new_text", "")

        # Guard: empty or whitespace-only old_text can never match meaningfully
        if not raw_old.strip():
            pending.append({
                "index": idx,
                "raw_old": raw_old,
                "raw_new": raw_new,
                "raw_start": None,
                "raw_end": None,
                "rejected_reason": "no_match",
            })
            continue

        # Try exact match in the raw body first (avoids any whitespace damage)
        raw_start = page_body.find(raw_old)
        if raw_start != -1:
            raw_end = raw_start + len(raw_old)
        else:
            # Fall back: try normalized match and map position back to raw span
            norm_old = normalize_whitespace(raw_old)
            norm_pos = norm_body.find(norm_old)
            if norm_pos != -1:
                if norm_map is None:
                    norm_map = _build_norm_to_raw_map(page_body)
                raw_start = norm_map[norm_pos]
                raw_end   = norm_map[norm_pos + len(norm_old)]
            else:
                raw_start = -1
                raw_end   = -1

        if raw_start == -1 or raw_start in seen_raw_starts:
            pending.append({
                "index": idx,
                "raw_old": raw_old,
                "raw_new": raw_new,
                "raw_start": None,
                "raw_end": None,
                "rejected_reason": "no_match",
            })
        else:
            seen_raw_starts.add(raw_start)
            pending.append({
                "index": idx,
                "raw_old": raw_old,
                "raw_new": raw_new,
                "raw_start": raw_start,
                "raw_end": raw_end,
                "rejected_reason": None,
            })

    # ------------------------------------------------------------------
    # Step 2 — sort matched blocks by raw position
    # ------------------------------------------------------------------
    matched = [p for p in pending if p["raw_start"] is not None]
    unmatched = [p for p in pending if p["raw_start"] is None]

    matched.sort(key=lambda p: p["raw_start"])  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Step 3 — detect overlapping raw spans → conflict
    # ------------------------------------------------------------------
    for i in range(len(matched)):
        if matched[i]["rejected_reason"] is not None:
            continue
        span_end_i = matched[i]["raw_end"]
        for j in range(i + 1, len(matched)):
            if matched[j]["rejected_reason"] is not None:
                continue
            pos_j = matched[j]["raw_start"]
            if pos_j < span_end_i:  # type: ignore[operator]
                # Overlap — mark both conflict
                matched[i]["rejected_reason"] = "conflict"
                matched[j]["rejected_reason"] = "conflict"
                span_end_i = max(span_end_i, matched[j]["raw_end"])

    # ------------------------------------------------------------------
    # Step 4 — heading-mutation and sentence-loss guards
    # ------------------------------------------------------------------
    for blk in matched:
        if blk["rejected_reason"] is not None:
            continue
        if not allow_heading_mutation and _check_heading_mutation(blk["raw_old"], blk["raw_new"]):
            blk["rejected_reason"] = "heading_mutation"
            continue
        if _check_sentence_loss(blk["raw_old"], blk["raw_new"]):
            blk["rejected_reason"] = "sentence_loss"

    # ------------------------------------------------------------------
    # Step 5 — apply non-rejected blocks by splicing the raw body in
    # reverse position order (rightmost first so earlier offsets stay stable)
    # ------------------------------------------------------------------
    body = page_body
    try:
        for blk in reversed(matched):
            if blk["rejected_reason"] is not None:
                continue
            body = body[: blk["raw_start"]] + blk["raw_new"] + body[blk["raw_end"] :]
    except Exception:  # pragma: no cover — safety net
        body = page_body

    # ------------------------------------------------------------------
    # Build BlockResult list (preserve original input order via index)
    # ------------------------------------------------------------------
    all_processed = {p["index"]: p for p in matched + unmatched}

    block_results: list[BlockResult] = []
    for idx in range(len(raw_blocks)):
        blk = all_processed[idx]
        if blk["rejected_reason"] is None:
            block_results.append(
                BlockResult(
                    index=idx,
                    old_text=blk["raw_old"],
                    new_text=blk["raw_new"],
                    status="applied",
                    rejection_reason=None,
                )
            )
        else:
            block_results.append(
                BlockResult(
                    index=idx,
                    old_text=blk["raw_old"],
                    new_text=blk["raw_new"],
                    status="rejected",
                    rejection_reason=blk["rejected_reason"],
                )
            )

    applied = [b for b in block_results if b.status == "applied"]
    rejected = [b for b in block_results if b.status == "rejected"]

    result.blocks = block_results
    result.accumulated_body = body
    result.applied_count = len(applied)
    result.rejected_count = len(rejected)
    return result


# ---------------------------------------------------------------------------
# describe_all_blocks_rejected
# ---------------------------------------------------------------------------

def describe_all_blocks_rejected(result: ApplyResult, blocks: list[dict]) -> str | None:
    """Return a "block N: reason" summary when *blocks* was non-empty but every
    block was rejected, or None otherwise.

    Shared by tool_propose_and_apply_blocks (contradiction_resolver's
    Strategy 1) and content_health_resolver's write_content_health_fix: both
    call apply_blocks and, when nothing could be safely applied, skip the
    full-page ScopedConfirmCard — which would otherwise show a confusing
    empty diff — in favor of telling the LLM to move on (to Strategy 2, or
    to dismissal) instead. An empty *blocks* list means nothing was proposed
    at all, a different case from "everything proposed was rejected", so it
    returns None too.
    """
    if not (result.applied_count == 0 and blocks):
        return None
    return "; ".join(
        f"block {i + 1}: {br.rejection_reason or 'no_match'}"
        for i, br in enumerate(result.blocks)
        if br.status == "rejected"
    ) or "no reasons available"
