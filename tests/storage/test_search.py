# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from synthadoc.storage.wiki import WikiStorage, WikiPage
from synthadoc.storage.search import HybridSearch


def _make_page(content: str) -> WikiPage:
    return WikiPage(title=content[:20], tags=[], content=content,
                    status="active", confidence="medium", sources=[])


def _write_page(store, slug, content):
    store.write_page(slug, WikiPage(
        title=slug.replace("-", " ").title(), tags=[],
        content=content, status="active", confidence="high", sources=[]))


def test_bm25_finds_relevant_page(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("transformers", _make_page("Transformers use self-attention mechanisms."))
    store.write_page("rlhf", _make_page("RLHF trains models with human feedback."))
    store.write_page("cnn", _make_page("CNNs use convolutional filters for images."))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    results = search.bm25_search(["attention", "transformer"], top_n=2)
    assert any(r.slug == "transformers" for r in results)


def test_returns_at_most_top_n(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    for i in range(10):
        store.write_page(f"page-{i}", _make_page(f"content about topic {i}"))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    results = search.bm25_search(["content", "topic"], top_n=3)
    assert len(results) <= 3


def test_empty_wiki_returns_empty(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    assert search.bm25_search(["anything"], top_n=5) == []


def test_bm25_finds_cjk_page(tmp_wiki):
    """Chinese character queries and documents should produce non-zero BM25 scores.
    Requires 3+ docs: BM25Okapi IDF = log((N-df+0.5)/(df+0.5)); with N=2 df=1 → log(1) = 0.
    """
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("ai-zh",  _make_page("人工智能是计算机科学的一个分支。"))
    store.write_page("other1", _make_page("Unrelated English content here."))
    store.write_page("other2", _make_page("More unrelated English text about history."))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    results = search.bm25_search(["人工智能"], top_n=5)
    assert any(r.slug == "ai-zh" for r in results)


def test_tokenize_includes_cjk_chars():
    """Tokenizer must not drop CJK characters."""
    from synthadoc.storage.search import HybridSearch
    tokens = HybridSearch._tokenize("人工智能 AI")
    assert "人" in tokens
    assert "工" in tokens
    assert "ai" in tokens


def test_tokenize_compound_identifier():
    """total_mv_cny → compound token plus parts, all lowercase."""
    from synthadoc.storage.search import HybridSearch
    tokens = HybridSearch._tokenize("total_mv_cny")
    assert "total_mv_cny" in tokens
    assert "total" in tokens
    assert "mv" in tokens
    assert "cny" in tokens


def test_tokenize_compound_mixed_case():
    """FCF_calc_v2 → lowercase compound plus parts."""
    from synthadoc.storage.search import HybridSearch
    tokens = HybridSearch._tokenize("FCF_calc_v2")
    assert "fcf_calc_v2" in tokens
    assert "fcf" in tokens
    assert "calc" in tokens
    assert "v2" in tokens


def test_tokenize_no_regression_plain_text():
    """Plain words without underscores → no compound tokens added."""
    from synthadoc.storage.search import HybridSearch
    tokens = HybridSearch._tokenize("plain text")
    assert "plain" in tokens
    assert "text" in tokens
    # No compound token for plain words
    assert not any("_" in t for t in tokens)


def test_tokenize_empty_string_no_crash():
    """Empty string → empty list."""
    from synthadoc.storage.search import HybridSearch
    assert HybridSearch._tokenize("") == []


def test_tokenize_cjk_unchanged():
    """CJK characters still tokenized individually."""
    from synthadoc.storage.search import HybridSearch
    tokens = HybridSearch._tokenize("现金桥")
    assert "现" in tokens
    assert "金" in tokens
    assert "桥" in tokens


def test_tokenize_formula_no_compound():
    """Formulas without underscores produce no compound tokens."""
    from synthadoc.storage.search import HybridSearch
    tokens = HybridSearch._tokenize("fcf = cfo - capex")
    assert "fcf" in tokens
    assert "cfo" in tokens
    assert "capex" in tokens
    assert not any("_" in t for t in tokens)


# ── corpus cache tests ────────────────────────────────────────────────────────

def test_bm25_corpus_built_once_for_repeated_calls(tmp_wiki):
    """Corpus must only be built once — same object reused on second search."""
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "chlorine", "chlorine treats algae in pools")
    _write_page(store, "ph", "pH balance is important for pools")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")

    search.bm25_search(["chlorine"], top_n=5)
    corpus_after_first = search._cached_corpus
    search.bm25_search(["pH"], top_n=5)
    assert search._cached_corpus is corpus_after_first, "corpus must not be rebuilt between searches"


def test_bm25_corpus_invalidated_after_write(tmp_wiki):
    """After invalidate_index(), corpus must be rebuilt on next search."""
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "chlorine", "chlorine treats algae")
    _write_page(store, "unrelated", "the quick brown fox jumps over the lazy dog")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")

    search.bm25_search(["chlorine"], top_n=5)
    corpus_before = search._cached_corpus

    _write_page(store, "nitrogen", "nitrogen fertiliser for lawns")
    search.invalidate_index()
    # After invalidation, corpus must be None
    assert search._cached_corpus is None
    results = search.bm25_search(["nitrogen"], top_n=5)
    # Corpus rebuilt — must be a new object
    assert search._cached_corpus is not corpus_before
    assert "nitrogen" in [r.slug for r in results]


# ── performance: corpus cache behaviour ─────────────────────────────────────

def test_corpus_cache_populated_after_first_search(tmp_wiki):
    """_cached_corpus must be set (non-None) after the first bm25_search call."""
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "chlorine", "chlorine treats algae in pools")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    assert search._cached_corpus is None
    search.bm25_search(["chlorine"], top_n=5)
    assert search._cached_corpus is not None


