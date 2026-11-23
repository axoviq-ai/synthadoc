# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Guarded HTTP client: pinning, manual redirects, size caps, timeouts."""
from __future__ import annotations

import asyncio
import gzip

import httpx
import pytest

from synthadoc.security.ssrf import (
    ResponseTooLarge,
    SsrfBlocked,
    UrlPolicy,
    guarded_client,
)

STRICT = UrlPolicy()


def _resolver(mapping):
    async def resolve(host, port):
        return list(mapping[host])
    return resolve


PUBLIC = _resolver({
    "example.com": ["93.184.216.34"],
    "other.example": ["8.8.4.4"],
    "v6.example": ["2606:4700:4700::1111"],
    "internal.example": ["10.0.0.5"],
    "multi.example": ["93.184.216.34", "8.8.8.8"],
})


class Recorder:
    """MockTransport handler that records requests and serves scripted responses."""

    def __init__(self, *responses):
        self.requests: list = []
        self._responses = list(responses)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        return item(request) if callable(item) else item


def _ok(body=b"hello", **kwargs):
    return httpx.Response(200, content=body, **kwargs)


def _redirect(location, status=302):
    return httpx.Response(status, headers={"location": location})


def _client(handler, policy=STRICT, resolver=PUBLIC):
    return guarded_client(policy, resolver=resolver, transport=httpx.MockTransport(handler))


async def test_request_is_pinned_to_the_validated_ip():
    rec = Recorder(_ok())
    async with _client(rec) as client:
        resp = await client.get("http://example.com/a/b?x=1")
    sent = rec.requests[0]
    assert sent.url.host == "93.184.216.34"
    assert sent.url.path == "/a/b" and sent.url.query == b"x=1"
    assert sent.headers["host"] == "example.com"
    assert resp.status_code == 200 and resp.text == "hello"


async def test_https_sets_sni_to_the_original_hostname():
    rec = Recorder(_ok())
    async with _client(rec) as client:
        await client.get("https://example.com/")
    assert rec.requests[0].extensions["sni_hostname"] == "example.com"
    assert rec.requests[0].headers["host"] == "example.com"


async def test_explicit_port_is_kept_in_url_and_host_header():
    rec = Recorder(_ok())
    async with _client(rec) as client:
        await client.get("http://example.com:8080/x")
    assert rec.requests[0].url.port == 8080
    assert rec.requests[0].headers["host"] == "example.com:8080"


async def test_ipv6_address_is_pinned_with_brackets():
    rec = Recorder(_ok())
    async with _client(rec) as client:
        await client.get("http://v6.example/")
    assert rec.requests[0].url.host == "2606:4700:4700::1111"


async def test_first_validated_address_is_the_one_used():
    rec = Recorder(_ok())
    async with _client(rec) as client:
        await client.get("http://multi.example/")
    assert rec.requests[0].url.host == "93.184.216.34"


async def test_caller_headers_are_forwarded():
    rec = Recorder(_ok())
    async with _client(rec) as client:
        await client.get("http://example.com/", headers={"User-Agent": "synthadoc-test"})
    assert rec.requests[0].headers["user-agent"] == "synthadoc-test"


async def test_head_is_supported():
    rec = Recorder(httpx.Response(404))
    async with _client(rec) as client:
        resp = await client.head("http://example.com/gone")
    assert rec.requests[0].method == "HEAD"
    assert resp.status_code == 404


async def test_blocked_url_never_reaches_the_transport():
    rec = Recorder(_ok())
    async with _client(rec) as client:
        with pytest.raises(SsrfBlocked):
            await client.get("http://internal.example/")
    assert rec.requests == []


async def test_redirect_to_a_blocked_host_is_blocked():
    rec = Recorder(_redirect("http://internal.example/secret"), _ok())
    async with _client(rec) as client:
        with pytest.raises(SsrfBlocked):
            await client.get("http://example.com/")
    assert len(rec.requests) == 1


async def test_redirect_to_a_public_host_is_followed_and_revalidated():
    rec = Recorder(_redirect("https://other.example/final"), _ok(b"done"))
    async with _client(rec) as client:
        resp = await client.get("http://example.com/")
    assert [r.url.host for r in rec.requests] == ["93.184.216.34", "8.8.4.4"]
    assert rec.requests[1].headers["host"] == "other.example"
    assert str(resp.url) == "https://other.example/final"
    assert resp.text == "done"


