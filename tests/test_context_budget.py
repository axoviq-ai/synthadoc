# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from synthadoc.core.context_budget import resolve_context_window, compute_char_budgets
from synthadoc.config import QueryConfig


def test_resolve_context_window_claude_sonnet():
    assert resolve_context_window("claude-sonnet-4-6", 0) == 200_000


def test_resolve_context_window_gpt4o():
    # prefix match: "gpt-4o-2024-11" starts with "gpt-4o"
    assert resolve_context_window("gpt-4o-2024-11", 0) == 128_000


def test_resolve_context_window_unknown_fallback():
    assert resolve_context_window("some-unknown-model-x", 0) == 128_000


def test_resolve_context_window_manual_override():
    # config_override beats model map
    assert resolve_context_window("claude-sonnet-4-6", 32_000) == 32_000


def test_resolve_context_window_gpt4_exact():
    # "gpt-4" exact match must win over "gpt-4-turbo" prefix for the string "gpt-4"
    assert resolve_context_window("gpt-4", 0) == 8_192


def test_compute_char_budgets_defaults():
    cfg = QueryConfig()
    budgets = compute_char_budgets("claude-sonnet-4-6", cfg)
    assert budgets["wiki"] == int(200_000 * 0.60 * 4)
    assert budgets["history"] == int(200_000 * 0.20 * 4)
    assert budgets["system"] == int(200_000 * 0.15 * 4)
    assert budgets["index"] == int(200_000 * 0.05 * 4)


def test_compute_char_budgets_respects_custom_pcts():
    cfg = QueryConfig(context_wiki_pct=50, context_history_pct=30,
                      context_system_pct=15, context_index_pct=5)
    budgets = compute_char_budgets("gpt-4o", cfg)
    assert budgets["wiki"] == int(128_000 * 0.50 * 4)


def test_query_config_pct_sum_over_100_raises():
    with pytest.raises(ValueError, match="sum to"):
        QueryConfig(context_wiki_pct=60, context_history_pct=25,
                    context_system_pct=15, context_index_pct=5)


def test_query_config_pct_sum_exactly_100_ok():
    cfg = QueryConfig(context_wiki_pct=60, context_history_pct=20,
                      context_system_pct=15, context_index_pct=5)
    assert cfg.context_wiki_pct == 60


def test_query_config_pct_sum_under_100_ok():
    cfg = QueryConfig(context_wiki_pct=50, context_history_pct=20,
                      context_system_pct=15, context_index_pct=5)
    # 90% total — remaining 10% is unused safety buffer
    assert cfg.context_wiki_pct == 50
