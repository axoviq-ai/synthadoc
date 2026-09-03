# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import asyncio
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


def _make_mock_proc(stdout: bytes, stderr: bytes, returncode: int):
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.kill = MagicMock()
    return proc


@pytest.mark.asyncio
async def test_base_raises_environment_error_when_binary_missing():
    """Binary not in PATH → EnvironmentError at construction.

    Patches _find_binary (not shutil.which) so all three search strategies
    (shutil.which, augmented PATH, login-shell fallback) are bypassed — the
    test is valid even when the 'claude' binary is installed on the machine.
    """
    from synthadoc.providers.coding_tool import ClaudeCodeCLIProvider
    with patch("synthadoc.providers.coding_tool._find_binary", return_value=None):
        with pytest.raises(EnvironmentError, match="claude"):
            ClaudeCodeCLIProvider(model=None, timeout=30)


@pytest.mark.asyncio
async def test_base_raises_timeout_error():
    """asyncio.TimeoutError from communicate → TimeoutError."""
    with patch("shutil.which", return_value="/usr/bin/claude"):
        from synthadoc.providers.coding_tool import ClaudeCodeCLIProvider
        provider = ClaudeCodeCLIProvider(model=None, timeout=1)

    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_proc.kill = MagicMock()

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        from synthadoc.providers.base import Message
        with pytest.raises(TimeoutError, match="timed out"):
            await provider.complete([Message(role="user", content="hello")])


@pytest.mark.asyncio
async def test_base_raises_runtime_error_on_nonzero_exit():
    """Non-zero exit code → RuntimeError with stderr."""
    with patch("shutil.which", return_value="/usr/bin/claude"):
        from synthadoc.providers.coding_tool import ClaudeCodeCLIProvider
        provider = ClaudeCodeCLIProvider(model=None, timeout=30)

    mock_proc = _make_mock_proc(b"", b"something went wrong", returncode=1)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        from synthadoc.providers.base import Message
        with pytest.raises(RuntimeError, match="something went wrong"):
            await provider.complete([Message(role="user", content="hello")])


@pytest.mark.asyncio
async def test_base_raises_quota_exhausted():
    """Quota exhaustion pattern in stderr → CodingToolQuotaExhaustedException."""
    with patch("shutil.which", return_value="/usr/bin/claude"):
        from synthadoc.providers.coding_tool import ClaudeCodeCLIProvider
        provider = ClaudeCodeCLIProvider(model=None, timeout=30)

    mock_proc = _make_mock_proc(b"", b"Claude AI usage limit reached", returncode=1)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        from synthadoc.providers.base import Message
        from synthadoc.errors import CodingToolQuotaExhaustedException
        with pytest.raises(CodingToolQuotaExhaustedException):
            await provider.complete([Message(role="user", content="hello")])


# ── ClaudeCodeCLIProvider ─────────────────────────────────────────────────────

def _make_claude_provider():
    with patch("shutil.which", return_value="/usr/bin/claude"):
        from synthadoc.providers.coding_tool import ClaudeCodeCLIProvider
        return ClaudeCodeCLIProvider(model=None, timeout=30)


def test_claude_parse_output_valid():
    """Valid JSON output → correct CompletionResponse."""
    import json
    provider = _make_claude_provider()
    raw = json.dumps({
        "result": "The answer is 42.",
        "total_input_tokens": 100,
        "total_output_tokens": 50,
        "is_error": False,
    })
    resp = provider._parse_output(raw)
    assert resp.text == "The answer is 42."
    assert resp.input_tokens == 100
    assert resp.output_tokens == 50


def test_claude_parse_output_is_error_raises():
    """is_error: true in JSON → RuntimeError."""
    import json
    provider = _make_claude_provider()
    raw = json.dumps({"is_error": True, "result": "context length exceeded"})
    with pytest.raises(RuntimeError, match="context length exceeded"):
        provider._parse_output(raw)


def test_claude_parse_output_missing_result_raises():
    """JSON with no result field → ValueError."""
    import json
    provider = _make_claude_provider()
    raw = json.dumps({"is_error": False})
    with pytest.raises(ValueError, match="empty result"):
        provider._parse_output(raw)


def test_claude_parse_output_bad_json_raises():
    """Non-JSON stdout → ValueError."""
    provider = _make_claude_provider()
    with pytest.raises(ValueError, match="malformed JSON"):
        provider._parse_output("not json at all")


