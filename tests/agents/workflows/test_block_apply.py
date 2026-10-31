# Copyright (C) 2026 William Johnason / axoviq.com
from synthadoc.agents.workflows.block_apply import apply_blocks, normalize_whitespace


def test_normalize_collapses_spaces():
    assert normalize_whitespace("a  b\r\nc") == "a b\nc"


def test_basic_apply():
    body = "Hello world. Goodbye world."
    result = apply_blocks(body, [{"old_text": "Hello world.", "new_text": "Hi world."}])
    assert result.applied_count == 1
    assert result.rejected_count == 0
    assert "Hi world." in result.accumulated_body


def test_no_match_rejected():
    body = "Hello world."
    result = apply_blocks(body, [{"old_text": "Not present.", "new_text": "X"}])
    assert result.blocks[0].status == "rejected"
    assert result.blocks[0].rejection_reason == "no_match"
    assert result.accumulated_body == body


def test_duplicate_old_text_second_rejected():
    body = "Fix this. Fix this."
    result = apply_blocks(body, [
        {"old_text": "Fix this.", "new_text": "Done."},
        {"old_text": "Fix this.", "new_text": "Also done."},
    ])
    applied = [b for b in result.blocks if b.status == "applied"]
    rejected = [b for b in result.blocks if b.status == "rejected"]
    assert len(applied) == 1
    assert len(rejected) == 1
    assert rejected[0].rejection_reason == "no_match"


def test_overlapping_blocks_both_rejected():
    body = "The quick brown fox."
    result = apply_blocks(body, [
        {"old_text": "quick brown", "new_text": "slow red"},
        {"old_text": "brown fox",   "new_text": "red dog"},
    ])
    assert all(b.status == "rejected" for b in result.blocks)
    assert all(b.rejection_reason == "conflict" for b in result.blocks)


def test_heading_mutation_rejected():
    body = "# My Heading\n\nSome text."
    result = apply_blocks(body, [{"old_text": "# My Heading", "new_text": "# Renamed Heading"}])
    assert result.blocks[0].status == "rejected"
    assert result.blocks[0].rejection_reason == "heading_mutation"


def test_sentence_loss_rejected():
    body = "First sentence. Second sentence. Third sentence."
    # new_text drops two of three sentences — below 80% retention
    result = apply_blocks(body, [
        {"old_text": "First sentence. Second sentence. Third sentence.",
         "new_text": "First sentence."}
    ])
    assert result.blocks[0].status == "rejected"
    assert result.blocks[0].rejection_reason == "sentence_loss"


def test_blocks_applied_in_document_order():
    body = "A. B. C."
    result = apply_blocks(body, [
        {"old_text": "C.", "new_text": "Z."},
        {"old_text": "A.", "new_text": "X."},
    ])
    assert result.applied_count == 2
    assert result.accumulated_body == "X. B. Z."


def test_partial_apply_bad_block_discarded():
    body = "Fix me. Keep me."
    result = apply_blocks(body, [
        {"old_text": "Fix me.",   "new_text": "Fixed."},
        {"old_text": "Not here.", "new_text": "X"},
    ])
    assert result.applied_count == 1
    assert result.rejected_count == 1
    assert "Fixed." in result.accumulated_body
    assert "Keep me." in result.accumulated_body
