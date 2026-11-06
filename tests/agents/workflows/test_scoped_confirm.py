# Copyright (C) 2026 William Johnason / axoviq.com
import asyncio, pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

from synthadoc.agents.workflows.block_apply import ApplyResult, BlockResult


def _make_apply_result(applied=1, rejected=0) -> ApplyResult:
    blocks = []
    for i in range(applied):
        blocks.append(BlockResult(
            index=i, old_text=f"old{i}", new_text=f"new{i}",
            status="applied", rejection_reason=None
        ))
    for j in range(rejected):
        blocks.append(BlockResult(
            index=applied + j, old_text=f"bad{j}", new_text=f"x{j}",
            status="rejected", rejection_reason="no_match"
        ))
    accumulated = "new0 some text." if applied else "original content."
    return ApplyResult(blocks=blocks, accumulated_body=accumulated,
                       applied_count=applied, rejected_count=rejected)


@pytest.mark.asyncio
async def test_tool_scoped_confirm_sends_correct_sse_event():
    from synthadoc.agents.workflows._tools import tool_scoped_confirm
    ctx = MagicMock()
    ctx.session_id = "sess1"
    ctx.run_id = "run1"
    ctx.send_sse_event = AsyncMock()
    ctx.confirm_registry = {}
    ctx.confirm_result_registry = {}
    ctx.scoped_confirm_registry = {}

    ar = _make_apply_result(applied=2, rejected=1)

    # Simulate immediate resolution (blocks mode, include all applied)
    async def resolver():
        await asyncio.sleep(0)  # yield
        ctx.confirm_result_registry["run1"] = {
            "confirmed": True, "mode": "blocks",
            "included_block_ids": ["b0", "b1"], "page_body": None,
        }
        ctx.confirm_registry["run1"].set()

    asyncio.get_event_loop().create_task(resolver())
    result = await tool_scoped_confirm(ctx, slug="pg", apply_result=ar,
                                       current_body="old0 old1 some text.")

    event_name = ctx.send_sse_event.call_args[0][0]
    payload = ctx.send_sse_event.call_args[0][1]
    assert event_name == "scoped_edit_confirm"
    assert payload["page_slug"] == "pg"
    assert len(payload["blocks"]) == 3
    assert payload["accumulated_body"] == ar.accumulated_body

    assert result["confirmed"] is True
    assert result["final_body"] is not None


@pytest.mark.asyncio
async def test_tool_scoped_confirm_zero_blocks_sends_page_tab_default():
    from synthadoc.agents.workflows._tools import tool_scoped_confirm
    ctx = MagicMock()
    ctx.session_id = "sess2"
    ctx.run_id = "run2"
    ctx.send_sse_event = AsyncMock()
    ctx.confirm_registry = {}
    ctx.confirm_result_registry = {}
    ctx.scoped_confirm_registry = {}

    ar = _make_apply_result(applied=0, rejected=2)

    async def resolver():
        await asyncio.sleep(0)
        ctx.confirm_result_registry["run2"] = {
            "confirmed": False, "mode": "page",
            "included_block_ids": [], "page_body": None,
        }
        ctx.confirm_registry["run2"].set()

    asyncio.get_event_loop().create_task(resolver())
    await tool_scoped_confirm(ctx, slug="pg", apply_result=ar, current_body="original content.")

    payload = ctx.send_sse_event.call_args[0][1]
    assert payload["default_tab"] == "page"
    assert "No safe edits found" in payload["header_message"]
