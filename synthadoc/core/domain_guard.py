# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse


def load_blocked_domains(wiki_root: Path) -> set[str]:
    """Return the set of auto-blocked domains from .synthadoc/blocked_domains.json."""
    p = wiki_root / ".synthadoc" / "blocked_domains.json"
    if not p.exists():
        return set()
    try:
        return set(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return set()


def is_domain_blocked(url: str, wiki_root: Path) -> bool:
    """Return True when the URL's hostname matches a domain in blocked_domains.json."""
    blocked = load_blocked_domains(wiki_root)
    if not blocked:
        return False
    host = urlparse(url).hostname or ""
    return any(host == d or host.endswith("." + d) for d in blocked)
