# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import json
import pytest
from pathlib import Path


def _load_skill():
    from synthadoc.agents.skill_agent import SkillAgent
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    (tmp / "wiki").mkdir()
    agent = SkillAgent(wiki_root=tmp)
    return agent.get_skill("session")


def _cc_user(text: str, is_sidechain: bool = False) -> str:
    """Build a Claude Code user line."""
    return json.dumps({
        "type": "user",
        "isSidechain": is_sidechain,
        "message": {"role": "user", "content": text},
    })


def _cc_assistant(blocks: list[dict] | str, is_sidechain: bool = False) -> str:
    """Build a Claude Code assistant line."""
    return json.dumps({
        "type": "assistant",
        "isSidechain": is_sidechain,
        "message": {"role": "assistant", "content": blocks},
    })


def _cc_text_block(text: str) -> dict:
    return {"type": "text", "text": text}


def _cc_tool_use_block() -> dict:
    return {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}}


def _cc_tool_result_block() -> dict:
    return {"type": "tool_result", "tool_use_id": "t1", "content": "file1.py\nfile2.py"}


def _cc_thinking_block() -> dict:
    return {"type": "thinking", "thinking": "I need to think about this…"}


def _codex_line(role: str, content: str) -> str:
    return json.dumps({"role": role, "content": content})


def _write_jsonl(tmp_path: Path, lines: list[str], name: str = "session.jsonl") -> Path:
    p = tmp_path / name
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


# ── Format detection ──────────────────────────────────────────────────────────

def test_detect_format_claude_code():
    from synthadoc.skills.session.scripts.main import _detect_format
    lines = [
        _cc_user("hello"),
        _cc_assistant([_cc_text_block("hi there from the assistant response")]),
    ]
    assert _detect_format(lines) == "claude_code"


def test_detect_format_codex():
    from synthadoc.skills.session.scripts.main import _detect_format
    lines = [
        _codex_line("user", "hello world"),
        _codex_line("assistant", "hi"),
    ]
    assert _detect_format(lines) == "codex"


def test_detect_format_unknown_for_garbage():
    from synthadoc.skills.session.scripts.main import _detect_format
    assert _detect_format(["not json at all", "{broken"]) == "unknown"


def test_detect_format_unknown_for_empty():
    from synthadoc.skills.session.scripts.main import _detect_format
    assert _detect_format([]) == "unknown"


def test_detect_format_skips_blank_lines():
    from synthadoc.skills.session.scripts.main import _detect_format
    lines = ["", "  ", _cc_user("hello"), _cc_assistant("reply text here for testing")]
    assert _detect_format(lines) == "claude_code"


# ── Text content extraction ───────────────────────────────────────────────────

def test_extract_text_string_content():
    from synthadoc.skills.session.scripts.main import _extract_text_content
    assert _extract_text_content("hello world") == "hello world"


def test_extract_text_strips_whitespace():
    from synthadoc.skills.session.scripts.main import _extract_text_content
    assert _extract_text_content("  hello  ") == "hello"


def test_extract_text_list_with_text_block():
    from synthadoc.skills.session.scripts.main import _extract_text_content
    blocks = [_cc_text_block("first part"), _cc_text_block("second part")]
    result = _extract_text_content(blocks)
    assert "first part" in result
    assert "second part" in result


def test_extract_text_skips_tool_use():
    from synthadoc.skills.session.scripts.main import _extract_text_content
    blocks = [_cc_text_block("visible"), _cc_tool_use_block()]
    result = _extract_text_content(blocks)
    assert "visible" in result
    assert "Bash" not in result
    assert "ls" not in result


def test_extract_text_skips_tool_result():
    from synthadoc.skills.session.scripts.main import _extract_text_content
    blocks = [_cc_text_block("answer"), _cc_tool_result_block()]
    result = _extract_text_content(blocks)
    assert "answer" in result
    assert "file1.py" not in result


def test_extract_text_skips_thinking():
    from synthadoc.skills.session.scripts.main import _extract_text_content
    blocks = [_cc_thinking_block(), _cc_text_block("final response")]
    result = _extract_text_content(blocks)
    assert "final response" in result
    assert "think" not in result.lower()


def test_extract_text_empty_list():
    from synthadoc.skills.session.scripts.main import _extract_text_content
    assert _extract_text_content([]) == ""


def test_extract_text_all_skipped_blocks():
    from synthadoc.skills.session.scripts.main import _extract_text_content
    blocks = [_cc_tool_use_block(), _cc_tool_result_block(), _cc_thinking_block()]
    assert _extract_text_content(blocks) == ""


def test_extract_text_non_dict_content():
    from synthadoc.skills.session.scripts.main import _extract_text_content
    assert _extract_text_content(None) == ""
    assert _extract_text_content(42) == ""


