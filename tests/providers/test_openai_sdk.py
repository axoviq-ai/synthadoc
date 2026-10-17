# SPDX-License-Identifier: AGPL-3.0-or-later
"""OpenAIProvider against the REAL openai SDK and a fake chat-completions API.

Checks the request parameters each provider sends (the native OpenAI API needs
max_completion_tokens, and GPT-5-era and newer models reject a non-default
temperature) and that responses still parse end to end.
"""
from __future__ import annotations

import json

import httpx
import openai
import pytest

from synthadoc.config import AgentConfig
from synthadoc.providers.base import Message
from synthadoc.providers.openai import OpenAIProvider

# (provider, model, expected sampling arguments in the request body)
CASES = [
    ("openai", "gpt-4o-mini", {"max_completion_tokens": 4096, "temperature": 0.0}),
    ("openai", "gpt-4.1", {"max_completion_tokens": 4096, "temperature": 0.0}),
    ("openai", "gpt-5.6-terra", {"max_completion_tokens": 4096}),
    ("openai", "gpt-6-luna", {"max_completion_tokens": 4096}),
    ("openai", "o3", {"max_completion_tokens": 4096}),
    ("minimax", "MiniMax-M3", {"max_tokens": 4096, "temperature": 0.0}),
    ("gemini", "gemini-2.5-flash-lite", {"max_tokens": 4096, "temperature": 0.0}),
    ("deepseek", "deepseek-flash", {"max_tokens": 4096, "temperature": 0.0}),
    ("groq", "openai/gpt-oss-20b", {"max_tokens": 4096, "temperature": 0.0}),
    ("qwen", "qwen-plus", {"max_tokens": 4096, "temperature": 0.0}),
]
_SAMPLING_KEYS = ("max_tokens", "max_completion_tokens", "temperature")


def _completion(model: str) -> dict:
    return {"id": "c1", "object": "chat.completion", "created": 1, "model": model,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "Hello world"}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19}}


def _chunks(model: str) -> str:
    base = {"id": "c1", "object": "chat.completion.chunk", "created": 1, "model": model}
    parts = [dict(base, choices=[{"index": 0, "delta": {"role": "assistant", "content": t},
                                  "finish_reason": None}]) for t in ("Hello", " world")]
    parts.append(dict(base, choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}]))
    parts.append(dict(base, choices=[], usage={"prompt_tokens": 12, "completion_tokens": 7,
                                               "total_tokens": 19}))
    return "".join(f"data: {json.dumps(p)}\n\n" for p in parts) + "data: [DONE]\n\n"


def _provider(provider: str, model: str):
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        if body.get("stream"):
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  text=_chunks(model))
        return httpx.Response(200, json=_completion(model))

    p = OpenAIProvider(api_key="sk-test", config=AgentConfig(provider=provider, model=model))
    p._client = openai.AsyncOpenAI(
        api_key="sk-test", base_url="http://fake/v1", max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return p, requests


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,model,expected", CASES)
async def test_complete_sends_provider_specific_sampling_args(provider, model, expected):
    p, requests = _provider(provider, model)
    resp = await p.complete([Message(role="user", content="hi")], system="sys")
    assert (resp.text, resp.input_tokens, resp.output_tokens) == ("Hello world", 12, 7)
    assert {k: v for k, v in requests[0].items() if k in _SAMPLING_KEYS} == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,model,expected", CASES)
async def test_complete_stream_sends_provider_specific_sampling_args(provider, model, expected):
    p, requests = _provider(provider, model)
    tokens = [t async for t in p.complete_stream([Message(role="user", content="hi")], system="sys")]
    assert "".join(tokens) == "Hello world"
    assert {k: v for k, v in requests[0].items() if k in _SAMPLING_KEYS} == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("finish_reason,truncated", [("stop", False), ("length", True)])
async def test_complete_reports_truncation_from_finish_reason(finish_reason, truncated):
    def handler(request: httpx.Request) -> httpx.Response:
        body = _completion("deepseek-flash")
        body["choices"][0]["finish_reason"] = finish_reason
        return httpx.Response(200, json=body)

    p = OpenAIProvider(api_key="sk-test", config=AgentConfig(provider="deepseek", model="deepseek-flash"))
    p._client = openai.AsyncOpenAI(
        api_key="sk-test", base_url="http://fake/v1", max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    resp = await p.complete([Message(role="user", content="hi")])
    assert resp.text == "Hello world"
    assert resp.truncated is truncated