def test_claude_is_quota_exhausted_true():
    provider = _make_claude_provider()
    assert provider._is_quota_exhausted("Claude AI usage limit reached") is True
    assert provider._is_quota_exhausted("You've reached your usage cap") is True
    assert provider._is_quota_exhausted("You've hit your session limit · resets 2:30pm") is True


def test_claude_is_quota_exhausted_false():
    provider = _make_claude_provider()
    assert provider._is_quota_exhausted("some other error") is False


@pytest.mark.asyncio
async def test_coding_tool_complete_stream_yields_words():
    """complete_stream() shim delegates to complete() and yields word-by-word."""
    import json
    from synthadoc.providers.base import Message
    provider = _make_claude_provider()
    raw = json.dumps({
        "result": "Hello world answer",
        "total_input_tokens": 10,
        "total_output_tokens": 5,
        "is_error": False,
    })
    mock_proc = _make_mock_proc(raw.encode(), b"", returncode=0)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        tokens = []
        async for tok in provider.complete_stream([Message(role="user", content="hi")]):
            tokens.append(tok)
    assert "".join(tokens) == "Hello world answer"
    assert len(tokens) == 3  # three words


def test_claude_build_command_no_model():
    provider = _make_claude_provider()
    cmd = provider._build_command(provider._resolved_binary)
    assert cmd[0] == provider._resolved_binary
    assert "-p" in cmd
    assert "--output-format" in cmd
    assert "--dangerously-skip-permissions" in cmd

def test_claude_build_command_with_model():
    with patch("shutil.which", return_value="/usr/bin/claude"):
        from synthadoc.providers.coding_tool import ClaudeCodeCLIProvider
        provider = ClaudeCodeCLIProvider(model="claude-sonnet-4-5", timeout=30)
    cmd = provider._build_command(provider._resolved_binary)
    assert "--model" in cmd
    assert "claude-sonnet-4-5" in cmd


def test_claude_build_system_args_with_system():
    """System prompt present → --system-prompt flag with value."""
    provider = _make_claude_provider()
    args = provider._build_system_args("You are a wiki agent.")
    assert "--system-prompt" in args
    idx = args.index("--system-prompt")
    assert args[idx + 1] == "You are a wiki agent."
    assert "--no-system-prompt" not in args


def test_claude_build_system_args_no_system():
    """No system prompt → no extra flags (--no-system-prompt not universally supported)."""
    provider = _make_claude_provider()
    args = provider._build_system_args(None)
    assert args == []
    assert "--no-system-prompt" not in args
    assert "--system-prompt" not in args


def test_claude_build_prompt_excludes_system():
    """_build_prompt must not embed system in stdin for ClaudeCodeCLIProvider."""
    from synthadoc.providers.base import Message
    provider = _make_claude_provider()
    prompt = provider._build_prompt(
        [Message(role="user", content="Find stale pages")],
        system="You are a maintenance agent.",
    )
    assert "You are a maintenance agent." not in prompt
    assert "Find stale pages" in prompt


def test_claude_build_prompt_no_system():
    """_build_prompt with system=None returns only user content."""
    from synthadoc.providers.base import Message
    provider = _make_claude_provider()
    prompt = provider._build_prompt(
        [Message(role="user", content="List orphans")],
        system=None,
    )
    assert "List orphans" in prompt


@pytest.mark.asyncio
async def test_claude_complete_passes_system_via_flag():
    """complete() with a system prompt must pass --system-prompt to the subprocess,
    not embed the system text in stdin."""
    import json
    from synthadoc.providers.base import Message
    provider = _make_claude_provider()
    raw = json.dumps({
        "result": "tool call response",
        "total_input_tokens": 20,
        "total_output_tokens": 10,
        "is_error": False,
    })
    mock_proc = _make_mock_proc(raw.encode(), b"", returncode=0)
    captured_cmd: list = []
    captured_stdin: list = []

    async def fake_exec(*args, **kwargs):
        captured_cmd.extend(args)
        return mock_proc

    mock_proc.communicate = AsyncMock(
        side_effect=lambda input=None: (
            captured_stdin.append(input) or (raw.encode(), b"")
        )
    )

    with patch("asyncio.create_subprocess_exec", fake_exec):
        await provider.complete(
            [Message(role="user", content="run workflow")],
            system="You are a JSON tool-call agent.",
        )

    # --system-prompt must be in the command argv, not in the stdin blob
    cmd_str = " ".join(str(a) for a in captured_cmd)
    assert "--system-prompt" in cmd_str
    assert "You are a JSON tool-call agent." not in (captured_stdin[0] or b"").decode()
    assert "run workflow" in (captured_stdin[0] or b"").decode()


