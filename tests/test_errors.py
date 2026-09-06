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