# ── Substantive turn filter ───────────────────────────────────────────────────

def test_is_substantive_assistant_above_threshold():
    from synthadoc.skills.session.scripts.main import _is_substantive
    text = " ".join(["word"] * 20)
    assert _is_substantive("assistant", text) is True


def test_is_substantive_assistant_below_threshold():
    from synthadoc.skills.session.scripts.main import _is_substantive
    text = " ".join(["word"] * 19)
    assert _is_substantive("assistant", text) is False


def test_is_substantive_user_above_threshold():
    from synthadoc.skills.session.scripts.main import _is_substantive
    assert _is_substantive("user", "fix the bug") is True


def test_is_substantive_user_below_threshold():
    from synthadoc.skills.session.scripts.main import _is_substantive
    assert _is_substantive("user", "ok") is False
    assert _is_substantive("user", "yes") is False


def test_is_substantive_user_exactly_three_words():
    from synthadoc.skills.session.scripts.main import _is_substantive
    assert _is_substantive("user", "three word message") is True


def test_is_substantive_human_role_same_as_user():
    from synthadoc.skills.session.scripts.main import _is_substantive
    assert _is_substantive("human", "three word message") is True


# ── Claude Code parser ────────────────────────────────────────────────────────

def test_parse_claude_code_basic():
    from synthadoc.skills.session.scripts.main import _parse_claude_code
    lines = [
        _cc_user("How do I sort a list in Python?"),
        _cc_assistant([_cc_text_block("Use the sorted() function or list.sort() method.")]),
    ]
    turns = _parse_claude_code(lines)
    assert len(turns) == 2
    assert turns[0] == ("user", "How do I sort a list in Python?")
    assert "sorted()" in turns[1][1]


def test_parse_claude_code_skips_sidechain():
    from synthadoc.skills.session.scripts.main import _parse_claude_code
    lines = [
        _cc_user("main question"),
        _cc_user("sidechain question", is_sidechain=True),
        _cc_assistant([_cc_text_block("main answer")]),
        _cc_assistant([_cc_text_block("sidechain answer")], is_sidechain=True),
    ]
    turns = _parse_claude_code(lines)
    assert len(turns) == 2
    assert all(not t[1].startswith("sidechain") for t in turns)


def test_parse_claude_code_skips_metadata_types():
    from synthadoc.skills.session.scripts.main import _parse_claude_code
    lines = [
        json.dumps({"type": "permission-mode", "message": {"role": "system", "content": "ACCEPTALL"}}),
        json.dumps({"type": "system", "message": {"role": "system", "content": "system prompt"}}),
        json.dumps({"type": "last-prompt", "message": {"role": "user", "content": "last question"}}),
        _cc_user("real question here"),
        _cc_assistant([_cc_text_block("real answer here for the question")]),
    ]
    turns = _parse_claude_code(lines)
    assert len(turns) == 2
    assert turns[0][1] == "real question here"


def test_parse_claude_code_string_user_content():
    from synthadoc.skills.session.scripts.main import _parse_claude_code
    lines = [_cc_user("simple string content")]
    turns = _parse_claude_code(lines)
    assert turns == [("user", "simple string content")]


def test_parse_claude_code_mixed_blocks_filters_tool_use():
    from synthadoc.skills.session.scripts.main import _parse_claude_code
    lines = [
        _cc_assistant([
            _cc_text_block("Here is what I found."),
            _cc_tool_use_block(),
            _cc_thinking_block(),
        ])
    ]
    turns = _parse_claude_code(lines)
    assert len(turns) == 1
    assert turns[0][1] == "Here is what I found."


def test_parse_claude_code_skips_invalid_json():
    from synthadoc.skills.session.scripts.main import _parse_claude_code
    lines = [
        "not json",
        "{broken: true}",
        _cc_user("valid question here"),
    ]
    turns = _parse_claude_code(lines)
    assert len(turns) == 1
    assert turns[0][1] == "valid question here"


def test_parse_claude_code_empty_content_skipped():
    from synthadoc.skills.session.scripts.main import _parse_claude_code
    # Assistant with only tool_use — no text extracted
    lines = [_cc_assistant([_cc_tool_use_block()])]
    turns = _parse_claude_code(lines)
    assert turns == []


# ── Codex / Cursor parser ─────────────────────────────────────────────────────

def test_parse_codex_basic():
    from synthadoc.skills.session.scripts.main import _parse_codex
    lines = [
        _codex_line("user", "What is a binary tree?"),
        _codex_line("assistant", "A binary tree is a data structure where each node has at most two children."),
    ]
    turns = _parse_codex(lines)
    assert len(turns) == 2
    assert turns[0] == ("user", "What is a binary tree?")
    assert "binary tree" in turns[1][1]


