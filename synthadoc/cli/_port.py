# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
"""Port availability utilities — no app imports so tests can import safely."""
from __future__ import annotations

import socket as _socket

_DEFAULT_PORT = 7070


def find_free_port(start: int = _DEFAULT_PORT, max_scan: int = 100) -> int:
    """Scan upward from `start` and return the first unbound port."""
    for port in range(start, start + max_scan):
        with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(
        f"No free port found in range {start}–{start + max_scan - 1}. "
        "Use --port to specify one manually."
    )


def assign_wiki_port(reserved_ports: set[int], start: int = _DEFAULT_PORT) -> int:
    """Return the lowest port ≥ start that is neither registry-reserved nor currently bound.

    Unlike find_free_port(), this also skips ports already assigned to other
    wikis in the registry, even when those wikis are not running.  That prevents
    two wikis from ever sharing a port — even across reboots.
    """
    candidate = start
    while candidate <= 65535:
        if candidate not in reserved_ports:
            with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", candidate))
                    return candidate
                except OSError:
                    pass
        candidate += 1
    raise RuntimeError(
        "No free port found below 65536. Use --port to specify one manually."
    )