def test_corpus_built_once_for_different_queries(tmp_wiki):
    """Corpus instance must be reused across different queries without invalidation."""
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "chlorine", "chlorine treats algae in pools")
    _write_page(store, "ph", "pH balance is important for pools")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")

    search.bm25_search(["chlorine"], top_n=5)
    corpus_id = id(search._cached_corpus)
    search.bm25_search(["pH balance"], top_n=5)
    assert id(search._cached_corpus) == corpus_id, "corpus must be built once, not once per query"


def test_corpus_repopulated_after_invalidation(tmp_wiki):
    """After invalidation a new page must be findable — corpus must be rebuilt."""
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "chlorine", "chlorine treats algae")
    _write_page(store, "unrelated", "the quick brown fox jumps over the lazy dog")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    search.bm25_search(["chlorine"], top_n=5)
    assert search._cached_corpus is not None

    search.invalidate_index()
    assert search._cached_corpus is None

    # Third page ensures nitrogen has positive BM25 IDF (N=3, df=1)
    _write_page(store, "nitrogen", "nitrogen fertiliser for lawns")
    results = search.bm25_search(["nitrogen"], top_n=5)
    assert search._cached_corpus is not None
    assert "nitrogen" in [r.slug for r in results]


# ── VectorStore ───────────────────────────────────────────────────────────────

import asyncio
from pathlib import Path

import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from synthadoc.config import SearchConfig
from synthadoc.storage.search import (
    SearchResult, VectorStore, _keyword_dominates, embedding_text, merge_results,
)


async def _store(tmp_wiki) -> VectorStore:
    store = VectorStore(tmp_wiki / ".synthadoc" / "embeddings.db")
    await store.init()
    return store


async def test_vector_store_upsert_and_load_one_row_per_page(tmp_wiki):
    store = await _store(tmp_wiki)
    await store.upsert_many([("b", "h-b", [0, 1]), ("a", "h-a", [0.5, 0.5])])
    slugs, matrix = await store.load()
    assert slugs == ["a", "b"]
    assert matrix.shape == (2, 2) and matrix[0].tolist() == [0.5, 0.5]
    assert await store.text_hashes() == {"a": "h-a", "b": "h-b"}


async def test_vector_store_upsert_replaces_a_page(tmp_wiki):
    store = await _store(tmp_wiki)
    await store.upsert_many([("a", "old", [1, 0])])
    await store.upsert_many([("a", "new", [0.3, 0.7])])
    slugs, matrix = await store.load()
    assert slugs == ["a"] and matrix[0].tolist() == pytest.approx([0.3, 0.7])
    assert await store.text_hashes() == {"a": "new"}


async def test_vector_store_delete_and_empty_load(tmp_wiki):
    store = await _store(tmp_wiki)
    await store.upsert_many([("a", "h", [1, 0])])
    await store.delete_pages(["a"])
    slugs, matrix = await store.load()
    assert slugs == [] and matrix.size == 0


async def test_vector_store_init_is_idempotent_and_drops_the_untracked_table(tmp_wiki):
    import aiosqlite
    path = tmp_wiki / ".synthadoc" / "embeddings.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(path) as db:
        await db.execute("CREATE TABLE embeddings (slug TEXT PRIMARY KEY, embedding BLOB)")
        await db.commit()
    store = VectorStore(path)
    await store.init()
    await store.init()
    async with aiosqlite.connect(path) as db:
        async with db.execute("SELECT name FROM sqlite_master WHERE type='table'") as cur:
            tables = {r[0] for r in await cur.fetchall()}
    assert tables == {"page_embeddings"}


