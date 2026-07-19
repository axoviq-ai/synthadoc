# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from synthadoc.providers.pricing import _PRICING, _FALLBACK, estimate_cost


# ---------------------------------------------------------------------------
# Core mechanics
# ---------------------------------------------------------------------------

def test_known_model_uses_separate_input_output_rates():
    """claude-haiku input ($1/M) and output ($5/M) rates applied separately."""
    cost = estimate_cost("claude-haiku-4-5-20251001", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 6.0) < 0.001  # $1 input + $5 output


def test_ollama_is_always_zero():
    """Local inference has no cost regardless of token count."""
    assert estimate_cost("llama3", input_tokens=999_999, output_tokens=999_999, is_local=True) == 0.0


def test_unknown_model_uses_fallback_rate():
    """Unknown models use a conservative fallback rather than crashing."""
    cost = estimate_cost("some-future-model", input_tokens=1_000_000, output_tokens=0)
    assert cost > 0.0


def test_fallback_rate_is_nonzero():
    """Fallback must never silently report $0 for unknown paid models."""
    assert _FALLBACK[0] > 0 and _FALLBACK[1] > 0


def test_zero_tokens_returns_zero():
    cost = estimate_cost("gpt-4o", input_tokens=0, output_tokens=0)
    assert cost == 0.0


def test_pricing_table_has_no_zero_rates():
    """Every entry in the table must have positive input AND output rates."""
    for model, (inp, out) in _PRICING.items():
        assert inp > 0, f"{model}: input rate is 0"
        assert out > 0, f"{model}: output rate is 0"


def test_pricing_table_output_ge_input():
    """Output tokens should always cost at least as much as input for every model."""
    for model, (inp, out) in _PRICING.items():
        assert out >= inp, f"{model}: output rate {out} < input rate {inp}"


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

def test_claude_fable5_rates():
    """claude-fable-5: $10/M input, $50/M output."""
    cost = estimate_cost("claude-fable-5", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 60.0) < 0.001


def test_claude_opus_48_rates():
    """claude-opus-4-8: $5/M input, $25/M output."""
    cost = estimate_cost("claude-opus-4-8", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 30.0) < 0.001


def test_claude_sonnet5_rates():
    """claude-sonnet-5: $3/M input, $15/M output."""
    cost = estimate_cost("claude-sonnet-5", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 18.0) < 0.001


def test_claude_sonnet46_rates():
    """claude-sonnet-4-6: $3/M input, $15/M output."""
    cost = estimate_cost("claude-sonnet-4-6", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 18.0) < 0.001


def test_claude_opus47_rates():
    """claude-opus-4-7 (legacy): $5/M input, $25/M output."""
    cost = estimate_cost("claude-opus-4-7", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 30.0) < 0.001


def test_claude_haiku_rates():
    """claude-haiku-4-5-20251001: $1/M input, $5/M output."""
    cost = estimate_cost("claude-haiku-4-5-20251001", input_tokens=2_000_000, output_tokens=0)
    assert abs(cost - 2.0) < 0.001


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

def test_gpt4o_rates():
    """gpt-4o: $2.50/M input, $10/M output."""
    cost = estimate_cost("gpt-4o", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 12.50) < 0.001


def test_gpt4o_mini_rates():
    """gpt-4o-mini: $0.15/M input, $0.60/M output."""
    cost = estimate_cost("gpt-4o-mini", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 0.75) < 0.001


def test_gpt41_rates():
    """gpt-4.1: $2/M input, $8/M output."""
    cost = estimate_cost("gpt-4.1", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 10.0) < 0.001


def test_gpt41_mini_rates():
    """gpt-4.1-mini: $0.40/M input, $1.60/M output."""
    cost = estimate_cost("gpt-4.1-mini", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 2.0) < 0.001


def test_o3_rates():
    """o3: $2/M input, $8/M output."""
    cost = estimate_cost("o3", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 10.0) < 0.001


def test_o4_mini_rates():
    """o4-mini: $1.10/M input, $4.40/M output."""
    cost = estimate_cost("o4-mini", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 5.50) < 0.001


def test_gpt56_sol_rates():
    """gpt-5.6-sol: $5/M input, $30/M output."""
    cost = estimate_cost("gpt-5.6-sol", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 35.0) < 0.001


def test_gpt54_mini_rates():
    """gpt-5.4-mini: $0.75/M input, $4.50/M output."""
    cost = estimate_cost("gpt-5.4-mini", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 5.25) < 0.001


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------

def test_gemini_35_flash_rates():
    """gemini-3.5-flash: $1.50/M input, $9/M output."""
    cost = estimate_cost("gemini-3.5-flash", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 10.50) < 0.001


