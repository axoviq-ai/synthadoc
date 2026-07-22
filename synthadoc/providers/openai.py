# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations
import asyncio
import json as _json
import logging
import re
from typing import AsyncGenerator, Optional
import openai as _openai
from openai import AsyncOpenAI
from synthadoc.config import AgentConfig
from synthadoc.providers.base import CompletionResponse, LLMProvider, Message

logger = logging.getLogger(__name__)

# Providers whose chat endpoint does not support image inputs
_NO_VISION_HOSTS = ("groq.com", "api.deepseek.com")

# Retry delays (seconds) after an HTTP 429 rate-limit response.
#
# One retry after 65 s covers the most common cause: a per-minute quota window
# that resets after 60 s (the extra 5 s is buffer).  If the second attempt
# also fails, the provider's hourly or daily quota is exhausted — no number of
# additional retries will help.  Failing fast lets the orchestrator requeue the
# job and move on; the worker-level pause (also ~60 s) provides the inter-job
# breathing room.
#
# NOTE: daily quota exhaustion is detected separately (_is_daily_quota_error) and
# raises immediately without any sleep — sleeping 65 s then retrying would waste
# time and burn one more precious daily request on a call that will always fail.
#
# Default demo model is Gemini 2.5 Flash-Lite: 30 RPM / 1,000 RPD.  Groq has similar caps.
_RATE_LIMIT_RETRY_DELAYS_S: tuple[int, ...] = (65,)

# Retry delays (seconds) after an HTTP 5xx server error (e.g. Gemini 503
# "model experiencing high demand").  These are transient — a short backoff
# is enough.  Three attempts with escalating waits cover the typical
# load-spike window without waiting as long as a rate-limit retry.
_SERVER_ERROR_RETRY_DELAYS_S: tuple[int, ...] = (5, 15, 30)

# Module-level alias so tests can patch precisely:
#   patch("synthadoc.providers.openai._sleep", new=AsyncMock())
_sleep = asyncio.sleep

_THINKING_EXTRA_BODY: dict[str, dict] = {
    "disabled": {"thinking": {"type": "disabled"}},
    "enabled":  {"thinking": {"type": "adaptive"}},
    "adaptive": {"thinking": {"type": "adaptive"}},
}

_QWEN_THINKING_EXTRA_BODY: dict[str, dict] = {
    "disabled": {"enable_thinking": False},
    "enabled":  {"enable_thinking": True},
    "adaptive": {"enable_thinking": True},
}


def _build_extra_body(thinking: str, provider: str = "") -> dict:
    """Return the provider extra_body dict for the given thinking setting.

    Empty string (unset) → no extra_body; provider default applies.
    DashScope (qwen) uses enable_thinking; MiniMax/others use thinking.type.
    """
    if provider == "qwen":
        return _QWEN_THINKING_EXTRA_BODY.get(thinking, {})
    return _THINKING_EXTRA_BODY.get(thinking, {})