def test_embedding_text_is_the_start_of_the_search_text():
    page = _make_page("ENIAC was the first general-purpose computer. " * 40)
    page.title, page.tags = "ENIAC", ["history"]
    text = embedding_text(page)
    assert text.startswith("ENIAC history ENIAC was")
    assert len(text) == 512


# ── helpers ───────────────────────────────────────────────────────────────────

def _res(slug, score, rank_score=None):
    return SearchResult(slug=slug, score=score, title=slug, snippet="",
                        rank_score=score if rank_score is None else rank_score)


def test_merge_results_keeps_best_per_page_and_orders_by_rank_score():
    merged = merge_results([[_res("a", 1, 0.2), _res("b", 5, 0.1)], [_res("a", 0, 0.9), _res("c", 2, 0.5)]])
    assert [(r.slug, r.rank_score) for r in merged] == [("a", 0.9), ("c", 0.5), ("b", 0.1)]
    assert len(merge_results([[_res("a", 1), _res("b", 2)]], top_n=1)) == 1


def test_keyword_dominates():
    assert _keyword_dominates([_res("a", 2.2), _res("b", 2.0)])
    assert not _keyword_dominates([_res("a", 2.05), _res("b", 2.0)])
    assert _keyword_dominates([_res("a", 1.0)])
    assert not _keyword_dominates([])


# ── HybridSearch with embeddings ─────────────────────────────────────────────

_TOPICS = ("attention", "image", "feedback")


def _fake_embed(texts):
    """Deterministic embedding: one axis per topic word, plus a small bias."""
    rows = [[float(t in text.lower()) for t in _TOPICS] + [0.01] for text in texts]
    vectors = np.array(rows, dtype=np.float32)
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def _ml_wiki(tmp_wiki) -> WikiStorage:
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "transformers", "Transformers rely on attention between tokens.")
    _write_page(store, "cnn", "Convolutional networks classify every image pixel by pixel.")
    _write_page(store, "rlhf", "RLHF tunes models with human feedback rewards.")
    return store


async def _vector_search(tmp_wiki, store=None, **cfg) -> HybridSearch:
    search = HybridSearch(store or _ml_wiki(tmp_wiki), tmp_wiki / ".synthadoc" / "embeddings.db",
                          search_cfg=SearchConfig(vector=True, **cfg))
    with patch.dict("sys.modules", {"fastembed": MagicMock()}):
        await search.init_vector()
    search._embed_texts = _fake_embed
    return search


async def test_hybrid_search_bm25_only_when_vector_disabled(tmp_wiki):
    search = HybridSearch(_ml_wiki(tmp_wiki), tmp_wiki / ".synthadoc" / "embeddings.db",
                          search_cfg=SearchConfig(vector=False))
    results = await search.hybrid_search(["attention", "transformers"])
    assert results[0].slug == "transformers"
    assert results[0].rank_score == results[0].score and results[0].similarity is None
    assert search._vector_store is None


async def test_hybrid_search_returns_empty_for_empty_wiki(tmp_wiki):
    search = HybridSearch(WikiStorage(tmp_wiki / "wiki"), tmp_wiki / ".synthadoc" / "embeddings.db",
                          search_cfg=SearchConfig(vector=False))
    assert await search.hybrid_search(["anything"]) == []


async def test_sync_embeds_each_page_once_and_only_changes_after(tmp_wiki):
    search = await _vector_search(tmp_wiki)
    assert await search.sync_embeddings() == 3
    assert search._page_slugs == ["cnn", "rlhf", "transformers"]
    assert await search.sync_embeddings() == 0
    _write_page(search._store, "rlhf", "RLHF tunes models with human feedback and a reward model.")
    search.invalidate_index()
    assert await search.sync_embeddings() == 1


async def test_sync_drops_pages_that_leave_the_corpus(tmp_wiki):
    search = await _vector_search(tmp_wiki)
    await search.sync_embeddings()
    page = search._store.read_page("cnn")
    page.status = "archived"
    search._store.write_page("cnn", page)
    search.invalidate_index()
    await search.sync_embeddings()
    assert "cnn" not in search._page_slugs
    assert "cnn" not in await search._vector_store.text_hashes()


async def test_hybrid_search_finds_a_paraphrase_bm25_misses(tmp_wiki):
    search = await _vector_search(tmp_wiki)
    await search.sync_embeddings()
    assert search.bm25_search(["picture"]) == []
    search._embed_texts = lambda texts: _fake_embed(["image" if t == "picture" else t for t in texts])
    results = await search.hybrid_search(["picture"], top_n=3)
    assert results[0].slug == "cnn"
    assert results[0].score == 0.0 and results[0].similarity == pytest.approx(1.0, abs=1e-3)
    assert results[0].title == "Cnn" and results[0].snippet


