# Retrieval benchmark

Measures how well Synthadoc's search finds the right wiki page, with and
without semantic embeddings ([issue #411](https://github.com/axoviq-ai/synthadoc/issues/411)).
It scores retrieval only — no LLM runs during evaluation — so results are
deterministic, cheap and work offline once the corpora are cached.

## Corpora

| Corpus | Pages | Queries | What it tests |
| --- | --- | --- | --- |
| **wikipedia** | ~2,000 English Wikipedia articles from 24 overlapping computing categories, pinned to fixed revisions, converted to wiki pages (lead + sections, capped at 1,500 words) | 3 LLM-written queries for each of 500 sampled pages | `lexical` (page's own terms), `paraphrase` (same need, no title words or distinctive terms — the case embeddings target), `identifier` (exact name / acronym / number lookup — regressions show here) |
| **hotpot** | ~2,900 Wikipedia intro paragraphs | 300 human-written HotpotQA questions, 2 gold paragraphs each | Questions people actually wrote, as a check on LLM-written queries |

The wikipedia corpus is also scored at 200, 500 and 1,000 pages as well as in full
(nested seeded subsets), to see whether the gap between keyword and semantic
search grows with wiki size.

## What is committed

Only small files (see [NOTICE.md](NOTICE.md) for licences):

- `data/articles.json` — article titles, revision IDs, source category
- `data/queries.jsonl` — the frozen generated queries
- `data/hotpot.json` — the HotpotQA question IDs used
- `data/baseline.json` — the latest recorded scores

Article text, HotpotQA paragraphs and embeddings live in a local cache,
`~/.cache/synthadoc-bench` (override with `SYNTHADOC_BENCH_CACHE` or `--cache`).

## Running

From the repository root:

```bash
python -m benchmarks.retrieval fetch                       # once: download + build the wikis (~30 min)
python -m benchmarks.retrieval evaluate                    # BM25 only
pip install -e ".[vectors]"                                # for embedding configs
python -m benchmarks.retrieval evaluate --configs bm25,hybrid
python -m benchmarks.retrieval evaluate --configs bm25,hybrid --write-baseline
```

Configurations:

| Name | Search |
| --- | --- |
| `bm25` | BM25 only — `[search] vector = false`, the default |
| `hybrid` | `[search] vector = true`: BM25 fused with page-embedding search, keyword pin (see [design](../../docs/design.md#semantic-search)) |

The first `hybrid` run embeds every page of the corpus (cached in the
corpus's `embeddings.db`; later runs only embed changed pages).

### How the design was chosen

Measured on the full 1,985-page corpus while designing semantic search
(recall@5, page-level embeddings of each page's first 512 characters):

| Setup | lexical | identifier | paraphrase | all |
| --- | ---: | ---: | ---: | ---: |
| BM25 | 0.998 | 0.994 | 0.479 | 0.840 |
| BM25 top 20 re-sorted by embedding similarity (the former `vector = true`) | 0.986 | 0.625 | 0.595 | 0.742 |
| BM25 + embedding search, reciprocal rank fusion | 0.994 | 0.936 | 0.694 | 0.883 |
| Fusion + keyword pin (BM25 top 3 kept when its best score ≥ 1.05× its second) | 0.998 | 0.984 | 0.676 | 0.896 |
| Same, but one embedding per section instead of per page | 0.998 | 0.986 | 0.613 | 0.878 |

Section embeddings rank better on their own (paraphrase recall@5 0.669 vs
0.616 for the embedding search alone) but fuse worse, because they mostly
find the pages BM25 already finds, and embedding the 14,511 sections took
82 minutes against a few minutes for one embedding per page. Semantic search
therefore embeds each page once (title, tags, first 512 characters).

Metrics, per query type and wiki size: recall@5/10/20 (share of the right
pages in the top k), MRR@10 and nDCG@10 (how high they rank), and P50/P95
search latency.

### Latency

P95 search latency, all queries (each query is asked once, so the query
embedding cache never helps here):

| Pages | `bm25` | `hybrid`, embedding after BM25 | `hybrid`, embedding alongside BM25 |
| ---: | ---: | ---: | ---: |
| 200 | 4 ms | 66 ms | 27 ms |
| 500 | 5 ms | 64 ms | 29 ms |
| 1,000 | 8 ms | 70 ms | 62 ms |
| 1,985 | 15 ms | 166 ms | 74 ms |

Embedding the query is most of the extra time (about 20 ms on CPU); comparing
it with every page embedding takes under 2 ms. Starting the query embedding
in a worker thread before BM25 runs overlaps the two, with identical results.
Latency varies by roughly ±10 ms between runs on the same machine.

### Maintainers only

```bash
python -m benchmarks.retrieval select      # re-pin the article list (changes every result)
python -m benchmarks.retrieval generate --provider anthropic --model claude-sonnet-5-5
```

`generate` needs the provider's API key in the environment, resumes if
interrupted, and retries paraphrases that reuse page terms (dropping any that
still do). Re-generating changes the queries, so commit the new
`queries.jsonl` and `baseline.json` together.

## Caveats

- Queries are run the way `QueryAgent` runs them (lowercased, split, top 20)
  but without its LLM question decomposition, so absolute numbers are a lower
  bound for the full query path; comparisons between configurations hold.
- Each generated query has one labelled page. Another page may also answer it,
  which lowers every configuration's score the same way.
- LLM-written paraphrases may suit embedding models better than real user
  wording; the human-written HotpotQA set is the check on that.
- HotpotQA distractor paragraphs were chosen for word overlap with the
  question, which makes that corpus deliberately hard for keyword search.