def test_gemini_31_flash_lite_rates():
    """gemini-3.1-flash-lite: $0.25/M input, $1.50/M output."""
    cost = estimate_cost("gemini-3.1-flash-lite", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 1.75) < 0.001


def test_gemini_25_pro_rates():
    """gemini-2.5-pro: $1.25/M input, $10/M output."""
    cost = estimate_cost("gemini-2.5-pro", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 11.25) < 0.001


def test_gemini_25_flash_rates():
    """gemini-2.5-flash: $0.30/M input, $2.50/M output."""
    cost = estimate_cost("gemini-2.5-flash", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 2.80) < 0.001


def test_gemini_25_flash_lite_rates():
    """gemini-2.5-flash-lite: $0.10/M input, $0.40/M output (updated from $0.075)."""
    cost = estimate_cost("gemini-2.5-flash-lite", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 0.50) < 0.001


def test_gemini_20_flash_rates():
    """gemini-2.0-flash (deprecated 2026-06-01): $0.10/M input, $0.40/M output."""
    cost = estimate_cost("gemini-2.0-flash", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 0.50) < 0.001


def test_gemini_15_flash_rates():
    """gemini-1.5-flash: $0.075/M input, $0.30/M output."""
    cost = estimate_cost("gemini-1.5-flash", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 0.375) < 0.001


# ---------------------------------------------------------------------------
# MiniMax
# ---------------------------------------------------------------------------

def test_minimax_m3_rates():
    """MiniMax-M3: $0.30/M input, $1.20/M output."""
    cost = estimate_cost("MiniMax-M3", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 1.50) < 0.001


def test_minimax_m25_rates():
    """MiniMax-M2.5: $0.30/M input, $1.20/M output (updated from $0.15)."""
    cost = estimate_cost("MiniMax-M2.5", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 1.50) < 0.001


def test_minimax_m25_highspeed_rates():
    """MiniMax-M2.5-highspeed: $0.60/M input, $2.40/M output (priority queue, 2× standard)."""
    cost = estimate_cost("MiniMax-M2.5-highspeed", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 3.00) < 0.001


def test_minimax_m27_rates():
    """MiniMax-M2.7: $0.30/M input, $1.20/M output."""
    cost = estimate_cost("MiniMax-M2.7", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 1.50) < 0.001


def test_minimax_m27_highspeed_rates():
    """MiniMax-M2.7-highspeed: $0.60/M input, $2.40/M output."""
    cost = estimate_cost("MiniMax-M2.7-highspeed", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 3.00) < 0.001


def test_minimax_highspeed_costs_more_than_standard():
    """Highspeed (priority queue) must be pricier than standard for both M2.5 and M2.7."""
    assert estimate_cost("MiniMax-M2.5-highspeed", 1_000_000, 1_000_000) > \
           estimate_cost("MiniMax-M2.5", 1_000_000, 1_000_000)
    assert estimate_cost("MiniMax-M2.7-highspeed", 1_000_000, 1_000_000) > \
           estimate_cost("MiniMax-M2.7", 1_000_000, 1_000_000)


# ---------------------------------------------------------------------------
# DeepSeek
# ---------------------------------------------------------------------------

def test_deepseek_v4_flash_rates():
    """deepseek-v4-flash: $0.14/M input, $0.28/M output."""
    cost = estimate_cost("deepseek-v4-flash", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 0.42) < 0.001


def test_deepseek_v4_pro_rates():
    """deepseek-v4-pro: $0.435/M input, $0.87/M output."""
    cost = estimate_cost("deepseek-v4-pro", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 1.305) < 0.001


def test_deepseek_chat_alias_matches_v4_flash():
    """deepseek-chat is an alias for deepseek-v4-flash — must have identical pricing."""
    assert estimate_cost("deepseek-chat", 1_000_000, 1_000_000) == \
           estimate_cost("deepseek-v4-flash", 1_000_000, 1_000_000)


def test_deepseek_reasoner_alias_matches_v4_pro():
    """deepseek-reasoner is an alias for deepseek-v4-pro — must have identical pricing."""
    assert estimate_cost("deepseek-reasoner", 1_000_000, 1_000_000) == \
           estimate_cost("deepseek-v4-pro", 1_000_000, 1_000_000)


def test_deepseek_v3_legacy_rates():
    """deepseek-v3 (legacy): same input/output rates as deepseek-v4-flash."""
    cost = estimate_cost("deepseek-v3", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 0.42) < 0.001


def test_deepseek_r1_legacy_rates():
    """deepseek-r1 (legacy reasoning model): same rates as deepseek-v4-pro."""
    cost = estimate_cost("deepseek-r1", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 1.305) < 0.001