async def test_hybrid_search_keeps_a_dominant_keyword_hit_on_top(tmp_wiki):
    search = await _vector_search(tmp_wiki)
    await search.sync_embeddings()
    # Embeddings prefer the attention page; BM25 has one clear match for "rlhf".
    search._embed_texts = lambda texts: _fake_embed(["attention"] * len(texts))
    results = await search.hybrid_search(["rlhf"], top_n=3)
    assert results[0].slug == "rlhf" and results[0].score > 0
    assert results[0].rank_score > 1.0


async def test_hybrid_search_respects_scope_and_corpus(tmp_wiki):
    search = await _vector_search(tmp_wiki)
    await search.sync_embeddings()
    scoped = await search.hybrid_search(["attention"], top_n=3, scoped_slugs=["cnn", "rlhf"])
    assert {r.slug for r in scoped} <= {"cnn", "rlhf"}
    page = search._store.read_page("transformers")
    page.status = "contradicted"
    search._store.write_page("transformers", page)
    search._cached_corpus = None   # corpus changes before the embeddings re-sync
    assert "transformers" not in [r.slug for r in await search.hybrid_search(["attention"], top_n=3)]


async def test_hybrid_search_is_bm25_only_until_the_first_sync_and_schedules_it(tmp_wiki):
    search = await _vector_search(tmp_wiki)
    results = await search.hybrid_search(["attention"], top_n=3)
    assert [r.slug for r in results] == ["transformers"]
    await search.wait_for_embedding_sync()
    assert search._matrix is not None and not search._vectors_dirty


async def test_invalidate_index_schedules_a_resync_on_the_next_search(tmp_wiki):
    search = await _vector_search(tmp_wiki)
    await search.sync_embeddings()
    _write_page(search._store, "gan", "GANs generate an image from noise.")
    search.invalidate_index()
    await search.hybrid_search(["image"], top_n=3)
    await search.wait_for_embedding_sync()
    assert "gan" in search._page_slugs


async def test_failed_background_sync_is_logged_not_raised(tmp_wiki, caplog):
    search = await _vector_search(tmp_wiki)
    def boom(texts):
        raise RuntimeError("model download failed")
    search._embed_texts = boom
    search.schedule_embedding_sync()
    await search.wait_for_embedding_sync()
    assert "embedding sync failed" in caplog.text
    assert [r.slug for r in await search.hybrid_search(["attention"], top_n=3)] == ["transformers"]


async def test_close_cancels_a_running_sync(tmp_wiki):
    search = await _vector_search(tmp_wiki)
    started = asyncio.Event()
    async def slow_sync():
        started.set()
        await asyncio.sleep(60)
    search.sync_embeddings = slow_sync
    search.schedule_embedding_sync()
    await started.wait()
    await search.close()
    assert search._sync_task.cancelled()


def test_vectors_requested_for_true_and_auto_only(tmp_wiki):
    def requested(mode):
        return HybridSearch(WikiStorage(tmp_wiki / "wiki"), tmp_wiki / "e.db",
                            search_cfg=SearchConfig(vector=mode)).vectors_requested()
    assert requested(True) and requested("auto")
    assert not requested(False)
    assert not HybridSearch(WikiStorage(tmp_wiki / "wiki"), tmp_wiki / "e.db").vectors_requested()


@pytest.mark.parametrize("mode", [True, "auto"])
async def test_init_vector_raises_when_fastembed_is_missing(tmp_wiki, mode):
    search = HybridSearch(WikiStorage(tmp_wiki / "wiki"), tmp_wiki / "e.db",
                          search_cfg=SearchConfig(vector=mode))
    with patch.dict("sys.modules", {"fastembed": None}):
        with pytest.raises(ImportError, match="synthadoc\\[vectors\\]"):
            await search.init_vector()
    assert search._vector_store is None


async def test_init_vector_is_a_noop_when_disabled(tmp_wiki):
    search = HybridSearch(WikiStorage(tmp_wiki / "wiki"), tmp_wiki / "e.db",
                          search_cfg=SearchConfig(vector=False))
    await search.init_vector()
    assert search._vector_store is None


def _model_files(folder):
    from synthadoc.storage.search import _EMBED_MODEL_FILES
    folder.mkdir(parents=True, exist_ok=True)
    for name in _EMBED_MODEL_FILES:
        (folder / name).write_text("x")
    return folder


