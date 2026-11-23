# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""The lint URL-availability HEAD check must go through the SSRF guard."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx

from synthadoc.agents.lint_agent import LintAgent
from synthadoc.config import IngestConfig, ServerConfig


class _Cfg:
    def __init__(self, **server):
        self.server = ServerConfig(**server)
        self.ingest = IngestConfig()


@pytest.fixture(autouse=True)
def _empty_registry(monkeypatch):
    monkeypatch.setattr("synthadoc.cli._wiki.read_registry_all", lambda: {})


def _agent(tmp_path, cfg=None) -> LintAgent:
    return LintAgent(AsyncMock(), MagicMock(), log_writer=MagicMock(), audit_db=MagicMock(),
                     wiki_root=tmp_path, cfg=cfg)


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data/", "http://127.0.0.1:8330/x", "http://10.0.0.5/x",
])
@respx.mock
async def test_internal_urls_are_never_probed(tmp_path, url):
    route = respx.head(url)
    assert await _agent(tmp_path)._is_url_unavailable(url) is False
    assert not route.called


@pytest.mark.parametrize("status, expected", [(404, True), (410, True), (200, False), (500, False)])
@respx.mock
async def test_status_codes_for_a_public_url(tmp_path, fake_public_dns, status, expected):
    respx.head("https://example.com/gone").mock(return_value=httpx.Response(status))
    assert await _agent(tmp_path)._is_url_unavailable("https://example.com/gone") is expected


@respx.mock
async def test_the_check_uses_head(tmp_path, fake_public_dns):
    route = respx.head("https://example.com/p").mock(return_value=httpx.Response(200))
    await _agent(tmp_path)._is_url_unavailable("https://example.com/p")
    assert route.called


@respx.mock
async def test_connection_errors_are_ambiguous_not_unavailable(tmp_path, fake_public_dns):
    respx.head("https://example.com/slow").mock(side_effect=httpx.ConnectTimeout("t"))
    assert await _agent(tmp_path)._is_url_unavailable("https://example.com/slow") is False


@respx.mock
async def test_redirect_to_an_internal_address_is_not_followed(tmp_path, fake_public_dns):
    respx.head("https://example.com/r").mock(
        return_value=httpx.Response(302, headers={"location": "http://169.254.169.254/x"}))
    internal = respx.head("http://169.254.169.254/x")
    assert await _agent(tmp_path)._is_url_unavailable("https://example.com/r") is False
    assert not internal.called


@respx.mock
async def test_private_urls_are_checked_when_the_server_opts_in(tmp_path):
    route = respx.head("http://127.0.0.1:8331/doc").mock(return_value=httpx.Response(404))
    agent = _agent(tmp_path, cfg=_Cfg(allow_private_urls=True))
    assert await agent._is_url_unavailable("http://127.0.0.1:8331/doc") is True
    assert route.called


async def test_policy_is_built_off_the_event_loop(tmp_path, monkeypatch):
    """Building the policy can resolve registry host names (blocking), so it must run in a
    worker thread, not on the event loop."""
    import threading
    import synthadoc.core.url_policy as url_policy_module

    real = url_policy_module.url_policy_from_config
    threads = []

    def recording(cfg, **kwargs):
        threads.append(threading.current_thread())
        return real(cfg, **kwargs)

    monkeypatch.setattr(url_policy_module, "url_policy_from_config", recording)
    assert await _agent(tmp_path)._is_url_unavailable("http://169.254.169.254/x") is False
    assert threads and threads[0] is not threading.main_thread()
