# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Generate the frozen benchmark queries for the Wikipedia corpus with an LLM.

For each sampled page the model writes three queries that the page answers:

- ``lexical``    — uses the page's own key terms (keyword search should win);
- ``paraphrase`` — the same need in different words, avoiding the title and
                   the page's distinctive terms (the case semantic routing targets);
- ``identifier`` — a short lookup of a specific name, acronym, number or code
                   from the page (exact-match regressions show up here).

Paraphrase queries are checked mechanically for term overlap and retried once
with feedback; ones that still overlap are dropped rather than mislabelled.
Run once and commit ``data/queries.jsonl``; evaluation never calls an LLM.
``--types paraphrase`` re-asks only pages that lack a paraphrase.
"""
from __future__ import annotations

import asyncio
import json
import random
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from synthadoc.agents._query_utils import STOPWORDS
from synthadoc.providers.base import LLMProvider, Message
from synthadoc.storage.search import HybridSearch
from synthadoc.storage.wiki import WikiStorage

from benchmarks.retrieval.corpus import DATA_DIR

QUERIES_FILE = DATA_DIR / "queries.jsonl"
QUERY_TYPES = ("lexical", "paraphrase", "identifier")
SAMPLE_SEED = 411            # GitHub issue the benchmark was built for
SAMPLE_PAGES = 500
_PAGE_CHARS = 6000           # page text shown to the generator
_DISTINCT_TERMS = 30         # a page's most frequent non-generic terms
_MAX_PARAPHRASE_OVERLAP = 2  # distinctive page terms a paraphrase may still use
_GENERIC_PAGE_SHARE = 0.10   # a term on more than this share of pages gives nothing away

_SYSTEM = """\
You write search queries for evaluating a wiki search engine. Reply with one
JSON object and nothing else."""

_PROMPT = """\
Wiki page title: {title}

Page text:
{text}

Write three queries a user might type that THIS page answers better than any
other page about the same general field. Make each specific to this page.

1. "lexical": a natural question that uses the page's own key terms.
2. "paraphrase": the same kind of information need, but worded the way someone
   who does not know the terminology would ask. Do NOT use any word from the
   title, and avoid the page's distinctive names and technical terms; describe
   them instead.
3. "identifier": a short lookup (2-6 words) for a specific name, acronym,
   model number, date or code that appears in the page text but not in the title.

{feedback}Reply as: {{"lexical": "...", "paraphrase": "...", "identifier": "..."}}"""


@dataclass
class Query:
    id: str
    type: str
    text: str
    relevant: list[str]       # slugs


def content_terms(text: str) -> list[str]:
    """Search tokens of *text* without question words or 1-2 character tokens."""
    return [t for t in HybridSearch._tokenize(text) if len(t) > 2 and t not in STOPWORDS]


@dataclass
class TermStats:
    """Document frequencies over a wiki, to tell distinctive terms from common ones."""
    pages: int = 0
    df: Counter = field(default_factory=Counter)

    @classmethod
    def from_store(cls, store: WikiStorage) -> "TermStats":
        stats = cls()
        for slug in store.list_pages():
            if page := store.read_page(slug):
                stats.pages += 1
                stats.df.update(set(content_terms(page.content)))
        return stats

    def is_generic(self, term: str) -> bool:
        """True for words like "the" or "system" that appear across much of the wiki."""
        return self.pages > 0 and self.df[term] / self.pages > _GENERIC_PAGE_SHARE

    def specific(self, terms) -> list[str]:
        return [t for t in terms if not self.is_generic(t)]


def distinctive_terms(title: str, body: str, stats: TermStats) -> set[str]:
    """Title terms plus the page's most frequent terms, leaving out generic ones."""
    common = Counter(stats.specific(content_terms(body))).most_common(_DISTINCT_TERMS)
    return set(stats.specific(content_terms(title))) | {t for t, _ in common}


def paraphrase_overlap(query: str, title: str, body: str, stats: TermStats) -> list[str]:
    """Terms of *query* that give the page away; empty when it is a fair paraphrase.

    Any non-generic title term is disqualifying; beyond that, up to
    _MAX_PARAPHRASE_OVERLAP of the page's distinctive terms are tolerated.
    """
    terms = set(content_terms(query))
    title_hits = terms & set(stats.specific(content_terms(title)))
    page_hits = terms & distinctive_terms(title, body, stats)
    if title_hits or len(page_hits) > _MAX_PARAPHRASE_OVERLAP:
        return sorted(page_hits | title_hits)
    return []


