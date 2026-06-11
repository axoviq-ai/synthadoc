# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations
import json as _json
import logging
from typing import AsyncGenerator, Optional
import httpx
from synthadoc.config import AgentConfig
from synthadoc.providers.base import CompletionResponse, LLMProvider, Message

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 300


class OllamaProvider(LLMProvider):
    def __init__(self, config: AgentConfig, base_url: str = "http://localhost:11434",
                 timeout: int = _DEFAULT_TIMEOUT) -> None:
        self._config = config
        self._base_url = base_url
        self._timeout = timeout if timeout > 0 else _DEFAULT_TIMEOUT
        logger.warning(
            "Local Ollama model '%s' selected. GPU acceleration is required for "
            "interactive use — CPU-only inference is typically 10-50× slower and "
            "will time out on most queries. Switch to a cloud provider "
            "(e.g. gemini-2.5-flash-lite, free) if you do not have a CUDA/Metal GPU.",
            config.model,
        )

    async def complete(self, messages: list[Message], system: Optional[str] = None,
                       temperature: float = 0.0, max_tokens: int = 4096) -> CompletionResponse:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend({"role": m.role, "content": m.content} for m in messages)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(f"{self._base_url}/api/chat", json={
                "model": self._config.model, "messages": msgs, "stream": False,
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
                        break
