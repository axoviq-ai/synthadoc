# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import pytest
from synthadoc.config import SecurityConfig
from synthadoc.core.retract import SensitiveDataType, ScanMatch, SensitiveScanner


def _scanner(custom_patterns=None) -> SensitiveScanner:
    cfg = SecurityConfig(
        sensitive_scan_enabled=True,
        custom_patterns=custom_patterns or [],
    )
    return SensitiveScanner(cfg)


# ---------------------------------------------------------------------------
# SensitiveDataType
# ---------------------------------------------------------------------------

def test_enum_values():
    assert SensitiveDataType.API_KEY.value == "api_key"
    assert SensitiveDataType.EMAIL.value == "email"
    assert SensitiveDataType.PHONE.value == "phone"
    assert SensitiveDataType.SSN.value == "ssn"
    assert SensitiveDataType.CREDIT_CARD.value == "credit_card"
    assert SensitiveDataType.GENERIC_SECRET.value == "generic_secret"
    assert SensitiveDataType.CUSTOM.value == "custom"


# ---------------------------------------------------------------------------
# scan_page — built-in patterns
# ---------------------------------------------------------------------------

def test_scan_api_key():
    s = _scanner()
    content = "Some config:\napi_key = sk-abcdefghijklmnopqrst\nOther line"
    matches = s.scan_page("test-page", content)
    assert any(m.data_type == SensitiveDataType.API_KEY for m in matches)
    match = next(m for m in matches if m.data_type == SensitiveDataType.API_KEY)
    assert match.slug == "test-page"
    assert match.line_no == 2
    assert match.pattern_name == "api_key"


def test_scan_email():
    s = _scanner()
    matches = s.scan_page("p", "Contact: user@example.com for help")
    assert any(m.data_type == SensitiveDataType.EMAIL for m in matches)


def test_scan_phone_us():
    s = _scanner()
    matches = s.scan_page("p", "Call us at 555-867-5309 anytime")
    assert any(m.data_type == SensitiveDataType.PHONE for m in matches)


def test_scan_ssn():
    s = _scanner()
    matches = s.scan_page("p", "SSN: 123-45-6789")
    assert any(m.data_type == SensitiveDataType.SSN for m in matches)


def test_scan_credit_card_consecutive():
    """16-digit Visa with no separators."""
    s = _scanner()
    matches = s.scan_page("p", "Card: 4111111111111111")
    assert any(m.data_type == SensitiveDataType.CREDIT_CARD for m in matches)


def test_scan_credit_card_spaced():
    """16-digit Visa written in the common 4-4-4-4 spaced format."""
    s = _scanner()
    matches = s.scan_page("p", "billing card on file 4532 0151 2345 6789 exp 09/28")
    assert any(m.data_type == SensitiveDataType.CREDIT_CARD for m in matches)


def test_scan_credit_card_dashed():
    """16-digit Visa with dash separators."""
    s = _scanner()
    matches = s.scan_page("p", "card: 4532-0151-2345-6789")
    assert any(m.data_type == SensitiveDataType.CREDIT_CARD for m in matches)


def test_scan_credit_card_mastercard_spaced():
    """MasterCard in spaced format."""
    s = _scanner()
    matches = s.scan_page("p", "mc: 5412 7512 3456 7890")
    assert any(m.data_type == SensitiveDataType.CREDIT_CARD for m in matches)


def test_scan_generic_secret():
    s = _scanner()
    matches = s.scan_page("p", "password = mysupersecretpassword123")
    assert any(m.data_type == SensitiveDataType.GENERIC_SECRET for m in matches)


def test_scan_generic_secret_already_redacted():
    """A line with 'password: [REDACTED]' must not re-trigger as a new match.

    [REDACTED] is 10 non-whitespace characters and would match the value group
    without the (?!\\[REDACTED\\]) negative lookahead guard.
    """
    s = _scanner()
    matches = s.scan_page("p", "   source-db-password: [REDACTED]")
    assert matches == [], (
        "scanner should not re-match a line whose value is already [REDACTED]"
    )


