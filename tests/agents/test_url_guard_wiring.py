# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Inside Synthadoc the URL skill must always receive a guarded fetcher (fail closed)."""
from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
import respx

from synthadoc.agents.ingest_agent import IngestAgent
from synthadoc.agents.skill_agent import SkillAgent
from synthadoc.config import IngestConfig, ServerConfig
from synthadoc.security.ssrf import SsrfBlocked, UrlPolicy

HTML = "<html><body><p>doc body</p></body></html>"


class _Cfg:
    def __init__(self, **server):
        self.server = ServerConfig(**server)
        self.ingest = IngestConfig()


@pytest.fixture(autouse=True)
def _empty_registry(monkeypatch):
    monkeypatch.setattr("synthadoc.cli._wiki.read_registry_all", lambda: {})


def _agent(**kwargs) -> IngestAgent:
    return IngestAgent(provider=MagicMock(), store=MagicMock(), search=MagicMock(),
                       log_writer=MagicMock(), audit_db=MagicMock(), cache=MagicMock(), **kwargs)


async def test_bare_skill_agent_gets_a_strict_guarded_url_skill():
    # /analyse builds a bare SkillAgent(); this is the path from the original SSRF report.
    skill = SkillAgent().get_skill("url")
    with pytest.raises(SsrfBlocked):
        await skill.extract("http://127.0.0.1:1/")
    with pytest.raises(SsrfBlocked):
        await skill.extract("http://169.254.169.254/latest/meta-data/")


async def test_skill_agent_keeps_an_explicitly_injected_fetcher():
    calls = []

    async def fetcher(url, **kwargs):
        calls.append(url)
        return httpx.Response(200, text=HTML, request=httpx.Request("GET", url))

    skill = SkillAgent(skill_kwargs={"url": {"fetcher": fetcher}}).get_skill("url")
    await skill.extract("http://127.0.0.1:1/ok")
    assert calls == ["http://127.0.0.1:1/ok"]


async def test_ingest_agent_without_config_is_strict():
    skill = _agent()._skill_agent.get_skill("url")
    with pytest.raises(SsrfBlocked):
        await skill.extract("http://127.0.0.1:8123/doc")


@respx.mock
async def test_ingest_agent_honours_allow_private_urls_from_config():
    respx.get("http://127.0.0.1:8123/doc").mock(return_value=httpx.Response(200, text=HTML))
    skill = _agent(cfg=_Cfg(allow_private_urls=True))._skill_agent.get_skill("url")
    assert "doc body" in (await skill.extract("http://127.0.0.1:8123/doc")).text


async def test_ingest_agent_blocks_private_urls_when_the_config_does_not_allow_them():
    skill = _agent(cfg=_Cfg(allow_private_urls=False))._skill_agent.get_skill("url")
    with pytest.raises(SsrfBlocked):
        await skill.extract("http://127.0.0.1:8123/doc")


async def test_ingest_agent_never_reaches_its_own_server_port_even_when_private_is_allowed():
    skill = _agent(cfg=_Cfg(allow_private_urls=True, port=7070))._skill_agent.get_skill("url")
    with pytest.raises(SsrfBlocked):
        await skill.extract("http://127.0.0.1:7070/query?q=x")


@respx.mock
async def test_explicit_url_policy_overrides_the_config():
    respx.get("http://127.0.0.1:8124/doc").mock(return_value=httpx.Response(200, text=HTML))
    agent = _agent(cfg=_Cfg(allow_private_urls=False), url_policy=UrlPolicy(allow_private=True))
    assert "doc body" in (await agent._skill_agent.get_skill("url").extract(
        "http://127.0.0.1:8124/doc")).text
