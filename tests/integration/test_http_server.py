# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests for http_server.py multi-turn conversation wiring (Task 7)."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def _make_app(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    return create_app(wiki_root=tmp_wiki)


# ---------------------------------------------------------------------------
# Test 1: get_history called when session_id is present
# ---------------------------------------------------------------------------

def test_query_stream_loads_history_when_session_id_present(tmp_wiki):
    """get_all_messages must be called with (session_id,) when session_id is in the request."""
    from fastapi.testclient import TestClient

    app = _make_app(tmp_wiki)

    async def _fake_stream(question, session_id=None, session_mode="POWER_USER",
                           history=None):
        yield {"event": "token", "data": {"text": "hello"}}
        yield {"event": "done", "data": {"cacheable": False}}

    fake_history = [{"role": "user", "content": "prev"}, {"role": "assistant", "content": "ans"}]

    with patch("synthadoc.core.orchestrator.Orchestrator.query_stream",
               new=_fake_stream):
        with patch("synthadoc.storage.log.AuditDB.get_summary",
                   new=AsyncMock(return_value=(None, 0))):
            with patch("synthadoc.storage.log.AuditDB.get_all_messages",
                       new=AsyncMock(return_value=fake_history)) as mock_get_all_messages:
                with TestClient(app) as client:
                    resp = client.get("/query/stream?q=hello&session_id=test-session-123")

    assert resp.status_code == 200
    mock_get_all_messages.assert_awaited_once_with("test-session-123")


# ---------------------------------------------------------------------------
# Test 2: get_history NOT called when conversation_history_turns=0
# ---------------------------------------------------------------------------

def test_query_stream_no_history_when_turns_zero(tmp_wiki):
    """get_all_messages must NOT be called when conversation_history_turns=0."""
    from fastapi.testclient import TestClient
    from synthadoc.config import load_config

    app = _make_app(tmp_wiki)

    # Patch config so that chat.conversation_history_turns == 0
    orig_load = load_config

    def _patched_load(*args, **kwargs):
        cfg = orig_load(*args, **kwargs)
        cfg.chat.conversation_history_turns = 0
        return cfg

    async def _fake_stream(question, session_id=None, session_mode="POWER_USER",
                           history=None):
        yield {"event": "token", "data": {"text": "hello"}}
        yield {"event": "done", "data": {"cacheable": False}}

    with patch("synthadoc.config.load_config", side_effect=_patched_load):
        app2 = _make_app(tmp_wiki)

    with patch("synthadoc.core.orchestrator.Orchestrator.query_stream",
               new=_fake_stream):
        with patch("synthadoc.storage.log.AuditDB.get_all_messages",
                   new=AsyncMock(return_value=[])) as mock_get_all_messages:
            with TestClient(app2) as client:
                resp = client.get("/query/stream?q=hello&session_id=test-session-456")

    assert resp.status_code == 200
    mock_get_all_messages.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test 3: clarify event forwarded through SSE
# ---------------------------------------------------------------------------

def test_query_stream_clarify_event_forwarded(tmp_wiki):
    """A 'clarify' event from the query agent must be forwarded as SSE event: clarify."""
    from fastapi.testclient import TestClient

    app = _make_app(tmp_wiki)

    async def _fake_stream_with_clarify(question, session_id=None,
                                         session_mode="POWER_USER", history=None):
        yield {"event": "clarify", "data": {"question": "Did you mean X or Y?",
                                             "options": ["X", "Y"]}}
        yield {"event": "done", "data": {"cacheable": False}}

    with patch("synthadoc.storage.log.AuditDB.get_history",
               new=AsyncMock(return_value=[])):
        with patch("synthadoc.storage.log.AuditDB.get_summary",
                   new=AsyncMock(return_value=(None, 0))):
            with patch("synthadoc.storage.log.AuditDB.get_all_messages",
                       new=AsyncMock(return_value=[])):
                with TestClient(app) as client:
                    app.state.orch.query_stream = _fake_stream_with_clarify
                    resp = client.get("/query/stream?q=ambiguous&session_id=sess-clarify")

    assert resp.status_code == 200
    assert b"event: clarify" in resp.content


# ---------------------------------------------------------------------------
# Test 4: notice event emitted on first overflow
# ---------------------------------------------------------------------------

def test_query_stream_notice_emitted_on_first_overflow(tmp_wiki):
    """A 'notice' SSE event must be emitted when history overflows for the first time."""
    from fastapi.testclient import TestClient

    app = _make_app(tmp_wiki)

    # 12 messages = 6 turns, window is 5 → overflow = 1 turn
    many_messages = [
        {"role": ("user" if i % 2 == 0 else "assistant"), "content": f"msg {i}"}
        for i in range(12)
    ]

    async def _fake_stream(question, session_id=None, session_mode="POWER_USER",
                           history=None):
        yield {"event": "token", "data": {"text": "answer"}}
        yield {"event": "done", "data": {"cacheable": False}}

    fake_provider = MagicMock()

    with patch("synthadoc.storage.log.AuditDB.get_history",
               new=AsyncMock(return_value=many_messages[-10:])):
        with patch("synthadoc.storage.log.AuditDB.get_summary",
                   new=AsyncMock(return_value=(None, 0))):
            with patch("synthadoc.storage.log.AuditDB.get_all_messages",
                       new=AsyncMock(return_value=many_messages)):
                with patch("synthadoc.providers.make_provider",
                           return_value=fake_provider):
                    with patch("synthadoc.agents.summarize_agent.SummarizeAgent.summarize",
                               new=AsyncMock(return_value="Earlier topics: X and Y.")):
                        with patch("synthadoc.storage.log.AuditDB.update_summary",
                                   new=AsyncMock()):
                            with TestClient(app) as client:
                                app.state.orch.query_stream = _fake_stream
                                resp = client.get(
                                    "/query/stream?q=what+next&session_id=sess-overflow"
                                )

    assert resp.status_code == 200
    assert b"event: notice" in resp.content
