# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Peter White / axoviq.com
"""Where Synthadoc keeps its per-user state: the wiki registry, the default wiki, the
cross-wiki routing file, global skills and the embedding model cache.

All of it lives under ``synthadoc_home()`` (``$SYNTHADOC_HOME`` if set, else
``~/.synthadoc``), the same root as the secrets, so a Docker deployment mounts one
volume at ``$SYNTHADOC_HOME`` and everything survives a recreated container. Only the
path is used here: none of the secret directory's ownership or git checks apply to this
non-secret state.
"""
from __future__ import annotations

from pathlib import Path

from synthadoc.security.paths import SecretPathError, synthadoc_home


def state_path(*parts: str) -> Path:
    """``synthadoc_home() / *parts``. A bad ``SYNTHADOC_HOME`` (a relative path) ends the
    process with a one-line message instead of a traceback, because this runs at import
    time, before any command can report it."""
    try:
        return synthadoc_home().joinpath(*parts)
    except SecretPathError as exc:
        raise SystemExit(f"synthadoc: {exc.detail or exc.public_message} {exc.hint}".rstrip()) from None
