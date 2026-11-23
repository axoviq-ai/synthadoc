# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""SSRF guard: address classification and URL validation.

Validation looks at the *resolved* addresses, never the host string, so odd IP
notations (decimal, hex, octal) are caught after the resolver normalises them.
Every error carries a client-safe ``public_message``; the specifics (resolved
address, rule hit) live in ``detail`` for the server log only.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
import ssl
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Union
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

logger = logging.getLogger("synthadoc.security.ssrf")

_IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]
Resolver = Callable[[str, int], Awaitable[list]]

_DEFAULT_PORTS = {"http": 80, "https": 443}


class SsrfBlocked(Exception):
    """The URL (or an address it resolves to) is not permitted."""

    public_message = "URL is not permitted."

    def __init__(self, detail: str) -> None:
        super().__init__(self.public_message)
        self.detail = detail


class SsrfResolutionError(Exception):
    """The host name could not be resolved (a transient failure, not a block)."""

    public_message = "Name resolution failed."

    def __init__(self, detail: str = "") -> None:
        super().__init__(self.public_message)
        self.detail = detail


@dataclass(frozen=True)
class UrlPolicy:
    allowed_schemes: frozenset = frozenset({"http", "https"})
    allow_private: bool = False
    trust_proxy_env: bool = False
    max_redirects: int = 5
    max_bytes: int = 25 * 1024 * 1024
    connect_timeout: float = 10.0
    total_timeout: float = 30.0
    always_block: frozenset = frozenset()
    ssl_context: Optional[ssl.SSLContext] = None

    def __post_init__(self) -> None:
        for entry in self.always_block:
            ip, port = entry
            ipaddress.ip_address(ip)
            if port is not None and not 0 < port < 65536:
                raise ValueError(f"always_block port out of range: {port}")


@dataclass(frozen=True)
class ResolvedTarget:
    scheme: str
    host: str
    port: int
    addresses: tuple
    url: str


_DEFAULT_POLICY = UrlPolicy()


def get_default_policy() -> UrlPolicy:
    """Strictest policy; the fail-closed fallback when no policy is injected."""
    return _DEFAULT_POLICY


def _nets(*cidrs: str) -> tuple:
    return tuple(ipaddress.ip_network(c) for c in cidrs)


# Ranges a private-allowed deployment may reach (never the metadata addresses).
_RELAXABLE = _nets("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
                   "::1/128", "fc00::/7")
_METADATA = frozenset(ipaddress.ip_address(a) for a in (
    "169.254.169.254", "fd00:ec2::254", "168.63.129.16", "100.100.100.200"))
_SPECIAL_V4 = _nets("0.0.0.0/8", "100.64.0.0/10", "192.0.0.0/24", "192.0.2.0/24",
                    "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24",
                    "224.0.0.0/4", "240.0.0.0/4")
# IPv4-compatible, SIIT, discard, Teredo, 6to4, local-use NAT64, documentation,
# link-local, site-local, multicast: blocked wholesale rather than unwrapped.
_SPECIAL_V6 = _nets("::/96", "::ffff:0:0/96", "100::/64", "2001::/32", "2002::/16",
                    "64:ff9b:1::/48", "2001:db8::/32", "fe80::/10", "fec0::/10", "ff00::/8")
_NAT64 = ipaddress.ip_network("64:ff9b::/96")


def _coerce(ip: Union[str, _IPAddress]) -> _IPAddress:
    return ip if not isinstance(ip, str) else ipaddress.ip_address(ip)


def _in(addr: _IPAddress, nets: tuple) -> bool:
    return any(addr in net for net in nets)


def _unwrap_mapped(addr: _IPAddress) -> _IPAddress:
    if addr.version == 6 and addr.ipv4_mapped is not None:
        return addr.ipv4_mapped
    return addr


def _always_blocked(addr: _IPAddress, policy: UrlPolicy, port: Optional[int]) -> bool:
    for ip, blocked_port in policy.always_block:
        if _unwrap_mapped(ipaddress.ip_address(ip)) == addr and blocked_port in (None, port):
            return True
    return False


