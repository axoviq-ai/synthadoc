# Copyright (C) 2026 Peter W. / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run the retrieval benchmark: no LLM, deterministic, offline once cached.

Each configuration is a real ``HybridSearch`` over the cached wiki pages,
queried the way ``QueryAgent._run_search`` queries it (lowercased, split,
top 20 candidates), minus the LLM decomposition step. Smaller wiki sizes are
nested seeded subsets searched through ``scoped_slugs``, so BM25 statistics are
those of a wiki of that size.
"""
from __future__ import annotations

import random
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from synthadoc.config import SearchConfig
from synthadoc.storage.search import HybridSearch
from synthadoc.storage.wiki import WikiStorage

from benchmarks.retrieval.metrics import RECALL_KS, percentile, score_run
from benchmarks.retrieval.queries import Query

CANDIDATE_POOL = 20          # QueryAgent's _CANDIDATE_POOL_SIZE
WIKI_SIZES = (200, 500, 1000)   # plus the full corpus
# Must differ from queries.SAMPLE_SEED: sample() and shuffle() draw the same
# random stream, so with one seed the subsets would avoid the query pages.
SUBSET_SEED = 2026


@dataclass
class Config:
    name: str
    search_cfg: SearchConfig


CONFIGS = {
    "bm25": Config("bm25", SearchConfig(vector=False)),
    # Production semantic search (what vector = "auto" or true runs): BM25 fused with
    # page embeddings + keyword pin; CJK pages and queries stay on BM25.
    "hybrid": Config("hybrid", SearchConfig(vector=True, vector_top_candidates=CANDIDATE_POOL)),
}


def has_fastembed() -> bool:
    try:
        import fastembed  # noqa: F401
    except ImportError:
        return False
    return True


async def make_search(wiki_dir: Path, config: Config, log: Callable[[str], None] = print) -> HybridSearch:
    """Build the search for *config*; with embeddings, sync them first (cached
    in the corpus's embeddings.db, so only the first run embeds)."""
    search = HybridSearch(WikiStorage(wiki_dir), wiki_dir.parent / "embeddings.db",
                          search_cfg=config.search_cfg)
    if search.vectors_requested():
        await search.init_vector()
        start = time.perf_counter()
        embedded = await search.sync_embeddings()
        if embedded:
            log(f"  embedded {embedded} page(s) in {time.perf_counter() - start:.0f}s")
    return search


def nested_subsets(slugs: list[str], sizes: tuple[int, ...], seed: int = SUBSET_SEED) -> dict[int, list[str] | None]:
    """Seeded prefixes of one shuffle, so each larger wiki contains the smaller ones.

    The full corpus is always included, unscoped (None).
    """
    order = sorted(slugs)
    random.Random(seed).shuffle(order)
    subsets: dict[int, list[str] | None] = {n: order[:n] for n in sizes if n < len(order)}
    subsets[len(order)] = None
    return subsets


async def run_queries(search: HybridSearch, queries: list[Query],
                      scope: list[str] | None) -> tuple[dict[str, dict], dict[str, float]]:
    """Score *queries* (grouped by type, plus "all") and time each search."""
    rankings: dict[str, list] = defaultdict(list)
    latencies: list[float] = []
    for q in queries:
        start = time.perf_counter()
        results = await search.hybrid_search(q.text.lower().split(), top_n=CANDIDATE_POOL,
                                             scoped_slugs=scope)
        latencies.append((time.perf_counter() - start) * 1000)
        pair = ([r.slug for r in results], q.relevant)
        rankings[q.type].append(pair)
        rankings["all"].append(pair)
    metrics = {kind: score_run(pairs) for kind, pairs in sorted(rankings.items())}
    latency = {"p50_ms": round(percentile(latencies, 50), 1), "p95_ms": round(percentile(latencies, 95), 1)}
    return metrics, latency


async def evaluate_corpus(wiki_dir: Path, queries: list[Query], configs: list[str],
                          sizes: tuple[int, ...] | None, log: Callable[[str], None] = print) -> dict:
    """Results as {config: {size: {"metrics": {type: {...}}, "latency": {...}}}}."""
    all_slugs = WikiStorage(wiki_dir).list_pages()
    subsets = nested_subsets(all_slugs, sizes or ())
    results: dict = {}
    for name in configs:
        search = await make_search(wiki_dir, CONFIGS[name], log)
        search._corpus()     # build the BM25 corpus outside the timed searches
        results[name] = {}
        for size, scope in subsets.items():
            in_scope = set(scope) if scope is not None else None
            sized = [q for q in queries if in_scope is None or set(q.relevant) <= in_scope]
            log(f"  {name:<7} {size:>5} pages  {len(sized):>5} queries")
            metrics, latency = await run_queries(search, sized, scope)
            results[name][str(size)] = {"metrics": metrics, "latency": latency}
    return results


def format_table(corpus: str, results: dict) -> str:
    """Markdown table: one row per config × size × query type."""
    head = ["config", "pages", "type", "queries", *(f"R@{k}" for k in RECALL_KS), "MRR@10", "nDCG@10", "p95 ms"]
    lines = [f"### {corpus}", "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for name, by_size in results.items():
        for size, run in by_size.items():
            for kind, m in run["metrics"].items():
                row = [name, size, kind, str(m["queries"]),
                       *(f"{m[f'recall@{k}']:.3f}" for k in RECALL_KS),
                       f"{m['mrr@10']:.3f}", f"{m['ndcg@10']:.3f}", str(run["latency"]["p95_ms"])]
                lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)
