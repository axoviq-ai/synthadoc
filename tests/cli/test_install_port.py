# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import socket
import pytest
from synthadoc.cli._port import find_free_port as _find_free_port


def _find_bindable_base(count: int) -> int:
    """Return the first port in a run of `count` consecutively bindable ports.

    Hardcoded port numbers fail on Windows when Hyper-V or other system
    components exclude specific ranges (WinError 10013). Starting from a
    high ephemeral range and scanning avoids those exclusions.
    """
    for base in range(40000, 41000):
        socks: list[socket.socket] = []
        try:
            for i in range(count):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", base + i))
                socks.append(s)
            return base
        except OSError:
            pass
        finally:
            for s in socks:
                try:
                    s.close()
                except OSError:
                    pass
    pytest.skip("No block of consecutive bindable ports found")


def test_find_free_port_returns_start_when_available():
    """Returns the start port if it is not bound."""
    base = _find_bindable_base(1)
    assert _find_free_port(start=base) == base


def test_find_free_port_skips_bound_port():
    """Skips a port that is already bound and returns the next free one."""
    base = _find_bindable_base(2)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", base))
        port = _find_free_port(start=base)
    assert port == base + 1


def test_find_free_port_scans_multiple():
    """Scans past multiple bound ports."""
    base = _find_bindable_base(3)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s1, \
         socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
        s1.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s1.bind(("127.0.0.1", base))
        s2.bind(("127.0.0.1", base + 1))
        port = _find_free_port(start=base)
    assert port == base + 2