def test_get_embed_model_creates_and_caches_model(tmp_wiki, monkeypatch):
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(tmp_wiki / "models"))
    _model_files(tmp_wiki / "models" / "bge-small-en-v1.5")
    search = HybridSearch(WikiStorage(tmp_wiki / "wiki"), tmp_wiki / "e.db",
                          search_cfg=SearchConfig(vector=True))
    mock_te_cls = MagicMock(return_value=MagicMock())
    with patch.dict("sys.modules", {"fastembed": MagicMock(TextEmbedding=mock_te_cls)}):
        assert search._get_embed_model() is search._get_embed_model()
    mock_te_cls.assert_called_once()


def test_embed_model_is_cached_under_synthadoc_home_unless_overridden(tmp_wiki, monkeypatch):
    from synthadoc.storage.search import embed_model_cache_dir, embed_model_dir
    monkeypatch.delenv("FASTEMBED_CACHE_PATH", raising=False)
    assert embed_model_cache_dir() == Path.home() / ".synthadoc" / "models"
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(tmp_wiki / "models"))
    assert embed_model_cache_dir() == tmp_wiki / "models"
    assert embed_model_dir() == tmp_wiki / "models" / "bge-small-en-v1.5"


def test_embed_model_loads_from_its_plain_folder(tmp_wiki, monkeypatch):
    from synthadoc.storage.search import load_embed_model
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(tmp_wiki / "models"))
    folder = _model_files(tmp_wiki / "models" / "bge-small-en-v1.5")
    text_embedding = MagicMock()
    with patch.dict("sys.modules", {"fastembed": MagicMock(TextEmbedding=text_embedding)}), \
         patch("huggingface_hub.snapshot_download") as download:
        load_embed_model()
    download.assert_not_called()
    assert text_embedding.call_args.kwargs == {"specific_model_path": str(folder)}


def test_embed_model_reuses_a_hub_cache_from_earlier_versions(tmp_wiki, monkeypatch):
    from synthadoc.storage.search import load_embed_model
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(tmp_wiki / "models"))
    snapshot = _model_files(tmp_wiki / "models" / "models--Qdrant--bge-small-en-v1.5-onnx-Q"
                            / "snapshots" / "aa8f8b0")
    text_embedding = MagicMock()
    with patch.dict("sys.modules", {"fastembed": MagicMock(TextEmbedding=text_embedding)}), \
         patch("huggingface_hub.snapshot_download") as download:
        load_embed_model()
    download.assert_not_called()
    assert text_embedding.call_args.kwargs == {"specific_model_path": str(snapshot)}


def test_embed_model_downloads_plain_files_the_first_time(tmp_wiki, monkeypatch):
    """No symlinks: Windows refuses them without Developer Mode (WinError 1314)."""
    from synthadoc.storage.search import _EMBED_MODEL_FILES, load_embed_model
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(tmp_wiki / "models"))
    folder = tmp_wiki / "models" / "bge-small-en-v1.5"
    text_embedding = MagicMock()
    with patch.dict("sys.modules", {"fastembed": MagicMock(TextEmbedding=text_embedding)}), \
         patch("huggingface_hub.snapshot_download") as download:
        load_embed_model()
    download.assert_called_once_with("Qdrant/bge-small-en-v1.5-onnx-Q", local_dir=str(folder),
                                     allow_patterns=list(_EMBED_MODEL_FILES))
    assert text_embedding.call_args.kwargs == {"specific_model_path": str(folder)}


def test_embed_texts_returns_normalised_rows(tmp_wiki):
    search = HybridSearch(WikiStorage(tmp_wiki / "wiki"), tmp_wiki / "e.db",
                          search_cfg=SearchConfig(vector=True))
    model = MagicMock()
    model.embed.return_value = [np.array([3.0, 4.0]), np.array([0.0, 2.0])]
    with patch.object(search, "_get_embed_model", return_value=model):
        vectors = search._embed_texts(["a", "b"])
    np.testing.assert_allclose(vectors, [[0.6, 0.8], [0.0, 1.0]], rtol=1e-6)


# ── routing-scoped search ─────────────────────────────────────────────────────

def test_bm25_scoped_slugs_limits_results(tmp_wiki):
    """bm25_search with scoped_slugs must only return results from the given slugs."""
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "alan-turing", "Alan Turing developed the theoretical basis of computation.")
    _write_page(store, "grace-hopper", "Grace Hopper pioneered compiler development.")
    _write_page(store, "eniac", "ENIAC was the first general-purpose electronic computer.")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")

    results = search.bm25_search(["computer computation"], top_n=5,
                                  scoped_slugs=["alan-turing", "grace-hopper"])
    slugs = [r.slug for r in results]
    assert "eniac" not in slugs
    assert all(s in ("alan-turing", "grace-hopper") for s in slugs)


def test_bm25_scoped_slugs_empty_scope_returns_empty(tmp_wiki):
    """bm25_search with scoped_slugs=[] must return an empty list."""
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "alan-turing", "Alan Turing developed theoretical computation.")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    results = search.bm25_search(["computation"], top_n=5, scoped_slugs=[])
    assert results == []


