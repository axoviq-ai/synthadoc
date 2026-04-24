# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations
from typing import Optional
import httpx
from synthadoc.config import AgentConfig
from synthadoc.providers.base import CompletionResponse, LLMProvider, Message


class OllamaProvider(LLMProvider):
    def __init__(self, config: AgentConfig, base_url: str = "http://localhost:11434") -> None:
        self._config = config
        self._base_url = base_url

    async def complete(self, messages: list[Message], system: Optional[str] = None,
                       temperature: float = 0.0, max_tokens: int = 4096) -> CompletionResponse:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend({"role": m.role, "content": m.content} for m in messages)
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{self._base_url}/api/chat", json={
                "model": self._config.model, "messages": msgs, "stream": False,
            })
            resp.raise_for_status()
        data = resp.json()
        return CompletionResponse(text=data.get("message", {}).get("content", ""),
                                  input_tokens=data.get("prompt_eval_count", 0),
                                  output_tokens=data.get("eval_count", 0))
