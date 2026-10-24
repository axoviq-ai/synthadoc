# Copyright (C) 2026 Paul Chen / axoviq.com
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
from synthadoc.storage.search import HybridSearch, SearchResult, page_search_text
from synthadoc.storage.wiki import WikiStorage

from benchmarks.retrieval.metrics import RECALL_KS, percentile, score_run
from benchmarks.retrieval.queries import Query

CANDIDATE_POOL = 20          # QueryAgent's _CANDIDATE_POOL_SIZE
WIKI_SIZES = (200, 500, 1000)   # plus the full corpus
# Must differ from queries.SAMPLE_SEED: sample() and shuffle() draw the same
# random stream, so with one seed the subsets would avoid the query pages.
SUBSET_SEED = 2026
RRF_K = 60                   # standard reciprocal-rank-fusion constant


@dataclass
class Config:
    name: str
    search_cfg: SearchConfig
    needs_embeddings: bool = False
    fusion: bool = False


_VECTOR = SearchConfig(vector=True, vector_top_candidates=CANDIDATE_POOL)
CONFIGS = {
    "bm25": Config("bm25", SearchConfig(vector=False)),
    "rerank": Config("rerank", _VECTOR, needs_embeddings=True),
    "fusion": Config("fusion", _VECTOR, needs_embeddings=True, fusion=True),
}


class FusionSearch:
    """Prototype of the proposed retrieval for issue #411 (benchmark only).

    Runs BM25 and an embedding search over the whole (scoped) wiki side by
    side and merges the two rankings with reciprocal rank fusion, so a page
    either method finds can surface. Embeddings are held in memory as one
    matrix. It reuses today's page embeddings (first 512 characters per page);
    section-level embeddings are not prototyped here.
    """

    def __init__(self, search: HybridSearch, slugs: list[str], matrix) -> None:
        self._search = search
        self._slugs = slugs
        self._matrix = matrix                      # rows L2-normalised
        self._row = {slug: i for i, slug in enumerate(slugs)}

    @classmethod
    async def create(cls, search: HybridSearch) -> "FusionSearch":
        import numpy as np
        stored = await search._vector_store.get_all()
        slugs = sorted(stored)
        matrix = np.array([stored[s] for s in slugs], dtype=np.float32)
        matrix /= np.linalg.norm(matrix, axis=1, keepdims=True).clip(min=1e-12)
        return cls(search, slugs, matrix)

    def _corpus(self):
        return self._search._corpus()

    def _vector_ranking(self, query: str, scope: list[str] | None, top_n: int) -> list[str]:
        import numpy as np
        q = np.array(self._search._embed_text(query), dtype=np.float32)
        sims = self._matrix @ (q / max(float(np.linalg.norm(q)), 1e-12))
        rows = [self._row[s] for s in scope if s in self._row] if scope is not None else range(len(self._slugs))
        ranked = sorted(rows, key=lambda i: sims[i], reverse=True)[:top_n]
        return [self._slugs[i] for i in ranked]

    async def hybrid_search(self, query_terms: list[str], top_n: int = 10,
                            scoped_slugs: list[str] | None = None) -> list[SearchResult]:
        keyword = [r.slug for r in self._search.bm25_search(query_terms, CANDIDATE_POOL, scoped_slugs)]
        semantic = self._vector_ranking(" ".join(query_terms), scoped_slugs, CANDIDATE_POOL)
        fused: dict[str, float] = defaultdict(float)
        for ranking in (keyword, semantic):
            for rank, slug in enumerate(ranking, 1):
                fused[slug] += 1 / (RRF_K + rank)
        best = sorted(fused, key=fused.get, reverse=True)[:top_n]
        return [SearchResult(slug=s, score=fused[s], title=s, snippet="") for s in best]


def has_fastembed() -> bool:
    try:
        import fastembed  # noqa: F401
    except ImportError:
        return False
    return True


async def make_search(wiki_dir: Path, config: Config,
                      log: Callable[[str], None] = print) -> HybridSearch | FusionSearch:
    """Build the search for *config*, embedding every page once (cached on disk)."""
    store = WikiStorage(wiki_dir)
    search = HybridSearch(store, wiki_dir.parent / "embeddings.db", search_cfg=config.search_cfg)
    if config.needs_embeddings:
        await search.init_vector()
        done = set(await search._vector_store.list_slugs())
        todo = [s for s in store.list_pages() if s not in done]
        if todo:
            log(f"  embedding {len(todo)} page(s)…")
        for slug in todo:
            if page := store.read_page(slug):
                await search.embed_page(slug, page_search_text(page))
    return await FusionSearch.create(search) if config.fusion else search


def nested_subsets(slugs: list[str], sizes: tuple[int, ...], seed: int = SUBSET_SEED) -> dict[int, list[str] | None]:
    """Seeded prefixes of one shuffle, so each larger wiki contains the smaller ones.

    The full corpus is always included, unscoped (None).
    """
    order = sorted(slugs)
    random.Random(seed).shuffle(order)
    subsets: dict[int, list[str] | None] = {n: order[:n] for n in sizes if n < len(order)}
    subsets[len(order)] = None
    return subsets


async def run_queries(search: HybridSearch | FusionSearch, queries: list[Query],
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
