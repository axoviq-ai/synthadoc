# Copyright (C) 2026 William Johnason / axoviq.com
from synthadoc.agents.workflows.block_apply import (
    apply_blocks, normalize_whitespace, describe_all_blocks_rejected,
)


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


# ---------------------------------------------------------------------------
# New tests for Finding A (raw-body splicing) and Finding G (thin tests)
# ---------------------------------------------------------------------------

def test_empty_old_text_rejected():
    """Empty old_text must be rejected with no_match before any matching."""
    body = "Some content here."
    result = apply_blocks(body, [{"old_text": "", "new_text": "replacement"}])
    assert result.blocks[0].status == "rejected"
    assert result.blocks[0].rejection_reason == "no_match"
    assert result.accumulated_body == body


def test_whitespace_only_old_text_rejected():
    """Whitespace-only old_text must be rejected with no_match."""
    body = "Some content here."
    result = apply_blocks(body, [{"old_text": "   \t  ", "new_text": "replacement"}])
    assert result.blocks[0].status == "rejected"
    assert result.blocks[0].rejection_reason == "no_match"
    assert result.accumulated_body == body


def test_no_cross_contamination_from_earlier_block_new_text():
    """Earlier block's new_text may introduce a substring that matches a later
    block's old_text.  Reverse-order splicing must apply each block against the
    *original* raw body position, not against text produced by a prior splice.
    """
    # body = "aaa bbb."
    # Block 0 replaces "aaa" with "aaa bbb" (introduces an extra "bbb" prefix)
    # Block 1 replaces "bbb." with "ccc."
    # Correct result: "aaa bbb ccc." (block 1 replaced the ORIGINAL "bbb.", not the one introduced by block 0)
    body = "aaa bbb."
    result = apply_blocks(body, [
        {"old_text": "aaa",  "new_text": "aaa bbb"},  # new_text contains "bbb"
        {"old_text": "bbb.", "new_text": "ccc."},      # must match original position
    ])
    assert result.applied_count == 2
    assert result.accumulated_body == "aaa bbb ccc."


def test_raw_body_preserved_no_whitespace_damage():
    """apply_blocks must return the raw body (with original whitespace preserved),
    not a normalized version, for the parts not touched by any block.
    """
    # The body has list indentation and a fenced code block that normalize_whitespace
    # would damage (collapsing the leading spaces).
    body = "Intro.\n\n- item one\n  - nested item\n\n```python\nx  =  1\n```\n\nEnd."
    # Replace only "Intro." — everything else must be byte-for-byte identical.
    result = apply_blocks(body, [{"old_text": "Intro.", "new_text": "Introduction."}])
    assert result.applied_count == 1
    expected = "Introduction.\n\n- item one\n  - nested item\n\n```python\nx  =  1\n```\n\nEnd."
    assert result.accumulated_body == expected


def test_normalized_fallback_match():
    """old_text with extra internal spaces should still find a match via the
    normalized fallback path and splice the correct raw span.
    """
    # raw body has a single space; old_text has two spaces (normalized: same)
    body = "Hello world. Goodbye."
    result = apply_blocks(body, [{"old_text": "Hello  world.", "new_text": "Hi world."}])
    assert result.applied_count == 1
    assert result.accumulated_body == "Hi world. Goodbye."


# ---------------------------------------------------------------------------
# describe_all_blocks_rejected — shared "every block rejected" detection,
# used by both tool_propose_and_apply_blocks (contradiction_resolver's
# Strategy 1) and content_health_resolver's write_content_health_fix to skip
# the confusing full-page ScopedConfirmCard when nothing could be applied.
# ---------------------------------------------------------------------------

def test_describe_all_blocks_rejected_returns_none_when_something_applied():
    body = "Hello world. Goodbye."
    result = apply_blocks(body, [{"old_text": "Hello world.", "new_text": "Hi world."}])
    assert describe_all_blocks_rejected(result, [{"old_text": "Hello world.", "new_text": "Hi world."}]) is None


def test_describe_all_blocks_rejected_returns_none_for_no_blocks_proposed():
    """blocks=[] means nothing was proposed at all — a different case from
    'everything proposed was rejected', so it must not trigger the skip."""
    body = "Hello world."
    result = apply_blocks(body, [])
    assert describe_all_blocks_rejected(result, []) is None


def test_describe_all_blocks_rejected_returns_reasons_when_every_block_rejected():
    body = "Hello world."
    blocks = [{"old_text": "text that is not in the body", "new_text": "x"}]
    result = apply_blocks(body, blocks)
    assert result.applied_count == 0
    reasons = describe_all_blocks_rejected(result, blocks)
    assert reasons is not None
    assert "block 1" in reasons
    assert "no_match" in reasons


def test_describe_all_blocks_rejected_lists_every_rejected_block():
    body = "Hello world."
    blocks = [
        {"old_text": "not present one", "new_text": "x"},
        {"old_text": "not present two", "new_text": "y"},
    ]
    result = apply_blocks(body, blocks)
    reasons = describe_all_blocks_rejected(result, blocks)
    assert "block 1" in reasons and "block 2" in reasons
