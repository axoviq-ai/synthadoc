# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import logging
import os
import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Optional

import aiosqlite
from rank_bm25 import BM25Okapi

from synthadoc.storage.wiki import WikiPage, WikiStorage

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    slug: str
    score: float             # BM25 score; 0.0 when only the embedding search found the page
    title: str
    snippet: str
    tf_fallback: bool = False
    rank_score: float = 0.0  # ordering key: the BM25 score, or the fused rank when embeddings are on
    similarity: Optional[float] = None   # embedding similarity to the query, when embeddings are on


def merge_results(result_lists: Iterable[list[SearchResult]],
                  top_n: Optional[int] = None) -> list[SearchResult]:
    """Combine several searches (e.g. one per sub-question): keep each page's
    best result and order by rank_score."""
    best: dict[str, SearchResult] = {}
    for results in result_lists:
        for r in results:
            if r.slug not in best or r.rank_score > best[r.slug].rank_score:
                best[r.slug] = r
    ranked = sorted(best.values(), key=lambda r: r.rank_score, reverse=True)
    return ranked if top_n is None else ranked[:top_n]


class VectorStore:
    """SQLite-backed store of page embeddings (float32 blobs).

    Each row carries a hash of the text it was embedded from, so a sync can
    tell which pages changed.
    """

    def __init__(self, db_path: Path) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS page_embeddings (
                    slug       TEXT PRIMARY KEY,
                    text_hash  TEXT NOT NULL,
                    embedding  BLOB NOT NULL
                )
            """)
            # Embeddings from before change tracking; re-embedded on the next sync.
            await db.execute("DROP TABLE IF EXISTS embeddings")
            await db.commit()

    async def text_hashes(self) -> dict[str, str]:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute("SELECT slug, text_hash FROM page_embeddings") as cur:
                return {slug: text_hash for slug, text_hash in await cur.fetchall()}

    async def upsert_many(self, rows: list[tuple[str, str, "np.ndarray"]]) -> None:
        """Store each (slug, text_hash, embedding), replacing older rows."""
        import numpy as np
        async with aiosqlite.connect(self._path) as db:
            await db.executemany(
                "INSERT OR REPLACE INTO page_embeddings (slug, text_hash, embedding) VALUES (?, ?, ?)",
                [(slug, text_hash, np.asarray(vec, dtype=np.float32).tobytes())
                 for slug, text_hash, vec in rows],
            )
            await db.commit()

    async def delete_pages(self, slugs: Iterable[str]) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.executemany("DELETE FROM page_embeddings WHERE slug=?", [(s,) for s in slugs])
            await db.commit()

    async def load(self) -> tuple[list[str], "np.ndarray"]:
        """(slugs, embedding matrix with one row per slug)."""
        import numpy as np
        async with aiosqlite.connect(self._path) as db:
            async with db.execute("SELECT slug, embedding FROM page_embeddings ORDER BY slug") as cur:
                rows = await cur.fetchall()
        if not rows:
            return [], np.zeros((0, 0), dtype=np.float32)
        return [r[0] for r in rows], np.stack([np.frombuffer(r[1], dtype=np.float32) for r in rows])


_EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"


def embed_model_cache_dir() -> Path:
    """Where the embedding model is cached: FASTEMBED_CACHE_PATH if set, else
    ~/.synthadoc/models. (fastembed's own default is the system temp folder,
    which the OS clears, forcing a 65 MB re-download.)"""
    return Path(os.environ.get("FASTEMBED_CACHE_PATH") or Path.home() / ".synthadoc" / "models")


def fastembed_installed() -> bool:
    """True when fastembed can be imported (checked without importing it)."""
    return importlib.util.find_spec("fastembed") is not None


def load_embed_model():
    """Load the embedding model, downloading it into embed_model_cache_dir()
    the first time. The Docker build calls this to bake the model in."""
    from fastembed import TextEmbedding
    return TextEmbedding(_EMBED_MODEL_NAME, cache_dir=str(embed_model_cache_dir()))

_COMPOUND_RE = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)+")

# Characters of a page's search text that are embedded: its title, tags and
# opening. Section-level embeddings (one per heading) were benchmarked and
# rejected: alone they rank better, but fused with BM25 they did worse (they
# find the pages BM25 already finds) and took ~20x longer to compute.
_EMBED_CHARS = 512
_EMBED_BATCH = 64
# Recent query embeddings, by query text. Embedding a query is most of the
# extra latency of semantic search; an embedding depends only on the text and
# the model, never on the wiki, so entries never go stale.
_QUERY_CACHE_SIZE = 256

# The embedding model (BAAI/bge-small-en-v1.5) is English-only. On Chinese text
# it hurt fused retrieval (DuRetrieval benchmark: recall@5 0.751 -> 0.645), so
# pages whose embedded text is mostly CJK are left to BM25, and a query with
# any CJK character is answered by BM25 alone.
_CJK_RE = re.compile("[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_CJK_PAGE_SHARE = 0.3     # CJK share of letters above which a page is not embedded


def is_mostly_cjk(text: str) -> bool:
    """True when CJK characters are at least _CJK_PAGE_SHARE of the letters in *text*."""
    cjk = len(_CJK_RE.findall(text))
    return cjk > 0 and cjk / (cjk + len(_LATIN_RE.findall(text))) >= _CJK_PAGE_SHARE

# Fusion of the BM25 and embedding rankings (see hybrid_search). Tuned on the
# retrieval benchmark in benchmarks/retrieval.
_RRF_K = 60
_PIN_DOMINANCE = 1.05    # BM25 best score >= this x its second -> trust BM25's top hits
_PIN_TOP = 3


def page_search_text(page: WikiPage) -> str:
    """Text a page is indexed by in BM25."""
    return f"{page.title} {' '.join(page.tags)} {page.content}"


def embedding_text(page: WikiPage) -> str:
    """The text a page is embedded from."""
    return page_search_text(page)[:_EMBED_CHARS]


def _text_hash(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()


def _keyword_dominates(results: list[SearchResult]) -> bool:
    """True when BM25's best score is at least _PIN_DOMINANCE times its second.

    A dominant BM25 hit is almost always an exact name or term match, so its top
    results are kept on top of the fused ranking.
    """
    if not results:
        return False
    if len(results) == 1 or results[1].score <= 0:
        return True
    return results[0].score >= _PIN_DOMINANCE * results[1].score


# Built BM25 indexes kept per search scope (full corpus plus routing scopes).
_MAX_CACHED_SCOPES = 8

# Only pages in these lifecycle states enter the BM25 corpus.
# contradicted, archived, and draft pages must not answer queries.
_QUERY_STATES: frozenset[str] = frozenset({"active", "stale"})


class HybridSearch:
    """BM25 full-text search, fused with embedding search when enabled.

    With ``[search] vector`` on (and fastembed installed), every query runs
    BM25 and an embedding search side by side and merges the two rankings
    with reciprocal rank fusion; a dominant BM25 hit keeps its top results on
    top. Page embeddings are kept in embeddings.db, held in memory as
    one matrix, and re-synced in the background when pages change.
    """

    def __init__(self, store: WikiStorage, index_path: Path,
                 search_cfg=None) -> None:
        self._store = store
        self._index_path = index_path
        self._cached_corpus: Optional[tuple[list[str], list[list[str]]]] = None
        # scope (None = full corpus) -> (slugs, tokenized docs, index); building
        # the index costs ~100x more than scoring a query, so reuse it.
        self._bm25_indexes: dict[Optional[frozenset[str]], tuple[list[str], list[list[str]], BM25Okapi]] = {}
        self._search_cfg = search_cfg      # SearchConfig or None
        self._vector_store: Optional[VectorStore] = None
        self._embed_model = None            # lazy loaded
        self._query_vecs: OrderedDict[str, "np.ndarray"] = OrderedDict()   # LRU, _QUERY_CACHE_SIZE
        # In-memory embeddings: one row per page, in _page_slugs order.
        self._matrix: Optional["np.ndarray"] = None
        self._page_slugs: list[str] = []
        self._vectors_dirty = True
        self._sync_lock = asyncio.Lock()
        self._sync_task: Optional[asyncio.Task] = None

    def vectors_requested(self) -> bool:
        """True when the config asks for embeddings (``vector = true`` or ``"auto"``)."""
        mode = getattr(self._search_cfg, "vector", False)
        return mode is True or mode == "auto"

    def _vector_enabled(self) -> bool:
        return self._vector_store is not None

    def _pool_size(self) -> int:
        return int(getattr(self._search_cfg, "vector_top_candidates", 20) or 20)

    async def init_vector(self) -> None:
        """Open embeddings.db when the config asks for embeddings.

        Raises ImportError when fastembed is not installed; the caller decides
        whether that is worth a warning (``true``) or not (``"auto"``).
        """
        if not self.vectors_requested():
            return
        try:
            from fastembed import TextEmbedding  # noqa: F401
        except ImportError:
            raise ImportError(
                "fastembed is required for vector search. "
                'Run: pip install "synthadoc[vectors]"  then restart the server.'
            )
        self._vector_store = VectorStore(self._index_path)
        await self._vector_store.init()

    def _get_embed_model(self):
        if self._embed_model is None:
            self._embed_model = load_embed_model()
        return self._embed_model

    def _embed_texts(self, texts: list[str]) -> "np.ndarray":
        """L2-normalised embeddings, one row per text (blocking; run in an executor)."""
        import numpy as np
        vectors = np.array(list(self._get_embed_model().embed(texts, batch_size=_EMBED_BATCH)),
                           dtype=np.float32)
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True).clip(min=1e-12)

    # ── embedding sync ──────────────────────────────────────────────────────

    async def sync_embeddings(self) -> int:
        """Embed pages that are new or changed, drop pages that left the corpus,
        and reload the in-memory matrix. Returns the number of pages embedded."""
        if self._vector_store is None:
            return 0
        async with self._sync_lock:
            self._vectors_dirty = False
            slugs, _ = self._corpus()
            stored = await self._vector_store.text_hashes()
            todo: list[tuple[str, str, str]] = []   # (slug, hash, text)
            embeddable: set[str] = set()
            for slug in slugs:
                page = self._store.read_page(slug)
                if page is None:
                    continue
                text = embedding_text(page)
                if is_mostly_cjk(text):
                    continue                         # BM25 only: see _CJK_PAGE_SHARE
                embeddable.add(slug)
                if stored.get(slug) != (text_hash := _text_hash(text)):
                    todo.append((slug, text_hash, text))
            if todo:
                skipped = len(slugs) - len(embeddable)
                logger.info("Vector search: embedding %d page(s)…%s", len(todo),
                            f" ({skipped} mostly Chinese/Japanese/Korean page(s) left to keyword search)"
                            if skipped else "")
            loop = asyncio.get_running_loop()
            for i in range(0, len(todo), _EMBED_BATCH * 4):
                batch = todo[i:i + _EMBED_BATCH * 4]
                vectors = await loop.run_in_executor(None, self._embed_texts, [t for _, _, t in batch])
                await self._vector_store.upsert_many(
                    [(slug, text_hash, vec) for (slug, text_hash, _), vec in zip(batch, vectors)])
            if removed := set(stored) - embeddable:
                await self._vector_store.delete_pages(removed)
            await self._load_matrix()
            return len(todo)

    async def _load_matrix(self) -> None:
        slugs, matrix = await self._vector_store.load()
        self._page_slugs = slugs
        self._matrix = matrix if slugs else None

    def schedule_embedding_sync(self) -> None:
        """Start a background sync unless one is already running (no-op when off)."""
        if self._vector_store is None or (self._sync_task and not self._sync_task.done()):
            return
        self._sync_task = asyncio.create_task(self._sync_in_background())

    async def _sync_in_background(self) -> None:
        try:
            await self.sync_embeddings()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — keep serving BM25; retried on the next page change
            logger.exception("Vector search: embedding sync failed — BM25 results only until it succeeds")

    async def wait_for_embedding_sync(self) -> None:
        if self._sync_task is not None:
            await self._sync_task

    async def close(self) -> None:
        """Cancel a running background sync."""
        if self._sync_task is not None and not self._sync_task.done():
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        lower = text.lower()
        compound = _COMPOUND_RE.findall(lower)      # "total_mv_cny", "fcf_calc_v2"
        ascii_t = re.findall(r"[a-z0-9]+", lower)   # individual parts
        cjk_t = re.findall(
            r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]", lower
        )
        return compound + ascii_t + cjk_t

    def invalidate_index(self) -> None:
        """Drop the in-memory corpus and index caches, and mark embeddings for a
        re-sync. Call after any page write."""
        self._cached_corpus = None
        self._bm25_indexes.clear()
        self._vectors_dirty = True

    def _corpus(self) -> tuple[list[str], list[list[str]]]:
        if self._cached_corpus is not None:
            return self._cached_corpus
        from synthadoc.agents.lint_agent import LINT_SKIP_SLUGS
        filtered_slugs = []
        tokenized = []
        for slug in self._store.list_pages():
            if slug in LINT_SKIP_SLUGS:
                continue
            page = self._store.read_page(slug)
            if not page or page.status not in _QUERY_STATES:
                continue
            tokenized.append(self._tokenize(page_search_text(page)))
            filtered_slugs.append(slug)
        self._cached_corpus = (filtered_slugs, tokenized)
        return self._cached_corpus

    def _bm25_index(self, scoped_slugs: list[str] | None
                    ) -> Optional[tuple[list[str], list[list[str]], BM25Okapi]]:
        """The BM25 index over the corpus (or its *scoped_slugs* subset), cached
        until invalidate_index(). None when the scope holds no pages."""
        key = frozenset(scoped_slugs) if scoped_slugs is not None else None
        if key in self._bm25_indexes:
            return self._bm25_indexes[key]
        slugs, corpus = self._corpus()
        if key is not None:
            pairs = [(s, t) for s, t in zip(slugs, corpus) if s in key]
            slugs, corpus = [p[0] for p in pairs], [p[1] for p in pairs]
        if not corpus:
            return None
        if len(self._bm25_indexes) >= _MAX_CACHED_SCOPES:
            self._bm25_indexes.pop(next(iter(self._bm25_indexes)))   # oldest first
        self._bm25_indexes[key] = (slugs, corpus, BM25Okapi(corpus))
        return self._bm25_indexes[key]

    def _result(self, slug: str, score: float, **fields) -> SearchResult:
        page = self._store.read_page(slug)
        snippet = (page.content[:120] + "...") if page and len(page.content) > 120 \
                  else (page.content if page else "")
        return SearchResult(slug=slug, score=float(score), title=page.title if page else slug,
                            snippet=snippet, **fields)

    def bm25_search(self, query_terms: list[str], top_n: int = 10,
                    scoped_slugs: list[str] | None = None) -> list[SearchResult]:
        index = self._bm25_index(scoped_slugs)
        if index is None:
            return []
        slugs, corpus, bm25 = index
        scores = bm25.get_scores(self._tokenize(" ".join(query_terms)))
        _used_tf_fallback = False
        if not any(s > 0 for s in scores):
            # BM25 IDF breakdown (tiny corpus or echo effect) — fall back to normalized TF.
            _query_set = set(self._tokenize(" ".join(query_terms)))
            _tf_scores = [
                sum(1 for t in doc_toks if t in _query_set) / max(len(doc_toks), 1)
                for doc_toks in corpus
            ]
            if any(s > 0 for s in _tf_scores):
                scores = _tf_scores
                _used_tf_fallback = True
        ranked = sorted(zip(slugs, scores), key=lambda x: x[1], reverse=True)
        return [
            self._result(slug, score, tf_fallback=_used_tf_fallback, rank_score=float(score))
            for slug, score in ranked[:top_n] if score > 0
        ]

    def _vector_ranking(self, query_vec: "np.ndarray", scoped_slugs: list[str] | None,
                        top_n: int) -> list[tuple[str, float]]:
        """Pages closest to *query_vec* by embedding similarity, within the corpus/scope."""
        import numpy as np
        page_sims = self._matrix @ query_vec
        allowed = set(self._corpus()[0])
        if scoped_slugs is not None:
            allowed &= set(scoped_slugs)
        ranked = []
        for i in np.argsort(-page_sims):
            if self._page_slugs[i] in allowed:
                ranked.append((self._page_slugs[i], float(page_sims[i])))
                if len(ranked) == top_n:
                    break
        return ranked

    def _fuse(self, keyword: list[SearchResult], semantic: list[tuple[str, float]],
              top_n: int) -> list[SearchResult]:
        """Reciprocal rank fusion of both rankings; BM25's top hits stay on top
        when BM25 has a dominant match."""
        fused: dict[str, float] = {}
        for ranking in ([r.slug for r in keyword], [slug for slug, _ in semantic]):
            for rank, slug in enumerate(ranking, 1):
                fused[slug] = fused.get(slug, 0.0) + 1 / (_RRF_K + rank)
        if _keyword_dominates(keyword):
            # Above any fused score (at most 2 / (_RRF_K + 1)), in BM25 order.
            for i, r in enumerate(keyword[:_PIN_TOP]):
                fused[r.slug] = 1.0 + (_PIN_TOP - i)
        by_slug = {r.slug: r for r in keyword}
        similarity = dict(semantic)
        results = []
        for slug in sorted(fused, key=fused.get, reverse=True)[:top_n]:
            base = by_slug.get(slug)
            result = (SearchResult(slug=base.slug, score=base.score, title=base.title,
                                   snippet=base.snippet, tf_fallback=base.tf_fallback)
                      if base else self._result(slug, 0.0))
            result.rank_score = fused[slug]
            result.similarity = similarity.get(slug)
            results.append(result)
        return results

    async def hybrid_search(self, query_terms: list[str],
                            top_n: int = 10,
                            scoped_slugs: list[str] | None = None) -> list[SearchResult]:
        """BM25 fused with embedding search when enabled; BM25 only otherwise.

        Until the first embedding sync has finished, results are BM25 only.
        """
        if self._vector_store is None:
            return self.bm25_search(query_terms, top_n=top_n, scoped_slugs=scoped_slugs)
        if self._vectors_dirty:
            self.schedule_embedding_sync()
        pool = max(top_n, self._pool_size())
        query = " ".join(query_terms)
        if self._matrix is None or _CJK_RE.search(query):
            return self.bm25_search(query_terms, top_n=pool, scoped_slugs=scoped_slugs)[:top_n]
        # Start embedding the query in a worker thread before BM25 runs, so the
        # two overlap (the model releases the GIL while it runs).
        query_vec = self._query_vecs.get(query)
        pending = None
        if query_vec is None:
            pending = asyncio.get_running_loop().run_in_executor(None, self._embed_texts, [query])
        keyword = self.bm25_search(query_terms, top_n=pool, scoped_slugs=scoped_slugs)
        if pending is not None:
            query_vec = (await pending)[0]
            self._remember_query(query, query_vec)
        else:
            self._query_vecs.move_to_end(query)
        semantic = self._vector_ranking(query_vec, scoped_slugs, pool)
        return self._fuse(keyword, semantic, top_n)

    def _remember_query(self, query: str, vector: "np.ndarray") -> None:
        self._query_vecs[query] = vector
        if len(self._query_vecs) > _QUERY_CACHE_SIZE:
            self._query_vecs.popitem(last=False)
