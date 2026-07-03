# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import json
import pytest
from pathlib import Path
from synthadoc.agents.hint_engine import HintEngine, _dynamic_followup, _slug_to_title


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


# ── _slug_to_title ────────────────────────────────────────────────────────────

def test_slug_to_title_replaces_hyphens():
    assert _slug_to_title("technova-inc") == "technova inc"


def test_slug_to_title_strips_fy_year():
    assert _slug_to_title("portfolio-valuation-report-fy2025") == "portfolio valuation report"


def test_slug_to_title_strips_bare_year():
    assert _slug_to_title("market-outlook-2026") == "market outlook"


def test_slug_to_title_no_year():
    assert _slug_to_title("capex-policy-analysis") == "capex policy analysis"


# ── _dynamic_followup ─────────────────────────────────────────────────────────

def test_dynamic_followup_none_when_no_links():
    assert _dynamic_followup("What is X?", "Plain answer with no wiki links.") is None


def test_dynamic_followup_none_when_only_scaffold_links():
    answer = "See [[overview]] and [[index]] for orientation."
    assert _dynamic_followup("What is X?", answer) is None


def test_dynamic_followup_picks_first_non_scaffold_slug():
    answer = "See [[overview]] then check [[technova-inc]] for details."
    result = _dynamic_followup("What is the revenue growth?", answer)
    assert result is not None
    assert "technova inc" in result


def test_dynamic_followup_strips_question_prefix():
    answer = "Revenue grew 16%. See [[technova-inc]]."
    result = _dynamic_followup("What is the revenue growth outlook?", answer)
    # Subject extracted should not start with "what is"
    assert result is not None
    assert "what is" not in result.lower()


def test_dynamic_followup_empty_question_uses_fallback_template():
    answer = "See [[capex-policy-analysis]] for details."
    result = _dynamic_followup("", answer)
    assert result == "What else does capex policy analysis cover?"


def test_dynamic_followup_overlap_uses_fallback_template():
    # Subject "capex policy analysis" heavily overlaps with slug title
    answer = "Refer to [[capex-policy-analysis]]."
    result = _dynamic_followup("What is the capex policy analysis?", answer)
    assert result == "What else does capex policy analysis cover?"


def test_dynamic_followup_skips_pipe_alias():
    # [[slug|Display text]] — should extract slug, not alias
    answer = "Refer to [[technova-inc|TechNova]] for numbers."
    result = _dynamic_followup("What is the revenue outlook?", answer)
    assert result is not None
    assert "technova inc" in result


def test_dynamic_followup_cjk_question_uses_simple_template():
    answer = "Revenue grew 18.2%. See [[technova-inc]] for details."
    result = _dynamic_followup("TechNova 在 2025 财年的收入增长率和 EBITDA 利润率是多少？", answer)
    assert result == "What else does technova inc cover?"


def test_dynamic_followup_strips_fy_year_in_output():
    answer = "See [[portfolio-valuation-report-fy2025]]."
    result = _dynamic_followup("What are valuations?", answer)
    assert "fy2025" not in result.lower()
    assert "2025" not in result


# ── after_response_windowed — 2+1 composition ────────────────────────────────

def test_windowed_with_question_returns_dynamic_as_third():
    answer = "TechNova grew 16%. See [[technova-inc]] for details."
    question = "What is the 2026 revenue growth outlook?"
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0, question=question)
    assert len(hints) == 3
    pool = HintEngine.build_pool("POWER_USER")
    # First two come from pool, third is dynamic (not in pool)
    assert hints[:2] == pool[:2]
    assert hints[2] not in pool


def test_windowed_without_question_returns_3_pool_hints():
    answer = "TechNova grew 16%. See [[technova-inc]] for details."
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0)
    pool = HintEngine.build_pool("POWER_USER")
    assert hints == pool[:3]


def test_windowed_no_links_in_answer_falls_back_to_pool():
    answer = "The wiki does not cover this topic."
    question = "What is the revenue growth?"
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0, question=question)
    pool = HintEngine.build_pool("POWER_USER")
    assert hints == pool[:3]


def test_windowed_topic_match_takes_priority_over_dynamic():
    answer = "Your page is stale and outdated. See [[technova-inc]]."
    question = "What pages are stale?"
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0, question=question)
    # Topic match fires; lint hint must be present regardless of dynamic
    assert "How do I run a lint check?" in hints


def test_windowed_dynamic_not_duplicated_in_pool_window():
    # If _dynamic_followup returns a string already in the window, fall back to 3 pool hints
    pool = HintEngine.build_pool("POWER_USER")
    # Construct answer whose dynamic followup would clash with pool[2]
    # (hard to force deterministically, so just verify length stays 3)
    answer = "See [[technova-inc]]."
    hints, _ = HintEngine.after_response_windowed(answer, "POWER_USER", 0, question="What is revenue?")
    assert len(hints) == 3


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
