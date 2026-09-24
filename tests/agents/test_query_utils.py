# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from synthadoc.agents._query_utils import (
    has_cjk, detect_cjk_language, filter_history_by_language,
    history_block, build_synthesis_system, trim_history, STOPWORDS,
)

def test_has_cjk_false():
    assert has_cjk("hello world") is False

def test_has_cjk_true_chinese():
    assert has_cjk("北京") is True

def test_has_cjk_true_japanese():
    assert has_cjk("東京") is True

def test_detect_cjk_language_chinese():
    assert detect_cjk_language("北京") == "Chinese (Mandarin)"

def test_detect_cjk_language_japanese():
    assert detect_cjk_language("とうきょう") == "Japanese"

def test_detect_cjk_language_korean():
    assert detect_cjk_language("서울") == "Korean"

def test_filter_history_removes_mismatched_pair():
    history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "北京"},  # CJK response for English question
    ]
    result = filter_history_by_language(history, "hello again")
    assert result == []

def test_filter_history_keeps_matching():
    history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]
    assert filter_history_by_language(history, "how are you") == history

def test_history_block_empty():
    assert history_block([]) == ""

def test_history_block_formats():
    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    block = history_block(history, "how are you")
    assert "User: hi" in block
    assert "Assistant: hello" in block

def test_build_synthesis_system_english():
    s = build_synthesis_system("what is leverage?")
    assert "same language" in s.lower()

def test_build_synthesis_system_cjk():
    s = build_synthesis_system("北京是什么?")
    assert "Chinese" in s
    assert "MUST respond" in s

def test_trim_history_fits_all():
    h = [{"role": "user", "content": "ab"}, {"role": "assistant", "content": "cd"}]
    assert trim_history(h, 100) == h

def test_trim_history_drops_oldest_first():
    # budget=60: b_turn(50) + c_turn(10) = 60 exactly fits (uses >, not >=)
    # a_turn(50) would exceed: 60 + 50 = 110 > 60 → dropped
    h = [
        {"role": "user", "content": "a" * 50},
        {"role": "assistant", "content": "b" * 50},
        {"role": "user", "content": "c" * 10},
    ]
    result = trim_history(h, 60)
    assert result == [
        {"role": "assistant", "content": "b" * 50},
        {"role": "user", "content": "c" * 10},
    ]


def test_trim_history_drops_oldest_strict():
    # budget=59: b_turn(50) + c_turn(10) = 60 > 59 → b_turn dropped, only c_turn kept
    h = [
        {"role": "user", "content": "a" * 50},
        {"role": "assistant", "content": "b" * 50},
        {"role": "user", "content": "c" * 10},
    ]
    result = trim_history(h, 59)
    assert result == [{"role": "user", "content": "c" * 10}]

def test_stopwords_contains_common():
    assert "what" in STOPWORDS
    assert "how" in STOPWORDS
    assert "leverage" not in STOPWORDS  # content word
