# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations
import json as _json
import logging
from typing import AsyncGenerator, Optional
import httpx
from synthadoc.config import AgentConfig
from synthadoc.providers.base import CompletionResponse, LLMProvider, Message
from synthadoc.providers.openai import _estimate_tokens_from_chars

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 300

# Ollama's native /api/chat takes a top-level boolean "think" field (unlike the
# OpenAI-compatible providers' nested thinking.type/enable_thinking extra_body).
# "" (unset) omits the key entirely so the model's own default applies.
_OLLAMA_THINK: dict[str, bool] = {
    "disabled": False,
    "enabled": True,
    "adaptive": True,
}

# Without an explicit options.num_ctx, Ollama loads the model with its default
# 4096-token context window and *silently truncates* anything longer — a real
# query's retrieved wiki context routinely runs 20K-60K+ tokens, so the model
# ends up answering from whatever fraction of the prompt survived truncation
# (observed: a context-stuffed query about ENIAC was answered about unrelated
# pages that happened to survive the cut). Bucketing to fixed sizes (rather
# than the exact estimated token count) means repeated queries of similar size
# reuse the same loaded context — a changed num_ctx forces Ollama to reload
# the whole model (confirmed: ~15s and +1.1GB RAM per step up observed here),
# so picking a new bucket on every call would make every query pay that cost.
_NUM_CTX_BUCKETS: tuple[int, ...] = (4096, 8192, 16384, 32768, 65536)
# A buffer for chat-template/role overhead beyond the raw message text.
_NUM_CTX_BUFFER_TOKENS = 512


def _pick_num_ctx(needed_tokens: int, max_num_ctx: int) -> int:
    """Return the smallest bucket (capped at max_num_ctx) that fits needed_tokens."""
    for bucket in _NUM_CTX_BUCKETS:
        if bucket > max_num_ctx:
            break
        if needed_tokens <= bucket:
            return bucket
    return min(_NUM_CTX_BUCKETS[-1], max_num_ctx)


class OllamaProvider(LLMProvider):
    def __init__(self, config: AgentConfig, base_url: str = "http://localhost:11434",
                 timeout: int = _DEFAULT_TIMEOUT, max_num_ctx: int = 65536) -> None:
        """*max_num_ctx* caps how large a context window a query may request.

        Each doubling of num_ctx costs real RAM for the KV cache (measured
        here: 4096→32768 added ~1.1GB on top of the 6.1GB model). 65536 is
        comfortable on a typical 16GB+ machine; lower it on constrained
        hardware, or raise it (up to the model's own context_length) if you
        have the RAM and hit truncation on very large queries.
        """
        self._config = config
        self._base_url = base_url
        self._timeout = timeout if timeout > 0 else _DEFAULT_TIMEOUT
        self._max_num_ctx = max_num_ctx
        # One provider instance is reused for every LLM call within a single
        # query (decompose, routing/translation, synthesis — see query_agent.py),
        # each with very different prompt sizes. Never requesting a smaller
        # num_ctx than already used this instance avoids Ollama reloading the
        # whole model (and its KV cache) *down* between calls, only to reload
        # it back *up* moments later for the next bigger call — reproduced
        # live: a small decompose call right after a huge synthesis call
        # triggered a reload that stalled for minutes under CPU contention.
        self._num_ctx_high_water = 0
        logger.warning(
            "Local Ollama model '%s' selected. GPU acceleration is required for "
            "interactive use — CPU-only inference is typically 10-50× slower and "
            "will time out on most queries. Switch to a cloud provider "
            "(e.g. gemini-2.5-flash-lite, free) if you do not have a CUDA/Metal GPU.",
            config.model,
        )

    def _think_kwarg(self) -> dict:
        think = _OLLAMA_THINK.get(self._config.thinking)
        return {"think": think} if think is not None else {}

    def _num_ctx_kwarg(self, msgs: list[dict], max_tokens: int) -> dict:
        input_tokens, _ = _estimate_tokens_from_chars(msgs, 0)
        needed = input_tokens + max_tokens + _NUM_CTX_BUFFER_TOKENS
        num_ctx = max(_pick_num_ctx(needed, self._max_num_ctx), self._num_ctx_high_water)
        self._num_ctx_high_water = num_ctx
        return {"options": {"num_ctx": num_ctx}}

    async def complete(self, messages: list[Message], system: Optional[str] = None,
                       temperature: float = 0.0, max_tokens: int = 4096) -> CompletionResponse:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend({"role": m.role, "content": m.content} for m in messages)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(f"{self._base_url}/api/chat", json={
                "model": self._config.model, "messages": msgs, "stream": False,
                **self._think_kwarg(),
                **self._num_ctx_kwarg(msgs, max_tokens),
            })
            resp.raise_for_status()
        data = resp.json()
        return CompletionResponse(text=data.get("message", {}).get("content", ""),
                                  input_tokens=data.get("prompt_eval_count", 0),
                                  output_tokens=data.get("eval_count", 0))

    async def complete_stream(
        self, messages: list[Message], system: Optional[str] = None,
        temperature: float = 0.0, max_tokens: int = 4096
    ) -> AsyncGenerator[str, None]:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend({"role": m.role, "content": m.content} for m in messages)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream("POST", f"{self._base_url}/api/chat", json={
                "model": self._config.model, "messages": msgs, "stream": True,
                **self._think_kwarg(),
                **self._num_ctx_kwarg(msgs, max_tokens),
            }) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    data = _json.loads(line)
                    token = data.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if data.get("done"):
                        self.last_stream_input_tokens = data.get("prompt_eval_count", 0)
                        self.last_stream_output_tokens = data.get("eval_count", 0)
                        break