def test_bm25_scoped_slugs_none_searches_full_corpus(tmp_wiki):
    """bm25_search with scoped_slugs=None must search the full corpus."""
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "alan-turing", "Alan Turing developed theoretical computation.")
    _write_page(store, "eniac", "ENIAC was the first electronic computer.")
    _write_page(store, "unrelated", "Cooking is a great hobby for relaxation.")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    results = search.bm25_search(["computation computer"], top_n=5, scoped_slugs=None)
    slugs = [r.slug for r in results]
    assert "alan-turing" in slugs or "eniac" in slugs


@pytest.mark.asyncio
async def test_hybrid_search_scoped_slugs_limits_results(tmp_wiki):
    """hybrid_search with scoped_slugs must restrict candidates to the given slugs."""
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "alan-turing", "Alan Turing developed the theoretical basis of computation.")
    _write_page(store, "grace-hopper", "Grace Hopper pioneered compiler development.")
    _write_page(store, "eniac", "ENIAC was the first general-purpose electronic computer.")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")

    results = await search.hybrid_search(
        ["computer computation"], top_n=5,
        scoped_slugs=["alan-turing", "grace-hopper"]
    )
    slugs = [r.slug for r in results]
    assert "eniac" not in slugs


# ── BM25 TF fallback tests ────────────────────────────────────────────────────

def test_bm25_tf_fallback_single_page_corpus(tmp_wiki):
    """1-page corpus: BM25 IDF ≤ 0 → TF fallback returns the page with tf_fallback=True."""
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "plan", "The maintenance capex ratio is the core metric.")

    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    results = search.bm25_search(["maintenance", "capex"])

    assert results, "Expected at least one result via TF fallback"
    assert results[0].slug == "plan"
    assert results[0].tf_fallback is True


def test_bm25_tf_fallback_two_page_corpus(tmp_wiki):
    """2-page corpus where query term is in one page → TF fallback returns that page."""
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "capex", "capex maintenance plan")
    _write_page(store, "revenue", "revenue growth strategy")

    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    results = search.bm25_search(["capex", "maintenance"])

    assert results
    assert results[0].slug == "capex"
    assert results[0].tf_fallback is True


def test_bm25_no_tf_fallback_when_query_absent(tmp_wiki):
    """1-page corpus where query term is absent → TF = 0 for all → empty result (correct gap)."""
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "plan", "revenue and growth")

    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    results = search.bm25_search(["capex", "maintenance"])

    assert results == [], "Term not in corpus → should return empty (correct gap)"


def test_bm25_three_page_corpus_no_tf_fallback(tmp_wiki):
    """3-page corpus: BM25 IDF > 0 for discriminating terms → no TF fallback."""
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "capex", "capex maintenance plan formula")
    _write_page(store, "revenue", "revenue growth strategy")
    _write_page(store, "fcf", "free cash flow operating")

    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    results = search.bm25_search(["capex"])

    assert results
    assert results[0].slug == "capex"
    assert results[0].tf_fallback is False


def test_searchresult_tf_fallback_defaults_false():
    """SearchResult.tf_fallback defaults to False for backward compatibility."""
    from synthadoc.storage.search import SearchResult
    r = SearchResult(slug="test", score=1.0, title="T", snippet="s")
    assert r.tf_fallback is False


# ── Lifecycle-aware corpus filter ─────────────────────────────────────────────

def _make_status_page(content: str, status: str) -> WikiPage:
    return WikiPage(
        title=content[:20], tags=[], content=content,
        status=status, confidence="high", sources=[]
    )


def test_corpus_excludes_contradicted_pages(tmp_wiki):
    """contradicted pages must not appear in BM25 results."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("clean", _make_status_page(
        "The transformer architecture uses self-attention.", "active"))
    store.write_page("dirty", _make_status_page(
        "The transformer architecture uses self-attention.", "contradicted"))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    results = search.bm25_search(["transformer", "attention"], top_n=10)
    slugs = [r.slug for r in results]
    assert "clean" in slugs
    assert "dirty" not in slugs


def test_corpus_excludes_archived_pages(tmp_wiki):
    """archived pages must not appear in BM25 results."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("live", _make_status_page(
        "Backpropagation trains neural networks.", "active"))
    store.write_page("retired", _make_status_page(
        "Backpropagation trains neural networks.", "archived"))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    results = search.bm25_search(["backpropagation", "neural"], top_n=10)
    slugs = [r.slug for r in results]
    assert "live" in slugs
    assert "retired" not in slugs