# ── OpencodeProvider ──────────────────────────────────────────────────────────

def _make_opencode_provider():
    with patch("shutil.which", return_value="/usr/bin/opencode"):
        from synthadoc.providers.coding_tool import OpencodeProvider
        return OpencodeProvider(model=None, timeout=30)


def test_opencode_parse_output_valid():
    """Valid JSONL with text + step_finish → correct CompletionResponse."""
    import json
    provider = _make_opencode_provider()
    lines = [
        json.dumps({"type": "step_start"}),
        json.dumps({"type": "text", "data": "The answer "}),
        json.dumps({"type": "text", "data": "is 42."}),
        json.dumps({"type": "step_finish", "reason": "stop",
                    "tokens": {"input": 80, "output": 40}}),
    ]
    resp = provider._parse_output("\n".join(lines))
    assert resp.text == "The answer is 42."
    assert resp.input_tokens == 80
    assert resp.output_tokens == 40


def test_opencode_parse_output_no_text_events_raises():
    """JSONL with zero text events → ValueError."""
    import json
    provider = _make_opencode_provider()
    lines = [
        json.dumps({"type": "step_start"}),
        json.dumps({"type": "step_finish", "reason": "stop", "tokens": {}}),
    ]
    with pytest.raises(ValueError, match="no text content"):
        provider._parse_output("\n".join(lines))


def test_opencode_error_event_fatal_when_no_text():
    """error event with no prior text → RuntimeError."""
    import json
    provider = _make_opencode_provider()
    lines = [
        json.dumps({"type": "error", "error": {"name": "invalid api key"}}),
    ]
    with pytest.raises(RuntimeError, match="invalid api key"):
        provider._parse_output("\n".join(lines))


def test_opencode_error_event_nonfatal_when_text_collected():
    """error event after text has been collected → warning logged, text returned."""
    import json
    provider = _make_opencode_provider()
    lines = [
        json.dumps({"type": "text", "data": "The answer is 42."}),
        json.dumps({"type": "error", "error": {"name": "tool call failed"}}),
    ]
    resp = provider._parse_output("\n".join(lines))
    assert resp.text == "The answer is 42."


def test_opencode_parse_output_step_finish_error_raises():
    """step_finish with reason=error → RuntimeError."""
    import json
    provider = _make_opencode_provider()
    lines = [
        json.dumps({"type": "text", "data": "partial"}),
        json.dumps({"type": "step_finish", "reason": "error"}),
    ]
    with pytest.raises(RuntimeError, match="error"):
        provider._parse_output("\n".join(lines))


def test_opencode_parse_output_truncated_jsonl_raises():
    """Truncated JSONL (no step_finish, no text) → ValueError."""
    provider = _make_opencode_provider()
    with pytest.raises(ValueError, match="no text content"):
        provider._parse_output('{"type": "step_start"}\n{"type": "ste')


def test_opencode_is_quota_exhausted_true():
    provider = _make_opencode_provider()
    assert provider._is_quota_exhausted("Usage limit exceeded for your plan") is True
    assert provider._is_quota_exhausted("quota exceeded") is True


def test_opencode_is_quota_exhausted_false():
    provider = _make_opencode_provider()
    assert provider._is_quota_exhausted("some other error") is False


def test_opencode_build_command_no_model():
    provider = _make_opencode_provider()
    cmd = provider._build_command(provider._resolved_binary)
    assert cmd[0] == provider._resolved_binary
    assert "run" in cmd
    assert "--format" in cmd

def test_opencode_build_command_with_model():
    with patch("shutil.which", return_value="/usr/bin/opencode"):
        from synthadoc.providers.coding_tool import OpencodeProvider
        provider = OpencodeProvider(model="anthropic/claude-sonnet-4-5", timeout=30)
    cmd = provider._build_command(provider._resolved_binary)
    assert "--model" in cmd
    assert "anthropic/claude-sonnet-4-5" in cmd