def test_parse_codex_skips_system_role():
    from synthadoc.skills.session.scripts.main import _parse_codex
    lines = [
        _codex_line("system", "You are a helpful assistant."),
        _codex_line("user", "Hello there friend"),
        _codex_line("assistant", "Hi! How can I help you?"),
    ]
    turns = _parse_codex(lines)
    assert len(turns) == 2
    assert turns[0][0] == "user"


def test_parse_codex_accepts_human_role():
    from synthadoc.skills.session.scripts.main import _parse_codex
    lines = [_codex_line("human", "What does this function do exactly?")]
    turns = _parse_codex(lines)
    assert len(turns) == 1
    assert turns[0][0] == "human"


def test_parse_codex_skips_invalid_json():
    from synthadoc.skills.session.scripts.main import _parse_codex
    lines = ["garbage", _codex_line("user", "valid message here")]
    turns = _parse_codex(lines)
    assert len(turns) == 1


# ── Slug generation ───────────────────────────────────────────────────────────

def test_make_slug_starts_with_session(tmp_path):
    from synthadoc.skills.session.scripts.main import _make_slug
    f = tmp_path / "session.jsonl"
    f.write_text("")
    turns = [("user", "how do I implement this feature")]
    slug = _make_slug(f, turns)
    assert slug.startswith("session-")


def test_make_slug_contains_date(tmp_path):
    from synthadoc.skills.session.scripts.main import _make_slug
    import re
    f = tmp_path / "session.jsonl"
    f.write_text("")
    turns = [("user", "how do I implement this feature")]
    slug = _make_slug(f, turns)
    assert re.search(r"\d{4}-\d{2}-\d{2}", slug), f"No date in slug: {slug}"


def test_make_slug_topic_from_first_user_turn(tmp_path):
    from synthadoc.skills.session.scripts.main import _make_slug
    f = tmp_path / "session.jsonl"
    f.write_text("")
    turns = [("user", "how do I implement sliding window algorithm")]
    slug = _make_slug(f, turns)
    assert "how" in slug and "implement" in slug


def test_make_slug_max_80_chars(tmp_path):
    from synthadoc.skills.session.scripts.main import _make_slug
    f = tmp_path / "session.jsonl"
    f.write_text("")
    turns = [("user", "a" * 200 + " b c d e f g h i j k")]
    slug = _make_slug(f, turns)
    assert len(slug) <= 80


def test_make_slug_skips_assistant_for_topic(tmp_path):
    from synthadoc.skills.session.scripts.main import _make_slug
    f = tmp_path / "session.jsonl"
    f.write_text("")
    turns = [
        ("assistant", "Let me help you with that request"),
        ("user", "implement binary search algorithm please"),
    ]
    slug = _make_slug(f, turns)
    assert "implement" in slug or "binary" in slug


# ── Full extract() integration ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_nonexistent_file():
    skill = _load_skill()
    result = await skill.extract("/tmp/does-not-exist-at-all.jsonl")
    assert result.text == ""
    assert result.source_path == "/tmp/does-not-exist-at-all.jsonl"


@pytest.mark.asyncio
async def test_extract_empty_file(tmp_path):
    skill = _load_skill()
    f = _write_jsonl(tmp_path, [])
    result = await skill.extract(str(f))
    assert result.text == ""
    assert result.metadata.get("empty") is True


@pytest.mark.asyncio
async def test_extract_claude_code_session(tmp_path):
    skill = _load_skill()
    long_answer = "The sliding window algorithm keeps a contiguous subarray by advancing two pointers. " * 3
    lines = [
        _cc_user("How do I implement a sliding window algorithm in Python?"),
        _cc_assistant([_cc_text_block(long_answer)]),
        _cc_assistant([_cc_tool_use_block()]),  # tool-only turn — excluded from output
        _cc_user("Can you show an example with a list?"),
        _cc_assistant([
            _cc_thinking_block(),
            _cc_text_block("Sure, here is an example with a list of integers for you. " * 4),
        ]),
    ]
    f = _write_jsonl(tmp_path, lines)
    result = await skill.extract(str(f))

    assert "[USER]" in result.text
    assert "[ASSISTANT]" in result.text
    assert "sliding window" in result.text
    assert "---" in result.text
    assert result.metadata["format"] == "claude_code"
    assert result.metadata["turn_count"] >= 2
    assert result.metadata["suggested_slug"].startswith("session-")


