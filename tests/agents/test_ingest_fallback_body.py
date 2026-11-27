# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Peter White / axoviq.com
"""The body built from raw source when the LLM returns no page_content is cut at
_FALLBACK_BODY_CHARS; the cut must be logged and marked on the page."""
from __future__ import annotations

import logging

from synthadoc.agents.ingest_agent import _FALLBACK_BODY_CHARS, _fallback_body, _rebuilt_body


def test_a_short_source_is_kept_whole_with_no_marker():
    body = _fallback_body("Enigma", "Short text.", "enigma.md", 11)
    assert body == "# Enigma\n\nShort text."


def test_a_long_source_is_cut_logged_and_marked(caplog):
    text = "x" * 9000
    with caplog.at_level(logging.WARNING, logger="synthadoc.agents.ingest_agent"):
        body = _fallback_body("Enigma", text, "enigma.md", 18230)
    assert body.count("x") == _FALLBACK_BODY_CHARS
    assert body.endswith(
        "> Truncated: showing the first 4,000 of 18,230 characters of enigma.md. "
        "Re-ingest with `--force` to retry.")
    assert "enigma.md" in caplog.text and "18230" in caplog.text


def test_a_source_of_exactly_the_limit_is_not_marked():
    body = _fallback_body("T", "y" * _FALLBACK_BODY_CHARS, "a.md", _FALLBACK_BODY_CHARS)
    assert "Truncated" not in body


def test_rebuilt_body_prefers_the_llm_body_and_falls_back_with_the_marker():
    assert _rebuilt_body("# T\n\nWritten by the model.", "T", "z" * 9000, "a.md", 9000) \
        == "# T\n\nWritten by the model."
    assert "Truncated" in _rebuilt_body("  ", "T", "z" * 9000, "a.md", 9000)
