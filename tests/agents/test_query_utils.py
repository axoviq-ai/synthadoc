# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from synthadoc.agents._query_utils import (
    has_cjk, detect_cjk_language, detect_latin_language,
    filter_history_by_language,
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
    assert "English" in s
    assert "MUST respond" in s

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


def test_detect_latin_language_english():
    assert detect_latin_language("what is the history of the computer") == "English"

def test_detect_latin_language_french():
    assert detect_latin_language("quel est le rôle des réseaux de neurones dans les systèmes") == "French"

def test_detect_latin_language_empty():
    assert detect_latin_language("") == ""

def test_detect_latin_language_ambiguous_returns_empty():
    # Single word with no stopword matches — score < 2, returns ""
    assert detect_latin_language("Turing") == ""

def test_detect_latin_language_ambiguous_scores_returns_empty():
    # Construct text where two languages score within 75% of each other
    # "le the la is" — French: le, la (2); English: the, is (2) → tie → ""
    assert detect_latin_language("le the la is") == ""

def test_filter_history_drops_latin_language_mismatch():
    # French assistant response should be dropped when question is in English
    history = [
        {"role": "user", "content": "what is the history of computing"},
        {"role": "assistant", "content": "le rôle des réseaux est fondamental dans les systèmes modernes"},
    ]
    result = filter_history_by_language(history, "what is the history of computing")
    assert result == []

def test_filter_history_keeps_same_latin_language():
    history = [
        {"role": "user", "content": "what is the history of computing"},
        {"role": "assistant", "content": "the history of computing is a fascinating subject"},
    ]
    result = filter_history_by_language(history, "how did the internet develop")
    assert result == history

def test_build_synthesis_system_french():
    s = build_synthesis_system("quel est le rôle des réseaux dans les systèmes")
    assert "French" in s
    assert "MUST respond" in s
