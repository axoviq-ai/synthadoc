# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared rollback mechanics for any workflow that writes through
tool_propose_and_apply or tool_write_content_health_fix.

Extracted from the snapshot-resolve-and-restore logic that
tool_rollback_content_health_fix had duplicated inline — these functions are
generic: they don't touch any content-health-specific frontmatter field.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from synthadoc.agents.workflows._base import WorkflowContext

_STATUS_OK = "success"
_STATUS_ERR = "error"

_ROLLBACK_BARE_RE = re.compile(r"\broll\s*back\b", re.IGNORECASE)
# Capture the slug-shaped token right after "roll back"/"rollback". Slugs may
# contain underscores (e.g. a leading "_" marking a test/system page, as in
# this project's own live-test fixtures) as well as hyphens, so both are in
# the character class, not just the hyphen-separator position.
_ROLLBACK_SLUG_RE = re.compile(
    r"\broll\s*back\b\s+([a-z0-9_]+(?:-[a-z0-9_]+)*)", re.IGNORECASE
)
# Single (unhyphenated) words that commonly follow "roll back" in prose and
# must not be mistaken for a page slug ("roll back this page", "roll back our
# expectations", "roll back the last fix").
_ROLLBACK_FILLER_WORDS: frozenset[str] = frozenset({
    "this", "that", "our", "your", "my", "it", "them", "these", "those",
    "page", "pages",
    "the", "a", "an", "to", "last", "all", "everything", "fix", "fixes",
    "change", "changes",
})


def parse_rollback_intent(user_input: str) -> tuple[bool, str | None]:
    """Return (is_rollback, slug_or_None) from free-text user input.

    is_rollback=True with slug=None means "roll back" with no page named —
    callers should list recent fixes so the user can choose.

    Known limitation (inherited from the original ContentHealthResolverWorkflow
    matcher): "roll back" as a literal substring of unrelated prose still
    matches — this is a plain substring search, not intent classification.

    The word right after "roll back"/"rollback" is treated as a slug when
    EITHER (a) it is hyphenated (e.g. "alan-turing" — multi-word slugs are
    always hyphenated, so this is safe), OR (b) it is a single word that is
    NOT on a short list of common English filler/pronoun words
    (``_ROLLBACK_FILLER_WORDS``: "this", "our", "page", "the", ...).  So
    "roll back turing" yields slug "turing", while "roll back this page" and
    "roll back our expectations" yield slug=None.

    Known limitation of heuristic (b): any single English word NOT on the
    filler list is still taken as a slug — e.g. "roll back quickly" yields
    slug "quickly".  A wrong slug fails
    safely — the rollback tool reports no fix recorded for it — so this is
    accepted, in the same spirit as the substring-match limitation above.
    """
    if not _ROLLBACK_BARE_RE.search(user_input):
        return False, None
    match = _ROLLBACK_SLUG_RE.search(user_input)
    if not match:
        return True, None
    candidate = match.group(1)
    if "-" not in candidate and candidate.lower() in _ROLLBACK_FILLER_WORDS:
        return True, None
    return True, candidate


async def restore_page_snapshot(
    ctx: "WorkflowContext", slug: str, snapshot_id, fallback_index: int = 1
) -> dict:
    """Resolve snapshot_id to its current index (robust to snapshots taken
    since) and restore the page's content from it.

    Does not touch any fix-record field — callers own clearing their own
    record after a successful restore, since what that record looks like is
    caller-specific.

    Returns {"status": "success", "slug", "restored_content", "resolved_index"}
    or {"status": "error", "error": str}.
    """
    if ctx.store is None or ctx.audit_db is None:
        return {"status": _STATUS_ERR, "error": "No store or audit_db available"}
    page = ctx.store.read_page(slug)
    if page is None:
        return {"status": _STATUS_ERR, "error": f"Page '{slug}' not found"}

    if snapshot_id is not None:
        snapshots = await ctx.audit_db.list_page_snapshots(slug)
        resolved_index = next(
            (s["index"] for s in snapshots if s.get("id") == snapshot_id),
            fallback_index,
        )
    else:
        resolved_index = fallback_index

    snapshot = await ctx.audit_db.get_snapshot_by_index(slug, resolved_index)
    if snapshot is None or snapshot.get("content_snapshot") is None:
        return {
            "status": _STATUS_ERR,
            "error": f"Snapshot {resolved_index} for '{slug}' not found in audit log",
        }

    restored_content = snapshot["content_snapshot"]
    page.content = restored_content
    ctx.store.write_page(slug, page)
    if ctx.bump_epoch:
        ctx.bump_epoch()
    return {
        "status": _STATUS_OK,
        "slug": slug,
        "restored_content": restored_content,
        "resolved_index": resolved_index,
    }