def _parse(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        return {}
    return {k: str(v).strip() for k, v in data.items() if k in QUERY_TYPES and str(v).strip()}


async def _ask(provider: LLMProvider, title: str, body: str, feedback: str = "") -> dict:
    prompt = _PROMPT.format(title=title, text=body[:_PAGE_CHARS], feedback=feedback)
    resp = await provider.complete([Message(role="user", content=prompt)], system=_SYSTEM,
                                   temperature=0.7, max_tokens=400)
    return _parse(resp.text)


async def queries_for_page(provider: LLMProvider, slug: str, title: str, body: str,
                           stats: TermStats, log=print) -> list[Query]:
    got = await _ask(provider, title, body)
    if (para := got.get("paraphrase")) and (hits := paraphrase_overlap(para, title, body, stats)):
        feedback = (f"Your previous paraphrase \"{para}\" reused page terms "
                    f"({', '.join(hits)}). Avoid them this time.\n\n")
        retry = await _ask(provider, title, body, feedback)
        para = retry.get("paraphrase")
        if para and (hits := paraphrase_overlap(para, title, body, stats)):
            log(f"  {slug}: paraphrase dropped, reuses {', '.join(hits)}: {para}")
            para = ""
        got["paraphrase"] = para
    return [Query(f"{slug}:{kind}", kind, got[kind], [slug]) for kind in QUERY_TYPES if got.get(kind)]


def drop_leaky_paraphrases(queries: list[Query], store: WikiStorage, stats: TermStats) -> list[Query]:
    """Remove stored paraphrases that fail the current overlap check."""
    def fair(q: Query) -> bool:
        page = store.read_page(q.relevant[0])
        return q.type != "paraphrase" or (page is not None and
                                          not paraphrase_overlap(q.text, page.title, page.content, stats))
    return [q for q in queries if fair(q)]


def sample_slugs(slugs: list[str], n: int = SAMPLE_PAGES, seed: int = SAMPLE_SEED) -> list[str]:
    return sorted(random.Random(seed).sample(sorted(slugs), min(n, len(slugs))))


async def generate(provider: LLMProvider, wiki_dir: Path, out: Path = QUERIES_FILE,
                   types: tuple[str, ...] = QUERY_TYPES, concurrency: int = 4, log=print) -> list[Query]:
    """Generate *types* of query for sampled pages that lack them.

    Resumes from an existing *out* file: a page is asked again only for the
    types it is missing, and only those types are kept from the new reply.
    Stored paraphrases that fail the current overlap check are dropped first.
    """
    store = WikiStorage(wiki_dir)
    stats = TermStats.from_store(store)
    existing = drop_leaky_paraphrases(load_queries(out), store, stats) if out.exists() else []
    save_queries(existing, out)
    have = {(q.relevant[0], q.type) for q in existing}
    todo = [s for s in sample_slugs(store.list_pages()) if any((s, t) not in have for t in types)]
    log(f"Generating {', '.join(types)} queries for {len(todo)} page(s)")
    sem = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    out.parent.mkdir(parents=True, exist_ok=True)

    async def one(slug: str) -> None:
        page = store.read_page(slug)
        if not page:
            return
        async with sem:
            try:
                queries = await queries_for_page(provider, slug, page.title, page.content, stats, log)
            except Exception as exc:  # noqa: BLE001 — keep going; the page is retried on resume
                log(f"  {slug}: {exc}")
                return
        queries = [q for q in queries if q.type in types and (slug, q.type) not in have]
        async with lock:   # append as we go so an interrupted run resumes
            with out.open("a", encoding="utf-8") as fh:
                fh.writelines(json.dumps(asdict(q), ensure_ascii=False) + "\n" for q in queries)

    await asyncio.gather(*(one(s) for s in todo))
    queries = sorted({q.id: q for q in load_queries(out)}.values(), key=lambda q: q.id)  # stable order
    save_queries(queries, out)
    return queries


def save_queries(queries: list[Query], path: Path = QUERIES_FILE) -> None:
    path.write_text("".join(json.dumps(asdict(q), ensure_ascii=False) + "\n" for q in queries),
                    encoding="utf-8")


def load_queries(path: Path = QUERIES_FILE) -> list[Query]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [Query(**json.loads(line)) for line in lines if line.strip()]
