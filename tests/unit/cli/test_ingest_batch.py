# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Unit tests for --batch template-* exclusion in the ingest command."""
from __future__ import annotations

from pathlib import Path

import pytest

from synthadoc.cli.ingest import _SUPPORTED


def _batch_sources(directory: Path) -> list[str]:
    """Replicate the exact filtering expression used in ingest_cmd --batch."""
    return [
        str(f) for f in directory.rglob("*")
        if f.is_file()
        and f.suffix in _SUPPORTED
        and not f.name.startswith("template-")
    ]


@pytest.fixture()
def raw_sources(tmp_path: Path) -> Path:
    """raw_sources tree with template-* and real files across three subfolders."""
    rs = tmp_path / "raw_sources"
    (rs / "properties").mkdir(parents=True)
    (rs / "financial-models").mkdir(parents=True)
    (rs / "portfolio").mkdir(parents=True)

    # Template files — must be excluded
    (rs / "properties" / "template-property-intake.md").write_text("template")
    (rs / "financial-models" / "template-financial-model.md").write_text("template")
    (rs / "portfolio" / "template-portfolio-goals.md").write_text("template")

    # User-filled files — must be included
    (rs / "properties" / "highway7-condo.md").write_text("real")
    (rs / "financial-models" / "highway7-model.md").write_text("real")
    (rs / "portfolio" / "portfolio-goals.md").write_text("real")

    return rs


class TestBatchIngestExcludesTemplates:
    def test_template_files_not_collected(self, raw_sources: Path):
        sources = _batch_sources(raw_sources)
        for src in sources:
            assert not Path(src).name.startswith("template-"), (
                f"template-* file was collected for ingest: {src}"
            )

    def test_real_files_are_collected(self, raw_sources: Path):
        names = {Path(s).name for s in _batch_sources(raw_sources)}
        assert "highway7-condo.md" in names
        assert "highway7-model.md" in names
        assert "portfolio-goals.md" in names

    def test_all_three_template_files_excluded(self, raw_sources: Path):
        names = {Path(s).name for s in _batch_sources(raw_sources)}
        assert "template-property-intake.md" not in names
        assert "template-financial-model.md" not in names
        assert "template-portfolio-goals.md" not in names

    def test_exclusion_applies_at_any_depth(self, tmp_path: Path):
        """template- prefix is excluded regardless of directory depth."""
        rs = tmp_path / "raw_sources"
        (rs / "nested" / "deep").mkdir(parents=True)
        (rs / "nested" / "deep" / "template-something.md").write_text("template")
        (rs / "nested" / "deep" / "real-file.md").write_text("real")

        names = {Path(s).name for s in _batch_sources(rs)}
        assert "template-something.md" not in names
        assert "real-file.md" in names

    def test_non_template_prefix_with_template_in_name_is_included(self, tmp_path: Path):
        """Only the template- prefix triggers exclusion; substring match is not enough."""
        rs = tmp_path / "raw_sources"
        rs.mkdir()
        (rs / "my-template-notes.md").write_text("real")

        names = {Path(s).name for s in _batch_sources(rs)}
        assert "my-template-notes.md" in names