# ---------------------------------------------------------------------------
# Qwen / DashScope
# ---------------------------------------------------------------------------

def test_qwen_turbo_rates():
    """qwen-turbo: $0.05/M input, $0.20/M output."""
    cost = estimate_cost("qwen-turbo", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 0.25) < 0.001


def test_qwen_flash_rates():
    """qwen-flash: $0.25/M input, $1.50/M output."""
    cost = estimate_cost("qwen-flash", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 1.75) < 0.001


def test_qwen_plus_rates():
    """qwen-plus: $0.40/M input, $1.60/M output."""
    cost = estimate_cost("qwen-plus", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 2.00) < 0.001


def test_qwen_max_rates():
    """qwen-max: $1.60/M input, $6.40/M output."""
    cost = estimate_cost("qwen-max", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 8.00) < 0.001


def test_qwq_32b_rates():
    """qwq-32b: $0.80/M input, $2.40/M output (reasoning model)."""
    cost = estimate_cost("qwq-32b", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 3.20) < 0.001


def test_qwq_plus_matches_qwq_32b():
    """qwq-plus is the successor to qwq-32b — same pricing."""
    assert estimate_cost("qwq-plus", 1_000_000, 1_000_000) == \
           estimate_cost("qwq-32b", 1_000_000, 1_000_000)


def test_qwen_tier_order():
    """Qwen tiers must be priced in ascending order: turbo < flash < plus < max."""
    t = estimate_cost("qwen-turbo", 1_000_000, 1_000_000)
    f = estimate_cost("qwen-flash", 1_000_000, 1_000_000)
    p = estimate_cost("qwen-plus",  1_000_000, 1_000_000)
    m = estimate_cost("qwen-max",   1_000_000, 1_000_000)
    assert t < f < p < m


# ---------------------------------------------------------------------------
# Groq
# ---------------------------------------------------------------------------

def test_groq_llama33_70b_rates():
    """llama-3.3-70b-versatile: $0.59/M input, $0.79/M output."""
    cost = estimate_cost("llama-3.3-70b-versatile", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 1.38) < 0.001


def test_groq_llama4_scout_rates():
    """llama4-scout-17b-16e-instruct: $0.11/M input, $0.34/M output."""
    cost = estimate_cost("llama4-scout-17b-16e-instruct", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 0.45) < 0.001


def test_groq_llama4_maverick_rates():
    """llama4-maverick-17b-128e-instruct: $0.50/M input, $0.77/M output."""
    cost = estimate_cost("llama4-maverick-17b-128e-instruct", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 1.27) < 0.001


def test_groq_maverick_more_expensive_than_scout():
    """Maverick should cost more than Scout per million tokens."""
    assert estimate_cost("llama4-maverick-17b-128e-instruct", 1_000_000, 1_000_000) > \
           estimate_cost("llama4-scout-17b-16e-instruct", 1_000_000, 1_000_000)


# ---------------------------------------------------------------------------
# Cross-provider sanity checks
# ---------------------------------------------------------------------------

def test_input_only_charges_input_rate():
    """A call with output_tokens=0 should only charge the input rate."""
    inp, _out = 10.00e-6, 50.00e-6  # claude-fable-5 rates
    expected = 1_000_000 * inp
    cost = estimate_cost("claude-fable-5", input_tokens=1_000_000, output_tokens=0)
    assert abs(cost - expected) < 1e-9


def test_output_only_charges_output_rate():
    """A call with input_tokens=0 should only charge the output rate."""
    _inp, out = 10.00e-6, 50.00e-6  # claude-fable-5 rates
    expected = 500_000 * out
    cost = estimate_cost("claude-fable-5", input_tokens=0, output_tokens=500_000)
    assert abs(cost - expected) < 1e-9


def test_flagship_hierarchy_across_providers():
    """Each provider's flagship should cost more than its cheapest model."""
    assert estimate_cost("claude-fable-5", 1_000_000, 1_000_000) > \
           estimate_cost("claude-haiku-4-5-20251001", 1_000_000, 1_000_000)
    assert estimate_cost("gpt-5.6-sol", 1_000_000, 1_000_000) > \
           estimate_cost("gpt-4o-mini", 1_000_000, 1_000_000)
    assert estimate_cost("qwen-max", 1_000_000, 1_000_000) > \
           estimate_cost("qwen-turbo", 1_000_000, 1_000_000)
    assert estimate_cost("deepseek-v4-pro", 1_000_000, 1_000_000) > \
           estimate_cost("deepseek-v4-flash", 1_000_000, 1_000_000)
    assert estimate_cost("MiniMax-M2.5-highspeed", 1_000_000, 1_000_000) > \
           estimate_cost("MiniMax-M2.5", 1_000_000, 1_000_000)
