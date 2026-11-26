# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Query-cache performance charts.

Measures the query cache (read latency, hit versus miss, concurrent readers, throughput
with and without the cache) and draws four PNG charts. The pass/fail checks on the same
numbers are the tests in ``tests/performance/test_query_cache_perf.py``; this module is
only for regenerating the charts.

    python -m benchmarks.cache_perf                       # writes docs/png/cache-perf/ (~30 s)
    python -m benchmarks.cache_perf --out DIR             # write somewhere else
    python -m benchmarks.cache_perf --quick --out DIR     # small, fast run (smoke test)

Runs from a clone of the repository with the ``dev`` extras (matplotlib). Needs no LLM
or network: the LLM is simulated with a sleep.
"""
from __future__ import annotations

import argparse
import asyncio
import platform
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from synthadoc.core.cache import CacheManager, make_query_cache_key

SIMULATED_LLM_MS = 50        # ms: fast end of real provider latency
SIMULATED_PHASE1_MS = 20     # ms: BM25 retrieval baseline

QUESTIONS = [
    "What is Moore's Law?",
    "How did Alan Turing influence computing?",
    "What is the Von Neumann architecture?",
    "Explain the Unix philosophy.",
    "What is open source software?",
    "How does BM25 search work?",
    "What is machine learning?",
    "Explain neural networks.",
    "What is the Turing test?",
    "How did the internet evolve?",
]

RESULT = {
    "question": "What is Moore's Law?",
    "answer": (
        "Moore's Law is the observation that the number of transistors on a "
        "microchip doubles approximately every two years, first noted by "
        "Gordon Moore in 1965. It has driven semiconductor roadmaps for "
        "over five decades, though physical limits are now slowing the pace."
    ),
    "citations": ["moore-s-law", "semiconductor-history"],
    "tokens_used": 120,
    "knowledge_gap": False,
    "suggested_searches": [],
    "cacheable": True,
}

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "docs" / "png" / "cache-perf"
CHART_FILES = (
    "cache-read-latency.png",
    "hit-vs-miss-latency.png",
    "concurrent-readers.png",
    "cache-vs-nocache-qps.png",
)

_STYLE = {
    "cache":   {"color": "#2196F3", "label": "Cache hit"},
    "nocache": {"color": "#FF5722", "label": "No cache (simulated LLM)"},
    "p50":     {"color": "#4CAF50"},
    "p95":     {"color": "#FF9800"},
    "p99":     {"color": "#F44336"},
}


@dataclass(frozen=True)
class Profile:
    """How much to measure. FULL is what the published charts use."""
    warm_keys: int
    reads: int
    llm_speeds_ms: tuple[int, ...]
    miss_samples: int
    hit_samples: int
    concurrency: tuple[int, ...]


FULL = Profile(warm_keys=200, reads=500, llm_speeds_ms=(50, 200, 500, 2000),
               miss_samples=8, hit_samples=30, concurrency=(1, 5, 10, 25, 50, 100))
QUICK = Profile(warm_keys=20, reads=60, llm_speeds_ms=(5, 20),
                miss_samples=2, hit_samples=5, concurrency=(1, 5, 10))


@dataclass(frozen=True)
class Measurements:
    profile: Profile
    read_lats: list[float]
    miss_p50s: list[float]
    hit_p50s: list[float]
    speedups: list[float]
    concurrent_p95s: list[float]
    cache_qps: list[float]
    nocache_qps: list[float]


def percentile(data: list[float], pct: float) -> float:
    idx = max(0, int(pct * len(data)) - 1)
    return sorted(data)[idx]


async def make_cache(work_dir: Path) -> CacheManager:
    db = CacheManager(work_dir / ".synthadoc" / "cache.db")
    await db.init()
    return db


# ── measurement ───────────────────────────────────────────────────────────────

async def measure(work_dir: Path, profile: Profile = FULL) -> Measurements:
    """Run the four measurements against fresh caches under *work_dir*.

    Every cache it opens is closed on the way out: an open SQLite connection keeps its
    worker thread alive and, on Windows, locks the folder so it cannot be deleted.
    """
    opened: list[CacheManager] = []

    async def open_cache(path: Path) -> CacheManager:
        cache = await make_cache(path)
        opened.append(cache)
        return cache

    try:
        return await _measure(work_dir, profile, open_cache)
    finally:
        for cache in opened:
            await cache.close()


async def _measure(work_dir: Path, profile: Profile, open_cache) -> Measurements:
    # 1. read latency distribution
    cache = await open_cache(work_dir)
    keys = []
    for i in range(profile.warm_keys):
        k = make_query_cache_key(QUESTIONS[i % len(QUESTIONS)], epoch=i % 20)
        await cache.set_query(k, epoch=i % 20, result=RESULT)
        keys.append(k)
    read_lats = []
    for i in range(profile.reads):
        k = keys[i % len(keys)]
        t0 = time.perf_counter()
        await cache.get_query(k)
        read_lats.append((time.perf_counter() - t0) * 1000)

    # 2. hit versus miss at different simulated LLM speeds
    miss_p50s, hit_p50s, speedups = [], [], []
    for llm_ms in profile.llm_speeds_ms:
        cache2 = await open_cache(work_dir / f"llm{llm_ms}")
        k = make_query_cache_key("What is Moore's Law?", epoch=0)
        miss_samples = []
        for _ in range(profile.miss_samples):
            t0 = time.perf_counter()
            await asyncio.sleep(SIMULATED_PHASE1_MS / 1000)
            await asyncio.sleep(llm_ms / 1000)
            await cache2.set_query(k, epoch=0, result=RESULT.copy())
            miss_samples.append((time.perf_counter() - t0) * 1000)
        hit_samples = []
        for _ in range(profile.hit_samples):
            t0 = time.perf_counter()
            await cache2.get_query(k)
            hit_samples.append((time.perf_counter() - t0) * 1000)
        mp50 = statistics.median(miss_samples)
        hp50 = statistics.median(hit_samples)
        miss_p50s.append(mp50)
        hit_p50s.append(hp50)
        speedups.append(mp50 / max(hp50, 0.001))

    # 3. concurrent reader P95
    concurrent_p95s = []
    cache3 = await open_cache(work_dir / "concurrent")
    k = make_query_cache_key("What is Moore's Law?", epoch=0)
    await cache3.set_query(k, epoch=0, result=RESULT)
    for n in profile.concurrency:
        async def one_read(cache=cache3, key=k):
            t0 = time.perf_counter()
            await cache.get_query(key)
            return (time.perf_counter() - t0) * 1000

        outcomes = await asyncio.gather(*[one_read() for _ in range(n)])
        concurrent_p95s.append(percentile(list(outcomes), 0.95))

    # 4. throughput, cache versus no cache
    cache_qps, nocache_qps = [], []
    cache4 = await open_cache(work_dir / "throughput")
    for q in QUESTIONS:
        kk = make_query_cache_key(q, epoch=0)
        await cache4.set_query(kk, epoch=0, result=RESULT.copy())
    for n in profile.concurrency:
        qs = (QUESTIONS * ((n // len(QUESTIONS)) + 1))[:n]

        async def with_cache(q, c=cache4):
            kk = make_query_cache_key(q, epoch=0)
            if await c.get_query(kk) is None:
                await asyncio.sleep((SIMULATED_PHASE1_MS + SIMULATED_LLM_MS) / 1000)
                await c.set_query(kk, epoch=0, result=RESULT.copy())

        async def no_cache_fn(q):
            await asyncio.sleep((SIMULATED_PHASE1_MS + SIMULATED_LLM_MS) / 1000)

        t0 = time.perf_counter()
        await asyncio.gather(*[with_cache(q) for q in qs])
        cache_wall = time.perf_counter() - t0
        t0 = time.perf_counter()
        await asyncio.gather(*[no_cache_fn(q) for q in qs])
        nocache_wall = time.perf_counter() - t0
        cache_qps.append(n / max(cache_wall, 0.001))
        nocache_qps.append(n / max(nocache_wall, 0.001))

    return Measurements(profile, read_lats, miss_p50s, hit_p50s, speedups,
                        concurrent_p95s, cache_qps, nocache_qps)


# ── charts ────────────────────────────────────────────────────────────────────

def render(m: Measurements, out_dir: Path) -> list[Path]:
    """Draw the four charts into *out_dir* and return their paths (in CHART_FILES order)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    out_dir.mkdir(parents=True, exist_ok=True)
    p = m.profile
    levels = list(p.concurrency)
    llm_speeds_ms = list(p.llm_speeds_ms)
    written: list[Path] = []

    def save(name: str) -> None:
        plt.tight_layout()
        out = out_dir / name
        plt.savefig(out, dpi=150)
        plt.close()
        written.append(out)

    # chart 1: cache read latency distribution
    r_p50 = statistics.median(m.read_lats)
    r_p95 = percentile(m.read_lats, 0.95)
    r_p99 = percentile(m.read_lats, 0.99)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(m.read_lats, bins=40, color="#2196F3", alpha=0.75, edgecolor="white", linewidth=0.5)
    ax.axvline(r_p50, color=_STYLE["p50"]["color"], linewidth=2,
               linestyle="--", label=f"P50 = {r_p50:.2f} ms")
    ax.axvline(r_p95, color=_STYLE["p95"]["color"], linewidth=2,
               linestyle="--", label=f"P95 = {r_p95:.2f} ms")
    ax.axvline(r_p99, color=_STYLE["p99"]["color"], linewidth=2,
               linestyle="--", label=f"P99 = {r_p99:.2f} ms")
    ax.set_xlabel("Latency (ms)", fontsize=12)
    ax.set_ylabel("Frequency", fontsize=12)
    ax.set_title(f"Cache Read Latency Distribution\n"
                 f"({p.reads} reads across {p.warm_keys} cached entries)", fontsize=13)
    ax.legend(fontsize=11)
    ax.set_xlim(left=0)
    ax.annotate(
        f"SLO: P99 < 10ms\nActual P99: {r_p99:.2f}ms  ({'✓ PASS' if r_p99 < 10 else '✗ FAIL'})",
        xy=(0.97, 0.95), xycoords="axes fraction", ha="right", va="top",
        fontsize=10, color="#333",
        bbox=dict(boxstyle="round,pad=0.3", fc="#f5f5f5", ec="#ccc"),
    )
    save(CHART_FILES[0])

    # chart 2: hit versus miss at different LLM latencies
    x = np.arange(len(llm_speeds_ms))
    width = 0.35
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    ax1 = axes[0]
    bars_miss = ax1.bar(x - width / 2, m.miss_p50s, width, label="Cache miss (Phase1+LLM)",
                        color=_STYLE["nocache"]["color"], alpha=0.85)
    bars_hit = ax1.bar(x + width / 2, m.hit_p50s, width, label="Cache hit",
                       color=_STYLE["cache"]["color"], alpha=0.85)
    ax1.set_xticks(x)
    ax1.set_xticklabels([f"{ms}ms\nLLM" for ms in llm_speeds_ms])
    ax1.set_ylabel("P50 Latency (ms)", fontsize=11)
    ax1.set_title("Cache Hit vs Miss — P50 Latency\n(varying simulated LLM speed)", fontsize=12)
    ax1.legend(fontsize=10)
    ax1.set_yscale("log")
    for bar in bars_miss:
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() * 1.05,
                 f"{bar.get_height():.0f}ms", ha="center", va="bottom", fontsize=8)
    for bar in bars_hit:
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() * 1.05,
                 f"{bar.get_height():.2f}ms", ha="center", va="bottom", fontsize=8)
    ax2 = axes[1]
    bars_su = ax2.bar(x, m.speedups, color="#9C27B0", alpha=0.85)
    ax2.set_xticks(x)
    ax2.set_xticklabels([f"{ms}ms\nLLM" for ms in llm_speeds_ms])
    ax2.set_ylabel("Speedup (×)", fontsize=11)
    ax2.set_title("Cache Speedup Factor\n(miss P50 ÷ hit P50)", fontsize=12)
    for bar in bars_su:
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                 f"{bar.get_height():.0f}×", ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax2.axhline(1, color="#999", linewidth=1, linestyle="--")
    save(CHART_FILES[1])

    # chart 3: concurrent readers, WAL degradation curve
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(levels, m.concurrent_p95s, "o-",
            color=_STYLE["cache"]["color"], linewidth=2, markersize=7,
            label="P95 per-query latency")
    ax.fill_between(levels, m.concurrent_p95s, alpha=0.15, color=_STYLE["cache"]["color"])
    for x_val, y_val in zip(levels, m.concurrent_p95s):
        ax.annotate(f"{y_val:.1f}ms", (x_val, y_val),
                    textcoords="offset points", xytext=(0, 10),
                    ha="center", fontsize=9)
    ax.set_xlabel("Concurrent Readers", fontsize=12)
    ax.set_ylabel("P95 Latency per Query (ms)", fontsize=12)
    ax.set_title("Concurrent Cache Readers — Persistent Connection Scaling\n"
                 "(single aiosqlite connection, shared across all concurrent reads)", fontsize=12)
    ax.legend(fontsize=11)
    ax.set_xticks(levels)
    ax.set_ylim(bottom=0)
    ax.annotate(
        "One persistent connection shared\nacross all concurrent reads.\n"
        "Requests queue through aiosqlite's\nbackground thread — smooth\nmonotonic scaling.",
        xy=(0.97, 0.05), xycoords="axes fraction", ha="right", va="bottom",
        fontsize=9, color="#555",
        bbox=dict(boxstyle="round,pad=0.4", fc="#e8f5e9", ec="#4CAF50"),
    )
    save(CHART_FILES[2])

    # chart 4: throughput comparison
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    ax1 = axes[0]
    ax1.plot(levels, m.cache_qps, "o-",
             color=_STYLE["cache"]["color"], linewidth=2.5, markersize=8, label="With cache")
    ax1.plot(levels, m.nocache_qps, "s--",
             color=_STYLE["nocache"]["color"], linewidth=2.5, markersize=8,
             label=f"No cache (LLM={SIMULATED_LLM_MS}ms simulated)")
    ax1.fill_between(levels, m.cache_qps, m.nocache_qps,
                     alpha=0.10, color="#4CAF50", label="Cache advantage")
    ax1.set_xlabel("Concurrent Queries", fontsize=11)
    ax1.set_ylabel("Throughput (queries / second)", fontsize=11)
    ax1.set_title("Cache vs No-Cache Throughput\n(concurrent queries, simulated LLM)", fontsize=12)
    ax1.legend(fontsize=10)
    ax1.set_xticks(levels)
    ax2 = axes[1]
    ratios = [c / max(nc, 0.001) for c, nc in zip(m.cache_qps, m.nocache_qps)]
    bars = ax2.bar(range(len(levels)), ratios,
                   color="#4CAF50", alpha=0.85, tick_label=[str(c) for c in levels])
    ax2.set_xlabel("Concurrent Queries", fontsize=11)
    ax2.set_ylabel("Throughput Ratio (cache / no-cache)", fontsize=11)
    ax2.set_title("Cache Throughput Advantage\n(ratio > 1 means cache wins)", fontsize=12)
    ax2.axhline(1, color="#999", linewidth=1.5, linestyle="--", label="Break-even")
    ax2.legend(fontsize=10)
    for bar, ratio in zip(bars, ratios):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                 f"{ratio:.1f}×", ha="center", va="bottom", fontsize=10, fontweight="bold")
    save(CHART_FILES[3])
    return written


