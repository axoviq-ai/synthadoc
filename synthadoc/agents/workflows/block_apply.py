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
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BlockResult:
    index: int
    old_text: str
    new_text: str
    status: Literal["applied", "rejected"]
    rejection_reason: str | None = None


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

def apply_blocks(page_body: str, raw_blocks: list[dict]) -> ApplyResult:
    """Apply *raw_blocks* (list of ``{"old_text": …, "new_text": …}`` dicts)
    to *page_body* using the following pipeline:

    1. Normalise both sides; find each *old_text* as the **leftmost** substring
       in the *current* body; mark duplicates as ``no_match``.
    2. Sort matched blocks by their byte position.
    3. Scan adjacent pairs for overlapping spans → mark both ``conflict``.
    4. For each non-rejected block: heading-mutation guard, then
       sentence-loss guard.
    5. Apply remaining (non-rejected) blocks in document order by simple
       string replacement on a running copy of the body.
    6. Snapshot before step 5; restore on unexpected exception.
    """
    result = ApplyResult(accumulated_body=page_body)

    if not raw_blocks:
        return result

    norm_body = normalize_whitespace(page_body)

    # ------------------------------------------------------------------
    # Step 1 — find positions (leftmost match), mark duplicates no_match
    # ------------------------------------------------------------------
    # pending: list of (index, norm_old, norm_new, raw_old, raw_new, pos | None, rejected_reason | None)
    pending: list[dict] = []
    seen_positions: set[int] = set()

    for idx, blk in enumerate(raw_blocks):
        raw_old = blk.get("old_text", "")
        raw_new = blk.get("new_text", "")
        norm_old = normalize_whitespace(raw_old)
        norm_new = normalize_whitespace(raw_new)

        pos = norm_body.find(norm_old)

        if pos == -1 or pos in seen_positions:
            # Either genuinely absent OR already consumed by a prior block
            pending.append({
                "index": idx,
                "norm_old": norm_old,
                "norm_new": norm_new,
                "raw_old": raw_old,
                "raw_new": raw_new,
                "pos": None,
                "rejected_reason": "no_match",
            })
        else:
            seen_positions.add(pos)
            pending.append({
                "index": idx,
                "norm_old": norm_old,
                "norm_new": norm_new,
                "raw_old": raw_old,
                "raw_new": raw_new,
                "pos": pos,
                "rejected_reason": None,
            })

    # ------------------------------------------------------------------
    # Step 2 — sort matched blocks by position
    # ------------------------------------------------------------------
    matched = [p for p in pending if p["pos"] is not None]
    unmatched = [p for p in pending if p["pos"] is None]

    matched.sort(key=lambda p: p["pos"])  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Step 3 — detect overlapping spans → conflict
    # ------------------------------------------------------------------
    for i in range(len(matched)):
        if matched[i]["rejected_reason"] is not None:
            continue
        span_end_i = matched[i]["pos"] + len(matched[i]["norm_old"])  # type: ignore[operator]
        for j in range(i + 1, len(matched)):
            if matched[j]["rejected_reason"] is not None:
                continue
            pos_j = matched[j]["pos"]
            if pos_j < span_end_i:  # type: ignore[operator]
                # Overlap — mark both conflict
                matched[i]["rejected_reason"] = "conflict"
                matched[j]["rejected_reason"] = "conflict"
                # Update span_end_i to include j for further checks
                span_end_i = max(
                    span_end_i,
                    pos_j + len(matched[j]["norm_old"]),  # type: ignore[operator]
                )

    # ------------------------------------------------------------------
    # Step 4 — heading-mutation and sentence-loss guards
    # ------------------------------------------------------------------
    for blk in matched:
        if blk["rejected_reason"] is not None:
            continue
        if _check_heading_mutation(blk["norm_old"], blk["norm_new"]):
            blk["rejected_reason"] = "heading_mutation"
            continue
        if _check_sentence_loss(blk["norm_old"], blk["norm_new"]):
            blk["rejected_reason"] = "sentence_loss"

    # ------------------------------------------------------------------
    # Step 5 — apply non-rejected blocks in document order
    # ------------------------------------------------------------------
    snapshot = norm_body
    running_body = norm_body

    try:
        for blk in matched:
            if blk["rejected_reason"] is not None:
                continue
            running_body = running_body.replace(blk["norm_old"], blk["norm_new"], 1)
    except Exception:  # pragma: no cover — safety net
        running_body = snapshot

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
    result.accumulated_body = running_body
    result.applied_count = len(applied)
    result.rejected_count = len(rejected)
    return result
