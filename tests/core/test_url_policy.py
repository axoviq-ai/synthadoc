# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

from unittest.mock import MagicMock

from synthadoc.config import IngestConfig, ServerConfig
from synthadoc.core.url_policy import url_policy_from_config
from synthadoc.security.ssrf import classify_address, get_default_policy


class _Cfg:
    def __init__(self, server: ServerConfig | None = None, ingest: IngestConfig | None = None):
        self.server = server or ServerConfig()
        self.ingest = ingest or IngestConfig()


def test_no_config_gives_the_strict_default():
    assert url_policy_from_config(None) == get_default_policy()


def test_settings_are_mapped():
    cfg = _Cfg(ServerConfig(allow_private_urls=True, trust_proxy_env=True),
               IngestConfig(max_download_bytes=4096))
    policy = url_policy_from_config(cfg, registry={})
    assert policy.allow_private is True
    assert policy.trust_proxy_env is True
    assert policy.max_bytes == 4096


def test_defaults_stay_strict():
    policy = url_policy_from_config(_Cfg(), registry={})
    assert policy.allow_private is False and policy.trust_proxy_env is False
    assert policy.max_bytes == 25 * 1024 * 1024


def test_own_port_is_blocked_on_loopback_even_when_private_urls_are_allowed():
    cfg = _Cfg(ServerConfig(port=7070, allow_private_urls=True))
    policy = url_policy_from_config(cfg, registry={})
    assert classify_address("127.0.0.1", policy, port=7070) == "always-block"
    assert classify_address("::1", policy, port=7070) == "always-block"
    assert classify_address("127.0.0.1", policy, port=9999) is None


def test_every_registered_wiki_port_is_blocked():
    registry = {
        "alpha": {"path": "/w/a", "port": 7071},
        "beta": {"path": "/w/b", "port": 7072, "host": "192.0.2.9"},
        "no-port": {"path": "/w/c"},
    }
    cfg = _Cfg(ServerConfig(allow_private_urls=True))
    policy = url_policy_from_config(cfg, registry=registry)
    assert classify_address("127.0.0.1", policy, port=7071) == "always-block"
    assert classify_address("127.0.0.1", policy, port=7072) == "always-block"
    assert ("192.0.2.9", 7072) in policy.always_block
    assert classify_address("127.0.0.1", policy, port=7073) is None


def test_hostname_registry_entries_are_resolved(monkeypatch):
    import socket
    monkeypatch.setattr(
        "synthadoc.core.url_policy.socket.getaddrinfo",
        lambda host, port, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", port))])
    policy = url_policy_from_config(
        _Cfg(), registry={"remote": {"path": "/w", "port": 8000, "host": "wiki.internal"}})
    assert ("10.1.2.3", 8000) in policy.always_block


def test_unresolvable_registry_host_is_skipped_not_fatal(monkeypatch):
    def boom(*a, **k):
        raise OSError("no dns")
    monkeypatch.setattr("synthadoc.core.url_policy.socket.getaddrinfo", boom)
    policy = url_policy_from_config(
        _Cfg(), registry={"remote": {"path": "/w", "port": 8000, "host": "gone.internal"}})
    # The loopback pair for the registered port is blocked even though the name did not resolve.
    assert classify_address("127.0.0.1", policy, port=8000) == "always-block"


def test_unreadable_registry_falls_back_to_own_port_only(monkeypatch):
    def broken():
        raise ValueError("corrupt registry")
    monkeypatch.setattr("synthadoc.cli._wiki.read_registry_all", broken)
    policy = url_policy_from_config(_Cfg(ServerConfig(port=7070, allow_private_urls=True)))
    assert classify_address("127.0.0.1", policy, port=7070) == "always-block"


def test_mock_config_fails_closed():
    """A MagicMock config must never enable private URLs or produce a bogus size cap."""
    policy = url_policy_from_config(MagicMock(), registry={})
    assert policy.allow_private is False
    assert policy.trust_proxy_env is False
    assert policy.max_bytes == 25 * 1024 * 1024


def test_wildcard_bind_blocks_the_wiki_port_on_every_local_address():
    """Server bound to 0.0.0.0 (the Docker case) answers on every local address."""
    cfg = _Cfg(ServerConfig(host="0.0.0.0", port=7070, allow_private_urls=True))
    policy = url_policy_from_config(cfg, registry={})
    for ip in ("127.0.0.2", "192.168.1.5", "10.1.2.3", "172.20.0.9", "::1", "fd00::5"):
        assert classify_address(ip, policy, port=7070) == "always-block", ip
        assert classify_address(ip, policy, port=9999) is None, ip


def test_default_bind_also_blocks_any_loopback_address():
    policy = url_policy_from_config(_Cfg(ServerConfig(allow_private_urls=True)), registry={})
    assert classify_address("127.0.0.2", policy, port=7070) == "always-block"


def test_registered_wiki_ports_are_blocked_on_every_private_address():
    registry = {"alpha": {"path": "/w/a", "port": 7071}, "beta": {"path": "/w/b", "port": 7072}}
    policy = url_policy_from_config(_Cfg(ServerConfig(allow_private_urls=True)), registry=registry)
    for port in (7071, 7072):
        assert classify_address("192.168.1.5", policy, port=port) == "always-block"
    assert classify_address("192.168.1.5", policy, port=7073) is None


def test_public_hosts_on_a_wiki_port_stay_reachable():
    policy = url_policy_from_config(_Cfg(ServerConfig(port=7070, allow_private_urls=True)), registry={})
    assert classify_address("8.8.8.8", policy, port=7070) is None
