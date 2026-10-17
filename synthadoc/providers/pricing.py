# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Per-model LLM pricing table.

Refresh at each major release. Update _LAST_UPDATED and the rates below.
Sources (checked 2026-10-16):
  Anthropic — https://platform.claude.com/docs/en/about-claude/pricing
  OpenAI    — https://developers.openai.com/api/docs/pricing
  Gemini    — https://ai.google.dev/gemini-api/docs/pricing
  Groq      — https://console.groq.com/docs/models
  MiniMax   — https://platform.minimax.io/docs/guides/pricing-paygo
  DeepSeek  — https://api-docs.deepseek.com/quick_start/pricing
  Qwen      — https://www.alibabacloud.com/help/en/model-studio/model-pricing
  Kimi      — https://platform.moonshot.cn/docs/pricing (unchanged; not a configurable provider)

Tiered and date-scheduled prices record the CURRENT base rate; a comment gives the
tier threshold or change date and the future rate. Next scheduled refresh: early
January 2027 (Gemini 3.x Flash promotional rates end 2026-12-31).
"""
from __future__ import annotations

_LAST_UPDATED = "2026-10-16"

# (input_usd_per_token, output_usd_per_token)
# All rates are cache-miss / non-cached standard tier unless noted.
_PRICING: dict[str, tuple[float, float]] = {
    # ── Anthropic ────────────────────────────────────────────────────────────
    "claude-fable-5-1":          (10.00e-6, 50.00e-6),  # most capable (GA 2026-09)
    "claude-opus-5-5":           ( 4.00e-6, 20.00e-6),  # added 2026-10 (GA 2026-09-22)
    "claude-sonnet-5-5":         ( 2.00e-6, 10.00e-6),  # added 2026-10 (GA 2026-09-28)
    "claude-haiku-5-5":          ( 0.10e-6,  0.50e-6),  # added 2026-10; prompts >100K tokens: $0.50/$2.50
    "claude-fable-5":            (10.00e-6, 50.00e-6),
    "claude-opus-5":             ( 5.00e-6, 25.00e-6),  # added 2026-07-24
    "claude-opus-4-8":           ( 5.00e-6, 25.00e-6),  # recommended for agentic/enterprise
    "claude-sonnet-5":           ( 2.00e-6, 10.00e-6),  # $2/$10 confirmed permanent (Sept 1 increase cancelled)
    "claude-haiku-4-5-20251001": ( 1.00e-6,  5.00e-6),  # retirement eligible from 2026-10-15 (not yet announced)
    # legacy — still available
    "claude-opus-4-7":           ( 5.00e-6, 25.00e-6),
    "claude-opus-4-6":           ( 5.00e-6, 25.00e-6),
    "claude-sonnet-4-6":         ( 3.00e-6, 15.00e-6),

    # ── OpenAI ───────────────────────────────────────────────────────────────
    # GPT-6.x / GPT-5.x (current flagship families)
    "gpt-6-astra":               (10.00e-6, 50.00e-6),  # added 2026-09-03
    "gpt-6.1-sol":               ( 2.00e-6, 10.00e-6),  # added 2026-10
    "gpt-6-sol":                 ( 2.00e-6, 10.00e-6),  # added 2026-10
    "gpt-6-luna":                ( 0.10e-6,  0.50e-6),  # added 2026-10
    "gpt-5.6-sol":               ( 4.00e-6, 20.00e-6),  # promotional rate "at least through 2026-11-21"; was $5/$30
    "gpt-5.6-terra":             ( 2.00e-6, 12.00e-6),  # price cut 2026-07-30
    "gpt-5.6-luna":              ( 0.20e-6,  1.20e-6),  # price cut 2026-07-30
    "gpt-5.5":                   ( 5.00e-6, 30.00e-6),
    "gpt-5.4":                   ( 2.50e-6, 15.00e-6),
    "gpt-5.4-mini":              ( 0.75e-6,  4.50e-6),
    "gpt-5.4-nano":              ( 0.20e-6,  1.25e-6),  # added 2026-10
    "gpt-5.2":                   ( 1.75e-6, 14.00e-6),  # added 2026-10
    "gpt-5.1":                   ( 1.25e-6, 10.00e-6),  # added 2026-10
    "gpt-5":                     ( 1.25e-6, 10.00e-6),  # added 2026-10
    "gpt-5-mini":                ( 0.25e-6,  2.00e-6),  # added 2026-10
    "gpt-5-nano":                ( 0.05e-6,  0.40e-6),  # added 2026-10
    # GPT-4.x / reasoning
    "gpt-4.1":                   ( 2.00e-6,  8.00e-6),
    "gpt-4.1-mini":              ( 0.40e-6,  1.60e-6),
    "gpt-4o":                    ( 2.50e-6, 10.00e-6),
    "gpt-4o-mini":               ( 0.15e-6,  0.60e-6),
    "o3":                        ( 2.00e-6,  8.00e-6),
    "o4-mini":                   ( 1.10e-6,  4.40e-6),

    # ── Gemini ───────────────────────────────────────────────────────────────
    # Gemini 3.x (current)
    "gemini-4-argon":            ( 2.00e-6, 10.00e-6),  # added 2026-10; introductory through 2026-11-30, then $4/$20
    "gemini-3.8-flash":          ( 0.75e-6,  3.75e-6),  # promotional through 2026-12-31, then $1.50/$7.50
    "gemini-3.7-flash":          ( 0.75e-6,  3.75e-6),  # no longer on Google's price list (2026-10)
    "gemini-3.6-flash":          ( 0.75e-6,  3.75e-6),  # promotional through 2026-12-31, then $1.50/$7.50
    "gemini-3.5-flash":          ( 1.50e-6,  9.00e-6),  # no longer on Google's price list (2026-10)
    "gemini-3.5-flash-lite":     ( 0.30e-6,  2.50e-6),
    "gemini-3.1-flash-lite":     ( 0.25e-6,  1.50e-6),
    "gemini-3.1-pro-preview":    ( 2.00e-6, 12.00e-6),  # ≤200k input tier
    # Gemini 2.5
    "gemini-2.5-pro":            ( 1.25e-6, 10.00e-6),  # ≤200k input tier
    "gemini-2.5-flash":          ( 0.30e-6,  2.50e-6),
    "gemini-2.5-flash-lite":     ( 0.10e-6,  0.40e-6),

    # ── MiniMax ──────────────────────────────────────────────────────────────
    # M3 rates include MiniMax's permanent 50% discount; highspeed = priority queue
    "MiniMax-M3":                ( 0.30e-6,  1.20e-6),  # ≤512K input; >512K: $0.60/$2.40
    "MiniMax-M2.7":              ( 0.30e-6,  1.20e-6),  # corrected 2026-10 (was $0.21/$0.84)
    "MiniMax-M2.7-highspeed":    ( 0.60e-6,  2.40e-6),  # corrected 2026-10 (was $0.42/$1.68)
    "MiniMax-M2.5":              ( 0.30e-6,  1.20e-6),
    "MiniMax-M2.5-highspeed":    ( 0.60e-6,  2.40e-6),
    "MiniMax-M2.1":              ( 0.30e-6,  1.20e-6),  # legacy

    # ── DeepSeek ─────────────────────────────────────────────────────────────
    # Rates are PEAK pricing (01:00-04:00 and 06:00-10:00 UTC, Mon-Fri); off-peak = 50%.
    # deepseek-chat / deepseek-reasoner are aliases deprecated 2026-07-24 and no longer
    # documented; they map to the Flash model's non-thinking / thinking modes.
    "deepseek-flash":            ( 0.30e-6,  1.20e-6),  # DeepSeek-V4.1-Flash (released 2026-09-10); current name
    "deepseek-v4-flash":         ( 0.30e-6,  1.20e-6),  # legacy alias; now served by V4.1-Flash
    "deepseek-v4-pro":           ( 1.32e-6,  3.96e-6),  # corrected 2026-10: peak rate (was off-peak $0.66/$1.98)
    "deepseek-chat":             ( 0.30e-6,  1.20e-6),  # → deepseek-v4-flash (non-thinking)
    "deepseek-reasoner":         ( 0.30e-6,  1.20e-6),  # → deepseek-v4-flash (thinking mode)
    "deepseek-v3":               ( 0.30e-6,  1.20e-6),  # legacy
    "deepseek-r1":               ( 0.66e-6,  1.98e-6),  # legacy

    # ── Qwen / DashScope (international / Singapore tier) ────────────────────
    # Legacy names (qwen-X) still accepted by DashScope API and route correctly.
    # New Qwen 3.x names (qwen3.X-Y) cannot yet be used in config.toml — the
    # provider routing regex only matches names starting with "qwen-" or "qwq-".
    "qwen-turbo":                ( 0.05e-6,  0.20e-6),  # legacy; not on the international price list (2026-10)
    "qwen-flash":                ( 0.05e-6,  0.40e-6),  # corrected 2026-10 (≤256K input; >256K: $0.25/$2.00)
    "qwen-plus":                 ( 0.40e-6,  1.20e-6),  # corrected 2026-10: non-thinking (thinking output $4.00; >256K: $1.20/$3.60)
    "qwen-max":                  ( 1.60e-6,  6.40e-6),
    "qwq-32b":                   ( 0.80e-6,  2.40e-6),  # reasoning; not on the international price list (2026-10)
    "qwq-plus":                  ( 0.80e-6,  2.40e-6),  # reasoning; not on the international price list (2026-10)
    # Qwen 3.x (pricing only; not yet usable in config.toml — see routing note above)
    "qwen3.8-max":               ( 2.00e-6,  6.00e-6),  # added 2026-08-03
    "qwen3.8-flash":             ( 0.15e-6,  0.47e-6),  # corrected 2026-10 (was $0.14/$0.42)
    "qwen3.8-27b":               ( 0.50e-6,  3.00e-6),  # added 2026-10
    "qwen3.7-max":               ( 2.50e-6,  7.50e-6),  # added 2026-10
    "qwen3.7-plus":              ( 0.40e-6,  1.60e-6),  # added 2026-10 (≤256K input; >256K: $1.20/$4.80)
    "qwen3.7-flash":             ( 0.03e-6,  0.13e-6),  # added 2026-10 (≤32K; 32-256K: $0.10/$0.40; >256K: $0.20/$0.80)
    "qwen3.6-plus":              ( 0.50e-6,  3.00e-6),  # added 2026-10 (≤256K input)
    "qwen3.6-flash":             ( 0.25e-6,  1.50e-6),  # added 2026-10 (≤256K input)
    "qwen3.5-397b-a17b":         ( 0.60e-6,  3.60e-6),  # corrected ID 2026-10 (was "qwen3.5-397b")
    "qwen3.5-plus":              ( 0.40e-6,  2.40e-6),
    "qwen3.5-flash":             ( 0.10e-6,  0.40e-6),

    # ── Groq ─────────────────────────────────────────────────────────────────
    # gpt-oss model IDs require the "openai/" prefix in the Groq API
    "openai/gpt-oss-20b":                   ( 0.075e-6, 0.30e-6),
    "openai/gpt-oss-120b":                  ( 0.15e-6,  0.60e-6),
    "qwen/qwen3.8-27b":                     ( 0.80e-6,  4.00e-6),  # added 2026-10; Groq preview (not for production)
    # Llama 3.x: self-serve retired 2026-08-16; contact-sales only (last published rate kept)
    "llama-3.1-8b-instant":                 ( 0.05e-6,  0.08e-6),

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
