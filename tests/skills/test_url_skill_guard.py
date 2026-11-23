# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""The URL skill takes an injected fetcher; it never imports the guard itself.

Synthadoc injects ``make_fetcher(policy)``. Used standalone (no fetcher) the skill
keeps its plain httpx behaviour and needs nothing outside synthadoc/skills.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from synthadoc.security.ssrf import ResponseTooLarge, SsrfBlocked, UrlPolicy, make_fetcher
from synthadoc.skills.url.scripts.main import UrlSkill

HTML = "<html><body><p>doc body</p></body></html>"


def _guarded(policy: UrlPolicy | None = None) -> UrlSkill:
    return UrlSkill(fetcher=make_fetcher(policy or UrlPolicy()))


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:1/", "http://[::1]:1/", "http://localhost:1/",
    "http://169.254.169.254/latest/meta-data/", "http://10.0.0.5/admin",
    "file:///etc/passwd", "ftp://example.com/x",
])
async def test_guarded_skill_blocks_internal_targets_and_odd_schemes(url):
    with pytest.raises(SsrfBlocked):
        await _guarded().extract(url)


async def test_blocked_error_text_is_generic():
    with pytest.raises(SsrfBlocked) as info:
        await _guarded().extract("http://10.9.8.7/")
    assert "10.9.8.7" not in str(info.value)


@respx.mock
async def test_private_urls_work_when_the_operator_allows_them():
    respx.get("http://127.0.0.1:8123/doc").mock(return_value=httpx.Response(200, text=HTML))
    result = await _guarded(UrlPolicy(allow_private=True)).extract("http://127.0.0.1:8123/doc")
    assert "doc body" in result.text


async def test_registered_wiki_ports_stay_blocked_even_when_private_urls_are_allowed():
    policy = UrlPolicy(allow_private=True, always_block=frozenset({("127.0.0.1", 7071)}))
    with pytest.raises(SsrfBlocked):
        await _guarded(policy).extract("http://127.0.0.1:7071/query?q=x")


@respx.mock
async def test_metadata_stays_blocked_when_private_urls_are_allowed():
    route = respx.get("http://169.254.169.254/latest/meta-data/")
    with pytest.raises(SsrfBlocked):
        await _guarded(UrlPolicy(allow_private=True)).extract(
            "http://169.254.169.254/latest/meta-data/")
    assert not route.called


@respx.mock
async def test_redirect_to_an_internal_address_is_blocked(fake_public_dns):
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(302, headers={"location": "http://169.254.169.254/x"}))
    internal = respx.get("http://169.254.169.254/x")
    with pytest.raises(SsrfBlocked):
        await _guarded().extract("https://example.com/")
    assert not internal.called


@respx.mock
async def test_oversized_response_is_rejected(fake_public_dns):
    respx.get("https://example.com/big").mock(return_value=httpx.Response(200, text="x" * 5000))
    with pytest.raises(ResponseTooLarge):
        await _guarded(UrlPolicy(max_bytes=1000)).extract("https://example.com/big")


async def test_skill_passes_its_headers_timeout_and_ssl_context_to_the_fetcher():
    seen = {}

    async def fetcher(url, **kwargs):
        seen.update(kwargs, url=url)
        return httpx.Response(200, text=HTML, request=httpx.Request("GET", url))

    await UrlSkill(fetch_timeout=7, fetcher=fetcher).extract("https://example.com/p")
    assert seen["timeout"] == 7
    assert "Mozilla" in seen["headers"]["User-Agent"]
    assert seen["ssl_context"] is not None


@respx.mock
async def test_standalone_skill_without_a_fetcher_uses_plain_httpx_and_no_dns():
    # No fake_public_dns fixture: reaching the resolver would need real network.
    respx.get("https://example.com/").mock(return_value=httpx.Response(200, text=HTML))
    result = await UrlSkill().extract("https://example.com/")
    assert "doc body" in result.text