def _extract_last_json(s: str) -> str:
    """Extract the last complete JSON object or array from s using brace matching.

    Walks backwards from the last closing bracket to find its matching opener,
    correctly handling nested structures and ignoring stray braces in prose.
    """
    def _find_opening(text: str, close_pos: int, close_ch: str, open_ch: str) -> int:
        depth = 0
        in_str = False
        escape = False
        for i in range(close_pos, -1, -1):
            c = text[i]
            if escape:
                escape = False
                continue
            if c == '\\' and in_str:
                escape = True
                continue
            if c == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if c == close_ch:
                depth += 1
            elif c == open_ch:
                depth -= 1
                if depth == 0:
                    return i
        return -1

    obj_end = s.rfind("}")
    arr_end = s.rfind("]")
    result_obj = result_arr = ""
    if obj_end >= 0:
        start = _find_opening(s, obj_end, "}", "{")
        if start >= 0:
            result_obj = s[start: obj_end + 1]
    if arr_end >= 0:
        start = _find_opening(s, arr_end, "]", "[")
        if start >= 0:
            result_arr = s[start: arr_end + 1]
    if result_obj and result_arr:
        return result_obj if obj_end >= arr_end else result_arr
    return result_obj or result_arr


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, config: AgentConfig, timeout: int = 0) -> None:
        kwargs: dict = {"api_key": api_key}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self._client = AsyncOpenAI(**kwargs)
        self._config = config
        self._timeout: int | None = timeout if timeout > 0 else None
        base = str(config.base_url or "")
        self.supports_vision = not any(host in base for host in _NO_VISION_HOSTS)
        self._extra_body: dict = _build_extra_body(config.thinking, config.provider)

    @staticmethod
    def _to_openai_content(content):
        """Convert Anthropic-format content blocks to OpenAI format when needed."""
        if not isinstance(content, list):
            return content
        result = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "image":
                src = block.get("source", {})
                if src.get("type") == "base64":
                    mime = src.get("media_type", "image/png")
                    data = src.get("data", "")
                    result.append({"type": "image_url",
                                   "image_url": {"url": f"data:{mime};base64,{data}"}})
                    continue
            result.append(block)
        return result

    @staticmethod
    def _is_daily_quota_error(exc: _openai.RateLimitError) -> bool:
        """Return True when this 429 is a per-day (not per-minute) quota exhaustion.

        Gemini's daily-quota response includes a QuotaFailure detail with a
        quotaId containing 'PerDay'.  For Groq, OpenAI, and other providers
        the body won't match and we return False, preserving the 65 s retry.
        """
        body = exc.body if isinstance(exc.body, dict) else {}
        for detail in body.get("error", {}).get("details", []):
            for violation in detail.get("violations", []):
                if "PerDay" in violation.get("quotaId", ""):
                    return True
        text = str(exc).lower()
        return "perday" in text or "requests_per_day" in text or "daily quota" in text

    async def _call_with_retry(self, msgs: list, temperature: float,
                               max_tokens: int):
        """Call the completions API with retry logic for transient errors.

        - 429 RateLimitError: retried once after 65 s (per-minute quota window).
          Daily quota exhaustion raises immediately — no retry possible.
        - 5xx InternalServerError: retried up to 3 times with short backoff
          (5 s / 15 s / 30 s) for transient load spikes (e.g. Gemini 503).
        """
        rl_delays = list(_RATE_LIMIT_RETRY_DELAYS_S)
        se_delays = list(_SERVER_ERROR_RETRY_DELAYS_S)
        rl_idx = se_idx = 0

        while True:
            try:
                return await self._client.chat.completions.create(
                    model=self._config.model, messages=msgs,
                    temperature=temperature, max_tokens=max_tokens,
                    timeout=self._timeout,
                    **({"extra_body": self._extra_body} if self._extra_body else {}),
                )
            except _openai.APITimeoutError:
                logger.error(
                    "LLM call to %s timed out after %d s. "
                    "Increase [agents] llm_timeout_seconds in .synthadoc/config.toml "
                    "or switch to a faster model.",
                    self._config.provider, self._timeout,
                )
                raise
            except _openai.PermissionDeniedError as exc:
                # Some providers (e.g. Qwen/DashScope) return 403 with an
                # AllocationQuota error code when the free-tier quota is exhausted.
                body = exc.body if isinstance(exc.body, dict) else {}
                err_type = (body.get("error", {}).get("type") or "").lower()
                err_code = (body.get("error", {}).get("code") or "").lower()
                if "allocationquota" in err_type or "allocationquota" in err_code or "quota" in str(exc).lower():
                    err_msg = body.get("error", {}).get("message") or str(exc)
                    logger.error(
                        "Quota exhausted for %s (403) — %s",
                        self._config.provider, err_msg,
                    )
                    from synthadoc.errors import DailyQuotaExhaustedException
                    raise DailyQuotaExhaustedException(self._config.provider) from exc
                raise
            except _openai.RateLimitError as exc:
                if self._is_daily_quota_error(exc):
                    logger.error(
                        "Daily quota exhausted for %s — no retry possible until "
                        "quota resets (typically midnight UTC). Free-tier providers "
                        "cap daily usage; upgrade to a paid API key or switch "
                        "providers.",
                        self._config.provider,
                    )
                    from synthadoc.errors import DailyQuotaExhaustedException
                    raise DailyQuotaExhaustedException(self._config.provider) from exc
                if rl_idx >= len(rl_delays):
                    raise
                wait = rl_delays[rl_idx]
                rl_idx += 1
                logger.warning(
                    "Rate limit (429) from %s — waiting %d s then retrying "
                    "(per-minute window reset). If this retry also fails, the "
                    "hourly/daily quota is likely exhausted — check your provider "
                    "dashboard or switch providers.",
                    self._config.provider, wait,
                )
                await _sleep(wait)
            except _openai.InternalServerError as exc:
                if se_idx >= len(se_delays):
                    raise
                wait = se_delays[se_idx]
                se_idx += 1
                logger.warning(
                    "Server error (%d) from %s — waiting %d s then retrying "
                    "(%d attempt(s) left). Cause: %s",
                    exc.status_code, self._config.provider, wait,
                    len(se_delays) - se_idx, exc,
                )
                await _sleep(wait)

    async def complete(self, messages: list[Message], system: Optional[str] = None,
                       temperature: float = 0.0, max_tokens: int = 4096) -> CompletionResponse:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend({"role": m.role, "content": self._to_openai_content(m.content)}
                    for m in messages)
        resp = await self._call_with_retry(msgs, temperature, max_tokens)
        if not resp.choices:
            # Some providers (e.g. MiniMax) return choices=null when the model
            # exceeds its internal generation budget. Extract any error details.
            extra = getattr(resp, "model_extra", None) or {}
            base_resp = extra.get("base_resp") or {}
            err_code = base_resp.get("status_code", "unknown")
            err_msg  = base_resp.get("status_msg",  "no details")
            logger.error(
                "OpenAI provider: %s returned choices=null (code=%s, msg=%r). "
                "The model likely timed out internally. Set "
                "[agents] llm_timeout_seconds in .synthadoc/config.toml "
                "(e.g. llm_timeout_seconds = 90) to fail fast, or switch to "
                "a lighter model.",
                self._config.provider, err_code, err_msg,
            )
            raise RuntimeError(
                f"{self._config.provider} returned choices=null "
                f"(code={err_code}): {err_msg}"
            )
        choice = resp.choices[0]
        if choice.finish_reason == "length":
            logger.warning(
                "complete: response truncated by token limit "
                "(finish_reason=length, max_tokens=%d, model=%s). "
                "Increase scaffold_max_tokens (ingest) or query_max_tokens (queries) "
                "in [agents] of config.toml.",
                max_tokens, self._config.model,
            )
        original_content = choice.message.content or ""
        # Reasoning models (MiniMax M2, DeepSeek R1, Qwen QwQ) wrap their chain-of-thought
        # in <think> blocks, but the </think> tag can appear mid-JSON (e.g. inside a key
        # name), making regex-based stripping unreliable. For these models, extract the last
        # JSON structure directly via brace matching, then scrub residual think tags.
        if original_content.lstrip().startswith("<think>"):
            # Reasoning models embed chain-of-thought in <think> blocks. The </think>
            # tag can appear mid-JSON key, so regex stripping is unreliable. Extract
            # via brace matching, scrub think tags and control chars, then validate as
            # real JSON — brace matching can false-positive on [[wikilinks]], which are
            # not JSON. Invalid extractions fall through to prose handling.
            text = _extract_last_json(original_content)
            if text:
                text = re.sub(r"</?think>", "", text)
                text = re.sub(r"[\x00-\x1f]", "", text)
                try:
                    _json.loads(text)
                    logger.debug("OpenAI provider: extracted JSON from reasoning model content")
                except (_json.JSONDecodeError, ValueError):
                    text = ""  # false positive (e.g. [[wikilink]]) — fall through to prose
            if not text:
                # No JSON in content — check the reasoning side-channel field (MiniMax
                # uses "reasoning", DeepSeek uses "reasoning_content").
                extra = getattr(choice.message, "model_extra", None) or {}
                reasoning = (extra.get("reasoning_content") or extra.get("reasoning") or "").strip()
                extracted = _extract_last_json(reasoning)
                if extracted:
                    try:
                        _json.loads(extracted)
                        text = extracted
                        logger.debug("OpenAI provider: extracted JSON from reasoning side-channel")
                    except (_json.JSONDecodeError, ValueError):
                        pass
                if not text:
                    # Prose response — strip think blocks to get the actual answer text.
                    text = re.sub(r"<think>.*?</think>", "", original_content, flags=re.DOTALL).strip()
                    text = re.sub(r"<think>.*$", "", text, flags=re.DOTALL).strip()
                    if not text:
                        text = reasoning
                    logger.debug("OpenAI provider: using think-stripped content as prose answer")
        elif not original_content:
            # content=null — some reasoning models (e.g. MiniMax M2.x) omit content
            # entirely and put the answer in a side-channel field.
            extra = getattr(choice.message, "model_extra", None) or {}
            reasoning = (extra.get("reasoning_content") or extra.get("reasoning") or "").strip()
            extracted = _extract_last_json(reasoning)
            if extracted:
                try:
                    _json.loads(extracted)
                    text = extracted
                except (_json.JSONDecodeError, ValueError):
                    extracted = ""
            if not extracted:
                # Prose: strip any think tags from the reasoning field.
                clean = re.sub(r"<think>.*?</think>", "", reasoning, flags=re.DOTALL).strip()
                clean = re.sub(r"<think>.*$", "", clean, flags=re.DOTALL).strip()
                text = clean or reasoning
            if text:
                logger.debug("OpenAI provider: content=null — extracted from side-channel")
        else:
            text = original_content
        return CompletionResponse(text=text,
                                  input_tokens=resp.usage.prompt_tokens,
                                  output_tokens=resp.usage.completion_tokens)

    async def complete_stream(
        self, messages: list[Message], system: Optional[str] = None,
        temperature: float = 0.0, max_tokens: int = 4096
    ) -> AsyncGenerator[str, None]:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend({"role": m.role, "content": self._to_openai_content(m.content)}
                    for m in messages)
        buf = ""
        in_think = False
        _think_chars = 0
        _answer_chars = 0
        _use_fallback = False   # True when reasoning model detected
        _fallback_task = None   # asyncio.Task running complete() in parallel
        logger.info("complete_stream: max_tokens=%d model=%s", max_tokens, self._config.model)
        async for chunk in await self._client.chat.completions.create(
            model=self._config.model, messages=msgs,
            temperature=temperature, max_tokens=max_tokens,
            timeout=self._timeout, stream=True,
            **({"extra_body": self._extra_body} if self._extra_body else {}),
        ):
            if chunk.choices and chunk.choices[0].finish_reason == "length":
                logger.warning(
                    "complete_stream: response truncated by token limit "
                    "(finish_reason=length, max_tokens=%d, model=%s). "
                    "think_chars=%d answer_chars=%d. "
                    "Increase scaffold_max_tokens (ingest) or query_max_tokens (queries) "
                    "in [agents] of config.toml.",
                    max_tokens, self._config.model, _think_chars, _answer_chars,
                )
            if not (chunk.choices and chunk.choices[0].delta.content):
                continue
            delta = chunk.choices[0].delta.content
            if in_think:
                _think_chars += len(delta)
            else:
                _answer_chars += len(delta)

            buf += delta
            # Suppress the initial <think>...</think> CoT preamble.
            # Tags may arrive split across tokens, so we scan a rolling buffer.
            # For reasoning models (MiniMax M2.5, DeepSeek R1, etc.) we launch a
            # parallel non-streaming complete() call as soon as the opening <think>
            # tag is detected.  By the time </think> arrives the non-streaming call
            # is often already done — zero extra latency on the happy path.
            while True:
                if in_think:
                    idx = buf.find("</think>")
                    if idx == -1:
                        buf = buf[max(0, len(buf) - 7):]  # keep partial "</think>"
                        break
                    else:
                        buf = ""   # discard: answer comes from complete() fallback
                        in_think = False
                        _use_fallback = True
                        break
                else:
                    open_idx = buf.find("<think>")
                    if open_idx == -1:
                        # No think block yet — stream normally, hold back 6 chars to
                        # guard against a partial "<think>" tag spanning two deltas.
                        safe = max(0, len(buf) - 6)
                        if safe:
                            yield buf[:safe]
                            buf = buf[safe:]
                        break
                    else:
                        if open_idx > 0:
                            yield buf[:open_idx]
                        buf = buf[open_idx + 7:]  # strip "<think>"
                        in_think = True
                        if _fallback_task is None:
                            # Reasoning model detected: start complete() now, in parallel,
                            # so both calls run concurrently while we suppress the think block.
                            _fallback_task = asyncio.create_task(
                                self.complete(messages, system, temperature, max_tokens)
                            )

            if _use_fallback:
                break  # abort streaming — complete() will provide the full answer

        if _use_fallback and _fallback_task is not None:
            logger.info(
                "complete_stream: reasoning model — awaiting parallel complete() "
                "(think_chars=%d, model=%s)",
                _think_chars, self._config.model,
            )
            try:
                resp = await _fallback_task
                if resp.text:
                    logger.info(
                        "complete_stream: fallback done (answer_len=%d, model=%s)",
                        len(resp.text), self._config.model,
                    )
                    yield resp.text
            except Exception as exc:
                logger.warning(
                    "complete_stream: fallback complete() failed (%s: %s)",
                    type(exc).__name__, exc,
                )
            return

        if in_think:
            logger.warning(
                "complete_stream: stream ended inside <think> block — think block was never closed "
                "(think_chars=%d, answer_chars=%d, max_tokens=%d, model=%s). "
                "The model exhausted its token budget during reasoning. "
                "Increase query_max_tokens in [agents] of config.toml.",
                _think_chars, _answer_chars, max_tokens, self._config.model,
            )
        else:
            logger.info(
                "complete_stream: done (think_chars=%d, answer_chars=%d, max_tokens=%d, model=%s)",
                _think_chars, _answer_chars, max_tokens, self._config.model,
            )
        if buf and not in_think:
            yield buf
