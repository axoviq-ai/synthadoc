# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Keep the list of unguarded HTTP clients honest.

Every place that opens its own HTTP connection is listed below with the reason it is
not behind the SSRF guard. A new raw client (httpx, requests, urllib, aiohttp,
http.client) anywhere under synthadoc/ fails this test until it either uses the guard
or is added here WITH a reason. Stale entries fail too, so the list cannot rot.
Stdlib only, so the lean CI job can run it.
"""
from __future__ import annotations

import ast
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[3] / "synthadoc"

# Path (relative to synthadoc/) -> why it is not guarded.
ALLOWED = {
    "agents/cross_wiki_query_agent.py":
        "peer wiki /retrieve calls to registry wikis (loopback by design; needs per-peer keys, not the guard)",
    "integration/http_server.py":
        "peer /epoch calls to registry wikis (loopback by design)",
    "cli/_http.py": "CLI talking to its own server on loopback",
    "cli/_wiki.py": "CLI health probe of its own server on loopback",
    "cli/export.py": "CLI talking to its own server on loopback",
    "cli/status.py": "CLI talking to its own server on loopback",
    "cli/stop.py": "CLI talking to its own server on loopback",
    "cli/web.py": "CLI probing its own web UI on loopback",
    "cli/plugin.py": "CLI downloading release assets from a fixed GitHub URL on the operator's machine",
    "providers/ollama.py": "operator-configured provider URL, not user input",
    "skills/url/scripts/main.py":
        "standalone fallback when no hardened fetcher is injected; Synthadoc always injects the guarded one (SkillAgent)",
    "skills/youtube/scripts/main.py": "oEmbed request to a fixed host; the video id is URL-encoded",
}
# The guard itself and the demo scripts (not server code) are not scanned.
SKIPPED_PREFIXES = ("security/", "demos/")

_CLIENT_ATTRS = {
    "httpx": {"AsyncClient", "Client", "get", "post", "put", "delete", "head", "patch",
              "request", "stream"},
    "requests": {"get", "post", "put", "delete", "head", "patch", "request", "Session"},
    "urllib.request": {"urlopen", "urlretrieve"},
    "aiohttp": {"ClientSession", "request"},
    "http.client": {"HTTPConnection", "HTTPSConnection"},
}


def find_clients(source: str) -> list:
    """Return ``(line, description)`` for raw HTTP client calls, following import aliases."""
    tree = ast.parse(source)
    module_aliases: dict = {}      # local name -> dotted module
    direct_names: dict = {}        # local name -> "module.attr"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _CLIENT_ATTRS:
                    module_aliases[alias.asname or alias.name] = alias.name
                elif alias.name.startswith("urllib") and alias.asname is None:
                    module_aliases["urllib.request"] = "urllib.request"   # `import urllib.request`
        elif isinstance(node, ast.ImportFrom) and node.module:
            module = node.module
            for alias in node.names:
                if module in _CLIENT_ATTRS and alias.name in _CLIENT_ATTRS[module]:
                    direct_names[alias.asname or alias.name] = f"{module}.{alias.name}"
                elif f"{module}.{alias.name}" in _CLIENT_ATTRS:           # from urllib import request
                    module_aliases[alias.asname or alias.name] = f"{module}.{alias.name}"

    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in direct_names:
            found.append((node.lineno, direct_names[func.id]))
        elif isinstance(func, ast.Attribute):
            chain = []
            base = func.value
            while isinstance(base, ast.Attribute):
                chain.append(base.attr)
                base = base.value
            if isinstance(base, ast.Name):
                dotted = ".".join([base.id] + list(reversed(chain)))
                module = module_aliases.get(base.id)
                if module is not None:
                    full_module = module if not chain else f"{module}." + ".".join(reversed(chain))
                    if func.attr in _CLIENT_ATTRS.get(full_module, set()):
                        found.append((node.lineno, f"{full_module}.{func.attr}"))
                elif dotted in _CLIENT_ATTRS and func.attr in _CLIENT_ATTRS[dotted]:
                    found.append((node.lineno, f"{dotted}.{func.attr}"))
    return found


def _scan_tree() -> dict:
    found = {}
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        rel = path.relative_to(SOURCE_ROOT).as_posix()
        if rel.startswith(SKIPPED_PREFIXES):
            continue
        hits = find_clients(path.read_text(encoding="utf-8"))
        if hits:
            found[rel] = hits
    return found


def test_every_raw_http_client_is_listed_with_a_reason():
    unlisted = {p: hits for p, hits in _scan_tree().items() if p not in ALLOWED}
    assert not unlisted, (
        "New raw HTTP client(s) found. Route them through synthadoc.security.ssrf "
        f"(guarded_client / make_fetcher) or add them to ALLOWED with a reason: {unlisted}")


def test_allowlist_has_no_stale_entries():
    found = _scan_tree()
    stale = [p for p in ALLOWED if p not in found]
    assert not stale, f"These ALLOWED entries no longer use a raw HTTP client: {stale}"


def test_every_allowed_entry_has_a_reason():
    assert all(reason.strip() for reason in ALLOWED.values())


def test_scanner_follows_aliases_and_direct_imports():
    assert find_clients("import httpx as _h\n_h.AsyncClient()\n")
    assert find_clients("from httpx import AsyncClient as AC\nAC()\n")
    assert find_clients("import httpx\nhttpx.get('u')\n")
    assert find_clients("import requests\nrequests.post('u')\n")
    assert find_clients("from urllib.request import urlopen\nurlopen('u')\n")
    assert find_clients("import urllib.request\nurllib.request.urlopen('u')\n")
    assert find_clients("import aiohttp\naiohttp.ClientSession()\n")
    assert find_clients("import http.client\nhttp.client.HTTPSConnection('h')\n")


def test_scanner_ignores_non_client_uses():
    assert not find_clients("import httpx\ntry:\n    pass\nexcept httpx.ConnectError:\n    pass\n")
    assert not find_clients("import httpx\nx = httpx.Response(200)\n")
    assert not find_clients("def get():\n    pass\nget()\n")
    assert not find_clients("import json\njson.get('x')\n")
