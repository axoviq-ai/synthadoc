# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Per-model LLM pricing table.

Refresh at each major release. Update _LAST_UPDATED and the rates below.
Sources (checked 2026-09-15):
  Anthropic — https://platform.claude.com/docs/en/about-claude/pricing
  OpenAI    — https://developers.openai.com/api/docs/pricing
  Gemini    — https://ai.google.dev/gemini-api/docs/pricing
  Groq      — https://groq.com/pricing/
  MiniMax   — https://platform.minimax.io/docs/guides/pricing-paygo
  DeepSeek  — https://api-docs.deepseek.com/quick_start/pricing
  Qwen      — https://www.alibabacloud.com/help/en/model-studio/model-pricing
  Kimi      — https://platform.moonshot.cn/docs/pricing
"""
from __future__ import annotations

_LAST_UPDATED = "2026-09-15"

# (input_usd_per_token, output_usd_per_token)
# All rates are cache-miss / non-cached standard tier unless noted.
_PRICING: dict[str, tuple[float, float]] = {
    # ── Anthropic ────────────────────────────────────────────────────────────
    "claude-fable-5-1":          (10.00e-6, 50.00e-6),  # current flagship (GA 2026-09)
    "claude-fable-5":            (10.00e-6, 50.00e-6),
    "claude-opus-5":             ( 5.00e-6, 25.00e-6),  # added 2026-07-24
    "claude-opus-4-8":           ( 5.00e-6, 25.00e-6),  # recommended for agentic/enterprise
    "claude-sonnet-5":           ( 2.00e-6, 10.00e-6),  # $2/$10 confirmed permanent (Sept 1 increase cancelled)
    "claude-haiku-4-5-20251001": ( 1.00e-6,  5.00e-6),
    # legacy — still available
    "claude-opus-4-7":           ( 5.00e-6, 25.00e-6),
    "claude-opus-4-6":           ( 5.00e-6, 25.00e-6),
    "claude-sonnet-4-6":         ( 3.00e-6, 15.00e-6),

    # ── OpenAI ───────────────────────────────────────────────────────────────
    # GPT-6.x / GPT-5.x (current flagship families)
    "gpt-6-astra":               (10.00e-6, 50.00e-6),  # added 2026-09-03
    "gpt-5.6-sol":               ( 5.00e-6, 30.00e-6),
    "gpt-5.6-terra":             ( 2.00e-6, 12.00e-6),  # price cut 2026-07-30
    "gpt-5.6-luna":              ( 0.20e-6,  1.20e-6),  # price cut 2026-07-30
    "gpt-5.5":                   ( 5.00e-6, 30.00e-6),
    "gpt-5.4":                   ( 2.50e-6, 15.00e-6),
    "gpt-5.4-mini":              ( 0.75e-6,  4.50e-6),
    # GPT-4.x / reasoning
    "gpt-4.1":                   ( 2.00e-6,  8.00e-6),
    "gpt-4.1-mini":              ( 0.40e-6,  1.60e-6),
    "gpt-4o":                    ( 2.50e-6, 10.00e-6),
    "gpt-4o-mini":               ( 0.15e-6,  0.60e-6),
    "o3":                        ( 2.00e-6,  8.00e-6),
    "o4-mini":                   ( 1.10e-6,  4.40e-6),

    # ── Gemini ───────────────────────────────────────────────────────────────
    # Gemini 3.x (current)
    "gemini-3.8-flash":          ( 0.75e-6,  3.75e-6),  # promotional rate through 2026-12-31
    "gemini-3.7-flash":          ( 0.75e-6,  3.75e-6),
    "gemini-3.6-flash":          ( 0.75e-6,  3.75e-6),
    "gemini-3.5-flash":          ( 1.50e-6,  9.00e-6),
    "gemini-3.5-flash-lite":     ( 0.30e-6,  2.50e-6),
    "gemini-3.1-flash-lite":     ( 0.25e-6,  1.50e-6),
    "gemini-3.1-pro-preview":    ( 2.00e-6, 12.00e-6),  # ≤200k input tier
    # Gemini 2.5
    "gemini-2.5-pro":            ( 1.25e-6, 10.00e-6),  # ≤200k input tier
    "gemini-2.5-flash":          ( 0.30e-6,  2.50e-6),
    "gemini-2.5-flash-lite":     ( 0.10e-6,  0.40e-6),

    # ── MiniMax ──────────────────────────────────────────────────────────────
    # All rates include MiniMax's permanent 50% discount; highspeed = priority queue
    "MiniMax-M3":                ( 0.30e-6,  1.20e-6),
    "MiniMax-M2.7":              ( 0.21e-6,  0.84e-6),  # revised 2026-09
    "MiniMax-M2.7-highspeed":    ( 0.42e-6,  1.68e-6),  # 2× standard
    "MiniMax-M2.5":              ( 0.30e-6,  1.20e-6),
    "MiniMax-M2.5-highspeed":    ( 0.60e-6,  2.40e-6),

    # ── DeepSeek ─────────────────────────────────────────────────────────────
    # deepseek-chat / deepseek-reasoner are aliases deprecated 2026-07-24;
    # they map to deepseek-v4-flash non-thinking / thinking modes respectively.
    # Rates reflect peak pricing (off-peak = 50% of these rates).
    "deepseek-v4-flash":         ( 0.30e-6,  1.20e-6),  # revised 2026-09 (peak rate)
    "deepseek-v4-pro":           ( 0.66e-6,  1.98e-6),  # revised 2026-09 (peak rate)
    "deepseek-chat":             ( 0.30e-6,  1.20e-6),  # → deepseek-v4-flash (non-thinking)
    "deepseek-reasoner":         ( 0.30e-6,  1.20e-6),  # → deepseek-v4-flash (thinking mode)
    "deepseek-v3":               ( 0.30e-6,  1.20e-6),  # legacy
    "deepseek-r1":               ( 0.66e-6,  1.98e-6),  # legacy

    # ── Qwen / DashScope (international / Singapore tier) ────────────────────
    # Legacy names (qwen-X) still accepted by DashScope API and route correctly.
    # New Qwen 3.x names (qwen3.X-Y) cannot yet be used in config.toml — the
    # provider routing regex only matches names starting with "qwen-" or "qwq-".
    "qwen-turbo":                ( 0.05e-6,  0.20e-6),  # legacy; Alibaba recommends qwen-flash
    "qwen-flash":                ( 0.25e-6,  1.50e-6),  # successor to qwen-turbo
    "qwen-plus":                 ( 0.40e-6,  1.60e-6),
    "qwen-max":                  ( 1.60e-6,  6.40e-6),
    "qwq-32b":                   ( 0.80e-6,  2.40e-6),  # reasoning; same rate as qwq-plus
    "qwq-plus":                  ( 0.80e-6,  2.40e-6),  # reasoning
    # Qwen 3.x (pricing only; not yet usable in config.toml — see routing note above)
    "qwen3.8-max":               ( 2.00e-6,  6.00e-6),  # added 2026-08-03
    "qwen3.8-flash":             ( 0.14e-6,  0.42e-6),  # added 2026-08-26
    "qwen3.5-397b":              ( 0.60e-6,  3.60e-6),
    "qwen3.5-plus":              ( 0.40e-6,  2.40e-6),
    "qwen3.5-flash":             ( 0.10e-6,  0.40e-6),

    # ── Groq ─────────────────────────────────────────────────────────────────
    # llama-3.3-70b-versatile moved to Enterprise-only (no published rate) 2026-08-26
    # gpt-oss model IDs require the "openai/" prefix in the Groq API
    "openai/gpt-oss-20b":                   ( 0.075e-6, 0.30e-6),
    "openai/gpt-oss-120b":                  ( 0.15e-6,  0.60e-6),
    "llama-3.1-8b-instant":                 ( 0.05e-6,  0.08e-6),  # free tier

    # ── Kimi (Moonshot AI) ───────────────────────────────────────────────────
    "kimi-k3":                   ( 3.00e-6, 15.00e-6),  # flagship; 1M context; added 2026-07-16
    "kimi-k2.6":                 ( 0.95e-6,  4.00e-6),  # general model
    "kimi-k2.7-code":            ( 0.95e-6,  4.00e-6),  # coding specialist
}

# Conservative fallback for models not in the table — avoids silent $0 underreporting
_FALLBACK: tuple[float, float] = (3.00e-6, 3.00e-6)


def estimate_cost(model: str, input_tokens: int, output_tokens: int,
                  is_local: bool = False) -> float:
    """Return estimated cost in USD for a single LLM call.

    Pass is_local=True for Ollama (always $0.00).
    Unknown models use a conservative fallback rate.
    """
    if is_local:
        return 0.0
    rates = _PRICING.get(model, _FALLBACK)
    return input_tokens * rates[0] + output_tokens * rates[1]
