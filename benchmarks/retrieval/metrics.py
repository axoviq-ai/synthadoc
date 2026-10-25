# Copyright (C) 2026 Peter W. / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ranking metrics with binary relevance."""
from __future__ import annotations

import math
from statistics import mean

RECALL_KS = (5, 10, 20)
RANK_DEPTH = 10              # depth for MRR and nDCG


def recall_at(ranked: list[str], relevant: list[str], k: int) -> float:
    """Share of *relevant* found in the top *k* of *ranked*."""
    return len(set(ranked[:k]) & set(relevant)) / len(relevant) if relevant else 0.0


def reciprocal_rank(ranked: list[str], relevant: list[str], depth: int = RANK_DEPTH) -> float:
    rel = set(relevant)
    return next((1 / i for i, slug in enumerate(ranked[:depth], 1) if slug in rel), 0.0)


def ndcg(ranked: list[str], relevant: list[str], depth: int = RANK_DEPTH) -> float:
    rel = set(relevant)
    dcg = sum(1 / math.log2(i + 1) for i, slug in enumerate(ranked[:depth], 1) if slug in rel)
    ideal = sum(1 / math.log2(i + 1) for i in range(1, min(len(rel), depth) + 1))
    return dcg / ideal if ideal else 0.0


def score_run(rankings: list[tuple[list[str], list[str]]]) -> dict[str, float]:
    """Average metrics over (ranked, relevant) pairs, rounded for stable JSON."""
    if not rankings:
        return {}
    scores = {f"recall@{k}": mean(recall_at(r, g, k) for r, g in rankings) for k in RECALL_KS}
    scores[f"mrr@{RANK_DEPTH}"] = mean(reciprocal_rank(r, g) for r, g in rankings)
    scores[f"ndcg@{RANK_DEPTH}"] = mean(ndcg(r, g) for r, g in rankings)
    scores = {k: round(v, 4) for k, v in scores.items()}
    scores["queries"] = len(rankings)
    return scores


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile (0 for no values)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(pct / 100 * len(ordered)) - 1))]
