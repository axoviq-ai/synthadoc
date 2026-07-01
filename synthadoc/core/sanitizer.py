# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Pre-LLM source text sanitizer.

Strips known prompt-injection vectors and malicious content before
any text reaches the LLM. Zero LLM cost; pure Python; auditable via warnings.
"""
from __future__ import annotations

import re

# --- Compiled patterns ---
_ZERO_WIDTH = re.compile("[\u200B\u200C\u200D\uFEFF]")
_BIDI = re.compile("[\u202A-\u202E\u2066-\u2069]")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_HIDDEN_SPAN = re.compile(
    r'<[^>]+style\s*=\s*["\'][^"\']*(?:display\s*:\s*none|visibility\s*:\s*hidden)[^"\']*["\'][^>]*>.*?</[^>]+>',
    re.DOTALL | re.IGNORECASE,
)
_BASE64_BLOB = re.compile(r"[A-Za-z0-9+/=]{200,}")
_OVERRIDE_PHRASES = re.compile(
    r"(?:"
    r"ignore\s+previous\s+instructions?"
    r"|disregard\s+the\s+above"
    r"|override\s+your\s+system\s+prompt"
    r"|forget\s+all\s+previous\s+instructions?"
    r"|you\s+are\s+now\s+(?:a\s+)?(?:an?\s+)?\w+"
    r"|act\s+as\s+(?:if\s+you\s+(?:are|were)\s+)?\w+"
    r"|pretend\s+you\s+(?:are|have\s+no)"
    r"|jailbreak"
    r")",
    re.IGNORECASE,
)


def sanitize(text: str) -> tuple[str, list[str]]:
    """Strip injection vectors from *text*. Returns (cleaned_text, warnings).

    warnings is empty when nothing suspicious was found.
    Applied in order: zero-width → bidi → HTML comments → hidden blocks →
    base64 blobs → instruction-override phrases.
    """
    warnings: list[str] = []

    # 1. Zero-width chars — silent removal
    text = _ZERO_WIDTH.sub("", text)

    # 2. Bidi override chars — warn
    if _BIDI.search(text):
        warnings.append("bidi override characters removed")
        text = _BIDI.sub("", text)

    # 3. HTML comments — silent removal
    text = _HTML_COMMENT.sub("", text)

    # 4. display:none / visibility:hidden blocks — silent removal
    text = _HIDDEN_SPAN.sub("", text)

    # 5. Base64 blobs ≥ 200 chars — warn
    if _BASE64_BLOB.search(text):
        warnings.append("base64 blob(s) removed")
        text = _BASE64_BLOB.sub("[base64 content removed]", text)
    # Note: line-wrapped base64 (MIME/PEM style, 64–76 chars/line) is not detected.

    # 6. Instruction-override phrases — always warn
    if _OVERRIDE_PHRASES.search(text):
        warnings.append("instruction-override phrase redacted")
        text = _OVERRIDE_PHRASES.sub("[redacted]", text)

    return text, warnings
