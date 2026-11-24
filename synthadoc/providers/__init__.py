# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations
import os
from synthadoc.config import Config, AgentConfig, Provider
from synthadoc.providers.base import LLMProvider
from synthadoc import errors as E


def _require_env(var: str, provider: str, url: str, config_path=None) -> str:
    value = os.environ.get(var, "").strip()
    if not value:
        raise E.MissingApiKeyError(var, provider, url, config_path=config_path)
    return value


def describe_provider(provider: object) -> str:
    """Return "provider/model" for the provider object that actually runs.

    Read from the provider itself rather than the config, so a log line can
    never name a role that is not the one doing the work.
    """
    cfg = getattr(provider, "_config", None)
    name, model = getattr(cfg, "provider", None), getattr(cfg, "model", None)
    if name and model:
        return f"{name}/{model}"
    # CLI-delegation providers keep only the model; the class names the tool.
    tool = getattr(provider, "_tool_binary", None) or type(provider).__name__
    return f"{tool}/{getattr(provider, '_model', None) or 'default'}"


def _make_ollama_provider(agent_cfg: AgentConfig, timeout: int) -> LLMProvider:
    """Build an OllamaProvider, forwarding base_url/max_num_ctx only when set
    so OllamaProvider's own defaults apply otherwise (base_url=localhost,
    max_num_ctx=65536)."""
    from synthadoc.providers.ollama import OllamaProvider
    kwargs: dict = {"config": agent_cfg, "timeout": timeout}
    if agent_cfg.base_url:
        kwargs["base_url"] = agent_cfg.base_url
    if agent_cfg.max_num_ctx > 0:
        kwargs["max_num_ctx"] = agent_cfg.max_num_ctx
    return OllamaProvider(**kwargs)


