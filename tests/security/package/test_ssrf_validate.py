# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Address classification and URL validation for the SSRF guard.

Only stdlib + pytest are needed here so the lean CI job can run this file on
every supported Python version.
"""
from __future__ import annotations

import dataclasses
import socket

import pytest

from synthadoc.security.ssrf import (
    SsrfBlocked,
    SsrfResolutionError,
    UrlPolicy,
    classify_address,
    get_default_policy,
    validate_url,
)

STRICT = UrlPolicy()
PRIVATE_OK = UrlPolicy(allow_private=True)

BLOCKED_BY_DEFAULT = [
    # IPv4
    "127.0.0.1", "127.1.2.3", "10.0.0.1", "172.16.5.4", "172.31.255.255",
    "192.168.1.1", "169.254.169.254", "169.254.1.1", "100.64.0.1",
    "100.100.100.200", "0.0.0.0", "0.1.2.3", "192.0.0.8", "198.18.0.1",
    "198.19.255.255", "224.0.0.1", "239.255.255.250", "240.0.0.1",
    "255.255.255.255", "192.0.2.1", "168.63.129.16",
    # IPv6
    "::", "::1", "fe80::1", "fec0::1", "fc00::1", "fd12:3456::1",
    "fd00:ec2::254", "ff02::1", "2001:db8::1", "64:ff9b:1::1",
    # embedded IPv4 forms that wrap a blocked IPv4
    "::ffff:127.0.0.1", "::ffff:10.0.0.1", "::ffff:169.254.169.254",
    "64:ff9b::7f00:1", "64:ff9b::a00:1",
    # forms that are blocked wholesale
    "2002:7f00:1::", "2002:808:808::",            # 6to4 (deprecated)
    "2001:0:4136:e378:8000:63bf:3fff:fdd2",       # Teredo
    "::7f00:1", "::808:808",                      # IPv4-compatible (deprecated)
]

ALLOWED_BY_DEFAULT = [
    "8.8.8.8", "1.1.1.1", "93.184.216.34",
    "2606:4700:4700::1111",
    "::ffff:8.8.8.8",          # mapped public address is fine
    "64:ff9b::808:808",        # NAT64 wrapping a public address (DNS64 networks)
]


@pytest.mark.parametrize("ip", BLOCKED_BY_DEFAULT)
def test_blocked_address_by_default(ip):
    assert classify_address(ip, STRICT) is not None


@pytest.mark.parametrize("ip", ALLOWED_BY_DEFAULT)
def test_public_address_allowed(ip):
    assert classify_address(ip, STRICT) is None


@pytest.mark.parametrize("ip", [
    "127.0.0.1", "10.1.1.1", "172.20.0.1", "192.168.0.5",
    "::1", "fd12:3456::1", "::ffff:127.0.0.1",
])
def test_allow_private_relaxes_only_private_and_loopback(ip):
    assert classify_address(ip, PRIVATE_OK) is None


@pytest.mark.parametrize("ip", [
    "169.254.169.254",      # cloud metadata, even in a private-allowed deployment
    "fd00:ec2::254",        # AWS IPv6 metadata (inside fc00::/7)
    "168.63.129.16",        # Azure wire server
    "100.64.0.1",           # CGNAT is not "private" for this purpose
    "0.0.0.0", "fe80::1", "169.254.1.1", "224.0.0.1",
    "::ffff:169.254.169.254",
])
def test_allow_private_never_relaxes_metadata_or_special_ranges(ip):
    assert classify_address(ip, PRIVATE_OK) is not None


def test_metadata_rule_name():
    assert classify_address("169.254.169.254", PRIVATE_OK) == "metadata"


def test_always_block_wins_even_when_private_allowed():
    policy = UrlPolicy(allow_private=True, always_block=frozenset({("127.0.0.1", 7070)}))
    assert classify_address("127.0.0.1", policy, port=7070) == "always-block"
    assert classify_address("127.0.0.1", policy, port=7071) is None


def test_always_block_with_no_port_blocks_every_port():
    policy = UrlPolicy(allow_private=True, always_block=frozenset({("127.0.0.1", None)}))
    assert classify_address("127.0.0.1", policy, port=1) == "always-block"
    assert classify_address("127.0.0.1", policy, port=65535) == "always-block"


def test_always_block_matches_mapped_ipv6_form():
    policy = UrlPolicy(allow_private=True, always_block=frozenset({("127.0.0.1", 7070)}))
    assert classify_address("::ffff:127.0.0.1", policy, port=7070) == "always-block"


def test_policy_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        STRICT.allow_private = True  # type: ignore[misc]


def test_default_policy_is_strict():
    policy = get_default_policy()
    assert policy.allow_private is False
    assert policy.trust_proxy_env is False
    assert policy.allowed_schemes == frozenset({"http", "https"})
    assert policy.max_redirects == 5
    assert policy.max_bytes == 25 * 1024 * 1024
    assert get_default_policy() == policy


def _resolver(*addresses):
    async def resolve(host, port):
        return list(addresses)
    return resolve


async def test_public_url_resolves_and_is_returned():
    target = await validate_url(
        "https://Example.com/a?x=1", STRICT, resolver=_resolver("93.184.216.34"))
    assert target.scheme == "https"
    assert target.host == "example.com"
    assert target.port == 443
    assert target.addresses == ("93.184.216.34",)


async def test_default_ports():
    http = await validate_url("http://example.com/", STRICT, resolver=_resolver("8.8.8.8"))
    assert http.port == 80
    custom = await validate_url("http://example.com:8080/", STRICT, resolver=_resolver("8.8.8.8"))
    assert custom.port == 8080


@pytest.mark.parametrize("url", [
    "ftp://example.com/x", "file:///etc/passwd", "gopher://example.com/",
    "javascript:alert(1)", "data:text/plain,hi", "//example.com/x", "example.com/x",
])
async def test_disallowed_scheme_is_blocked(url):
    with pytest.raises(SsrfBlocked):
        await validate_url(url, STRICT, resolver=_resolver("8.8.8.8"))


@pytest.mark.parametrize("url", [
    "http://user:pw@example.com/", "http://user@example.com/", "http://@example.com/",
])
async def test_userinfo_is_blocked(url):
    with pytest.raises(SsrfBlocked):
        await validate_url(url, STRICT, resolver=_resolver("8.8.8.8"))


@pytest.mark.parametrize("url", ["http:///path", "http://", "https://:443/"])
async def test_missing_host_is_blocked(url):
    with pytest.raises(SsrfBlocked):
        await validate_url(url, STRICT, resolver=_resolver("8.8.8.8"))


@pytest.mark.parametrize("url", [
    "http://[fe80::1%25eth0]/", "http://[::1%25lo]/", "http://example.com%25x/",
])
async def test_zone_ids_are_blocked(url):
    with pytest.raises(SsrfBlocked):
        await validate_url(url, STRICT, resolver=_resolver("8.8.8.8"))


@pytest.mark.parametrize("url", ["http://example.com:99999/", "http://example.com:abc/"])
async def test_invalid_port_is_blocked(url):
    with pytest.raises(SsrfBlocked):
        await validate_url(url, STRICT, resolver=_resolver("8.8.8.8"))


async def test_every_resolved_address_must_pass():
    with pytest.raises(SsrfBlocked):
        await validate_url(
            "http://example.com/", STRICT, resolver=_resolver("93.184.216.34", "10.0.0.5"))


@pytest.mark.parametrize("url, ip", [
    ("http://127.0.0.1:7070/", "127.0.0.1"),
    ("http://[::1]/", "::1"),
    ("http://169.254.169.254/latest/", "169.254.169.254"),
])
async def test_blocked_literal_ip_urls(url, ip):
    with pytest.raises(SsrfBlocked):
        await validate_url(url, STRICT, resolver=_resolver(ip))


async def test_always_block_uses_the_url_port():
    policy = UrlPolicy(allow_private=True, always_block=frozenset({("127.0.0.1", 7070)}))
    with pytest.raises(SsrfBlocked):
        await validate_url("http://127.0.0.1:7070/query", policy, resolver=_resolver("127.0.0.1"))
    target = await validate_url(
        "http://127.0.0.1:9999/doc", policy, resolver=_resolver("127.0.0.1"))
    assert target.port == 9999


async def test_empty_resolution_is_a_resolution_error_not_a_block():
    with pytest.raises(SsrfResolutionError):
        await validate_url("http://example.com/", STRICT, resolver=_resolver())


async def test_resolver_oserror_is_a_resolution_error():
    async def failing(host, port):
        raise socket.gaierror("no such host")

    with pytest.raises(SsrfResolutionError):
        await validate_url("http://example.com/", STRICT, resolver=failing)


async def test_error_messages_never_reveal_addresses():
    with pytest.raises(SsrfBlocked) as info:
        await validate_url("http://internal.example/", STRICT, resolver=_resolver("10.9.8.7"))
    exc = info.value
    assert exc.public_message == "URL is not permitted."
    assert "10.9.8.7" not in exc.public_message
    assert "10.9.8.7" not in str(exc)
    assert "10.9.8.7" in exc.detail          # operator log keeps the specifics


async def test_real_resolver_blocks_loopback_literals_and_localhost():
    for url in ("http://127.0.0.1:1/", "http://[::1]:1/", "http://localhost:1/"):
        with pytest.raises(SsrfBlocked):
            await validate_url(url, STRICT)


@pytest.mark.parametrize("url", [
    "http://2130706433/", "http://0x7f.1/", "http://0177.0.0.1/", "http://127.1/",
])
async def test_odd_ip_notations_are_never_allowed(url):
    # Depending on the OS resolver these either resolve to 127.0.0.1 (blocked)
    # or fail to resolve; they must never be treated as a public host.
    with pytest.raises((SsrfBlocked, SsrfResolutionError)):
        await validate_url(url, STRICT)
