# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the deterministic content-health fixes (merge + sentence preservation)."""
import pytest

from synthadoc.agents.content_health_fixes import (
    HeadingChange,
    dropped_sentences,
    heading_diff,
    heading_mismatch_error,
    merge_duplicate_sections,
    text_loss_error,
)
from synthadoc.agents.content_health_scanner import scan_page

_FLAG_DAY = (
    "# Internet\n\nIntro text about networks and protocols.\n\n"
    "## Flag Day (1 January 1983)\nARPANET switched from NCP to TCP/IP on that day.\n\n"
    "## Packet Switching\nPaul Baran and Donald Davies proposed packet switching.\n\n"
    "## Flag Day — 1 January 1983\nEvery host was reconfigured at the same time.\n"
    "ARPANET switched from NCP to TCP/IP on that day.\n\n"
    "## Flag Day (1 January 1983)\nARPANET switched from NCP to TCP/IP on that day.\n"
)


def _types(content):
    return [i.type for i in scan_page("p", content)]


def test_merge_folds_copies_into_first_and_keeps_every_sentence():
    result = merge_duplicate_sections(_FLAG_DAY)

    assert result.merged == ["Flag Day (1 January 1983)"]
    assert result.skipped == []
    assert dropped_sentences(_FLAG_DAY, result.content) == []
    assert "duplicate_section" not in _types(result.content)
    # The second copy's paragraph has a new sentence, so it moves under the first
    # heading whole (paragraphs are never cut). The third copy repeats the first
    # word for word, so it is dropped: the sentence appears twice, not three times.
    first = result.content.index("## Flag Day (1 January 1983)")
    assert first < result.content.index("Every host was reconfigured") < result.content.index("## Packet Switching")
    assert result.content.count("ARPANET switched from NCP to TCP/IP on that day.") == 2
    assert result.source_headings == [
        "Flag Day (1 January 1983)", "Flag Day — 1 January 1983", "Flag Day (1 January 1983)"]


def test_merge_is_a_no_op_without_duplicates():
    content = "# P\n\n## A\nOne sentence here for A.\n\n## B\nOne sentence here for B.\n"
    result = merge_duplicate_sections(content)
    assert (result.content, result.merged) == (content, [])


def test_merge_skips_copies_that_have_subsections():
    content = (
        "# P\n\n## ELIZA\nWeizenbaum wrote ELIZA at MIT.\n\n"
        "## ELIZA\nIt imitated a Rogerian therapist.\n\n### DOCTOR script\nThe best-known script was DOCTOR.\n"
    )
    result = merge_duplicate_sections(content)
    assert result.merged == [] and result.skipped == ["ELIZA"]
    assert result.content == content


def test_merge_ignores_headings_inside_code_fences():
    content = "# P\n\n## Usage\nRun the tool like this.\n\n```\n## Usage\n```\n"
    assert merge_duplicate_sections(content).content == content


@pytest.mark.parametrize("rewritten,lost", [
    ("Alpha beta gamma delta. Second sentence is right here.", []),
    ("- Alpha **beta** gamma\n  delta. Second sentence is right here.", []),   # markup and wrapping
    ("Alpha beta gamma delta.", ["second sentence is right here."]),
])
def test_dropped_sentences(rewritten, lost):
    assert dropped_sentences("Alpha beta gamma delta. Second sentence is right here.", rewritten) == lost


def test_heading_diff_identical_returns_empty():
    md = "# Title\n\nBody.\n\n## Section\n\nMore body.\n"
    assert heading_diff(md, md) == []


def test_heading_diff_no_headings_returns_empty():
    assert heading_diff("just prose, no headings\n", "still just prose\n") == []


def test_heading_diff_detects_removed_heading():
    before = "# Title\n\n## Empty\n\n## Keep\n\nbody\n"
    after = "# Title\n\n## Keep\n\nbody\n"
    changes = heading_diff(before, after)
    assert changes == [HeadingChange(kind="removed", before="Empty", after=None)]


def test_heading_diff_detects_added_heading():
    before = "# Title\n\n## Keep\n\nbody\n"
    after = "# Title\n\n## Keep\n\nbody\n\n## New\n\nmore\n"
    changes = heading_diff(before, after)
    assert changes == [HeadingChange(kind="added", before=None, after="New")]


def test_heading_diff_detects_level_change_same_text():
    before = "# Title\n\n### Stray\n\nbody\n"
    after = "# Title\n\n## Stray\n\nbody\n"
    changes = heading_diff(before, after)
    assert changes == [HeadingChange(kind="level_changed", before="Stray", after="Stray")]