def test_corpus_excludes_draft_pages(tmp_wiki):
    """draft pages must not appear in BM25 results."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("published", _make_status_page(
        "Support vector machines classify data points.", "active"))
    store.write_page("wip", _make_status_page(
        "Support vector machines classify data points.", "draft"))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    results = search.bm25_search(["support", "vector", "machines"], top_n=10)
    slugs = [r.slug for r in results]
    assert "published" in slugs
    assert "wip" not in slugs


def test_corpus_includes_stale_pages(tmp_wiki):
    """stale pages must still appear in BM25 results (outdated but valid)."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("old-but-valid", _make_status_page(
        "Random forests aggregate decision tree predictions.", "stale"))
    store.write_page("padding-1", _make_status_page("Unrelated padding one.", "active"))
    store.write_page("padding-2", _make_status_page("Unrelated padding two.", "active"))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    results = search.bm25_search(["random", "forest", "decision", "tree"], top_n=10)
    assert any(r.slug == "old-but-valid" for r in results)


def test_corpus_cache_invalidated_on_status_change(tmp_wiki):
    """After a page transitions to contradicted and the cache is dropped,
    the next search excludes it."""
    store = WikiStorage(tmp_wiki / "wiki")
    content = "Gradient descent minimises the loss function iteratively."
    store.write_page("grad-page", _make_status_page(content, "active"))
    store.write_page("pad-1", _make_status_page("Unrelated padding alpha.", "active"))
    store.write_page("pad-2", _make_status_page("Unrelated padding beta.", "active"))

    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")

    # First search: page is active → should be found
    results_before = search.bm25_search(["gradient", "descent", "loss"], top_n=10)
    assert any(r.slug == "grad-page" for r in results_before)

    # Simulate page being transitioned to contradicted
    page = store.read_page("grad-page")
    page.status = "contradicted"
    store.write_page("grad-page", page)

    # Invalidate the in-memory corpus cache
    search.invalidate_index()

    # Second search: page is contradicted → must not appear
    results_after = search.bm25_search(["gradient", "descent", "loss"], top_n=10)
    assert not any(r.slug == "grad-page" for r in results_after)


# ── BM25 index cache ─────────────────────────────────────────────────────────

def _three_page_search(tmp_wiki) -> HybridSearch:
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "chlorine", "chlorine treats algae in pools")
    _write_page(store, "ph", "pH balance is important for pools")
    _write_page(store, "nitrogen", "nitrogen fertiliser for lawns")
    return HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")


def test_bm25_index_reused_across_queries(tmp_wiki, monkeypatch):
    """The BM25 index is built once per scope, not once per query."""
    import synthadoc.storage.search as search_mod
    builds = []
    real = search_mod.BM25Okapi
    monkeypatch.setattr(search_mod, "BM25Okapi", lambda corpus: builds.append(len(corpus)) or real(corpus))
    search = _three_page_search(tmp_wiki)

    search.bm25_search(["chlorine"])
    search.bm25_search(["pools"])
    search.bm25_search(["pools"], scoped_slugs=["chlorine", "ph"])
    search.bm25_search(["algae"], scoped_slugs=["ph", "chlorine"])   # same scope, any order
    assert builds == [3, 2]


def test_scoped_search_only_returns_scoped_pages(tmp_wiki):
    search = _three_page_search(tmp_wiki)
    search.bm25_search(["pools"])                     # warm the full-corpus index
    slugs = {r.slug for r in search.bm25_search(["pools", "lawns"], scoped_slugs=["ph", "nitrogen"])}
    assert slugs <= {"ph", "nitrogen"} and slugs
    assert search.bm25_search(["pools"], scoped_slugs=["no-such-page"]) == []


def test_invalidate_index_drops_built_indexes(tmp_wiki):
    search = _three_page_search(tmp_wiki)
    search.bm25_search(["chlorine"])
    search.bm25_search(["chlorine"], scoped_slugs=["chlorine"])
    assert len(search._bm25_indexes) == 2
    _write_page(search._store, "copper", "copper algaecide for pools")
    search.invalidate_index()
    assert search._bm25_indexes == {}
    assert "copper" in [r.slug for r in search.bm25_search(["copper"])]


def test_bm25_index_cache_is_bounded(tmp_wiki):
    import synthadoc.storage.search as search_mod
    search = _three_page_search(tmp_wiki)
    for i in range(search_mod._MAX_CACHED_SCOPES + 3):
        search.bm25_search(["pools"], scoped_slugs=["chlorine", "ph", f"missing-{i}"])
    assert len(search._bm25_indexes) == search_mod._MAX_CACHED_SCOPES