def make_provider(agent_name: str, config: Config, min_timeout: int | None = None) -> LLMProvider:
    """*min_timeout* raises the provider's own HTTP client timeout floor.

    A caller that also enforces its own outer deadline (e.g. the CLI's
    --timeout, via asyncio.timeout_at around the whole query) must pass that
    deadline here too — otherwise a provider's inner HTTP client can time out
    first with a raw exception (httpx.ReadTimeout) instead of letting the
    outer mechanism produce the clean "Query timed out after Ns" message.
    Only ever raises the timeout, never lowers it below llm_timeout_seconds
    or the provider's own default.
    """
    agent_cfg = config.agents.resolve(agent_name)
    timeout = config.agents.llm_timeout_seconds
    if min_timeout is not None and min_timeout > timeout:
        timeout = min_timeout
    cfg_path = config.config_path
    name = agent_cfg.provider
    if name == Provider.ANTHROPIC:
        from synthadoc.providers.anthropic import AnthropicProvider
        key = _require_env("ANTHROPIC_API_KEY", "Anthropic", "https://console.anthropic.com/",
                           config_path=cfg_path)
        return AnthropicProvider(api_key=key, config=agent_cfg, timeout=timeout)
    if name == Provider.OPENAI:
        from synthadoc.providers.openai import OpenAIProvider
        key = _require_env("OPENAI_API_KEY", "OpenAI", "https://platform.openai.com/api-keys",
                           config_path=cfg_path)
        return OpenAIProvider(api_key=key, config=agent_cfg, timeout=timeout)
    if name == Provider.GEMINI:
        from synthadoc.providers.openai import OpenAIProvider
        key = _require_env("GEMINI_API_KEY", "Google Gemini",
                           "https://aistudio.google.com/app/apikey", config_path=cfg_path)
        cfg_with_url = AgentConfig(
            provider=Provider.GEMINI, model=agent_cfg.model,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            thinking=agent_cfg.thinking,
        )
        return OpenAIProvider(api_key=key, config=cfg_with_url, timeout=timeout)
    if name == Provider.GROQ:
        from synthadoc.providers.openai import OpenAIProvider
        key = _require_env("GROQ_API_KEY", "Groq", "https://console.groq.com/keys",
                           config_path=cfg_path)
        cfg_with_url = AgentConfig(
            provider=Provider.GROQ, model=agent_cfg.model,
            base_url="https://api.groq.com/openai/v1",
            thinking=agent_cfg.thinking,
        )
        return OpenAIProvider(api_key=key, config=cfg_with_url, timeout=timeout)
    if name == Provider.MINIMAX:
        from synthadoc.providers.openai import OpenAIProvider
        key = _require_env("MINIMAX_API_KEY", "MiniMax", "https://platform.minimax.io/",
                           config_path=cfg_path)
        cfg_with_url = AgentConfig(
            provider=Provider.MINIMAX, model=agent_cfg.model,
            base_url="https://api.minimax.io/v1",
            thinking=agent_cfg.thinking,
        )
        return OpenAIProvider(api_key=key, config=cfg_with_url, timeout=timeout)
    if name == Provider.DEEPSEEK:
        from synthadoc.providers.openai import OpenAIProvider
        key = _require_env("DEEPSEEK_API_KEY", "DeepSeek", "https://platform.deepseek.com/api_keys",
                           config_path=cfg_path)
        cfg_with_url = AgentConfig(
            provider=Provider.DEEPSEEK, model=agent_cfg.model,
            base_url="https://api.deepseek.com/v1",
            thinking=agent_cfg.thinking,
        )
        return OpenAIProvider(api_key=key, config=cfg_with_url, timeout=timeout)
    if name == Provider.KIMI:
        from synthadoc.providers.openai import OpenAIProvider
        # Kimi models are hosted on DashScope (Ali's QwenCloud).
        # Accept KIMI_API_KEY or fall back to QWEN_API_KEY / DASHSCOPE_API_KEY
        # since they share the same DashScope account.
        key = (
            os.environ.get("KIMI_API_KEY", "").strip()
            or os.environ.get("QWEN_API_KEY", "").strip()
            or os.environ.get("DASHSCOPE_API_KEY", "").strip()
        )
        if not key:
            raise E.MissingApiKeyError(
                "KIMI_API_KEY (or QWEN_API_KEY)", "Kimi (DashScope)",
                "https://bailian.console.aliyun.com/", config_path=cfg_path,
            )
        _default_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        base_url = os.environ.get("KIMI_BASE_URL", "").strip() or _default_url
        cfg_with_url = AgentConfig(
            provider=Provider.KIMI, model=agent_cfg.model,
            base_url=base_url,
            thinking=agent_cfg.thinking,
        )
        return OpenAIProvider(api_key=key, config=cfg_with_url, timeout=timeout)
    if name == Provider.QWEN:
        import re as _re
        # DashScope model names: qwen-plus, qwen3.8-flash, qwq-32b,
        #                        qwen2.5-72b-instruct, qwen-72b-chat …
        # Ollama model names:    qwen3.5, qwen3:8b, qwen2.5:72b …
        # Rule: DashScope names always have a hyphen-separated suffix (letter-
        # or digit-led — size suffixes like "72b" start with a digit);
        # Ollama names use a colon (qwen3:8b) or no hyphen (qwen3.5).
        # kimi-* models use provider = "kimi" — they are not routed here.
        _is_dashscope = bool(_re.match(r'^(qwen[\d.]*-[a-z0-9]|qwq-)', agent_cfg.model or ""))
        # Accept DASHSCOPE_API_KEY as an alias so workspace-specific Bailian
        # endpoints (which use that name in their sample code) work without renaming.
        key = (
            os.environ.get("QWEN_API_KEY", "").strip()
            or os.environ.get("DASHSCOPE_API_KEY", "").strip()
        )
        # QWEN_BASE_URL lets users point at a workspace-specific MaaS endpoint,
        # e.g. https://ws-<id>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
        # (used by Bailian free-tier and dedicated-endpoint deployments).
        _default_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        base_url = os.environ.get("QWEN_BASE_URL", "").strip() or _default_url
        if _is_dashscope and key:
            from synthadoc.providers.openai import OpenAIProvider
            cfg_with_url = AgentConfig(
                provider=Provider.QWEN, model=agent_cfg.model,
                base_url=base_url,
                thinking=agent_cfg.thinking,
            )
            return OpenAIProvider(api_key=key, config=cfg_with_url, timeout=timeout)
        elif _is_dashscope and not key:
            raise E.MissingApiKeyError(
                "QWEN_API_KEY (or DASHSCOPE_API_KEY)", "Qwen (DashScope)",
                "https://bailian.console.aliyun.com/", config_path=cfg_path,
            )
        else:
            return _make_ollama_provider(agent_cfg, timeout)
    if name == Provider.OLLAMA:
        return _make_ollama_provider(agent_cfg, timeout)
    if name == Provider.CLAUDE_CODE:
        from synthadoc.providers.coding_tool import ClaudeCodeCLIProvider
        return ClaudeCodeCLIProvider(
            model=agent_cfg.model or None,
            timeout=timeout,
        )
    if name == Provider.OPENCODE:
        from synthadoc.providers.coding_tool import OpencodeProvider
        return OpencodeProvider(
            model=agent_cfg.model or None,
            timeout=timeout,
        )
    E.cli_error(E.CFG_UNKNOWN_PROVIDER, f"Unknown provider: {name!r}",
                f"Supported providers: {', '.join(sorted(Provider))}")
