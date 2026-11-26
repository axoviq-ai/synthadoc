# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""The query-cache chart script (``python -m benchmarks.cache_perf``) still works.

The script replaced a pytest "test" that had no assertions and wrote PNGs into the tracked
``docs/`` folder. These tests run it in its quick profile into a temporary folder, check
the measurements are sane and the images are real PNGs, and prove the published charts are
never touched. matplotlib is a ``dev`` extra: a missing install fails here loudly.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from benchmarks import cache_perf as cp

REPO = Path(__file__).resolve().parents[2]
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _assert_valid_pngs(folder: Path) -> None:
    for name in cp.CHART_FILES:
        data = (folder / name).read_bytes()
        assert data.startswith(PNG_SIGNATURE), name
        assert len(data) > 5_000, f"{name} looks empty ({len(data)} bytes)"


def _published_state() -> dict:
    return {p.name: (p.stat().st_mtime_ns, p.stat().st_size) for p in cp.DEFAULT_OUT.glob("*.png")}


def test_published_profile_keeps_its_documented_size():
    assert (cp.FULL.reads, cp.FULL.warm_keys) == (500, 200)
    assert cp.FULL.llm_speeds_ms == (50, 200, 500, 2000)
    assert cp.FULL.concurrency == (1, 5, 10, 25, 50, 100)


def test_measurements_are_complete_and_the_cache_clearly_wins(tmp_path):
    m = cp._run(cp.measure(tmp_path, cp.QUICK))
    p = cp.QUICK
    assert len(m.read_lats) == p.reads and all(x > 0 for x in m.read_lats)
    assert len(m.miss_p50s) == len(m.hit_p50s) == len(m.speedups) == len(p.llm_speeds_ms)
    assert len(m.concurrent_p95s) == len(m.cache_qps) == len(m.nocache_qps) == len(p.concurrency)
    for miss, hit, speedup in zip(m.miss_p50s, m.hit_p50s, m.speedups):
        assert miss > hit and speedup > 1             # a hit beats Phase 1 + the simulated LLM
    for with_cache, without in zip(m.cache_qps, m.nocache_qps):
        assert with_cache > without                   # every question is cached, none waits


def test_render_writes_four_real_pngs(tmp_path):
    """Plotting alone, from fixed numbers: deterministic and independent of timing."""
    p = cp.QUICK
    m = cp.Measurements(
        profile=p,
        read_lats=[0.2 + 0.01 * (i % 7) for i in range(p.reads)],
        miss_p50s=[30.0, 50.0], hit_p50s=[0.2, 0.2], speedups=[150.0, 250.0],
        concurrent_p95s=[0.3, 0.8, 1.5],
        cache_qps=[900.0, 1200.0, 1500.0], nocache_qps=[14.0, 70.0, 140.0],
    )
    written = cp.render(m, tmp_path / "nested" / "out")
    assert [w.name for w in written] == list(cp.CHART_FILES)
    _assert_valid_pngs(tmp_path / "nested" / "out")


def test_quick_run_writes_charts_to_the_chosen_folder_and_leaves_the_published_ones(tmp_path, capsys):
    before = _published_state()
    assert cp.main(["--quick", "--out", str(tmp_path)]) == 0
    _assert_valid_pngs(tmp_path)
    assert _published_state() == before               # docs/png/cache-perf/ untouched
    out = capsys.readouterr().out
    assert "Summary" in out and "Speedup" in out


def test_quick_without_out_is_refused_so_published_charts_are_never_overwritten(capsys):
    before = _published_state()
    with pytest.raises(SystemExit) as info:
        cp.main(["--quick"])
    assert info.value.code == 2
    assert "--out" in capsys.readouterr().err
    assert _published_state() == before


def test_the_documented_command_line_works(tmp_path):
    """``python -m benchmarks.cache_perf`` exactly as benchmarks/README.md says to run it."""
    done = subprocess.run(
        [sys.executable, "-m", "benchmarks.cache_perf", "--quick", "--out", str(tmp_path)],
        cwd=REPO, capture_output=True, text=True, timeout=120,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    _assert_valid_pngs(tmp_path)