async def test_relative_redirect_is_resolved_against_the_current_url():
    rec = Recorder(_redirect("/next?a=1", status=301), _ok())
    async with _client(rec) as client:
        resp = await client.get("http://example.com/start")
    assert rec.requests[1].url.path == "/next"
    assert str(resp.url) == "http://example.com/next?a=1"


async def test_too_many_redirects():
    rec = Recorder(_redirect("http://example.com/loop"))
    async with _client(rec, policy=UrlPolicy(max_redirects=3)) as client:
        with pytest.raises(httpx.TooManyRedirects):
            await client.get("http://example.com/loop")
    assert len(rec.requests) == 4          # first request + 3 followed redirects


async def test_cross_host_redirect_drops_credentials():
    rec = Recorder(_redirect("https://other.example/"), _ok())
    async with _client(rec) as client:
        await client.get("https://example.com/", headers={
            "Authorization": "Bearer secret", "Cookie": "sid=1", "X-Trace": "keep"})
    assert "authorization" in rec.requests[0].headers
    second = rec.requests[1].headers
    assert "authorization" not in second and "cookie" not in second
    assert second["x-trace"] == "keep"


async def test_same_host_redirect_keeps_credentials():
    rec = Recorder(_redirect("/elsewhere"), _ok())
    async with _client(rec) as client:
        await client.get("https://example.com/", headers={"Authorization": "Bearer secret"})
    assert rec.requests[1].headers["authorization"] == "Bearer secret"


async def test_https_to_http_downgrade_drops_credentials_even_on_the_same_host():
    rec = Recorder(_redirect("http://example.com/plain"), _ok())
    async with _client(rec) as client:
        await client.get("https://example.com/", headers={"Authorization": "Bearer secret"})
    assert "authorization" not in rec.requests[1].headers


async def test_body_over_the_cap_is_rejected():
    rec = Recorder(_ok(b"x" * 2048))
    async with _client(rec, policy=UrlPolicy(max_bytes=1024)) as client:
        with pytest.raises(ResponseTooLarge):
            await client.get("http://example.com/")


async def test_declared_content_length_over_the_cap_is_rejected_early():
    rec = Recorder(httpx.Response(200, headers={"content-length": "999999"}, content=b"tiny"))
    async with _client(rec, policy=UrlPolicy(max_bytes=1024)) as client:
        with pytest.raises(ResponseTooLarge):
            await client.get("http://example.com/")


async def test_cap_counts_decoded_bytes_to_stop_decompression_bombs():
    bomb = gzip.compress(b"a" * 5_000_000)        # a few KB on the wire, 5 MB decoded
    assert len(bomb) < 50_000
    rec = Recorder(httpx.Response(200, headers={"content-encoding": "gzip"}, content=bomb))
    async with _client(rec, policy=UrlPolicy(max_bytes=1_000_000)) as client:
        with pytest.raises(ResponseTooLarge):
            await client.get("http://example.com/")


async def test_response_is_fully_read_and_decoded():
    body = gzip.compress(b"payload")
    rec = Recorder(httpx.Response(200, headers={"content-encoding": "gzip"}, content=body))
    async with _client(rec) as client:
        resp = await client.get("http://example.com/")
    assert resp.content == b"payload" and resp.text == "payload"
    assert "content-encoding" not in resp.headers


async def test_error_statuses_still_raise_for_status():
    rec = Recorder(httpx.Response(404, content=b"nope"))
    async with _client(rec) as client:
        resp = await client.get("http://example.com/")
    with pytest.raises(httpx.HTTPStatusError):
        resp.raise_for_status()


async def test_total_timeout_is_enforced():
    async def slow(request):
        await asyncio.sleep(1)
        return httpx.Response(200)

    async with _client(slow, policy=UrlPolicy(total_timeout=0.05)) as client:
        with pytest.raises(httpx.TimeoutException):
            await client.get("http://example.com/")


async def test_dns_failure_surfaces_as_connect_error_to_keep_retry_behaviour():
    async def failing(host, port):
        raise OSError("no such host")

    rec = Recorder(_ok())
    async with _client(rec, resolver=failing) as client:
        with pytest.raises(httpx.ConnectError):
            await client.get("http://example.com/")
    assert rec.requests == []


