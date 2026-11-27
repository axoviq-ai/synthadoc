# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""The coding-tool providers against a REAL child process, with no real tool installed.

``test_coding_tool_providers.py`` mocks ``Popen`` and ``shutil.which``. These tests run the
real code path instead: the provider finds a stub ``claude`` / ``opencode`` on PATH, spawns
it, feeds the prompt on stdin, and reads its stdout, stderr and exit code. That covers what
the mocks cannot: binary lookup, argv, byte-exact stdin (large and non-ASCII), exit codes,
the timeout kill, the opencode retries and its process-wide lock.

The stub is a Python script behind a one-line launcher (a ``.cmd`` on Windows, ``sh`` on
POSIX), so the Windows ``cmd /c`` branch of the provider is exercised for real. It needs
neither of the real tools, any network or any LLM, so it runs identically on every
developer machine and every CI runner. The real-CLI contract tests stay opt-in in
``test_coding_tool_integration.py``.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from synthadoc.errors import CodingToolPermanentError, CodingToolQuotaExhaustedException
from synthadoc.providers.base import Message
from synthadoc.providers.coding_tool import ClaudeCodeCLIProvider, OpencodeProvider

WINDOWS = sys.platform == "win32"

STUB_SOURCE = textwrap.dedent('''
    import hashlib, json, os, sys, time

    tool = os.environ["STUB_TOOL"]
    state = os.environ["STUB_DIR"]
    mode = os.environ.get("STUB_MODE", "ok")
    data = sys.stdin.buffer.read().decode("utf-8")

    counter = os.path.join(state, "calls")
    n = 1 + (int(open(counter).read()) if os.path.exists(counter) else 0)
    with open(counter, "w") as fh:
        fh.write(str(n))
    with open(os.path.join(state, "last.json"), "w", encoding="utf-8") as fh:
        json.dump({"argv": sys.argv[1:], "stdin": data}, fh)

    def event(tag):
        with open(os.path.join(state, "events.log"), "a") as fh:
            fh.write(tag + "\\n")

    if mode.startswith("once:"):                      # misbehave on the first call only
        mode = mode[5:] if n == 1 else "ok"

    def text_result():
        if mode == "echo":                            # proves the stdin bytes arrived intact
            return "len=%d sha=%s" % (len(data), hashlib.sha256(data.encode("utf-8")).hexdigest())
        return "stub says hi"

    event("start")
    if mode == "hang":
        time.sleep(3)
    if mode == "slow":
        time.sleep(0.3)
    if mode == "exit3":
        sys.stderr.write("boom: something broke")
        sys.exit(3)
    if mode == "quota":
        sys.stderr.write("You have hit your usage limit exceeded for today")
        sys.exit(1)
    if mode == "permanent":
        sys.stderr.write(json.dumps({"isRetryable": False, "statusCode": 400, "message": "bad model"}))
        sys.exit(1)
    if mode == "locked":
        sys.stderr.write("Error: database is locked")
        sys.exit(1)
    if mode == "empty":
        pass
    elif tool == "claude":
        if mode == "bad_json":
            sys.stdout.write("not json {")
        elif mode == "is_error":
            print(json.dumps({"is_error": True, "result": "model overloaded"}))
        else:
            print(json.dumps({"result": text_result(), "total_input_tokens": 11, "total_output_tokens": 7}))
    else:                                              # opencode: JSON lines
        if mode == "silent":
            print(json.dumps({"type": "step_start"}))
        elif mode == "echo":
            print(json.dumps({"type": "text", "part": {"text": text_result()}}))
        else:
            print(json.dumps({"type": "text", "part": {"text": "stub "}}))
            print(json.dumps({"type": "text", "part": {"text": "says hi"}}))
            print(json.dumps({"type": "step_finish", "part": {"tokens": {"input": 5, "output": 3}}}))
    event("end")
''')