def classify_address(
    ip: Union[str, _IPAddress], policy: UrlPolicy, port: Optional[int] = None,
) -> Optional[str]:
    """Return the name of the rule that blocks ``ip``, or None if it is allowed."""
    if isinstance(ip, str) and "%" in ip:
        return "zone-id"
    addr = _unwrap_mapped(_coerce(ip))

    if addr.version == 6 and addr in _NAT64:
        embedded = ipaddress.IPv4Address(addr.packed[-4:])
        # Judged under the strictest policy so allow_private never opens NAT64 to LAN hosts.
        return None if classify_address(embedded, _DEFAULT_POLICY) is None else "nat64-embedded"

    if _always_blocked(addr, policy, port):
        return "always-block"
    if addr in _METADATA:
        return "metadata"
    if policy.allow_private and _in(addr, _RELAXABLE):
        return None

    if addr.is_loopback:
        return "loopback"
    if addr.is_private and _in(addr, _RELAXABLE):
        return "private"
    if addr.is_link_local:
        return "link-local"
    if addr.is_multicast:
        return "multicast"
    if addr.is_unspecified:
        return "unspecified"
    if _in(addr, _SPECIAL_V4 if addr.version == 4 else _SPECIAL_V6):
        return "special-range"
    if not addr.is_global:
        return "not-global"
    return None


async def _system_resolver(host: str, port: int) -> list:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    out: list = []
    for _family, _type, _proto, _canon, sockaddr in infos:
        ip = sockaddr[0].split("%", 1)[0]
        if ip not in out:
            out.append(ip)
    return out


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


