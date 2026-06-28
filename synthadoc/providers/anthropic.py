# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations
import asyncio
import re
from typing import AsyncGenerator, Optional
import anthropic as anthropic_lib
from synthadoc.config import AgentConfig
from synthadoc.providers.base import CompletionResponse, LLMProvider, Message

# Claude 4.x models (claude-opus-4-8, claude-sonnet-4-6, claude-haiku-4-5, …) deprecated
# the temperature parameter; earlier models still accept it.
_CLAUDE4_RE = re.compile(r"^claude-(?:opus|sonnet|haiku)-4-")


def _supports_temperature(model: str) -> bool:
    return not bool(_CLAUDE4_RE.match(model))

# RateLimitError (429) is not retried — quota exhaustion needs a provider switch or wait.
# InternalServerError covers transient 500/529 overload; retry with backoff.
_RETRYABLE = (anthropic_lib.InternalServerError,)
_RATE_LIMIT = (anthropic_lib.RateLimitError,)
_MAX_RETRIES = 3


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, config: AgentConfig, timeout: int = 0) -> None:
        # timeout=0 means "use the SDK default" (600 s); any positive value caps the call.
        client_kwargs: dict = {"api_key": api_key}
        if timeout > 0:
            client_kwargs["timeout"] = float(timeout)
        self._client = anthropic_lib.AsyncAnthropic(**client_kwargs)
        self._config = config

    async def complete(self, messages: list[Message], system: Optional[str] = None,
                       temperature: float = 0.0, max_tokens: int = 4096) -> CompletionResponse:
        kwargs: dict = {
            "model": self._config.model,
            "max_tokens": max_tokens,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if _supports_temperature(self._config.model):
            kwargs["temperature"] = temperature
        if system:
            kwargs["system"] = system
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._client.messages.create(**kwargs)
                text = "".join(b.text for b in resp.content if hasattr(b, "text"))
                return CompletionResponse(text=text,
                                         input_tokens=resp.usage.input_tokens,
                                         output_tokens=resp.usage.output_tokens)
            except _RATE_LIMIT:
                raise  # quota exhaustion — propagate immediately, no retry
            except _RETRYABLE as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)  # 1 s, 2 s, 4 s backoff (attempt 0 → 1 s)
                continue
            except Exception:
                raise
        assert last_exc is not None
        raise last_exc

    async def complete_stream(
        self, messages: list[Message], system: Optional[str] = None,
        temperature: float = 0.0, max_tokens: int = 4096
    ) -> AsyncGenerator[str, None]:
        kwargs: dict = {
            "model": self._config.model,
            "max_tokens": max_tokens,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if _supports_temperature(self._config.model):
            kwargs["temperature"] = temperature
        if system:
            kwargs["system"] = system
        async with self._client.messages.stream(**kwargs) as stream:
            async for event in stream:
                if (event.type == "content_block_delta"
                        and hasattr(event.delta, "text")):
                    yield event.delta.text