class Stub:
    """A stub CLI on PATH plus helpers to read what it saw."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.bin = tmp_path / "bin"
        self.state = tmp_path / "state"
        self.bin.mkdir()
        self.state.mkdir()
        self._script = tmp_path / "stub_cli.py"
        self._script.write_text(STUB_SOURCE, encoding="utf-8")
        self._mp = monkeypatch
        monkeypatch.setenv("PATH", str(self.bin) + os.pathsep + os.environ.get("PATH", ""))
        monkeypatch.setenv("STUB_DIR", str(self.state))

    def install(self, tool: str, mode: str = "ok") -> Path:
        py, script = sys.executable, self._script
        if WINDOWS:
            launcher = self.bin / f"{tool}.cmd"
            launcher.write_text(f'@echo off\r\n"{py}" "{script}" %*\r\nexit /b %ERRORLEVEL%\r\n')
        else:
            launcher = self.bin / tool
            launcher.write_text(f'#!/bin/sh\nexec "{py}" "{script}" "$@"\n')
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self._mp.setenv("STUB_TOOL", tool)
        self.mode(mode)
        return launcher

    def mode(self, mode: str) -> None:
        self._mp.setenv("STUB_MODE", mode)

    @property
    def calls(self) -> int:
        f = self.state / "calls"
        return int(f.read_text()) if f.exists() else 0

    @property
    def last(self) -> dict:
        return json.loads((self.state / "last.json").read_text(encoding="utf-8"))

    @property
    def events(self) -> list[str]:
        f = self.state / "events.log"
        return f.read_text().split() if f.exists() else []


@pytest.fixture
def stub(tmp_path, monkeypatch):
    # The opencode lock is a class attribute; a lock that was contended in another test's
    # event loop must not leak into this one.
    monkeypatch.setattr(OpencodeProvider, "_subprocess_lock", None)
    return Stub(tmp_path, monkeypatch)


@pytest.fixture
def fast_retries(monkeypatch):
    monkeypatch.setattr(OpencodeProvider, "_SILENT_RETRY_DELAY", 0.0)
    monkeypatch.setattr(OpencodeProvider, "_DB_LOCKED_BASE_DELAY", 0.0)
    monkeypatch.setattr(random, "uniform", lambda a, b: 0.0)


def _claude(stub: Stub, mode: str = "ok", **kw) -> ClaudeCodeCLIProvider:
    stub.install("claude", mode)
    return ClaudeCodeCLIProvider(model=kw.pop("model", None), timeout=kw.pop("timeout", 30))


def _opencode(stub: Stub, mode: str = "ok", **kw) -> OpencodeProvider:
    stub.install("opencode", mode)
    return OpencodeProvider(model=kw.pop("model", None), timeout=kw.pop("timeout", 30))


def _msg(text: str) -> list[Message]:
    return [Message(role="user", content=text)]


# ------------------------------------------------------------- finding the binary

def test_provider_finds_the_stub_on_path_and_never_a_real_install(stub):
    launcher = stub.install("claude")
    provider = ClaudeCodeCLIProvider(model=None, timeout=30)
    assert os.path.samefile(provider._resolved_binary, launcher)
    assert provider._cmd_prefix == (["cmd", "/c"] if WINDOWS else [])


# --------------------------------------------------------------------- claude code

async def test_claude_round_trip_parses_text_and_tokens(stub):
    resp = await _claude(stub).complete(_msg("hello"))
    assert resp.text == "stub says hi"
    assert (resp.input_tokens, resp.output_tokens) == (11, 7)
    assert stub.calls == 1


async def test_claude_command_line_and_stdin(stub):
    provider = _claude(stub, model="stub-model")
    await provider.complete(_msg("the user question"), system="Be terse and exact.")
    seen = stub.last
    assert seen["argv"][:4] == ["-p", "--output-format", "json", "--dangerously-skip-permissions"]
    assert seen["argv"][seen["argv"].index("--model") + 1] == "stub-model"
    assert seen["argv"][seen["argv"].index("--system-prompt") + 1] == "Be terse and exact."
    assert seen["stdin"] == "the user question"      # the system prompt is a flag, not stdin


async def test_claude_without_a_system_prompt_adds_no_system_flag(stub):
    await _claude(stub).complete(_msg("q"))
    assert "--system-prompt" not in stub.last["argv"]


@pytest.mark.parametrize("prompt", [
    pytest.param("x" * 300_000, id="300kb"),          # far beyond any argv limit: must go via stdin
    pytest.param("日本語のテキスト and emoji \U0001F600 and accents éàü", id="unicode"),
    pytest.param("line one\r\nline two\n\n\ttabbed", id="crlf-and-tabs"),
])
async def test_claude_prompt_arrives_byte_exact_on_stdin(stub, prompt):
    resp = await _claude(stub, "echo").complete(_msg(prompt))
    assert resp.text == f"len={len(prompt)} sha={hashlib.sha256(prompt.encode('utf-8')).hexdigest()}"


async def test_claude_nonzero_exit_raises_with_the_stderr_detail(stub):
    with pytest.raises(RuntimeError, match="exited with code 3.*boom: something broke"):
        await _claude(stub, "exit3").complete(_msg("q"))


async def test_claude_quota_message_raises_quota_exhausted(stub):
    with pytest.raises(CodingToolQuotaExhaustedException):
        await _claude(stub, "quota").complete(_msg("q"))


async def test_claude_is_error_json_raises(stub):
    with pytest.raises(RuntimeError, match="model overloaded"):
        await _claude(stub, "is_error").complete(_msg("q"))


async def test_claude_malformed_json_raises_value_error(stub):
    with pytest.raises(ValueError, match="malformed JSON"):
        await _claude(stub, "bad_json").complete(_msg("q"))


async def test_claude_empty_output_raises_value_error(stub):
    with pytest.raises(ValueError, match="empty output"):
        await _claude(stub, "empty").complete(_msg("q"))


async def test_claude_permanent_error_is_not_retryable(stub):
    with pytest.raises(CodingToolPermanentError):
        await _claude(stub, "permanent").complete(_msg("q"))


async def test_claude_hung_tool_is_killed_after_the_timeout(stub):
    provider = _claude(stub, "hang", timeout=1)
    with pytest.raises(TimeoutError, match="timed out after 1s"):
        await provider.complete(_msg("q"))


async def test_claude_stream_yields_the_whole_answer_word_by_word(stub):
    chunks = [c async for c in _claude(stub).complete_stream(_msg("q"))]
    assert "".join(chunks) == "stub says hi" and len(chunks) == 3


# ----------------------------------------------------------------------- opencode

async def test_opencode_round_trip_joins_text_events_and_reads_tokens(stub):
    resp = await _opencode(stub, model="stub-model").complete(_msg("hello"))
    assert resp.text == "stub says hi"
    assert (resp.input_tokens, resp.output_tokens) == (5, 3)
    argv = stub.last["argv"]
    assert argv[:3] == ["run", "--format", "json"]
    assert argv[argv.index("--model") + 1] == "stub-model"
    assert stub.last["stdin"] == "hello"


async def test_opencode_prompt_arrives_byte_exact_on_stdin(stub):
    prompt = "x" * 200_000 + " 日本語 \U0001F600"
    resp = await _opencode(stub, "echo").complete(_msg(prompt))
    assert resp.text == f"len={len(prompt)} sha={hashlib.sha256(prompt.encode('utf-8')).hexdigest()}"


async def test_opencode_nonzero_exit_raises(stub):
    with pytest.raises(RuntimeError, match="exited with code 3"):
        await _opencode(stub, "exit3").complete(_msg("q"))


async def test_opencode_quota_message_raises_quota_exhausted(stub):
    with pytest.raises(CodingToolQuotaExhaustedException):
        await _opencode(stub, "quota").complete(_msg("q"))


async def test_opencode_permanent_error_is_not_retryable(stub):
    with pytest.raises(CodingToolPermanentError):
        await _opencode(stub, "permanent").complete(_msg("q"))
    assert stub.calls == 1                             # no retry budget spent


async def test_opencode_silent_output_is_retried_once_then_succeeds(stub, fast_retries):
    resp = await _opencode(stub, "once:silent").complete(_msg("q"))
    assert resp.text == "stub says hi" and stub.calls == 2


async def test_opencode_persistent_silent_output_fails_after_one_retry(stub, fast_retries):
    with pytest.raises(ValueError, match="no text content"):
        await _opencode(stub, "silent").complete(_msg("q"))
    assert stub.calls == 2


async def test_opencode_database_locked_is_retried_then_succeeds(stub, fast_retries):
    resp = await _opencode(stub, "once:locked").complete(_msg("q"))
    assert resp.text == "stub says hi" and stub.calls == 2


async def test_opencode_database_locked_gives_up_after_the_retry_budget(stub, fast_retries):
    with pytest.raises(RuntimeError, match="database is locked"):
        await _opencode(stub, "locked").complete(_msg("q"))
    assert stub.calls == 1 + OpencodeProvider._DB_LOCKED_MAX_RETRIES


async def test_opencode_hung_tool_is_killed_after_the_timeout(stub):
    with pytest.raises(TimeoutError, match="timed out after 1s"):
        await _opencode(stub, "hang", timeout=1).complete(_msg("q"))


async def test_opencode_serialises_concurrent_calls(stub):
    """Two concurrent jobs must never run two opencode processes at once (its SQLite session
    database races otherwise). The stub logs start and end; the log must strictly alternate."""
    provider = _opencode(stub, "slow")
    await asyncio.gather(provider.complete(_msg("a")), provider.complete(_msg("b")))
    assert stub.events == ["start", "end", "start", "end"]