async def validate_url(
    url: str, policy: UrlPolicy, *, resolver: Optional[Resolver] = None,
) -> ResolvedTarget:
    """Check scheme, userinfo, host and every resolved address; raise if any fails."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise SsrfBlocked("malformed url or port") from None

    scheme = parts.scheme.lower()
    if scheme not in policy.allowed_schemes:
        raise SsrfBlocked(f"scheme {scheme!r} not allowed")
    if "@" in parts.netloc:
        raise SsrfBlocked("userinfo in url")
    host = parts.hostname or ""
    if not host:
        raise SsrfBlocked("no host")
    if "%" in host:
        raise SsrfBlocked("zone id or encoded host")
    if port == 0:
        raise SsrfBlocked("port 0")
    port = port or _DEFAULT_PORTS.get(scheme, 443)

    if _is_ip_literal(host):
        addresses = [host]
    else:
        try:
            addresses = await (resolver or _system_resolver)(host, port)
        except SsrfResolutionError:
            raise
        except OSError as exc:
            raise SsrfResolutionError(f"{host}: {exc}") from exc
    if not addresses:
        raise SsrfResolutionError(f"{host}: no addresses")

    for address in addresses:
        rule = classify_address(address, policy, port)
        if rule is not None:
            raise SsrfBlocked(f"{host} -> {address}: {rule}")
    return ResolvedTarget(scheme, host, port, tuple(addresses), url)


class ResponseTooLarge(Exception):
    """The response body exceeded ``UrlPolicy.max_bytes`` (counted after decoding)."""

    public_message = "Response is too large."

    def __init__(self, detail: str = "") -> None:
        super().__init__(self.public_message)
        self.detail = detail


_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_CREDENTIAL_HEADERS = frozenset({"authorization", "cookie", "proxy-authorization"})
# The body is returned already decoded, so these would mislead a later reader.
_STALE_RESPONSE_HEADERS = frozenset({"content-encoding", "content-length", "transfer-encoding"})


def _origin(url: str) -> tuple:
    parts = urlsplit(url)
    return parts.hostname, parts.port or _DEFAULT_PORTS.get(parts.scheme.lower())


class GuardedClient:
    """GET/HEAD client that validates every hop and pins the connection to the checked IP."""

    def __init__(
        self, policy: UrlPolicy, *, resolver: Optional[Resolver] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self._policy = policy
        self._resolver = resolver
        self._transport = transport
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "GuardedClient":
        kwargs: dict = {
            "trust_env": self._policy.trust_proxy_env,
            "follow_redirects": False,
            "timeout": httpx.Timeout(self._policy.total_timeout,
                                     connect=self._policy.connect_timeout),
        }
        if self._policy.ssl_context is not None:
            kwargs["verify"] = self._policy.ssl_context
        if self._transport is not None:
            kwargs["transport"] = self._transport
        self._client = httpx.AsyncClient(**kwargs)
        if self._policy.trust_proxy_env:
            logger.warning("SSRF guard: proxy mode is on, so connections cannot be pinned "
                           "to the validated address (best-effort pre-check only)")
        return self

    async def __aexit__(self, *exc_info) -> None:
        assert self._client is not None
        await self._client.aclose()

    async def get(self, url: str, *, headers: Optional[dict] = None) -> httpx.Response:
        return await self._fetch("GET", url, headers)

    async def head(self, url: str, *, headers: Optional[dict] = None) -> httpx.Response:
        return await self._fetch("HEAD", url, headers)

    async def _fetch(self, method: str, url: str, headers: Optional[dict]) -> httpx.Response:
        try:
            async with asyncio.timeout(self._policy.total_timeout):
                return await self._follow(method, url, dict(headers or {}))
        except TimeoutError:
            raise httpx.TimeoutException("request exceeded the total time limit") from None

    async def _follow(self, method: str, url: str, headers: dict) -> httpx.Response:
        assert self._client is not None
        current, hops = url, 0
        while True:
            try:
                target = await validate_url(current, self._policy, resolver=self._resolver)
            except SsrfResolutionError as exc:
                logger.info("guarded fetch: %s", exc.detail)
                raise httpx.ConnectError("name resolution failed") from None
            except SsrfBlocked as exc:
                logger.warning("guarded fetch blocked: %s", exc.detail)
                raise
            pinned_url, send_headers, extensions = self._pin(target, headers)
            request = self._client.build_request(
                method, pinned_url, headers=send_headers, extensions=extensions)
            response = await self._client.send(request, stream=True, follow_redirects=False)
            try:
                location = response.headers.get("location")
                if response.status_code in _REDIRECT_STATUSES and location:
                    hops += 1
                    if hops > self._policy.max_redirects:
                        raise httpx.TooManyRedirects(
                            "Exceeded maximum allowed redirects.", request=request)
                    following = urljoin(current, location)
                    headers = self._headers_for_hop(headers, current, following)
                    current = following
                    continue
                body = await self._read_capped(response)
                return self._materialise(response, method, current, body)
            finally:
                await response.aclose()

    def _pin(self, target: ResolvedTarget, headers: dict) -> tuple:
        try:
            ascii_host = target.host.encode("idna").decode("ascii")
        except UnicodeError:
            raise SsrfBlocked(f"host {target.host!r} is not encodable") from None
        send = {k: v for k, v in headers.items() if k.lower() != "host"}
        if self._policy.trust_proxy_env:
            return target.url, send, {}
        default_port = _DEFAULT_PORTS.get(target.scheme)
        host_header = f"[{ascii_host}]" if ":" in ascii_host else ascii_host
        ip = target.addresses[0]
        ip_host = f"[{ip}]" if ":" in ip else ip
        netloc = ip_host
        if target.port != default_port:
            host_header = f"{host_header}:{target.port}"
            netloc = f"{ip_host}:{target.port}"
        send["Host"] = host_header
        parts = urlsplit(target.url)
        pinned = urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, ""))
        extensions = {"sni_hostname": ascii_host} if parts.scheme == "https" else {}
        return pinned, send, extensions

    @staticmethod
    def _headers_for_hop(headers: dict, current: str, following: str) -> dict:
        downgrade = (urlsplit(current).scheme.lower() == "https"
                     and urlsplit(following).scheme.lower() != "https")
        if _origin(current) == _origin(following) and not downgrade:
            return headers
        return {k: v for k, v in headers.items() if k.lower() not in _CREDENTIAL_HEADERS}

    async def _read_capped(self, response: httpx.Response) -> bytes:
        limit = self._policy.max_bytes
        declared = response.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            raise ResponseTooLarge(f"declared length {declared} exceeds {limit}")
        chunks, total = [], 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > limit:
                raise ResponseTooLarge(f"decoded body exceeds {limit} bytes")
            chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _materialise(response: httpx.Response, method: str, url: str, body: bytes) -> httpx.Response:
        headers = [(k, v) for k, v in response.headers.multi_items()
                   if k.lower() not in _STALE_RESPONSE_HEADERS]
        return httpx.Response(response.status_code, headers=headers, content=body,
                              request=httpx.Request(method, url))


def guarded_client(
    policy: UrlPolicy, *, resolver: Optional[Resolver] = None,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> GuardedClient:
    """Async context manager. ``resolver`` and ``transport`` are test hooks only."""
    return GuardedClient(policy, resolver=resolver, transport=transport)
