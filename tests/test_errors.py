# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
def test_coding_tool_quota_exception_message():
    from synthadoc.errors import CodingToolQuotaExhaustedException
    e = CodingToolQuotaExhaustedException("claude-code")
    assert "claude-code" in str(e)
    assert "quota" in str(e).lower()


def test_coding_tool_permanent_error_message():
    from synthadoc.errors import CodingToolPermanentError, CODING_TOOL_PERMANENT
    e = CodingToolPermanentError("opencode", "speech model cannot do chat completions")
    msg = str(e)
    assert CODING_TOOL_PERMANENT in msg          # ERR-PROV-004
    assert "opencode" in msg
    assert "speech model cannot do chat completions" in msg
    assert "retrying will not help" in msg.lower()


def test_short_wiki_path_drops_leading_directories():
    """Only the last 3 path components survive — enough to identify which
    wiki and which file, not enough to expose the home directory or
    OS username a full absolute path would carry."""
    from pathlib import Path
    from synthadoc.errors import _short_wiki_path
    full = Path("/Users/paulchen/wikis/history-of-computing/.synthadoc/config.toml")
    assert _short_wiki_path(full) == "history-of-computing/.synthadoc/config.toml"


def test_short_wiki_path_handles_short_paths_gracefully():
    from pathlib import Path
    from synthadoc.errors import _short_wiki_path
    assert _short_wiki_path(Path("config.toml")) == "config.toml"


def test_missing_api_key_error_with_config_path_does_not_leak_home_dir():
    from synthadoc.errors import MissingApiKeyError
    e = MissingApiKeyError(
        "ANTHROPIC_API_KEY", "Anthropic", "https://console.anthropic.com/",
        config_path="/Users/paulchen/wikis/history-of-computing/.synthadoc/config.toml",
    )
    msg = str(e)
    assert "history-of-computing/.synthadoc/config.toml" in msg
    assert "/Users/paulchen" not in msg


def test_missing_api_key_error_without_config_path_uses_generic_wording():
    from synthadoc.errors import MissingApiKeyError
    e = MissingApiKeyError("ANTHROPIC_API_KEY", "Anthropic", "https://console.anthropic.com/")
    assert "config.toml's [agents] section" in str(e)
