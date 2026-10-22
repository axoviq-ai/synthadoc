#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
"""
Deterministic static-analysis security scan — zero LLM calls, pure Python.

Catches the finding categories reported by third-party repo audits: dynamic
code execution (eval/exec in Python, eval/Function in JS/TS), invisible
Unicode (zero-width and bidi-override characters, in every tracked document),
weak hashing, unreviewed binaries (content-sniffed, not a fixed extension
list — includes demo/template raw_sources/), and raw IP literals. All are
regex/pattern matches a human reviewer would otherwise have to catch by eye.
Scans only git-tracked files, so build output, node_modules, venvs, etc. are
excluded automatically.

Run locally before opening a PR:
    python scripts/security_scan.py

CI runs this on every push and PR; it fails the build on any HIGH or MEDIUM
finding. LOW findings are printed but do not fail the build:
    python scripts/security_scan.py --fail-on medium
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).parent.parent

_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}

# Loopback / any-interface addresses used intentionally throughout the CLI
# and server (see synthadoc/cli/_wiki.py LOOPBACK_HOST) — not a finding.
_ALLOWED_IPS = frozenset({"127.0.0.1", "0.0.0.0", "::1", "255.255.255.255"})
# RFC 5737 / RFC 2606 ranges reserved specifically for documentation examples.
_DOC_EXAMPLE_PREFIXES = ("192.0.2.", "198.51.100.", "203.0.113.")

# Same character classes synthadoc/core/sanitizer.py strips from ingested
# content at runtime — reused here to scan our own source for the same thing.
_ZERO_WIDTH_RE = re.compile("[" + "".join(chr(c) for c in (0x200B, 0x200C, 0x200D, 0xFEFF)) + "]")
_BIDI_RE = re.compile("[" + chr(0x202A) + "-" + chr(0x202E) + chr(0x2066) + "-" + chr(0x2069) + "]")

_JS_EVAL_RE = re.compile(r"\beval\s*\(|\bFunction\s*\(")
_PY_EVAL_RE = re.compile(r"\beval\s*\(|\bexec\s*\(")
_MD5_RE = re.compile(r"\bhashlib\.md5\s*\(")
# A preceding "/" (e.g. "Chrome/124.0.0.0") marks a version string, not an IP.
_IPV4_RE = re.compile(r"(?<!/)\b(?:\d{1,3}\.){3}\d{1,3}\b")

# Office/archive formats that can carry macros or embedded objects — flagged
# at MEDIUM. Any other extension-recognized or content-sniffed binary (images,
# etc.) is flagged at LOW: expected as demo/doc assets, still worth a provenance note.
_RISKY_BINARY_EXTENSIONS = {".pptx", ".xlsx", ".docx", ".pdf", ".zip", ".pptm", ".xlsm",
                            ".doc", ".xls", ".ppt", ".rar", ".7z", ".jar"}

# Inline escape for a specific finding on a specific line, e.g.:
#   x = hashlib.md5(data)  # security-scan: allow (non-security fingerprint)
_ALLOW_COMMENT = "security-scan: allow"


@dataclass
class Finding:
    path: str
    line: int
    severity: str
    category: str
    cwe: str
    message: str


def _tracked_files() -> list[Path]:
    """Return git-tracked files as absolute paths, newline-robust."""
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    return [ROOT / line for line in out.splitlines() if line]


def _read_text(path: Path) -> str | None:
    """Return file text, or None if the file is binary/unreadable."""
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def _line_allows(line: str) -> bool:
    return _ALLOW_COMMENT in line


def check_dynamic_code_execution(files: list[Path]) -> list[Finding]:
    """Flag dynamic-code-execution calls in JS/TS (eval, Function) and Python (eval, exec)."""
    findings = []
    for path in files:
        if path.suffix in (".js", ".ts", ".jsx", ".tsx"):
            pattern, desc = _JS_EVAL_RE, "eval/Function"
        elif path.suffix == ".py":
            pattern, desc = _PY_EVAL_RE, "eval/exec"
        else:
            continue
        text = _read_text(path)
        if text is None:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line) and not _line_allows(line):
                findings.append(Finding(
                    path=str(path.relative_to(ROOT)), line=i, severity="high",
                    category="Code Injection", cwe="CWE-78, CWE-94, CWE-95",
                    message=f"dynamic code execution ({desc}) — evaluates text as code",
                ))
    return findings


def check_invisible_unicode(files: list[Path]) -> list[Finding]:
    """Flag zero-width/bidi-override characters, with two carve-outs:

    - A UTF-8 BOM (U+FEFF) as the literal first character of a file is an
      encoding marker, not obfuscation — reported separately at LOW severity.
    - tests/ is excluded for *embedded* occurrences: the sanitizer's own test
      fixtures (tests/test_sanitizer.py etc.) legitimately embed these exact
      characters to verify detection works. A real embedded character
      smuggled into non-fixture test code would still be rare enough that
      excluding the whole directory is the right trade-off.
    """
    findings = []
    for path in files:
        text = _read_text(path)
        if text is None:
            continue  # binary file — nothing to scan for embedded text chars
        rel = path.relative_to(ROOT)
        is_test = rel.parts[0] == "tests"

        leading_bom = text.startswith(chr(0xFEFF))
        if leading_bom:
            findings.append(Finding(
                path=str(rel), line=1, severity="low",
                category="Encoding — Leading BOM", cwe="CWE-1104",
                message="UTF-8 BOM at start of file — harmless to parse but inconsistent "
                        "with the rest of the codebase; strip it",
            ))

        if is_test:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if _line_allows(line):
                continue
            check_line = line[1:] if (i == 1 and leading_bom) else line
            if _ZERO_WIDTH_RE.search(check_line):
                findings.append(Finding(
                    path=str(rel), line=i, severity="high",
                    category="Prompt Injection / Obfuscation — Zero Width Characters",
                    cwe="CWE-94, CWE-1427, CWE-506",
                    message="invisible zero-width character embedded in tracked source/docs",
                ))
            if _BIDI_RE.search(check_line):
                findings.append(Finding(
                    path=str(rel), line=i, severity="high",
                    category="Obfuscation — Bidi/RTL Override",
                    cwe="CWE-506, CWE-94",
                    message="bidirectional-text override character (can visually reorder code/text)",
                ))
    return findings


def check_weak_hash(files: list[Path]) -> list[Finding]:
    findings = []
    for path in files:
        if path.suffix != ".py":
            continue
        text = _read_text(path)
        if text is None:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if _MD5_RE.search(line) and not _line_allows(line):
                findings.append(Finding(
                    path=str(path.relative_to(ROOT)), line=i, severity="low",
                    category="Weak Cryptography — MD5 Hash", cwe="CWE-327, CWE-338",
                    message="md5 hash use — not collision-resistant; fine only for "  # security-scan: allow
                            "non-security fingerprinting (mark with the allow comment)",
                ))
    return findings


def check_unreviewed_binaries(files: list[Path]) -> list[Finding]:
    """Flag binary files by content (failed UTF-8 decode), not a fixed
    extension list — so any binary type anywhere in the repo (demo/template
    raw_sources included) gets the same provenance check, not just the
    office-document extensions a prior audit happened to find.

    Office/archive formats that can carry macros or embedded objects are
    flagged everywhere in the repo (MEDIUM) — rare and worth a look
    regardless of location. Other binaries (images, etc.) are expected in
    known asset directories (docs/png, web-ui assets, the built web-ui
    bundle) and would otherwise drown every real finding in doc-screenshot
    noise; they're only flagged (LOW) inside a raw_sources/ directory,
    where ingest content is expected to be plain text and an image
    arriving there is actually worth a provenance check.
    """
    findings = []
    for path in files:
        if _read_text(path) is not None:
            continue  # decodes as UTF-8 text — not binary
        ext = path.suffix.lower()
        rel = path.relative_to(ROOT)
        if ext in _RISKY_BINARY_EXTENSIONS:
            severity = "medium"
        elif "raw_sources" in rel.parts:
            severity = "low"
        else:
            continue
        findings.append(Finding(
            path=str(rel), line=1, severity=severity,
            category="Inventory/Provenance — Binary File", cwe="CWE-1104",
            message=f"binary file ({ext or 'no extension'}) committed with no "
                    "source/provenance recorded — confirm this is intentional before merging",
        ))
    return findings


def check_raw_ip_literals(files: list[Path]) -> list[Finding]:
    findings = []
    for path in files:
        rel = path.relative_to(ROOT)
        if path.suffix != ".py" or rel.parts[0] == "tests":
            continue
        text = _read_text(path)
        if text is None:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if _line_allows(line):
                continue
            for ip in _IPV4_RE.findall(line):
                if ip in _ALLOWED_IPS or ip.startswith(_DOC_EXAMPLE_PREFIXES):
                    continue
                findings.append(Finding(
                    path=str(path.relative_to(ROOT)), line=i, severity="low",
                    category="Network Egress — Raw IP Literal", cwe="CWE-200, CWE-319",
                    message=f"hardcoded IP literal '{ip}' outside the loopback allowlist",
                ))
    return findings


CHECKS = (
    check_dynamic_code_execution,
    check_invisible_unicode,
    check_weak_hash,
    check_unreviewed_binaries,
    check_raw_ip_literals,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fail-on", choices=("low", "medium", "high"), default="medium",
                        help="Minimum severity that fails the build (default: medium)")
    args = parser.parse_args()

    files = _tracked_files()
    findings: list[Finding] = []
    for check in CHECKS:
        findings.extend(check(files))

    findings.sort(key=lambda f: (-_SEVERITY_ORDER[f.severity], f.path, f.line))

    threshold = _SEVERITY_ORDER[args.fail_on]
    blocking = [f for f in findings if _SEVERITY_ORDER[f.severity] >= threshold]

    if not findings:
        print("OK: security_scan found no issues.")
        return

    for f in findings:
        tag = f.severity.upper()
        print(f"[{tag}] {f.path}:{f.line} — {f.category} ({f.cwe})\n  {f.message}")

    print(f"\n{len(findings)} finding(s): "
          f"{sum(1 for f in findings if f.severity == 'high')} high, "
          f"{sum(1 for f in findings if f.severity == 'medium')} medium, "
          f"{sum(1 for f in findings if f.severity == 'low')} low.")

    if blocking:
        print(f"\nFAIL: {len(blocking)} finding(s) at or above --fail-on={args.fail_on}.")
        sys.exit(1)
    print(f"\nOK: no findings at or above --fail-on={args.fail_on} (lower-severity findings shown above).")


if __name__ == "__main__":
    main()