# ── command line ──────────────────────────────────────────────────────────────

def _run(coro):
    # ProactorEventLoop (IOCP) on Windows deadlocks when aiosqlite's worker thread signals
    # hundreds of rapid completions; SelectorEventLoop works on every platform and version.
    loop = asyncio.SelectorEventLoop() if platform.system() == "Windows" else asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m benchmarks.cache_perf",
                                 description="Measure the query cache and draw the performance charts.")
    ap.add_argument("--out", type=Path, default=None,
                    help=f"output folder (default: {DEFAULT_OUT})")
    ap.add_argument("--quick", action="store_true",
                    help="small fast run for checking the script; requires --out so the "
                         "published charts are never overwritten with low-quality data")
    args = ap.parse_args(argv)
    if args.quick and args.out is None:
        ap.error("--quick requires --out (it must not overwrite the published charts)")
    out_dir = args.out or DEFAULT_OUT
    profile = QUICK if args.quick else FULL

    with tempfile.TemporaryDirectory(prefix="synthadoc-cache-perf-") as work:
        m = _run(measure(Path(work), profile))
    paths = render(m, out_dir)
    for path in paths:
        print(f"  saved {path}")
    # ASCII only: a legacy Windows console cannot encode the characters used in the charts.
    print(f"  Summary - cache read: P50={statistics.median(m.read_lats):.2f}ms "
          f"P95={percentile(m.read_lats, 0.95):.2f}ms P99={percentile(m.read_lats, 0.99):.2f}ms")
    print(f"  Speedup at {profile.llm_speeds_ms[0]}ms LLM: {m.speedups[0]:.0f}x  |  "
          f"at {profile.llm_speeds_ms[-1]}ms LLM: {m.speedups[-1]:.0f}x")
    return 0


if __name__ == "__main__":
    sys.exit(main())
