# SPDX-License-Identifier: AGPL-3.0-or-later
"""AnthropicProvider against the REAL anthropic SDK and a fake Messages API.

Unlike the mock-based tests, these run the installed SDK end to end (request
building, SSE parsing, error mapping) through an in-process transport, so an
SDK upgrade that removes or renames an argument fails here instead of in
production. anthropic >= 1.0 uses httpx2, so the transport comes from httpx2.
"""
from __future__ import annotations

import json

import anthropic
import httpx2
import pytest

from synthadoc.config import AgentConfig
from synthadoc.providers.anthropic import AnthropicProvider
from synthadoc.providers.base import Message

# Current and legacy models listed in the pricing table / config template.
MODELS = [
    "claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-8",
    "claude-sonnet-5", "claude-opus-5", "claude-opus-5-5", "claude-sonnet-5-5",
    "claude-haiku-5-5", "claude-fable-5-1",
]


def _sse(events: list[dict]) -> str:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)


def _stream_body(model: str, *, thinking: bool) -> str:
    events = [{"type": "message_start", "message": {
        "id": "msg_1", "type": "message", "role": "assistant", "model": model, "content": [],
        "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 12, "output_tokens": 1}}}]
    idx = 0
    if thinking:  # adaptive thinking is always on for Opus 5.5 / Fable
        events += [
            {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": "", "signature": ""}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "SECRET-REASONING"}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "sig"}},
            {"type": "content_block_stop", "index": 0},
        ]
        idx = 1
    events += [
        {"type": "content_block_start", "index": idx, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": idx, "delta": {"type": "text_delta", "text": "Hello"}},
        {"type": "content_block_delta", "index": idx, "delta": {"type": "text_delta", "text": " world"}},
        {"type": "content_block_stop", "index": idx},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
         "usage": {"output_tokens": 7}},
        {"type": "message_stop"},
    ]
    return _sse(events)


def _provider(model: str, responses: list[httpx2.Response | None]):
    """Provider wired to a fake API. ``None`` entries mean "stream a normal reply"."""
    requests: list[dict] = []
    queue = list(responses)

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(json.loads(request.content))
        resp = queue.pop(0) if queue else None
        if resp is not None:
            return resp
        return httpx2.Response(200, headers={"content-type": "text/event-stream"},
                               text=_stream_body(model, thinking=model.startswith(("claude-opus-5-5", "claude-fable"))))

    provider = AnthropicProvider(api_key="sk-test", config=AgentConfig(provider="anthropic", model=model))
    provider._client = anthropic.AsyncAnthropic(
        api_key="sk-test", max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    return provider, requests


def _error(status: int, kind: str) -> httpx2.Response:
    return httpx2.Response(status, json={"type": "error", "error": {"type": kind, "message": "x"}})


@pytest.mark.asyncio
@pytest.mark.parametrize("model", MODELS)
async def test_complete_works_and_never_sends_temperature(model):
    provider, requests = _provider(model, [None])
    resp = await provider.complete([Message(role="user", content="hi")], system="sys", temperature=0.7)
    assert (resp.text, resp.input_tokens, resp.output_tokens) == ("Hello world", 12, 7)
    assert "temperature" not in requests[0]
    assert requests[0]["system"] == "sys" and requests[0]["model"] == model


@pytest.mark.asyncio
@pytest.mark.parametrize("model", MODELS)
async def test_complete_stream_works_and_never_sends_temperature(model):
    provider, requests = _provider(model, [None])
    tokens = [t async for t in provider.complete_stream(
        [Message(role="user", content="hi")], system="sys", temperature=0.7)]
    assert tokens == ["Hello", " world"]  # thinking text never leaks into the answer
    assert (provider.last_stream_input_tokens, provider.last_stream_output_tokens) == (12, 7)
    assert "temperature" not in requests[0]


@pytest.mark.asyncio
async def test_rate_limit_propagates_without_retry():
    provider, requests = _provider("claude-sonnet-5-5", [_error(429, "rate_limit_error")])
    with pytest.raises(anthropic.RateLimitError):
        await provider.complete([Message(role="user", content="hi")])
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_server_error_is_retried_then_succeeds(monkeypatch):
    async def _no_sleep(_):
        return None
    monkeypatch.setattr("synthadoc.providers.anthropic.asyncio.sleep", _no_sleep)
    provider, requests = _provider("claude-opus-5-5", [_error(500, "api_error"), None])
    resp = await provider.complete([Message(role="user", content="hi")])
    assert resp.text == "Hello world"
    assert len(requests) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_reason,truncated", [("end_turn", False), ("max_tokens", True)])
async def test_complete_reports_truncation_from_stop_reason(stop_reason, truncated):
    body = _stream_body("claude-haiku-5-5", thinking=False).replace('"end_turn"', f'"{stop_reason}"')
    provider, _ = _provider("claude-haiku-5-5", [
        httpx2.Response(200, headers={"content-type": "text/event-stream"}, text=body)])
    resp = await provider.complete([Message(role="user", content="hi")])
    assert resp.text == "Hello world"
    assert resp.truncated is truncated
