# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

from pathlib import Path
from typing import Optional


def _resolve_root(wiki_root: Optional[str]) -> Path:
    """Return the wiki root Path; defaults to CWD when wiki_root is None."""
    return Path(wiki_root) if wiki_root else Path(".")
