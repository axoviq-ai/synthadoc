# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""make_fetcher(): the callable a skill receives so it never imports the guard."""
from __future__ import annotations

import asyncio
import ssl

import httpx
import pytest

from synthadoc.security.ssrf import SsrfBlocked, UrlPolicy, make_fetcher


async def _public(host, port):
    return ["93.184.216.34"]


def _transport(handler):
    return httpx.MockTransport(handler)


async def test_fetcher_returns_a_guarded_response_and_forwards_headers():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, text="page")

    fetch = make_fetcher(UrlPolicy(), resolver=_public, transport=_transport(handler))
    resp = await fetch("http://example.com/p", headers={"User-Agent": "ua-test"})
    assert resp.text == "page"
    assert seen[0].headers["user-agent"] == "ua-test"
    assert seen[0].url.host == "93.184.216.34"          # pinned


async def test_fetcher_blocks_internal_targets():
    fetch = make_fetcher(UrlPolicy(), transport=_transport(lambda r: httpx.Response(200)))
    with pytest.raises(SsrfBlocked):
        await fetch("http://169.254.169.254/latest/meta-data/")


async def test_timeout_argument_bounds_the_whole_request():
    async def slow(request):
        await asyncio.sleep(1)
        return httpx.Response(200)

    fetch = make_fetcher(UrlPolicy(total_timeout=60), resolver=_public, transport=_transport(slow))
    with pytest.raises(httpx.TimeoutException):
        await fetch("http://example.com/", timeout=0.05)


async def test_ssl_context_argument_is_used_unless_the_policy_has_its_own(monkeypatch):
    captured = []
    real = httpx.AsyncClient

    class Spy(real):
        def __init__(self, *args, **kwargs):
            captured.append(kwargs.get("verify"))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("synthadoc.security.ssrf.httpx.AsyncClient", Spy)
    skill_ctx, policy_ctx = ssl.create_default_context(), ssl.create_default_context()
    ok = _transport(lambda r: httpx.Response(200))

    await make_fetcher(UrlPolicy(), resolver=_public, transport=ok)(
        "http://example.com/", ssl_context=skill_ctx)
    await make_fetcher(UrlPolicy(ssl_context=policy_ctx), resolver=_public, transport=ok)(
        "http://example.com/", ssl_context=skill_ctx)
    assert captured == [skill_ctx, policy_ctx]


async def test_policy_is_not_mutated_between_calls():
    policy = UrlPolicy(total_timeout=30)
    fetch = make_fetcher(policy, resolver=_public, transport=_transport(lambda r: httpx.Response(200)))
    await fetch("http://example.com/", timeout=5)
    assert policy.total_timeout == 30
