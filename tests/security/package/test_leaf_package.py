# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""``synthadoc/security/`` is a leaf package (interface spec section 0).

It may import the standard library, third-party packages and itself, and nothing else of
Synthadoc: not the server, config, agents, storage or ``synthadoc.auth``. The auth package
sits ABOVE it and may import it, never the reverse. This is what lets the security
primitives be reused by live sources and tested in a lean environment.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SECURITY = Path(__file__).resolve().parents[3] / "synthadoc" / "security"
_MODULES = sorted(p for p in _SECURITY.glob("*.py"))


def _synthadoc_imports(source: str) -> list:
    """Every absolute import of a synthadoc module outside synthadoc.security."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:                        # relative: stays inside the package
                continue
            base = node.module or ""
            # "from synthadoc import auth" imports synthadoc.auth
            names = [base] + ([f"{base}.{a.name}" for a in node.names] if base == "synthadoc" else [])
        else:
            continue
        found += [n for n in names
                  if (n == "synthadoc" or n.startswith("synthadoc."))
                  and not n.startswith("synthadoc.security")
                  and n != "synthadoc"]
    return found


def test_the_security_package_is_found():
    assert {m.name for m in _MODULES} >= {"paths.py", "redact.py", "ssrf.py", "_winacl.py"}


@pytest.mark.parametrize("module", _MODULES, ids=lambda m: m.name)
def test_a_security_module_imports_no_other_synthadoc_code(module):
    assert _synthadoc_imports(module.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("source", [
    "import synthadoc.auth.store",
    "from synthadoc.auth import store",
    "from synthadoc import auth",
    "from synthadoc.config import load_config",
    "import synthadoc.core.cache as c",
    "def f():\n    from synthadoc.agents import ingest_agent",      # a lazy import counts too
])
def test_the_detector_catches_forbidden_imports(source):
    assert _synthadoc_imports(source)


@pytest.mark.parametrize("source", [
    "from synthadoc.security import paths",
    "import synthadoc.security.redact",
    "from . import _winacl",
    "from .paths import synthadoc_home",
    "import os, json",
    "import httpx",
])
def test_the_detector_allows_the_package_itself_and_third_parties(source):
    assert _synthadoc_imports(source) == []
