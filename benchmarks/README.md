# Benchmarks

How Synthadoc measures retrieval quality and speed. Each entry says what it measures, where it lives, and how to run it. All of them run from a clone of the repository; none ship in the pip package, and none need an LLM API key.

```bash
git clone https://github.com/axoviq-ai/synthadoc.git && cd synthadoc
pip install -e ".[dev,vectors]"
```

## Retrieval quality — keyword vs. semantic search

**[`benchmarks/retrieval/`](retrieval/README.md)** — does search put the right page in front of the LLM? 1,985 pinned Wikipedia articles turned into wiki pages, 1,430 questions of three kinds (paraphrased, the page's own words, exact names), plus 300 human-written HotpotQA questions. Reports recall@5/10/20, MRR, nDCG and P95 latency, per question type and at wiki sizes of 200 to 1,985 pages.

```bash
python -m benchmarks.retrieval fetch                         # once, ~30 min: download and build the wikis
python -m benchmarks.retrieval evaluate --configs bm25,hybrid
```

Headline result on 1,985 pages: semantic search raises paraphrased questions found in the top 5 from 48% to 68%, with exact-name lookups at 98% (keyword search: 99%). Checked on corpora it was not tuned on: better on two English sets with human-written queries (SciFact, NFCorpus), and unchanged on Chinese, which is left to keyword search. Committed results: [`retrieval/data/baseline.json`](retrieval/data/baseline.json). This benchmark decides changes to search and to the semantic-search default.

## Search latency with and without routing

**[`tests/performance/test_routing_benchmark.py`](../tests/performance/test_routing_benchmark.py)** — BM25 query latency on synthetic wikis of 100 to 10,000 pages, searching the whole wiki or only the branches [ROUTING.md](../docs/user-quick-start-guide.md#step-17--set-up-routingmd--scoped-search) selects.

```bash
pytest tests/performance/test_routing_benchmark.py -m benchmark -v
```

Results: [Quick-Start Guide — Appendix H](../docs/user-quick-start-guide.md#appendix-h--bm25-routing-performance-benchmarks). Those figures were measured before the BM25 index cache, which made full-corpus search about 18× faster at 2,000 pages; the retrieval benchmark above reports the current latency.

## Service-level checks

**[`tests/performance/`](../tests/performance/)** — timing checks against the design doc's targets: BM25 search time, query-cache hit and miss latency, concurrent readers and throughput, epoch invalidation, and concurrent audit writes during citation checks. They are excluded from the default test run.

```bash
pytest tests/performance/ -v --benchmark-only        # full timings
pytest tests/performance/ -v --benchmark-disable     # pass/fail checks only, as in CI
pytest tests/performance/test_query_cache_perf.py -m charts   # regenerate the cache charts in docs/png/cache-perf/
```

## Knowledge graph at scale

The web UI's Graph tab was measured in headless Chromium on generated wikis of 500 to 5,000 pages: time until the graph appears, frame rate and longest freeze, before and after the cluster overview. The measurement scripts are not in the repository; results and method: [design doc — Knowledge graph web UI](../docs/design.md#web-ui) and [Quick-Start Guide — Large wikis](../docs/user-quick-start-guide.md#large-wikis-cluster-overview).