def test_scan_no_matches():
    s = _scanner()
    matches = s.scan_page("p", "This page has no sensitive data at all.")
    assert matches == []


def test_scan_returns_correct_line_numbers():
    s = _scanner()
    content = "line one\nline two\napi_key = sk-abcdefghijklmnopqrst\nline four"
    matches = s.scan_page("p", content)
    line_nos = [m.line_no for m in matches if m.data_type == SensitiveDataType.API_KEY]
    assert line_nos == [3]


def test_scan_multiple_matches_same_page():
    s = _scanner()
    content = "email: a@b.com\npassword = hunter2secr3t"
    matches = s.scan_page("p", content)
    types = {m.data_type for m in matches}
    assert SensitiveDataType.EMAIL in types
    assert SensitiveDataType.GENERIC_SECRET in types


# ---------------------------------------------------------------------------
# scan_page — custom patterns
# ---------------------------------------------------------------------------

def test_scan_custom_pattern():
    s = _scanner(custom_patterns=[
        {"name": "internal_token", "pattern": r"INTERNAL-[A-Z0-9]{16}"},
    ])
    matches = s.scan_page("p", "token: INTERNAL-ABCDEF1234567890")
    assert any(m.data_type == SensitiveDataType.CUSTOM for m in matches)
    assert any(m.pattern_name == "internal_token" for m in matches)


def test_scan_custom_pattern_case_insensitive():
    s = _scanner(custom_patterns=[
        {"name": "corp_id", "pattern": r"corp-\d{8}", "flags": "i"},
    ])
    matches = s.scan_page("p", "ID: CORP-12345678")
    assert any(m.pattern_name == "corp_id" for m in matches)


def test_scan_custom_invalid_regex_raises():
    with pytest.raises(Exception):
        _scanner(custom_patterns=[{"name": "bad", "pattern": r"[invalid"}])


# ---------------------------------------------------------------------------
# mask_page
# ---------------------------------------------------------------------------

def test_mask_email():
    s = _scanner()
    content = "Contact: user@example.com"
    matches = s.scan_page("p", content)
    masked, changed = s.mask_page("p", content, matches)
    assert "user@example.com" not in masked
    assert "[REDACTED]" in masked
    assert changed == 1


def test_mask_api_key_preserves_key_name():
    s = _scanner()
    content = "api_key = sk-abcdefghijklmnopqrst"
    matches = s.scan_page("p", content)
    masked, changed = s.mask_page("p", content, matches)
    # Key name survives; value is redacted
    assert "api_key" in masked
    assert "sk-abcdefghijklmnopqrst" not in masked
    assert "[REDACTED]" in masked


def test_mask_no_matches_returns_unchanged():
    s = _scanner()
    content = "Nothing sensitive here."
    masked, changed = s.mask_page("p", content, [])
    assert masked == content
    assert changed == 0


def test_mask_multiline_preserves_other_lines():
    s = _scanner()
    content = "safe line\napi_key = sk-abcdefghijklmnopqrst\nanother safe line"
    matches = s.scan_page("p", content)
    masked, _ = s.mask_page("p", content, matches)
    assert "safe line" in masked
    assert "another safe line" in masked


def test_mask_custom_pattern():
    s = _scanner(custom_patterns=[
        {"name": "tok", "pattern": r"INTERNAL-[A-Z0-9]{16}"},
    ])
    content = "key: INTERNAL-ABCDEF1234567890"
    matches = s.scan_page("p", content)
    masked, changed = s.mask_page("p", content, matches)
    assert "INTERNAL-ABCDEF1234567890" not in masked
    assert "[REDACTED]" in masked
    assert changed == 1


def test_mask_returns_correct_changed_count():
    s = _scanner()
    content = "a@b.com\nc@d.com\nnormal line"
    matches = s.scan_page("p", content)
    _, changed = s.mask_page("p", content, matches)
    assert changed == 2
