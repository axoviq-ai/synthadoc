# Copyright (C) 2026 Paul Chen / axoviq.com
# SPDX-License-Identifier: AGPL-3.0-or-later
from synthadoc.agents.content_health_scanner import ContentIssue, scan_page, scan_pages


def test_duplicate_section_detected():
    content = """# Alan Turing

## Early Life
Some content here.

## Early Life
More content here duplicated.
"""
    issues = scan_page("alan-turing", content)
    dup = [i for i in issues if i.type == "duplicate_section"]
    assert len(dup) == 1
    assert dup[0].severity == "critical"
    assert "Early Life" in dup[0].description
    assert "2" in dup[0].description


def test_clean_page_returns_empty():
    early_life = " ".join(["word"] * 55)
    career = " ".join(["word"] * 55)
    content = f"# Alan Turing\n\n## Early Life\n{early_life}\n\n## Career\n{career}\n"
    assert scan_page("alan-turing", content) == []


def test_empty_section_detected():
    content = "# Page\n\n## Empty Section\n\n## Not Empty\n" + " ".join(["word"] * 55) + "\n"
    issues = scan_page("test", content)
    empty = [i for i in issues if i.type == "empty_section"]
    assert len(empty) == 1
    assert empty[0].severity == "critical"


def test_thin_section_detected():
    content = "# Page\n\n## Thin\nOnly three words.\n\n## Normal\n" + " ".join(["word"] * 55) + "\n"
    issues = scan_page("test", content)
    thin = [i for i in issues if i.type == "thin_section"]
    assert len(thin) == 1
    assert thin[0].severity == "high"


def test_thin_section_boundary_exactly_50_words_not_flagged():
    content = "# Page\n\n## Section\n" + " ".join(["word"] * 50) + "\n"
    issues = scan_page("test", content)
    assert not any(i.type == "thin_section" for i in issues)


def test_unclosed_code_block():
    content = "# Page\n\n## Section\nSome text.\n\n```python\ncode here\n"
    issues = scan_page("test", content)
    assert any(i.type == "unclosed_code_block" for i in issues)


def test_closed_code_block_not_flagged():
    content = "# Page\n\n## Section\n" + " ".join(["word"] * 55) + "\n\n```python\ncode here\n```\n"
    issues = scan_page("test", content)
    assert not any(i.type == "unclosed_code_block" for i in issues)


def test_orphaned_heading():
    content = "# Title\n\n## Section\nContent.\n\n# Another H1\n\n## More\n" + " ".join(["word"] * 55) + "\n"
    issues = scan_page("test", content)
    assert any(i.type == "orphaned_heading" for i in issues)


def test_heading_inside_code_block_not_flagged():
    content = (
        "# Page\n\n## Section\n" + " ".join(["word"] * 55) + "\n\n"
        "```markdown\n# Heading inside fence\n## Also inside\n```\n"
    )
    issues = scan_page("test", content)
    assert not any(i.type in ("duplicate_section", "orphaned_heading") for i in issues)


def test_scan_pages_omits_clean_pages():
    pages = {
        "clean": "# Clean\n\n## Section\n" + " ".join(["word"] * 60) + "\n",
        "dirty": "# Dirty\n\n## Dup\nContent.\n\n## Dup\nMore.\n",
    }
    result = scan_pages(pages)
    assert "clean" not in result
    assert "dirty" in result


def test_custom_thin_threshold():
    content = "# Page\n\n## Section\n" + " ".join(["word"] * 30) + "\n"
    assert scan_page("test", content, thin_section_min_words=25) == []
    assert any(i.type == "thin_section" for i in scan_page("test", content, thin_section_min_words=35))


def test_content_issue_dataclass_fields():
    issue = ContentIssue(
        type="duplicate_section",
        severity="critical",
        location="## Intro",
        description="Appears 3 times",
    )
    assert issue.type == "duplicate_section"
    assert issue.severity == "critical"
    assert issue.location == "## Intro"
    assert issue.description == "Appears 3 times"


# ── Parent headings, reference sections, report-only types ───────────────────

_PARENT = (
    "# AI\n\n## Early AI Programs\n\n"
    "### Logic Theorist\n" + " ".join(["word"] * 30) + "\n\n"
    "### ELIZA\n" + " ".join(["word"] * 30) + "\n"
)


def test_heading_with_only_subsections_is_not_empty():
    types = {(i.type, i.location) for i in scan_page("ai", _PARENT)}
    assert ("empty_section", "Early AI Programs") not in types


def test_parent_length_includes_subsections():
    # 0 own words + 60 in sub-sections: the parent is not thin, each child (30) is.
    thin = [i.location for i in scan_page("ai", _PARENT) if i.type == "thin_section"]
    assert "Early AI Programs" not in thin
    assert thin == ["Logic Theorist", "ELIZA"]


def test_heading_with_no_text_and_no_subsections_is_still_empty():
    content = "# AI\n\n## Key Figures Added\n\n## Next\n" + " ".join(["word"] * 60) + "\n"
    assert [i.location for i in scan_page("ai", content) if i.type == "empty_section"] == ["Key Figures Added"]


def test_reference_sections_are_never_thin():
    content = "# AI\n\n## See Also\n- [[turing]]\n\n## Sources\n- book\n\n## Notes\nShort.\n"
    assert not [i for i in scan_page("ai", content) if i.type == "thin_section"]


def test_resolvable_issues_drops_report_only_types():
    from synthadoc.agents.content_health_scanner import REPORT_ONLY_ISSUE_TYPES, resolvable_issues
    issues = [{"type": "thin_section"}, {"type": "duplicate_section"}, {"type": "empty_section"}]
    assert REPORT_ONLY_ISSUE_TYPES == {"thin_section"}
    assert resolvable_issues(issues) == issues[1:]
