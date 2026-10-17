# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the deterministic content-health fixes (merge + sentence preservation)."""
import pytest

from synthadoc.agents.content_health_fixes import dropped_sentences, merge_duplicate_sections
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
