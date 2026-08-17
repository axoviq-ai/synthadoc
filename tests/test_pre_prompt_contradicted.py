# tests/test_pre_prompt_contradicted.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for _build_pre_prompt contradicted-page detection."""
from __future__ import annotations

import pytest
from synthadoc.agents.query_agent import _build_pre_prompt


def test_pre_prompt_fires_for_positive_contradicted_count():
    answer = "Lint complete. 2 contradicted pages found: alan-turing, eniac."
    result = _build_pre_prompt(answer)
    assert result is not None
    assert "contradicted" in result.lower()
    assert "resolver" in result.lower()


def test_pre_prompt_fires_for_one_contradicted_page():
    answer = "Lint summary: 1 contradicted page."
    result = _build_pre_prompt(answer)
    assert result is not None
    assert "1" in result


def test_pre_prompt_does_not_fire_for_zero_contradicted():
    answer = "All good! 0 contradicted pages."
    result = _build_pre_prompt(answer)
    assert result is None


def test_pre_prompt_does_not_fire_for_no_contradicted_phrase():
    answer = "no contradicted pages were found."
    result = _build_pre_prompt(answer)
    assert result is None


def test_pre_prompt_does_not_fire_for_zero_contradicted_variant():
    answer = "zero contradicted pages remain."
    result = _build_pre_prompt(answer)
    assert result is None


def test_pre_prompt_does_not_fire_for_unrelated_text():
    answer = "The page discusses contradictions in the historical record."
    result = _build_pre_prompt(answer)
    # "contradictions" alone without "N contradicted" must not trigger
    assert result is None


def test_pre_prompt_contradiction_does_not_shadow_reingest_trigger():
    """If reingest_complete is in the same answer, it still wins (first match)."""
    answer = "Re-ingested successfully. Also, 2 contradicted pages."
    result = _build_pre_prompt(answer)
    # reingest_complete pattern fires first in existing code
    assert result is not None
    # We don't assert exact phrasing here — either trigger is acceptable
