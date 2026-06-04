# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import json
import pytest
from pathlib import Path
from synthadoc.agents.hint_engine import HintEngine


@pytest.fixture(autouse=True)
def reset_hints():
    """Reset HintEngine to built-in defaults before each test."""
    HintEngine.configure(None)
    yield
    HintEngine.configure(None)


# ── build_pool ────────────────────────────────────────────────────────────────

def test_build_pool_mode_hints_first():
    pool = HintEngine.build_pool("EXPLORER")
    explorer_hints = ["What topics does this wiki cover?",
                      "What are the key topics in this wiki?",
                      "Show wiki status"]
    assert pool[:3] == explorer_hints


def test_build_pool_includes_other_mode_hints():
    pool = HintEngine.build_pool("EXPLORER")
    # POWER_USER hints must appear somewhere after the EXPLORER hints
    assert "Export my wiki as llms.txt" in pool
    assert "Which pages are marked stale?" in pool


def test_build_pool_no_duplicates():
    pool = HintEngine.build_pool("POWER_USER")
    assert len(pool) == len(set(pool))


def test_build_pool_is_cached():
    p1 = HintEngine.build_pool("POWER_USER")
    p2 = HintEngine.build_pool("POWER_USER")
    assert p1 is p2


# ── initial_hints ─────────────────────────────────────────────────────────────

def test_initial_hints_returns_three():
    for mode in ("NEW_WIKI", "EXPLORER", "HEALTH_CHECK", "POWER_USER"):
        assert len(HintEngine.initial_hints(mode)) == 3


def test_initial_hints_are_mode_first():
    hints = HintEngine.initial_hints("NEW_WIKI")
    assert hints[0] == "How do I ingest my first document?"


# ── after_response_windowed ───────────────────────────────────────────────────

def test_windowed_advances_cursor():
    pool = HintEngine.build_pool("POWER_USER")
    _, c1 = HintEngine.after_response_windowed("some answer", "POWER_USER", 0)
    assert c1 == 3 % len(pool)


def test_windowed_wraps_around():
    pool = HintEngine.build_pool("POWER_USER")
    last = len(pool) - 1
    hints, next_c = HintEngine.after_response_windowed("answer", "POWER_USER", last)
    assert len(hints) == 3
    assert next_c < len(pool)


def test_windowed_topic_match_advances_cursor():
    pool = HintEngine.build_pool("POWER_USER")
    _, cursor_before = HintEngine.after_response_windowed("answer", "POWER_USER", 0)
    _, cursor_after = HintEngine.after_response_windowed("the page is stale", "POWER_USER", cursor_before)
    # topic match must still advance the cursor so rotation continues
    assert cursor_after == (cursor_before + 3) % len(pool)


def test_windowed_topic_match_returns_relevant_hints():
    hints, _ = HintEngine.after_response_windowed("your page is stale and outdated", "POWER_USER", 0)
    assert "How do I run a lint check?" in hints


def test_windowed_no_topic_match_returns_pool_window():
    pool = HintEngine.build_pool("POWER_USER")
    hints, _ = HintEngine.after_response_windowed("generic answer with no keywords", "POWER_USER", 0)
    assert hints == pool[:3]


def test_windowed_skips_repeated_topic_hints():
    # Same topic match on consecutive calls should not return the same hints twice.
    stale_answer = "your page is stale and outdated"
    hints1, c1 = HintEngine.after_response_windowed(stale_answer, "POWER_USER", 0)
    # Second call passes previous_hints — same topic match should be skipped.
    hints2, _ = HintEngine.after_response_windowed(stale_answer, "POWER_USER", c1,
                                                    previous_hints=hints1)
    assert hints2 != hints1, "repeated topic hints must be suppressed"


def test_windowed_allows_topic_hints_after_different_previous():
    stale_answer = "your page is stale and outdated"
    hints1, _ = HintEngine.after_response_windowed(stale_answer, "POWER_USER", 0,
                                                   previous_hints=["some", "other", "hints"])
    assert "How do I run a lint check?" in hints1


# ── after_response (backward compat) ─────────────────────────────────────────

def test_after_response_returns_list():
    result = HintEngine.after_response("some answer", "POWER_USER")
    assert isinstance(result, list)
    assert len(result) == 3


# ── configure() — external hints.json ────────────────────────────────────────

def test_configure_extends_mode_hints(tmp_path):
    hints_file = tmp_path / "hints.json"
    hints_file.write_text(json.dumps({
        "by_mode": {
            "POWER_USER": ["My custom power hint"]
        }
    }), encoding="utf-8")
    HintEngine.configure(hints_file)
    pool = HintEngine.build_pool("POWER_USER")
    assert "My custom power hint" in pool
    assert "Export my wiki as llms.txt" in pool  # built-in preserved


def test_configure_adds_new_mode(tmp_path):
    hints_file = tmp_path / "hints.json"
    hints_file.write_text(json.dumps({
        "by_mode": {
            "CUSTOM_ROLE": ["Custom role hint 1", "Custom role hint 2"]
        }
    }), encoding="utf-8")
    HintEngine.configure(hints_file)
    pool = HintEngine.build_pool("CUSTOM_ROLE")
    assert "Custom role hint 1" in pool


def test_configure_no_duplicates_from_file(tmp_path):
    hints_file = tmp_path / "hints.json"
    hints_file.write_text(json.dumps({
        "by_mode": {
            "POWER_USER": ["Export my wiki as llms.txt"]  # already a built-in
        }
    }), encoding="utf-8")
    HintEngine.configure(hints_file)
    pool = HintEngine.build_pool("POWER_USER")
    assert pool.count("Export my wiki as llms.txt") == 1


def test_configure_custom_topic_pattern_takes_priority(tmp_path):
    hints_file = tmp_path / "hints.json"
    hints_file.write_text(json.dumps({
        "topic_patterns": [
            {"keywords": ["kubernetes"], "hints": ["K8s hint 1", "K8s hint 2", "K8s hint 3"]}
        ]
    }), encoding="utf-8")
    HintEngine.configure(hints_file)
    hints, _ = HintEngine.after_response_windowed("kubernetes deployment failed", "POWER_USER", 0)
    assert hints == ["K8s hint 1", "K8s hint 2", "K8s hint 3"]


def test_configure_missing_file_uses_builtins():
    HintEngine.configure(Path("/nonexistent/hints.json"))
    hints = HintEngine.initial_hints("POWER_USER")
    # Falls back to _FALLBACK_BY_MODE — just verify the core time-range hint is present
    assert "What changed in the wiki this week?" in hints


def test_configure_malformed_file_uses_builtins(tmp_path):
    hints_file = tmp_path / "hints.json"
    hints_file.write_text("not valid json", encoding="utf-8")
    HintEngine.configure(hints_file)  # must not raise
    assert len(HintEngine.initial_hints("POWER_USER")) > 0


def test_configure_resets_on_second_call(tmp_path):
    hints_file = tmp_path / "hints.json"
    hints_file.write_text(json.dumps({
        "by_mode": {"POWER_USER": ["Temp hint"]}
    }), encoding="utf-8")
    HintEngine.configure(hints_file)
    assert "Temp hint" in HintEngine.build_pool("POWER_USER")

    HintEngine.configure(None)  # reset
    assert "Temp hint" not in HintEngine.build_pool("POWER_USER")