async def test_hybrid_search_embeds_a_repeated_query_once(tmp_wiki):
    search = await _vector_search(tmp_wiki)
    await search.sync_embeddings()
    calls = []
    search._embed_texts = lambda texts: calls.append(texts) or _fake_embed(texts)
    first = await search.hybrid_search(["attention"], top_n=3)
    again = await search.hybrid_search(["attention"], top_n=3)
    assert calls == [["attention"]]
    assert [r.slug for r in again] == [r.slug for r in first]


async def test_query_embedding_cache_drops_the_least_recently_used(tmp_wiki, monkeypatch):
    import synthadoc.storage.search as search_mod
    monkeypatch.setattr(search_mod, "_QUERY_CACHE_SIZE", 2)
    search = await _vector_search(tmp_wiki)
    await search.sync_embeddings()
    calls = []
    search._embed_texts = lambda texts: calls.append(texts[0]) or _fake_embed(texts)
    for q in ("attention", "image", "attention", "feedback", "image"):
        await search.hybrid_search([q], top_n=3)
    # "attention" was used again before "feedback" arrived, so "image" was the one dropped.
    assert calls == ["attention", "image", "feedback", "image"]
    assert list(search._query_vecs) == ["feedback", "image"]


async def test_query_embedding_runs_while_bm25_searches(tmp_wiki):
    import threading
    search = await _vector_search(tmp_wiki)
    await search.sync_embeddings()
    started = threading.Event()

    def embed(texts):
        started.set()
        return _fake_embed(texts)

    bm25 = search.bm25_search
    overlapped = []

    def slow_bm25(*args, **kwargs):
        overlapped.append(started.wait(timeout=2))   # embedding already submitted?
        return bm25(*args, **kwargs)

    search._embed_texts = embed
    search.bm25_search = slow_bm25
    await search.hybrid_search(["attention"], top_n=3)
    assert overlapped == [True]


def test_is_mostly_cjk_counts_cjk_against_latin_letters():
    from synthadoc.storage.search import is_mostly_cjk
    assert is_mostly_cjk("国家法定节假日共多少天")
    assert is_mostly_cjk("Konrad Zuse 是德国工程师，他在1941年完成了Z3计算机。")   # names in Latin, prose in Chinese
    assert is_mostly_cjk("チューリングはエニグマを解読した")
    assert not is_mostly_cjk("Alan Turing broke the Enigma cipher at Bletchley Park (布莱切利园).")
    assert not is_mostly_cjk("Numbers only: 1941, 1945.")


async def test_sync_embeds_only_pages_that_are_not_mostly_cjk(tmp_wiki, caplog):
    import logging
    store = _ml_wiki(tmp_wiki)
    _write_page(store, "chunjie", "春节是中国最重要的传统节日，放假三天。")
    search = await _vector_search(tmp_wiki, store=store)
    with caplog.at_level(logging.INFO, logger="synthadoc.storage.search"):
        assert await search.sync_embeddings() == 3
    assert search._page_slugs == ["cnn", "rlhf", "transformers"]
    assert "1 mostly Chinese/Japanese/Korean page(s) left to keyword search" in caplog.text
    assert [r.slug for r in search.bm25_search(["春节"])] == ["chunjie"]    # still found by keyword


async def test_a_page_rewritten_in_chinese_loses_its_embedding(tmp_wiki):
    search = await _vector_search(tmp_wiki)
    await search.sync_embeddings()
    _write_page(search._store, "rlhf", "基于人类反馈的强化学习用奖励模型来调整语言模型。")
    search.invalidate_index()
    await search.sync_embeddings()
    assert "rlhf" not in search._page_slugs
    assert "rlhf" not in await search._vector_store.text_hashes()


async def test_cjk_query_is_answered_by_bm25_alone(tmp_wiki):
    store = _ml_wiki(tmp_wiki)
    _write_page(store, "attention-zh", "注意力机制 attention 让模型关注重要的词。")
    search = await _vector_search(tmp_wiki, store=store)
    await search.sync_embeddings()
    calls = []
    search._embed_texts = lambda texts: calls.append(texts) or _fake_embed(texts)
    results = await search.hybrid_search(["注意力机制"], top_n=3)
    assert calls == []
    assert [r.slug for r in results] == [r.slug for r in search.bm25_search(["注意力机制"], top_n=3)]
    assert all(r.similarity is None for r in results)


async def test_a_wiki_of_cjk_pages_falls_back_to_bm25(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "chunjie", "春节是中国最重要的传统节日。")
    _write_page(store, "zhongqiu", "中秋节人们赏月吃月饼。")
    search = await _vector_search(tmp_wiki, store=store)
    assert await search.sync_embeddings() == 0
    assert search._matrix is None
    results = await search.hybrid_search(["moon", "festival"], top_n=3)
    assert results == search.bm25_search(["moon", "festival"], top_n=3)
