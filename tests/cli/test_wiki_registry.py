# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import json
import pytest
from pathlib import Path
from unittest.mock import patch


def test_read_registry_all_empty(tmp_path):
    reg_path = tmp_path / "wikis.json"
    with patch("synthadoc.cli._wiki._REGISTRY", reg_path):
        from synthadoc.cli._wiki import read_registry_all
        assert read_registry_all() == {}


def test_read_registry_all_returns_dict(tmp_path):
    reg = {"wiki-a": {"path": "/x", "port": 7070, "purpose_summary": "finance"}}
    reg_path = tmp_path / "wikis.json"
    reg_path.write_text(json.dumps(reg))
    with patch("synthadoc.cli._wiki._REGISTRY", reg_path):
        from synthadoc.cli._wiki import read_registry_all
        result = read_registry_all()
        assert result["wiki-a"]["purpose_summary"] == "finance"


def test_extract_purpose_summary_no_frontmatter(tmp_path):
    """Returns first 500 chars of body when there is no YAML frontmatter."""
    wiki_root = tmp_path
    (wiki_root / "wiki").mkdir()
    (wiki_root / "wiki" / "purpose.md").write_text(
        "# My Wiki\n\nThis is the purpose.\n" * 50,
        encoding="utf-8",
    )
    from synthadoc.cli._wiki import extract_purpose_summary
    result = extract_purpose_summary(wiki_root)
    assert len(result) <= 500
    assert result.startswith("# My Wiki")


def test_extract_purpose_summary_strips_frontmatter(tmp_path):
    """YAML frontmatter is stripped; only body text is returned."""
    wiki_root = tmp_path
    (wiki_root / "wiki").mkdir()
    body = "# Purpose\n\nThis wiki covers AI research.\n"
    content = f"---\ntitle: Test\nstatus: active\n---\n{body}"
    (wiki_root / "wiki" / "purpose.md").write_text(content, encoding="utf-8")
    from synthadoc.cli._wiki import extract_purpose_summary
    result = extract_purpose_summary(wiki_root)
    assert "title:" not in result
    assert "# Purpose" in result


def test_extract_purpose_summary_missing_file(tmp_path):
    """Returns empty string when purpose.md does not exist."""
    wiki_root = tmp_path
    (wiki_root / "wiki").mkdir()
    from synthadoc.cli._wiki import extract_purpose_summary
    result = extract_purpose_summary(wiki_root)
    assert result == ""


def test_probe_port_returns_false_on_exception(tmp_path):
    """probe_port returns False when httpx raises any exception."""
    from synthadoc.cli._wiki import probe_port
    # Port 1 is always refused on non-root
    result = probe_port(1, timeout=0.1)
    assert result is False