# ── Factory + config ──────────────────────────────────────────────────────────

def test_make_provider_claude_code():
    """make_provider returns ClaudeCodeCLIProvider for provider='claude-code'."""
    from synthadoc.config import Config, AgentConfig, AgentsConfig
    cfg = Config(agents=AgentsConfig(
        default=AgentConfig(provider="claude-code", model="")
    ))
    with patch("shutil.which", return_value="/usr/bin/claude"):
        from synthadoc.providers import make_provider
        provider = make_provider("ingest", cfg)
    from synthadoc.providers.coding_tool import ClaudeCodeCLIProvider
    assert isinstance(provider, ClaudeCodeCLIProvider)


def test_make_provider_opencode():
    """make_provider returns OpencodeProvider for provider='opencode'."""
    from synthadoc.config import Config, AgentConfig, AgentsConfig
    cfg = Config(agents=AgentsConfig(
        default=AgentConfig(provider="opencode", model="")
    ))
    with patch("shutil.which", return_value="/usr/bin/opencode"):
        from synthadoc.providers import make_provider
        provider = make_provider("ingest", cfg)
    from synthadoc.providers.coding_tool import OpencodeProvider
    assert isinstance(provider, OpencodeProvider)


def test_config_accepts_claude_code_provider():
    """KNOWN_PROVIDERS includes claude-code and opencode."""
    from synthadoc.config import KNOWN_PROVIDERS
    assert "claude-code" in KNOWN_PROVIDERS
    assert "opencode" in KNOWN_PROVIDERS


# ── Performance benchmarks ────────────────────────────────────────────────────

import time
import json as _json_mod


def test_claude_parse_output_benchmark():
    """_parse_output on a 2000-token response completes in < 50ms."""
    provider = _make_claude_provider()
    big_text = "word " * 1600
    raw = _json_mod.dumps({
        "result": big_text,
        "total_input_tokens": 1000,
        "total_output_tokens": 2000,
        "is_error": False,
    })
    start = time.perf_counter()
    resp = provider._parse_output(raw)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert resp.text == big_text
    assert elapsed_ms < 50, f"_parse_output took {elapsed_ms:.1f}ms (limit: 50ms)"


def test_opencode_parse_output_benchmark():
    """_parse_output on 2000-token JSONL response completes in < 50ms."""
    provider = _make_opencode_provider()
    lines = [
        _json_mod.dumps({"type": "text", "data": "word " * 400})
        for _ in range(4)
    ]
    lines.append(_json_mod.dumps({
        "type": "step_finish", "reason": "stop",
        "tokens": {"input": 1000, "output": 2000},
    }))
    raw = "\n".join(lines)
    start = time.perf_counter()
    resp = provider._parse_output(raw)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert len(resp.text) > 0
    assert elapsed_ms < 50, f"_parse_output took {elapsed_ms:.1f}ms (limit: 50ms)"


# ── OpencodeProvider: new event layouts (post-refactor) ───────────────────────

