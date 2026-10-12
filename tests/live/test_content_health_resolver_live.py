# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration test: full round-trip from scanner to workflow fix to rollback."""
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock

import pytest

from synthadoc.agents.content_health_scanner import scan_page
from synthadoc.agents.workflows._base import WorkflowContext
from synthadoc.agents.workflows.tools.content_health_tools import (
    tool_list_content_health_fixes,
    tool_rollback_content_health_fix,
    tool_write_content_health_fix,
)
from synthadoc.storage.wiki import WikiPage, WikiStorage

_DUPLICATE_CONTENT = """\
# Alan Turing

## Bletchley Park and Cryptanalysis
Alan Turing worked at Bletchley Park during WWII. His work on Enigma was pivotal.

## Early Life and Education
Turing was born in London in 1912. He studied at Cambridge.

## Bletchley Park and Cryptanalysis
Alan Turing worked at Bletchley Park during WWII. His work on Enigma was pivotal.
This is a duplicate section that should be merged.

## Early Life and Education
More duplicate content about early life.
"""

_FIXED_CONTENT = """\
# Alan Turing

## Bletchley Park and Cryptanalysis
Alan Turing worked at Bletchley Park during WWII. His work on Enigma was pivotal.
This section has been consolidated from two copies. """ + " ".join(["x"] * 40) + """

## Early Life and Education
Turing was born in London in 1912. He studied at Cambridge.
This section consolidates all early life content. """ + " ".join(["x"] * 40) + """
"""


@pytest.mark.asyncio
async def test_full_round_trip(tmp_path):
    store = WikiStorage(tmp_path / "wiki")

    # 1. Scanner finds duplicate sections in content
    issues = scan_page("alan-turing", _DUPLICATE_CONTENT)
    assert any(i.type == "duplicate_section" for i in issues)

    page = WikiPage(title="Alan Turing", tags=[], content=_DUPLICATE_CONTENT,
                    status="active", confidence="", sources=[])
    page.content_health_issues = [asdict(i) for i in issues]
    store.write_page("alan-turing", page)

    # 2. count_content_health_issues picks up the page
    assert store.count_content_health_issues() == 1

    # 3. Workflow: apply fix via tool
    ctx = MagicMock(spec=WorkflowContext)
    ctx.store = store
    ctx.audit_db = MagicMock()
    ctx.audit_db.snapshot_if_changed = AsyncMock(return_value=True)
    ctx.audit_db.list_page_snapshots = AsyncMock(return_value=[{"index": 1, "id": 99}])
    ctx.bump_epoch = MagicMock()

    result = await tool_write_content_health_fix(
        ctx, slug="alan-turing", content=_FIXED_CONTENT,
        issues_fixed=["duplicate_section x2"],
    )
    assert result["status"] == "success"
    assert result["snapshot_id"] == 99
    assert result["snapshot_index"] == 1

    # 4. Fix record stored with correct fields
    fixed_page = store.read_page("alan-turing")
    assert fixed_page.content_health_fix_record is not None
    assert fixed_page.content_health_fix_record["snapshot_id"] == 99
    assert fixed_page.content_health_fix_record["snapshot_index_before"] == 1
    assert fixed_page.content_health_fix_record["slug"] == "alan-turing"

    # 5. Issues cleared (FIXED_CONTENT has no duplicate sections)
    assert fixed_page.content_health_issues == []

    # 6. Count drops to 0 after clean fix
    assert store.count_content_health_issues() == 0

    # 7. list_fixes surfaces the fix
    list_result = await tool_list_content_health_fixes(ctx)
    assert len(list_result["fixes"]) == 1
    assert list_result["fixes"][0]["slug"] == "alan-turing"
    assert list_result["fixes"][0]["snapshot_id"] == 99

    # 8. Rollback: snapshot id 99 resolves to index 1 via list_page_snapshots
    ctx.audit_db.list_page_snapshots = AsyncMock(return_value=[{"index": 1, "id": 99}])
    ctx.audit_db.get_snapshot_by_index = AsyncMock(return_value={
        "index": 1, "id": 99, "content_snapshot": _DUPLICATE_CONTENT
    })
    rollback_result = await tool_rollback_content_health_fix(ctx, slug="alan-turing")
    assert rollback_result["status"] == "success"
    assert rollback_result["rolled_back_to_snapshot"] == 1

    # 9. After rollback: fix_record cleared, issues restored, count back to 1
    rolled_page = store.read_page("alan-turing")
    assert rolled_page.content_health_fix_record is None
    assert rolled_page.content_health_issues  # issues restored from original content
    assert store.count_content_health_issues() == 1
