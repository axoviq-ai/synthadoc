# Copyright (C) 2026 Peter W. / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Independent check corpora: public retrieval sets with human-written queries
and human relevance judgements.

The fusion settings (RRF k, keyword pin) were chosen on the Wikipedia corpus.
These sets test them on data they were not tuned on: two English domains the
Wikipedia set does not cover (BEIR SciFact, NFCorpus) and one Chinese set
(C-MTEB DuRetrieval), for the English-only embedding model on CJK text.

Rows come from the Hugging Face dataset server, like HotpotQA, and are cached.
"""
from __future__ import annotations

import json
import random
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from synthadoc.storage.wiki import WikiStorage

from benchmarks.retrieval import corpus
from benchmarks.retrieval.queries import Query

EXTERNAL_FILE = corpus.DATA_DIR / "external.json"
_ROWS = corpus._HOTPOT_ROWS
_PAGE = 100                       # the dataset server's maximum rows per request
_PAUSE_S = 1.5                     # between requests: the server rate-limits bursts
SAMPLE_SEED = 411
DURETRIEVAL_PASSAGES = 3000       # first corpus rows: they hold every gold passage of the first ~440 queries
DURETRIEVAL_QUERIES = 300


@dataclass(frozen=True)
class Split:
    dataset: str
    config: str
    split: str


@dataclass(frozen=True)
class Spec:
    name: str
    corpus: Split
    queries: Split
    qrels: Split
    doc_id: str = "_id"
    query_id: str = "_id"
    qrel_query: str = "query-id"
    qrel_doc: str = "corpus-id"
    language: str = "en"


SPECS = {
    "scifact": Spec("scifact", Split("BeIR/scifact", "corpus", "corpus"),
                    Split("BeIR/scifact", "queries", "queries"), Split("BeIR/scifact-qrels", "default", "test")),
    "nfcorpus": Spec("nfcorpus", Split("BeIR/nfcorpus", "corpus", "corpus"),
                     Split("BeIR/nfcorpus", "queries", "queries"), Split("BeIR/nfcorpus-qrels", "default", "test")),
    "duretrieval": Spec("duretrieval", Split("C-MTEB/DuRetrieval", "default", "corpus"),
                        Split("C-MTEB/DuRetrieval", "default", "queries"),
                        Split("C-MTEB/DuRetrieval-qrels", "default", "dev"),
                        doc_id="id", query_id="id", qrel_query="qid", qrel_doc="pid", language="zh"),
}


def fetch_rows(split: Split, limit: int | None, cache_dir: Path) -> list[dict]:
    """All rows of *split* (or the first *limit*), cached as JSON."""
    name = f"{split.dataset.replace('/', '__')}__{split.config}__{split.split}"
    cached = cache_dir / "external" / f"{name}.json"
    if cached.exists():
        rows = json.loads(cached.read_text(encoding="utf-8"))
        if limit is None or len(rows) >= limit:
            return rows[:limit] if limit else rows
    rows: list[dict] = []
    with corpus._client() as client:
        total = limit
        offset = 0
        while total is None or offset < total:
            resp = corpus._get(client, _ROWS, dataset=split.dataset, config=split.config, split=split.split,
                               offset=offset, length=_PAGE if total is None else min(_PAGE, total - offset))
            data = resp.json()
            if total is None:
                total = data["num_rows_total"]
            rows += [r["row"] for r in data["rows"]]
            offset += _PAGE
            time.sleep(_PAUSE_S)
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return rows


def _slug(doc_id: str) -> str:
    return "d-" + re.sub(r"[^a-z0-9]+", "-", str(doc_id).lower()).strip("-")


def _title(row: dict, language: str) -> str:
    """The document's title, or its opening when it has none."""
    if title := (row.get("title") or "").strip():
        return title
    text = row["text"].strip()
    if language == "zh":
        return re.split(r"[。！？\n]", text, maxsplit=1)[0][:30] or text[:30]
    return " ".join(text.split()[:10])


def build(name: str, cache_dir: Path = corpus.CACHE_DIR) -> tuple[Path, list[Query]]:
    """Write the corpus as wiki pages and return its judged queries."""
    spec = SPECS[name]
    sampled = name == "duretrieval"
    docs = fetch_rows(spec.corpus, DURETRIEVAL_PASSAGES if sampled else None, cache_dir)
    qrels = fetch_rows(spec.qrels, None, cache_dir)
    texts = {str(r[spec.query_id]): r["text"] for r in fetch_rows(spec.queries, None, cache_dir)}

    doc_ids = {str(r[spec.doc_id]) for r in docs}
    relevant: dict[str, list[str]] = defaultdict(list)
    for r in qrels:
        if int(r.get("score", 1)) > 0:
            relevant[str(r[spec.qrel_query])].append(str(r[spec.qrel_doc]))
    # Keep queries whose judged documents are all in the corpus (always true for
    # the full BEIR corpora; the DuRetrieval slice holds only some queries' passages).
    qids = [q for q, docs_ in relevant.items() if q in texts and all(d in doc_ids for d in docs_)]
    if sampled:
        qids = sorted(random.Random(SAMPLE_SEED).sample(sorted(qids), min(DURETRIEVAL_QUERIES, len(qids))))

    wiki_dir = cache_dir / "external" / name / "wiki"
    if not wiki_dir.exists() or len(list(wiki_dir.glob("*.md"))) < len(docs):
        wiki_dir.mkdir(parents=True, exist_ok=True)
        store = WikiStorage(wiki_dir)
        for row in docs:
            corpus.write_bench_page(store, _slug(row[spec.doc_id]), _title(row, spec.language), [],
                                    row["text"].strip() + "\n")
    queries = [Query(q, "human", texts[q], [_slug(d) for d in dict.fromkeys(relevant[q])]) for q in qids]
    return wiki_dir, queries


def pin(name: str, queries: list[Query], pages: int, path: Path = EXTERNAL_FILE) -> None:
    """Record what was evaluated, so a changed upstream dataset is noticed."""
    pinned = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    spec = SPECS[name]
    pinned[name] = {"corpus": vars(spec.corpus), "qrels": vars(spec.qrels), "language": spec.language,
                    "pages": pages, "queries": len(queries),
                    "query_ids": sorted(q.id for q in queries) if name == "duretrieval" else None}
    path.write_text(json.dumps(pinned, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def check_pin(name: str, queries: list[Query], pages: int, path: Path = EXTERNAL_FILE) -> str | None:
    """A message when the data differs from the committed pin, else None."""
    if not path.exists() or name not in (pinned := json.loads(path.read_text(encoding="utf-8"))):
        return None
    want = pinned[name]
    if want["pages"] != pages or want["queries"] != len(queries):
        return f"{name}: {pages} pages / {len(queries)} queries, pinned {want['pages']} / {want['queries']}"
    if want["query_ids"] is not None and want["query_ids"] != sorted(q.id for q in queries):
        return f"{name}: sampled query IDs differ from {path.name}"
    return None
