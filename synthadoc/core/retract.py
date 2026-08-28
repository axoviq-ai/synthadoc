# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Sensitive-data detection and masking for wiki pages.

Usage
-----
scanner = SensitiveScanner(config.security)
matches = scanner.scan_page(slug, content)          # pure text scan
masked_content, lines_changed = scanner.mask_page(slug, content, matches)
"""
from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from synthadoc.config import SecurityConfig


class SensitiveDataType(str, enum.Enum):
    """Built-in sensitive data categories.

    Extensible without code changes: users add custom patterns via
    ``[[security.custom_patterns]]`` in config.toml; those matches
    surface with type ``CUSTOM`` and the user-supplied pattern name.
    """
    API_KEY = "api_key"
    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    GENERIC_SECRET = "generic_secret"
    CUSTOM = "custom"


@dataclass(frozen=True)
class ScanMatch:
    """One detected sensitive-data occurrence.

    Attributes
    ----------
    slug:
        Wiki page slug containing the match.
    line_no:
        1-indexed line number.
    data_type:
        Category of sensitive data detected.
    pattern_name:
        Canonical name of the pattern that fired
        (e.g. ``"api_key"`` or a user-defined custom name).
    """
    slug: str
    line_no: int
    data_type: SensitiveDataType
    pattern_name: str


# ---------------------------------------------------------------------------
# Built-in pattern table
# Each entry: (SensitiveDataType, compiled_regex, replacement_template)
# Replacement template uses re.sub() syntax:
#   - Literal "[REDACTED]" for patterns with no capture groups
#   - Backreference strings (r"\1\2[REDACTED]\3") to preserve key names
# ---------------------------------------------------------------------------

_BUILT_IN_PATTERNS: list[tuple[SensitiveDataType, re.Pattern, str]] = [
    (
        SensitiveDataType.API_KEY,
        re.compile(
            r'(?i)(api[_-]?key|apikey|api[_-]?token)'   # group 1: key name
            r'(\s*[:=]\s*)'                               # group 2: separator
            r'(["\']?)([A-Za-z0-9_\-]{20,})\3'          # group 3: optional quote; group 4: value
        ),
        r'\1\2\3[REDACTED]\3',
    ),
    (
        SensitiveDataType.EMAIL,
        re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'),
        '[REDACTED]',
    ),
    (
        SensitiveDataType.PHONE,
        re.compile(
            r'\b(?:\+?1[\s.\-]?)?\(?[0-9]{3}\)?[\s.\-][0-9]{3}[\s.\-][0-9]{4}\b'
        ),
        '[REDACTED]',
    ),
    (
        SensitiveDataType.SSN,
        re.compile(
            r'\b(?!000|666|9\d{2})\d{3}[-\s]?(?!00)\d{2}[-\s]?(?!0000)\d{4}\b'
        ),
        '[REDACTED]',
    ),
    (
        SensitiveDataType.CREDIT_CARD,
        re.compile(
            # Matches card numbers written as consecutive digits OR with a
            # single space or dash between each 4-digit group (the common
            # human-readable format, e.g. "4532 0151 2345 6789").
            # Separator must be consistent: all spaces or all dashes, not mixed.
            r'\b(?:'
            r'4[0-9]{3}(?:[ \-]?[0-9]{4}){3}'              # Visa (16 digits)
            r'|4[0-9]{3}(?:[ \-]?[0-9]{4}){2}(?:[ \-]?[0-9]{1,3})?'  # Visa 13
            r'|5[1-5][0-9]{2}(?:[ \-]?[0-9]{4}){3}'        # MasterCard
            r'|3[47][0-9]{2}[ \-]?[0-9]{6}[ \-]?[0-9]{5}'  # Amex (15 digits)
            r'|6(?:011|5[0-9]{2})(?:[ \-]?[0-9]{4}){3}'    # Discover
            r')\b'
        ),
        '[REDACTED]',
    ),
    (
        SensitiveDataType.GENERIC_SECRET,
        re.compile(
            r'(?i)(secret|password|passwd|pwd|token)'  # group 1: key name
            r'(\s*[:=]\s*)'                            # group 2: separator
            r'(["\']?)(?!\[REDACTED\])([^\s"\']{8,})\3'  # group 3: quote; group 4: value
            #           ^^^^^^^^^^^^^^ skip lines already masked by a prior pass
        ),
        r'\1\2\3[REDACTED]\3',
    ),
]


class SensitiveScanner:
    """Detect and mask sensitive data in wiki page content.

    Patterns are applied to individual lines so line numbers are
    accurately reported. The class is pure (no I/O): callers supply
    the content string and receive structured results.

    Parameters
    ----------
    security_config:
        The ``SecurityConfig`` instance from the loaded wiki config.
        Custom patterns defined there are compiled at construction time.
    """

    def __init__(self, security_config: "SecurityConfig") -> None:
        self._custom: list[tuple[str, re.Pattern]] = []
        for p in security_config.custom_patterns:
            flags = re.IGNORECASE if p.get("flags", "").lower() == "i" else 0
            # Raises re.error on invalid pattern — let it propagate at init time
            compiled = re.compile(p["pattern"], flags)
            self._custom.append((p["name"], compiled))

    def scan_page(self, slug: str, content: str) -> list[ScanMatch]:
        """Return one ScanMatch per (line, pattern) hit in *content*.

        Sensitive values are NEVER included in the returned objects.
        Each ScanMatch records only slug, 1-indexed line number, data
        type, and pattern name.
        """
        matches: list[ScanMatch] = []
        seen: set[tuple[int, str]] = set()  # (line_no, pattern_name) dedup

        for line_no, line in enumerate(content.splitlines(), start=1):
            for data_type, pattern, _ in _BUILT_IN_PATTERNS:
                if pattern.search(line):
                    key = (line_no, data_type.value)
                    if key not in seen:
                        seen.add(key)
                        matches.append(ScanMatch(
                            slug=slug,
                            line_no=line_no,
                            data_type=data_type,
                            pattern_name=data_type.value,
                        ))
            for name, pattern in self._custom:
                if pattern.search(line):
                    key = (line_no, name)
                    if key not in seen:
                        seen.add(key)
                        matches.append(ScanMatch(
                            slug=slug,
                            line_no=line_no,
                            data_type=SensitiveDataType.CUSTOM,
                            pattern_name=name,
                        ))
        return matches

    def mask_page(
        self,
        slug: str,
        content: str,
        matches: list[ScanMatch],
    ) -> tuple[str, int]:
        """Apply [REDACTED] substitutions to all matched lines.

        Parameters
        ----------
        slug:
            Wiki page slug (used only for future extensibility / logging).
        content:
            Full page content string (may include YAML frontmatter).
        matches:
            Output of a prior ``scan_page()`` call on this content.

        Returns
        -------
        tuple[str, int]
            ``(masked_content, lines_changed)`` where *lines_changed* is
            the count of lines that were actually modified.
        """
        if not matches:
            return content, 0

        match_line_nos = {m.line_no for m in matches}
        lines = content.splitlines(keepends=True)
        changed = 0

        for i in range(len(lines)):
            line_no = i + 1
            if line_no not in match_line_nos:
                continue
            new_line = lines[i]
            for _, pattern, repl in _BUILT_IN_PATTERNS:
                new_line = pattern.sub(repl, new_line)
            for _, pattern in self._custom:
                new_line = pattern.sub("[REDACTED]", new_line)
            if new_line != lines[i]:
                lines[i] = new_line
                changed += 1

        return "".join(lines), changed
