# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""
Query cache performance tests — validates SLOs from the v0.7.0 design doc.

Groups:
  1. Isolated cache layer latency     (P50 / P95 / P99 on SQLite reads and writes)
  2. Hit vs miss latency              (simulated 50ms LLM; proves structure, not absolute numbers)
  3. Concurrent readers               (10 / 50 / 100 concurrent asyncio tasks)
  4. Cache vs no-cache throughput     (queries/sec at increasing concurrency)
  5. Epoch invalidation cost          (O(1) key recomputation)
  6. pytest-benchmark variants        (steady-state throughput; run with --benchmark-only)

Run modes:
  # CI: assert SLOs only (no benchmark timing noise)
  pytest tests/performance/test_query_cache_perf.py --benchmark-disable -v

  # Local: full benchmark numbers
  pytest tests/performance/test_query_cache_perf.py --benchmark-only -v

The four charts in docs/png/cache-perf/ are drawn from the same measurements by a script,
not a test: python -m benchmarks.cache_perf (see benchmarks/README.md).
"""
import asyncio
import os
import platform
import statistics
import time

import pytest


# ProactorEventLoop (IOCP) deadlocks when aiosqlite's background thread
# signals 500+ rapid-fire completion callbacks in the tight read-latency loop.
# Scope the SelectorEventLoop fix to this module only so other async perf
# tests that relied on ProactorEventLoop are not disturbed.
if platform.system() == "Windows":
    import warnings
    warnings.filterwarnings("ignore", ".*WindowsSelectorEventLoopPolicy.*", DeprecationWarning)
    warnings.filterwarnings("ignore", ".*set_event_loop_policy.*", DeprecationWarning)

@pytest.fixture
def asyncio_event_loop_policy():
    if platform.system() == "Windows":
        return asyncio.WindowsSelectorEventLoopPolicy() # type: ignore
    return asyncio.DefaultEventLoopPolicy()

from synthadoc.core.cache import CacheManager, make_query_cache_key

# The constants, the sample result and the two helpers are shared with the chart script
# (benchmarks/cache_perf.py) so the tests and the published charts measure the same thing.
from benchmarks.cache_perf import (
    QUESTIONS,
    RESULT as _RESULT,
    SIMULATED_LLM_MS,
    SIMULATED_PHASE1_MS,
    make_cache as _make_cache,
    percentile as _percentile,
)


# ── helpers ───────────────────────────────────────────────────────────────────


def _new_sync_loop() -> asyncio.AbstractEventLoop:
    # ProactorEventLoop (IOCP) on Windows hangs when run_until_complete() is
    # called repeatedly in a tight loop alongside aiosqlite's worker thread.
    # SelectorEventLoop avoids this; it works correctly on all Python versions.
    if platform.system() == "Windows":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()


# ── Group 1: Isolated cache layer latency ─────────────────────────────────────

@pytest.mark.asyncio
async def test_cache_read_latency_p99(tmp_path):
    """
    get_query() P99 must be under 10ms.

    Populates 200 distinct entries then measures 500 reads to exercise
    the full SQLite path (open connection → SELECT → parse JSON → close).
    This is the canonical proof that cache hits add negligible overhead
    compared to any real LLM call (2–10s).
    """
    cache = await _make_cache(tmp_path)
    try:
        keys = []
        for i in range(200):
            k = make_query_cache_key(QUESTIONS[i % len(QUESTIONS)], epoch=i % 20)
            await cache.set_query(k, epoch=i % 20, result=_RESULT)
            keys.append(k)

        latencies_ms = []
        for i in range(500):
            k = keys[i % len(keys)]
            t0 = time.perf_counter()
            result = await cache.get_query(k)
            latencies_ms.append((time.perf_counter() - t0) * 1000)
            assert result is not None

        p50 = statistics.median(latencies_ms)
        p95 = _percentile(latencies_ms, 0.95)
        p99 = _percentile(latencies_ms, 0.99)
        print(f"\n  [cache read] P50={p50:.2f}ms  P95={p95:.2f}ms  P99={p99:.2f}ms  (n=500)")
        assert p99 < 10.0, f"Cache read P99 {p99:.2f}ms exceeds 10ms SLO"
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_cache_write_latency_p95(tmp_path):
    """
    set_query() P95 must be under 15ms on Linux.

    Windows/macOS CI runners have high write-latency variance (antivirus,
    kernel buffer flushes, shared CI disk activity) that makes P95 SLOs
    unreliable regardless of the threshold chosen. On non-Linux the test
    still runs and prints numbers — it just does not assert.
    """
    cache = await _make_cache(tmp_path)
    try:
        latencies_ms = []
        for i in range(200):
            k = make_query_cache_key(QUESTIONS[i % len(QUESTIONS)], epoch=0)
            t0 = time.perf_counter()
            await cache.set_query(k, epoch=0, result=_RESULT)
            latencies_ms.append((time.perf_counter() - t0) * 1000)

        p50 = statistics.median(latencies_ms)
        p95 = _percentile(latencies_ms, 0.95)
        print(f"\n  [cache write] P50={p50:.2f}ms  P95={p95:.2f}ms  (n=200)")
        if platform.system() == "Linux" and not os.environ.get("CI"):
            assert p95 < 15.0, f"Cache write P95 {p95:.2f}ms exceeds 15ms SLO"
        else:
            print(f"  (P95 SLO not enforced on {platform.system()} CI={os.environ.get('CI', 'unset')} — write tail latency too noisy on shared CI)")
    finally:
        await cache.close()


# ── Group 2: Hit vs miss latency (simulated LLM) ──────────────────────────────

@pytest.mark.asyncio
async def test_cache_hit_makes_zero_llm_calls(tmp_path):
    """
    A cache hit must produce exactly 0 LLM invocations.
    First query (miss) calls once; second identical query (hit) calls zero.
    """
    llm_calls = 0

    async def fake_llm() -> dict:
        nonlocal llm_calls
        llm_calls += 1
        await asyncio.sleep(SIMULATED_LLM_MS / 1000)
        return _RESULT.copy()

    cache = await _make_cache(tmp_path)
    try:
        k = make_query_cache_key("What is Moore's Law?", epoch=0)

        # Miss — LLM fires
        if await cache.get_query(k) is None:
            result = await fake_llm()
            await cache.set_query(k, epoch=0, result=result)
        first_calls = llm_calls

        llm_calls = 0
        # Hit — LLM must NOT fire
        if await cache.get_query(k) is None:
            await fake_llm()

        assert first_calls == 1, f"First query should call LLM once, called {first_calls}"
        assert llm_calls == 0, f"Cache hit should make 0 LLM calls, made {llm_calls}"
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_cache_hit_vs_miss_latency(tmp_path):
    """
    Cache hit P50 < 10ms.  Miss P50 ≈ phase1 + LLM (70ms simulated).
    Expected speedup > 5x — real-world speedup with a slow provider is 50–200x.

    The simulated LLM (50ms) is conservative.  Production queries on
    reasoning models (MiniMax M2, o3) regularly take 10–30s, giving
    cache speedups of 100x+.
    """
    cache = await _make_cache(tmp_path)
    try:
        k = make_query_cache_key("What is Moore's Law?", epoch=0)

        async def simulate(use_cache: bool) -> float:
            t0 = time.perf_counter()
            if use_cache:
                hit = await cache.get_query(k)
                if hit is not None:
                    return (time.perf_counter() - t0) * 1000
            await asyncio.sleep(SIMULATED_PHASE1_MS / 1000)
            await asyncio.sleep(SIMULATED_LLM_MS / 1000)
            await cache.set_query(k, epoch=0, result=_RESULT.copy())
            return (time.perf_counter() - t0) * 1000

        miss_samples = [await simulate(use_cache=False) for _ in range(10)]
        hit_samples = [await simulate(use_cache=True) for _ in range(30)]

        miss_p50 = statistics.median(miss_samples)
        hit_p50 = statistics.median(hit_samples)
        speedup = miss_p50 / max(hit_p50, 0.001)

        print(
            f"\n  [hit vs miss]"
            f"  miss P50={miss_p50:.1f}ms"
            f"  hit P50={hit_p50:.1f}ms"
            f"  speedup={speedup:.1f}x"
            f"  (simulated LLM={SIMULATED_LLM_MS}ms)"
        )
        assert hit_p50 < 10.0, f"Cache hit P50 {hit_p50:.1f}ms exceeds 10ms SLO"
        assert speedup > 5.0, f"Speedup {speedup:.1f}x is below 5x minimum"
    finally:
        await cache.close()


# ── Group 3: Concurrent readers ───────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("concurrency", [10, 50, 100])
async def test_concurrent_cache_reads(tmp_path, concurrency):
    """
    N concurrent get_query() calls.  Measures per-query P95 under load.

    With a persistent connection, all concurrent reads go through one
    aiosqlite connection (serialised by its background thread). The
    connection-open overhead is paid once at init(), not per-call.

    SLOs (single persistent connection, SSD):
      Linux bare-metal: 10→<10ms, 50→<20ms, 100→<40ms
      CI (shared runners): 3× for n≤50, 6× for n=100 — tail latency is more
      sensitive to runner load spikes at high concurrency.
    """
    cache = await _make_cache(tmp_path)
    try:
        k = make_query_cache_key("What is Moore's Law?", epoch=0)
        await cache.set_query(k, epoch=0, result=_RESULT)

        async def one_read() -> tuple[float, bool]:
            t0 = time.perf_counter()
            result = await cache.get_query(k)
            return (time.perf_counter() - t0) * 1000, result is not None

        wall_t0 = time.perf_counter()
        outcomes = await asyncio.gather(*[one_read() for _ in range(concurrency)])
        wall_ms = (time.perf_counter() - wall_t0) * 1000

        latencies = [o[0] for o in outcomes]
        all_hits = all(o[1] for o in outcomes)
        p50 = statistics.median(latencies)
        p95 = _percentile(latencies, 0.95)
        throughput = concurrency / (wall_ms / 1000)

        print(
            f"\n  [concurrent reads n={concurrency:>3}]"
            f"  P50={p50:.1f}ms  P95={p95:.1f}ms"
            f"  wall={wall_ms:.0f}ms  throughput={throughput:.0f} q/s"
        )
        assert all_hits, "One or more concurrent reads returned a cache miss (data race?)"
        # Bare-metal Linux SLOs; CI runners get extra headroom for shared-disk /
        # virtualised SQLite overhead.  Windows CI observed ~26× spikes due to
        # IOCP/thread overhead.  Linux shared runners observed up to ~10× spikes
        # at all concurrency levels (189ms P95 at n=50 vs 20ms base).
        import os as _os
        base_slo = {10: 10.0, 50: 20.0, 100: 40.0}[concurrency]
        on_ci = _os.environ.get("CI") == "true" or platform.system() != "Linux"
        if platform.system() == "Windows":
            ci_multiplier = 30
        else:
            ci_multiplier = 15
        slo = base_slo * ci_multiplier if on_ci else base_slo
        assert p95 < slo, f"P95 {p95:.1f}ms exceeds {slo:.0f}ms SLO at concurrency={concurrency}"
    finally:
        await cache.close()


# ── Group 4: Cache vs no-cache throughput ─────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("concurrency", [10])
async def test_concurrent_cache_vs_no_cache_throughput(tmp_path, concurrency):
    """
    Compares queries/sec: all-cache-hit vs all-cache-miss (simulated LLM).

    Tested at n=10. At higher concurrency (n=50+), concurrent aiosqlite.connect()
    calls can serialize enough that cache wall time exceeds parallel asyncio sleeps —
    WAL contention at that scale is documented by test_concurrent_cache_reads.

    The cache path should always win at n=10 on any runner.
    """
    cache = await _make_cache(tmp_path)
    try:
        questions = (QUESTIONS * ((concurrency // len(QUESTIONS)) + 1))[:concurrency]

        for q in set(questions):
            k = make_query_cache_key(q, epoch=0)
            await cache.set_query(k, epoch=0, result=_RESULT.copy())

        async def with_cache(q: str) -> float:
            t0 = time.perf_counter()
            k = make_query_cache_key(q, epoch=0)
            if await cache.get_query(k) is None:
                await asyncio.sleep((SIMULATED_PHASE1_MS + SIMULATED_LLM_MS) / 1000)
                await cache.set_query(k, epoch=0, result=_RESULT.copy())
            return (time.perf_counter() - t0) * 1000

        async def no_cache(q: str) -> float:
            t0 = time.perf_counter()
            await asyncio.sleep((SIMULATED_PHASE1_MS + SIMULATED_LLM_MS) / 1000)
            return (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        cached_lats = await asyncio.gather(*[with_cache(q) for q in questions])
        cached_wall = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        nocache_lats = await asyncio.gather(*[no_cache(q) for q in questions])
        nocache_wall = (time.perf_counter() - t0) * 1000

        cached_qps = concurrency / (cached_wall / 1000)
        nocache_qps = concurrency / (nocache_wall / 1000)
        cached_p95 = _percentile(list(cached_lats), 0.95)
        nocache_p95 = _percentile(list(nocache_lats), 0.95)
        speedup = nocache_wall / max(cached_wall, 0.001)

        print(
            f"\n  [throughput n={concurrency:>3}]"
            f"  cache: {cached_qps:6.0f} q/s  P95={cached_p95:.1f}ms"
            f"  | no-cache: {nocache_qps:6.0f} q/s  P95={nocache_p95:.1f}ms"
            f"  | speedup={speedup:.1f}x"
        )
        assert cached_qps > nocache_qps, (
            f"Cache ({cached_qps:.0f} q/s) not faster than no-cache ({nocache_qps:.0f} q/s)"
        )
    finally:
        await cache.close()


# ── Group 5: Epoch invalidation cost ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_epoch_bump_invalidates_instantly(tmp_path):
    """
    Epoch bump is a pure in-memory key recomputation — should be sub-millisecond.
    Old epoch key becomes unreachable immediately; no database write needed.
    """
    cache = await _make_cache(tmp_path)
    try:
        q = "What is Moore's Law?"

        k0 = make_query_cache_key(q, epoch=0)
        await cache.set_query(k0, epoch=0, result=_RESULT)

        t0 = time.perf_counter()
        k1 = make_query_cache_key(q, epoch=1)   # simulates wiki_epoch += 1
        bump_ms = (time.perf_counter() - t0) * 1000

        old_via_new_key = await cache.get_query(k1)  # epoch=1 key doesn't exist
        old_still_present = await cache.get_query(k0)  # epoch=0 entry physically still there

        print(f"\n  [epoch bump]  key recomputation={bump_ms:.4f}ms  (sub-ms O(1) operation)")
        assert old_via_new_key is None,     "New epoch key should not exist before first fresh query"
        assert old_still_present is not None, "Old epoch key still physically present — lazy cleanup"
        assert bump_ms < 1.0,               f"Key recomputation took {bump_ms:.3f}ms — should be sub-ms"
    finally:
        await cache.close()


# ── Group 6: pytest-benchmark steady-state variants ───────────────────────────

def test_cache_read_benchmark(benchmark, tmp_path):
    """Steady-state get_query() throughput — run with --benchmark-only."""
    loop = _new_sync_loop()
    cache = loop.run_until_complete(_make_cache(tmp_path))
    k = make_query_cache_key("What is Moore's Law?", epoch=0)
    loop.run_until_complete(cache.set_query(k, epoch=0, result=_RESULT))

    def _read():
        return loop.run_until_complete(cache.get_query(k))

    result = benchmark(_read)
    loop.run_until_complete(cache.close())
    loop.close()
    assert result is not None


def test_cache_write_benchmark(benchmark, tmp_path):
    """Steady-state set_query() throughput — run with --benchmark-only."""
    loop = _new_sync_loop()
    cache = loop.run_until_complete(_make_cache(tmp_path))
    counter = [0]

    def _write():
        counter[0] += 1
        k = make_query_cache_key("test", epoch=counter[0])
        loop.run_until_complete(cache.set_query(k, epoch=counter[0], result=_RESULT))

    benchmark(_write)
    loop.run_until_complete(cache.close())
    loop.close()