def test_opencode_parse_output_content_block_delta():
    """Layout E: content_block_delta events with nested delta.text."""
    import json
    provider = _make_opencode_provider()
    lines = [
        json.dumps({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello "}}),
        json.dumps({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "world"}}),
        json.dumps({"type": "step_finish", "reason": "stop",
                    "tokens": {"input": 10, "output": 5}}),
    ]
    resp = provider._parse_output("\n".join(lines))
    assert resp.text == "Hello world"
    assert resp.input_tokens == 10


def test_opencode_parse_output_text_delta_event():
    """Layout E: top-level text_delta event type."""
    import json
    provider = _make_opencode_provider()
    lines = [
        json.dumps({"type": "text_delta", "text": "Foo bar"}),
        json.dumps({"type": "step_finish", "reason": "stop",
                    "tokens": {"input": 5, "output": 3}}),
    ]
    resp = provider._parse_output("\n".join(lines))
    assert resp.text == "Foo bar"


def test_opencode_parse_output_message_event_string_content():
    """Layout F: message event with content as a string."""
    import json
    provider = _make_opencode_provider()
    lines = [
        json.dumps({"type": "message", "role": "assistant",
                    "message": {"role": "assistant", "content": "Baz"}}),
        json.dumps({"type": "step_finish", "reason": "stop",
                    "tokens": {"input": 1, "output": 1}}),
    ]
    resp = provider._parse_output("\n".join(lines))
    assert resp.text == "Baz"


def test_opencode_parse_output_catch_all_part_type_text():
    """Layout G (catch-all): unknown outer event type with part.type=='text'."""
    import json
    provider = _make_opencode_provider()
    lines = [
        json.dumps({"type": "future_event_x", "part": {"type": "text", "text": "Catch-all text"}}),
        json.dumps({"type": "step_finish", "reason": "stop",
                    "tokens": {"input": 5, "output": 5}}),
    ]
    resp = provider._parse_output("\n".join(lines))
    assert resp.text == "Catch-all text"


def test_opencode_parse_output_step_finish_tokens_in_part():
    """Tokens inside step_finish.part sub-object are extracted correctly."""
    import json
    provider = _make_opencode_provider()
    lines = [
        json.dumps({"type": "text", "data": "Hi"}),
        json.dumps({"type": "step_finish", "reason": "stop",
                    "part": {"type": "step-finish", "reason": "stop",
                              "tokens": {"input": 42, "output": 17}}}),
    ]
    resp = provider._parse_output("\n".join(lines))
    assert resp.text == "Hi"
    assert resp.input_tokens == 42
    assert resp.output_tokens == 17


def test_opencode_parse_output_session_id_in_error_message():
    """session_id from events is included in the ValueError message."""
    import json
    provider = _make_opencode_provider()
    lines = [
        json.dumps({"type": "step_start", "sessionID": "ses_abc123",
                    "part": {"type": "step-start"}}),
        json.dumps({"type": "step_finish", "sessionID": "ses_abc123", "reason": "stop",
                    "tokens": {"input": 10, "output": 5}}),
    ]
    with pytest.raises(ValueError, match="ses_abc123"):
        provider._parse_output("\n".join(lines))


# ── OpencodeProvider: auto-retry on silent output ─────────────────────────────

@pytest.mark.asyncio
async def test_opencode_complete_retries_on_no_text_content():
    """complete() retries once when _parse_output raises 'no text content'."""
    import json
    provider = _make_opencode_provider()

    # First call: only step events (no text) → triggers retry.
    silent_output = "\n".join([
        json.dumps({"type": "step_start", "sessionID": "ses_x"}),
        json.dumps({"type": "step_finish", "reason": "stop",
                    "tokens": {"input": 10, "output": 50}}),
    ]).encode()

    # Second call: text present → succeeds.
    good_output = "\n".join([
        json.dumps({"type": "text", "data": "Retry succeeded"}),
        json.dumps({"type": "step_finish", "reason": "stop",
                    "tokens": {"input": 10, "output": 5}}),
    ]).encode()

    calls = 0

    async def _fake_exec(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _make_mock_proc(
            silent_output if calls == 1 else good_output,
            b"", returncode=0,
        )

    from synthadoc.providers.base import Message
    with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        with patch("asyncio.sleep", new_callable=AsyncMock):  # skip real sleep
            resp = await provider.complete([Message(role="user", content="hi")])

    assert calls == 2, f"Expected 2 subprocess calls, got {calls}"
    assert resp.text == "Retry succeeded"


@pytest.mark.asyncio
async def test_opencode_complete_raises_after_two_silent_failures():
    """complete() raises ValueError after both attempts return no text."""
    import json
    provider = _make_opencode_provider()

    silent_output = "\n".join([
        json.dumps({"type": "step_start", "sessionID": "ses_y"}),
        json.dumps({"type": "step_finish", "reason": "stop",
                    "tokens": {"input": 5, "output": 20}}),
    ]).encode()

    async def _fake_exec(*args, **kwargs):
        return _make_mock_proc(silent_output, b"", returncode=0)

    from synthadoc.providers.base import Message
    with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ValueError, match="no text content"):
                await provider.complete([Message(role="user", content="hi")])


@pytest.mark.asyncio
async def test_opencode_complete_does_not_retry_on_other_errors():
    """complete() does NOT retry when the error is not 'no text content'."""
    provider = _make_opencode_provider()

    calls = 0

    async def _fake_exec(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _make_mock_proc(b"", b"auth failed", returncode=1)

    from synthadoc.providers.base import Message
    with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        with pytest.raises(RuntimeError, match="auth failed"):
            await provider.complete([Message(role="user", content="hi")])

    assert calls == 1, "Should not retry on non-ValueError errors"