def test_heading_diff_detects_text_change_same_level():
    before = "## The Cathedral and the Bazaar (1999)\n\nbody\n"
    after = "## The Cathedral and the Bazaar\n\nbody\n"
    changes = heading_diff(before, after)
    assert changes == [HeadingChange(
        kind="text_changed", before="The Cathedral and the Bazaar (1999)",
        after="The Cathedral and the Bazaar",
    )]


def test_heading_diff_detects_reordered_headings():
    before = "# Title\n\n## A\n\nbody a\n\n## B\n\nbody b\n"
    after = "# Title\n\n## B\n\nbody b\n\n## A\n\nbody a\n"
    changes = heading_diff(before, after)
    assert any(c.kind == "reordered" for c in changes)


def test_heading_diff_ignores_headings_inside_code_fences():
    before = "# Title\n\n```\n# not a heading\n```\n\nbody\n"
    after = "# Title\n\n```\n# not a heading either\n```\n\nbody\n"
    assert heading_diff(before, after) == []


def test_heading_mismatch_error_strict_rejects_any_change():
    before = "# Title\n\n## A\n\nbody\n"
    after = "# Title\n\n## B\n\nbody\n"
    result = heading_mismatch_error("my-slug", before, after)
    assert result is not None
    assert result["status"] == "error"
    assert result["slug"] == "my-slug"


def test_heading_mismatch_error_strict_allows_no_change():
    md = "# Title\n\n## A\n\nbody\n"
    assert heading_mismatch_error("my-slug", md, md) is None


def test_heading_mismatch_error_allows_one_removed_per_empty_section_issue():
    before = "# Title\n\n## Empty\n\n## Keep\n\nbody\n"
    after = "# Title\n\n## Keep\n\nbody\n"
    assert heading_mismatch_error("s", before, after, issues_fixed=["empty_section"]) is None


def test_heading_mismatch_error_rejects_removed_beyond_budget():
    before = "# Title\n\n## Empty1\n\n## Empty2\n\n## Keep\n\nbody\n"
    after = "# Title\n\n## Keep\n\nbody\n"
    result = heading_mismatch_error("s", before, after, issues_fixed=["empty_section"])
    assert result is not None
    assert result["heading_changes"] == 1


def test_heading_mismatch_error_allows_level_change_per_orphaned_heading_issue():
    before = "# Title\n\n### Stray\n\nbody\n"
    after = "# Title\n\n## Stray\n\nbody\n"
    assert heading_mismatch_error("s", before, after, issues_fixed=["orphaned_heading"]) is None


def test_heading_mismatch_error_rejects_level_change_with_text_change():
    before = "# Title\n\n### Stray Old\n\nbody\n"
    after = "# Title\n\n## Stray New\n\nbody\n"
    result = heading_mismatch_error("s", before, after, issues_fixed=["orphaned_heading"])
    assert result is not None


def test_heading_mismatch_error_rejects_change_not_permitted_by_issue_type():
    before = "# Title\n\n## A\n\nbody\n"
    after = "# Title\n\n## B\n\nbody\n"
    result = heading_mismatch_error("s", before, after, issues_fixed=["unclosed_code_block"])
    assert result is not None


def test_heading_mismatch_error_each_change_consumes_its_own_issue_type_budget():
    # Two different tolerated changes, each backed by its own issue type —
    # one type's budget must not absorb the other type's change.
    before = "# Title\n\n## Empty\n\n### Stray\n\nbody\n"
    after = "# Title\n\n## Stray\n\nbody\n"
    result = heading_mismatch_error(
        "s", before, after, issues_fixed=["empty_section", "orphaned_heading"],
    )
    assert result is None


def test_heading_mismatch_error_rejects_reorder_hidden_behind_tolerated_level_change():
    before = "# Title\n\n## B\n\nb1\n\n## C\n\nb2\n\n### Stray\n\nb3\n"
    after = "# Title\n\n## Stray\n\nb3\n\n## B\n\nb1\n\n## C\n\nb2\n"
    result = heading_mismatch_error("s", before, after, issues_fixed=["orphaned_heading"])
    assert result is not None  # must reject: a reorder is hiding behind the tolerated level change


def test_text_loss_error_none_when_nothing_dropped():
    md = "# Title\n\nThis is a complete sentence here.\n"
    assert text_loss_error("s", md, md) is None


def test_text_loss_error_rejects_dropped_sentence():
    current = "# Title\n\nThis is a complete sentence that must survive rewrites.\n"
    proposed = "# Title\n\nCompletely different content now.\n"
    result = text_loss_error("s", current, proposed)
    assert result is not None
    assert result["status"] == "error"
    assert result["dropped_sentences"] == 1
