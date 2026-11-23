# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Redaction: patterns, URLs, deep objects, registered values, logging, linear time."""
from __future__ import annotations

import io
import logging
import time

import pytest

from synthadoc.security.redact import (
    clear_registered_values,
    find_secret_params,
    install_log_filter,
    redact_obj,
    redact_text,
    redact_url,
    register_secret_value,
    safe_error,
)

MASK = "[REDACTED]"


@pytest.fixture(autouse=True)
def _clean_registry():
    clear_registered_values()
    yield
    clear_registered_values()


@pytest.mark.parametrize("text, secret", [
    ("Authorization: Bearer abc.DEF-123_xyz", "abc.DEF-123_xyz"),
    ("authorization=Basic dXNlcjpwYXNz", "dXNlcjpwYXNz"),
    ("Proxy-Authorization: Basic c2VjcmV0cw==", "c2VjcmV0cw"),
    ("Cookie: sid=abc123; theme=dark", "abc123"),
    ("Set-Cookie: session=topsecretvalue; Secure", "topsecretvalue"),
    ("headers={'Authorization': 'Bearer tok_1234567890abcdef'}", "tok_1234567890abcdef"),
    ("got Bearer abcdefgh12345678 back", "abcdefgh12345678"),
    ("key sd_ab12cd_" + "A1b2C3d4" * 5, "A1b2C3d4A1b2"),
    ("jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.c2lnbmF0dXJl end", "c2lnbmF0dXJl"),
    ("ANTHROPIC key sk-ant-api03-" + "x" * 40, "x" * 40),
    ("openai sk-proj-" + "y" * 30, "y" * 30),
    ("tavily tvly-" + "z" * 24, "z" * 24),
    ("gemini AIza" + "Q" * 35, "Q" * 35),
    ("groq gsk_" + "g" * 24, "g" * 24),
    ("github ghp_" + "h" * 36, "h" * 36),
    ("slack xoxb-1234567890-abcdefghij", "1234567890-abcdefghij"),
    ("aws AKIAABCDEFGHIJKLMNOP end", "AKIAABCDEFGHIJKLMNOP"),
    ("clone https://user:hunter2@example.com/repo.git", "hunter2"),
    ("clone https://ghp_abcdefghijklmnopqrstuvwxyz0123456789@github.com/o/r", "ghp_abcdef"),
    ("GET https://api.example.com/v1?api_key=SECRET123&x=1", "SECRET123"),
    ("https://x.example/p?a=1&Token=S3CR3T&b=2", "S3CR3T"),
    ("https://x.example/p?X-Amz-Signature=abcdef012345&X-Amz-Date=20260101", "abcdef012345"),
    ("redirect #access_token=frag123456 done", "frag123456"),
    ("password=hunter2 and more", "hunter2"),
    ('{"client_secret": "shhh-its-secret"}', "shhh-its-secret"),
    ("api-key: 0123456789abcdef", "0123456789abcdef"),
])
def test_secret_is_removed(text, secret):
    out = redact_text(text)
    assert secret not in out
    assert MASK in out


@pytest.mark.parametrize("text", [
    "plain log line with no secrets",
    "mail me at bob@example.com about max_tokens=500 and tokens_used: 5",
    "risk-based-assessment-framework-for-sk-learn",
    "https://example.com/path?page=2&lang=en",
])
def test_benign_text_is_untouched(text):
    assert redact_text(text) == text


def test_log_masking_uses_the_broad_parameter_list():
    # Over-redacting a log line is harmless; refusal uses the narrow list (find_secret_params).
    assert redact_text("https://example.com/p?code=US&page=2") == f"https://example.com/p?code={MASK}&page=2"


@pytest.mark.parametrize("text", [
    "Authorization: Bearer abc.DEF-123_xyz",
    "password=hunter2 api_key=abcd1234 https://u:p@h/x?token=t&a=1",
    "sk-ant-api03-" + "x" * 40 + " Cookie: a=b",
    "nothing to see",
])
def test_redaction_is_idempotent(text):
    once = redact_text(text)
    assert redact_text(once) == once


def test_non_strings_pass_through():
    assert redact_text(None) is None
    assert redact_text(42) == 42


def test_registered_values_are_scrubbed_anywhere():
    register_secret_value("my-oauth-token-value-123")
    register_secret_value(b"bytes-secret-value-456")
    out = redact_text("a my-oauth-token-value-123 b bytes-secret-value-456 c")
    assert "oauth-token-value" not in out and "bytes-secret" not in out


def test_very_short_registered_values_are_ignored():
    register_secret_value("ab")
    assert redact_text("about the lab") == "about the lab"


def test_registry_is_capped():
    for i in range(1500):
        register_secret_value(f"secret-value-{i:05d}")
    assert redact_text("x secret-value-00001 y") != ""   # still works under the cap