@pytest.mark.asyncio
async def test_extract_codex_session(tmp_path):
    skill = _load_skill()
    long_answer = "A binary search tree stores values in sorted order for efficient lookup. " * 3
    lines = [
        _codex_line("user", "What is a binary search tree and how does it work?"),
        _codex_line("assistant", long_answer),
    ]
    f = _write_jsonl(tmp_path, lines)
    result = await skill.extract(str(f))

    assert "[USER]" in result.text
    assert "[ASSISTANT]" in result.text
    assert result.metadata["format"] == "codex"
    assert result.metadata["turn_count"] == 2


@pytest.mark.asyncio
async def test_extract_filters_short_turns(tmp_path):
    skill = _load_skill()
    lines = [
        _cc_user("ok"),          # < 3 words — filtered
        _cc_user("yes"),         # < 3 words — filtered
        _cc_user("How do I implement a binary search tree in Python?"),
        _cc_assistant([_cc_text_block("Sure.")]),   # < 20 words — filtered
        _cc_assistant([_cc_text_block(
            "A binary search tree organises nodes so each left child is smaller and each right child is larger. " * 2
        )]),
    ]
    f = _write_jsonl(tmp_path, lines)
    result = await skill.extract(str(f))

    assert "ok" not in result.text
    assert "Sure." not in result.text
    assert "binary search tree" in result.text


@pytest.mark.asyncio
async def test_extract_sidechain_turns_excluded(tmp_path):
    skill = _load_skill()
    long_main = "This is the main assistant response with enough words to pass the threshold. " * 2
    lines = [
        _cc_user("Main user question with enough words for the filter to pass"),
        _cc_assistant([_cc_text_block(long_main)]),
        _cc_user("sidechain sub question", is_sidechain=True),
        _cc_assistant([_cc_text_block("sidechain sub answer")], is_sidechain=True),
    ]
    f = _write_jsonl(tmp_path, lines)
    result = await skill.extract(str(f))

    assert "sidechain" not in result.text.lower()
    assert result.metadata["turn_count"] == 2


@pytest.mark.asyncio
async def test_extract_tool_content_excluded(tmp_path):
    skill = _load_skill()
    lines = [
        _cc_user("Read the config file and tell me the port setting please"),
        _cc_assistant([
            _cc_tool_use_block(),
            _cc_tool_result_block(),
            _cc_text_block(
                "The port is set to 7070 in the configuration file. "
                "I can see this from the output of the tool call above. "
                "You can change it in the config."
            ),
        ]),
    ]
    f = _write_jsonl(tmp_path, lines)
    result = await skill.extract(str(f))

    assert "file1.py" not in result.text  # tool_result content excluded
    assert "7070" in result.text


@pytest.mark.asyncio
async def test_extract_metadata_keys(tmp_path):
    skill = _load_skill()
    long_answer = "This answer is long enough to pass the twenty word minimum threshold check. " * 2
    lines = [
        _cc_user("How does async await work in Python and why is it useful?"),
        _cc_assistant([_cc_text_block(long_answer)]),
    ]
    f = _write_jsonl(tmp_path, lines)
    result = await skill.extract(str(f))

    assert "format" in result.metadata
    assert "turn_count" in result.metadata
    assert "suggested_slug" in result.metadata


@pytest.mark.asyncio
async def test_extract_all_short_returns_empty(tmp_path):
    skill = _load_skill()
    lines = [
        _cc_user("ok"),
        _cc_assistant([_cc_text_block("sure")]),
    ]
    f = _write_jsonl(tmp_path, lines)
    result = await skill.extract(str(f))
    assert result.text == ""
    assert result.metadata.get("empty") is True


@pytest.mark.asyncio
async def test_extract_source_path_preserved(tmp_path):
    skill = _load_skill()
    f = _write_jsonl(tmp_path, [_cc_user("hello world question")])
    result = await skill.extract(str(f))
    assert result.source_path == str(f)


@pytest.mark.asyncio
async def test_extract_unknown_format_falls_back_to_codex(tmp_path):
    skill = _load_skill()
    long_answer = "The answer to this question is quite detailed and involves several steps. " * 2
    lines = [
        _codex_line("user", "What is the history of Python programming language?"),
        _codex_line("assistant", long_answer),
    ]
    f = _write_jsonl(tmp_path, lines)
    result = await skill.extract(str(f))
    assert result.text != ""


# ── Skill registration ────────────────────────────────────────────────────────

def test_skill_detected_for_jsonl_extension():
    from synthadoc.agents.skill_agent import SkillAgent
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    (tmp / "wiki").mkdir()
    agent = SkillAgent(wiki_root=tmp)
    meta = agent.detect_skill("/path/to/my-session.jsonl")
    assert meta is not None
    assert meta.name == "session"


def test_skill_loaded_by_name():
    skill = _load_skill()
    assert skill is not None
    assert skill.__class__.__name__ == "SessionSkill"