async def test_proxy_mode_keeps_the_hostname_but_still_pre_checks():
    rec = Recorder(_ok())
    policy = UrlPolicy(trust_proxy_env=True)
    async with _client(rec, policy=policy) as client:
        await client.get("http://example.com/x")
        with pytest.raises(SsrfBlocked):
            await client.get("http://internal.example/")
    assert rec.requests[0].url.host == "example.com"      # no pinning through a proxy
    assert len(rec.requests) == 1


async def test_client_ignores_proxy_environment_by_default(monkeypatch):
    seen = {}
    real = httpx.AsyncClient

    class Spy(real):
        def __init__(self, *args, **kwargs):
            seen.update(kwargs)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("synthadoc.security.ssrf.httpx.AsyncClient", Spy)
    async with _client(Recorder(_ok())):
        pass
    assert seen["trust_env"] is False
    assert seen["follow_redirects"] is False


async def test_proxy_environment_is_honoured_only_when_opted_in(monkeypatch):
    seen = {}
    real = httpx.AsyncClient

    class Spy(real):
        def __init__(self, *args, **kwargs):
            seen.update(kwargs)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("synthadoc.security.ssrf.httpx.AsyncClient", Spy)
    async with _client(Recorder(_ok()), policy=UrlPolicy(trust_proxy_env=True)):
        pass
    assert seen["trust_env"] is True


# ---- fall back to the next validated address (dual-stack hosts) ---------------

DUAL_STACK = _resolver({"dual.example": ["2606:4700:4700::1111", "93.184.216.34"]})
V6 = "2606:4700:4700::1111"


async def test_connect_error_falls_back_to_the_next_validated_address():
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if request.url.host == V6:
            raise httpx.ConnectError("no route to host", request=request)
        return httpx.Response(200, text="ok")

    async with _client(handler, resolver=DUAL_STACK) as client:
        resp = await client.get("https://dual.example/p")
    assert hosts == [V6, "93.184.216.34"]
    assert resp.text == "ok"


async def test_fallback_attempt_keeps_the_hostname_for_host_header_and_sni():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.host == V6:
            raise httpx.ConnectTimeout("timed out", request=request)
        return httpx.Response(200)

    async with _client(handler, resolver=DUAL_STACK) as client:
        await client.get("https://dual.example/")
    second = seen[1]
    assert second.headers["host"] == "dual.example"
    assert second.extensions["sni_hostname"] == "dual.example"


async def test_all_addresses_failing_raises_the_last_connect_error():
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        raise httpx.ConnectError("refused", request=request)

    async with _client(handler, resolver=DUAL_STACK) as client:
        with pytest.raises(httpx.ConnectError):
            await client.get("http://dual.example/")
    assert hosts == [V6, "93.184.216.34"]


async def test_read_errors_are_not_retried_on_another_address():
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        raise httpx.ReadTimeout("slow", request=request)

    async with _client(handler, resolver=DUAL_STACK) as client:
        with pytest.raises(httpx.ReadTimeout):
            await client.get("http://dual.example/")
    assert hosts == [V6]


async def test_redirect_hops_also_fall_back():
    hosts = []

    def handler(request):
        hosts.append((request.url.host, request.headers["host"]))
        if request.headers["host"] == "dual.example":
            if request.url.host == V6:
                raise httpx.ConnectError("no route", request=request)
            return httpx.Response(200, text="done")
        return httpx.Response(302, headers={"location": "http://dual.example/final"})

    resolver = _resolver({"example.com": ["93.184.216.34"],
                          "dual.example": ["2606:4700:4700::1111", "93.184.216.34"]})
    async with _client(handler, resolver=resolver) as client:
        resp = await client.get("http://example.com/")
    assert resp.text == "done"
    assert hosts[-1] == ("93.184.216.34", "dual.example")


async def test_proxy_mode_makes_a_single_attempt():
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        raise httpx.ConnectError("refused", request=request)

    async with _client(handler, policy=UrlPolicy(trust_proxy_env=True), resolver=DUAL_STACK) as client:
        with pytest.raises(httpx.ConnectError):
            await client.get("http://dual.example/")
    assert hosts == ["dual.example"]