@pytest.mark.parametrize("prefix", [
    "Bearer ", "sd_", "sd_a_", "://", "https://a:", "?token=", "&k=", "sk-", "sk-ant-",
    "eyJ", "eyJa.b.", "password=", "Authorization: ", "Cookie:", "AKIA", "AIza", "gsk_",
    "xoxb-", "ghp_", "tvly-", "#access_token=",
])
def test_patterns_run_in_linear_time(prefix):
    for filler in ("a" * 200_000, " " * 200_000, "&" * 100_000, "-_" * 100_000):
        start = time.perf_counter()
        redact_text(prefix + filler)
        assert time.perf_counter() - start < 2.0, (prefix, filler[:4])


def test_repeated_prefixes_run_in_linear_time():
    start = time.perf_counter()
    redact_text("Bearer " * 30_000)
    redact_text("://" * 30_000)
    redact_text("sd_a" * 30_000)
    assert time.perf_counter() - start < 3.0


# ---- URLs -------------------------------------------------------------------

def test_redact_url_drops_userinfo_and_masks_broad_params():
    out = redact_url("https://user:pw@example.com/p?code=US&page=2&API_KEY=abc#access_token=zzz")
    assert "pw" not in out and "abc" not in out and "zzz" not in out
    assert "page=2" in out and "example.com/p" in out


def test_redact_url_keeps_a_clean_url_equivalent():
    assert redact_url("https://example.com/a/b?x=1") == "https://example.com/a/b?x=1"


def test_redact_url_on_garbage_falls_back_to_text_redaction():
    assert "hunter2" not in redact_url("not a url password=hunter2")


def test_find_secret_params_uses_the_narrow_list():
    assert find_secret_params("https://h/p?api_key=1&x=2&Token=3") == ["api_key", "Token"]
    assert find_secret_params("https://h/p?X-Amz-Signature=abc&X-Amz-Date=1") == ["X-Amz-Signature"]
    # identifiers must never gate ingest
    assert find_secret_params("https://h/p?code=US&key=docid&sig=1&auth=2") == []
    assert find_secret_params("https://h/p") == []


# ---- objects ----------------------------------------------------------------

def test_redact_obj_masks_sensitive_keys_deeply_without_mutating():
    original = {
        "Authorization": "Bearer abc", "user": "bob", "nested": {"password": "pw", "ok": 1},
        "items": [{"api_key": "k"}, "https://h/p?token=zzz"], "pair": ("x", {"secret": "s"}),
        "max_tokens": 500, "tokens_used": 7, "input_tokens": 3,
        "gh_api_key": "k2", "none": None,
    }
    snapshot = repr(original)
    out = redact_obj(original)
    assert repr(original) == snapshot
    assert out["Authorization"] == MASK and out["nested"]["password"] == MASK
    assert out["items"][0]["api_key"] == MASK and "zzz" not in out["items"][1]
    assert out["pair"][1]["secret"] == MASK and isinstance(out["pair"], tuple)
    assert out["gh_api_key"] == MASK
    assert out["user"] == "bob" and out["nested"]["ok"] == 1
    assert out["max_tokens"] == 500 and out["tokens_used"] == 7 and out["input_tokens"] == 3
    assert out["none"] is None


def test_redact_obj_handles_cycles_and_odd_types():
    loop: dict = {"a": 1}
    loop["self"] = loop
    assert redact_obj(loop)["a"] == 1               # no infinite recursion
    assert redact_obj(5) == 5 and redact_obj(b"raw") == b"raw"


# ---- errors and logging -----------------------------------------------------

def test_safe_error_returns_the_public_text_and_logs_redacted_detail(caplog):
    caplog.set_level(logging.DEBUG)
    out = safe_error(RuntimeError("boom password=hunter2"), public="Something failed.")
    assert out == "Something failed."
    assert "boom" in caplog.text and "hunter2" not in caplog.text


def _logger_with_filter(name: str, stream: io.StringIO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)
    install_log_filter([name])
    return logger


def test_log_filter_redacts_message_args_and_exception_text():
    stream = io.StringIO()
    logger = _logger_with_filter("redact.test.a", stream)
    logger.warning("call %s failed: %s", 42, "Authorization: Bearer abcdefgh12345678")
    try:
        raise ValueError("bad password=hunter2")
    except ValueError:
        logger.error("boom", exc_info=True)
    out = stream.getvalue()
    assert "abcdefgh12345678" not in out and "hunter2" not in out
    assert "42" in out and "boom" in out and "ValueError" in out


def test_log_filter_is_idempotent_and_leaves_clean_records_alone():
    stream = io.StringIO()
    logger = _logger_with_filter("redact.test.b", stream)
    install_log_filter(["redact.test.b"])
    install_log_filter(["redact.test.b"])
    logger.info("hello %s", "world")
    assert stream.getvalue().strip() == "INFO hello world"
    assert sum(type(f).__name__ == "RedactingFilter"
               for h in logger.handlers for f in h.filters) == 1
