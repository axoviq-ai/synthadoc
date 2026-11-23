# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Build the SSRF guard policy from Synthadoc configuration.

Lives in core (not in synthadoc.security) because it reads [server] and [ingest]
settings and the machine-wide wiki registry; the security package stays a leaf.
"""
from __future__ import annotations

import ipaddress
import socket
from typing import Optional

from synthadoc.security.ssrf import UrlPolicy, get_default_policy

_DEFAULT_MAX_BYTES = 25 * 1024 * 1024
_LOOPBACK = ("127.0.0.1", "::1")


def _flag(obj: object, name: str) -> bool:
    # `is True` so a mock or malformed config can never switch a relaxation on.
    return getattr(obj, name, False) is True


def _positive_int(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return default


def _valid_port(value: object) -> Optional[int]:
    port = _positive_int(value, 0)
    return port if 0 < port < 65536 else None


def _host_addresses(host: str) -> list:
    try:
        return [str(ipaddress.ip_address(host))]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return []
    return sorted({info[4][0].split("%", 1)[0] for info in infos})


def _read_registry() -> dict:
    try:
        from synthadoc.cli._wiki import read_registry_all
        registry = read_registry_all()
    except Exception:  # noqa: BLE001 - an unreadable registry must not break ingest
        return {}
    return registry if isinstance(registry, dict) else {}


def url_policy_from_config(cfg: object, *, registry: Optional[dict] = None) -> UrlPolicy:
    """Policy for server-side URL fetches; strict default when ``cfg`` is None."""
    if cfg is None:
        return get_default_policy()
    server = getattr(cfg, "server", None)
    ingest = getattr(cfg, "ingest", None)

    blocked: set = set()
    private_ports: set = set()

    def block_port(port: object, hosts: list) -> None:
        valid = _valid_port(port)
        if valid is None:
            return
        # Every loopback/private address, not only the bound ones: a server bound to
        # 0.0.0.0 also answers on 127.0.0.2, its LAN address and so on.
        private_ports.add(valid)
        # Exact entries still matter for non-private (public) registry hosts.
        for ip in set(hosts) | set(_LOOPBACK):
            blocked.add((ip, valid))

    own_host = getattr(server, "host", None)
    block_port(getattr(server, "port", None), _host_addresses(own_host) if isinstance(own_host, str) else [])
    for entry in (_read_registry() if registry is None else registry).values():
        if not isinstance(entry, dict):
            continue
        host = entry.get("host", "127.0.0.1")
        block_port(entry.get("port"), _host_addresses(host) if isinstance(host, str) else [])

    return UrlPolicy(
        allow_private=_flag(server, "allow_private_urls"),
        trust_proxy_env=_flag(server, "trust_proxy_env"),
        max_bytes=_positive_int(getattr(ingest, "max_download_bytes", None), _DEFAULT_MAX_BYTES),
        always_block=frozenset(blocked),
        always_block_private_ports=frozenset(private_ports),
    )
