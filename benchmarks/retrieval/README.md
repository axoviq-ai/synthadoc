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
python -m benchmarks.retrieval evaluate --configs bm25,rerank
python -m benchmarks.retrieval evaluate --configs bm25,rerank --write-baseline
```

Configurations:

| Name | Search |
| --- | --- |
| `bm25` | BM25 only — the default today |
| `rerank` | `[search] vector = true` today: BM25 top 20, re-sorted by embedding similarity |
| `fusion` | Prototype of the proposed design: BM25 top 20 and embedding top 20 over the whole wiki, merged by reciprocal rank fusion |

Metrics, per query type and wiki size: recall@5/10/20 (share of the right
pages in the top k), MRR@10 and nDCG@10 (how high they rank), and P50/P95
search latency.

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
