# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Compute proportional context budgets from model context window + config percentages."""
from __future__ import annotations

_CHARS_PER_TOKEN = 4

_MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-opus-4":     1_000_000,
    "claude-sonnet-4":   1_000_000,
    "claude-haiku-4":      200_000,
    "gpt-4o":              128_000,
    "gpt-4-turbo":         128_000,
    "gpt-4":                 8_192,
    "gpt-3.5-turbo":        16_385,
    "deepseek-v3":         128_000,
    "deepseek-r1":         128_000,
    "deepseek-v4":       1_000_000,
    "minimax/text-01":   1_000_000,
    "minimax/abab6.5":     204_800,
}
_DEFAULT_CONTEXT_WINDOW = 128_000


def resolve_context_window(model: str, config_override: int) -> int:
    """Return effective context window in tokens.
    If config_override > 0, use it. Otherwise prefix-match model name, falling back to 128k.
    """
    if config_override > 0:
        return config_override
    if model in _MODEL_CONTEXT_WINDOWS:
        return _MODEL_CONTEXT_WINDOWS[model]
    best = None
    for prefix, window in _MODEL_CONTEXT_WINDOWS.items():
        if model.startswith(prefix):
            if best is None or len(prefix) > len(best[0]):
                best = (prefix, window)
    return best[1] if best else _DEFAULT_CONTEXT_WINDOW


def compute_char_budgets(model: str, cfg) -> dict[str, int]:
    """Return char budgets for wiki/history/system/index given model + QueryConfig.

    wiki    — enforced in QueryAgent._build_wiki_context()
    history — enforced in QueryAgent._trim_history()
    system  — enforced in QueryAgent._load_purpose_context() (purpose.md preamble)
    index   — computed but not yet enforced; routing index is a structured object,
              not raw text injected into prompts
    """
    window = resolve_context_window(model, cfg.context_window)
    return {
        "wiki":    int(window * (cfg.context_wiki_pct    / 100) * _CHARS_PER_TOKEN),
        "history": int(window * (cfg.context_history_pct / 100) * _CHARS_PER_TOKEN),
        "system":  int(window * (cfg.context_system_pct  / 100) * _CHARS_PER_TOKEN),
        "index":   int(window * (cfg.context_index_pct   / 100) * _CHARS_PER_TOKEN),
    }
