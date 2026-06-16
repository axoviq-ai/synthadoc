# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from pathlib import Path
from unittest.mock import patch

from synthadoc.cli.demo import _extract_body, _extract_frontmatter_block, sync_demo


# ── helper tests ────────────────────────────────────────────────────────────

def test_extract_body_with_frontmatter():
    text = "---\ntitle: Test\n---\n\n# Hello\n"
    assert _extract_body(text) == "\n\n# Hello\n"


def test_extract_body_no_frontmatter():
    text = "# No frontmatter\n"
    body = _extract_body(text)
    assert "# No frontmatter" in body


def test_extract_frontmatter_block_returns_normalized_yaml():
    text = "---\ntitle: Test\nstatus: active\n---\n\n# Body\n"
    fm = _extract_frontmatter_block(text)
    assert fm == "\ntitle: Test\nstatus: active\n"
    assert fm.startswith("\n")
    assert fm.endswith("\n")


def test_extract_frontmatter_block_normalizes_double_newline():
    """If the installed file already has a spurious blank line, it must be stripped."""
    text = "---\n\ntitle: Test\nstatus: active\n---\n\n# Body\n"
    fm = _extract_frontmatter_block(text)
    assert fm == "\ntitle: Test\nstatus: active\n"


def test_extract_frontmatter_block_no_frontmatter():
    text = "# No frontmatter\n"
    assert _extract_frontmatter_block(text) == ""


# ── sync_demo integration tests ─────────────────────────────────────────────

def _make_template(tmp_path: Path, name: str) -> Path:
    """Create a minimal demo template directory."""
    tmpl = tmp_path / "templates" / name
    (tmpl / "raw_sources").mkdir(parents=True)
    (tmpl / "wiki").mkdir(parents=True)

    (tmpl / "raw_sources" / "source_a.txt").write_text("Source A\n", encoding="utf-8")
    (tmpl / "wiki" / "dashboard.md").write_text(
        "---\ntitle: Dashboard\n---\n\n## Section\nNew body.\n",
        encoding="utf-8",
    )
    (tmpl / "wiki" / "new-page.md").write_text(
        "---\ntitle: New Page\n---\n\nContent.\n",
        encoding="utf-8",
    )
    return tmpl


def _make_installed(tmp_path: Path, name: str) -> Path:
    """Create a minimal installed wiki directory."""
    inst = tmp_path / "installed" / name
    (inst / "raw_sources").mkdir(parents=True)
    (inst / "wiki").mkdir(parents=True)

    (inst / "raw_sources" / "source_a.txt").write_text("Source A\n", encoding="utf-8")
    (inst / "wiki" / "dashboard.md").write_text(
        "---\naliases: []\ncategories:\n- Overview\ntitle: Dashboard\n---\n\n## Old Section\nOld body.\n",
        encoding="utf-8",
    )
    return inst


def test_sync_copies_new_raw_sources(tmp_path):
    tmpl = _make_template(tmp_path, "test-wiki")
    inst = _make_installed(tmp_path, "test-wiki")
    (tmpl / "raw_sources" / "source_b.txt").write_text("Source B\n", encoding="utf-8")

    registry = {"test-wiki": {"path": str(inst)}}
    demos = {"test-wiki": tmpl}

    with patch("synthadoc.cli.demo._read_registry", return_value=registry), \
         patch("synthadoc.cli.demo._DEMOS", demos):
        from typer.testing import CliRunner
        from synthadoc.cli.demo import demo_app
        result = CliRunner().invoke(demo_app, ["sync", "test-wiki"])

    assert result.exit_code == 0
    assert (inst / "raw_sources" / "source_b.txt").exists()


def test_sync_does_not_overwrite_existing_raw_sources(tmp_path):
    tmpl = _make_template(tmp_path, "test-wiki")
    inst = _make_installed(tmp_path, "test-wiki")
    (inst / "raw_sources" / "source_a.txt").write_text("User edited\n", encoding="utf-8")

    registry = {"test-wiki": {"path": str(inst)}}
    demos = {"test-wiki": tmpl}

    with patch("synthadoc.cli.demo._read_registry", return_value=registry), \
         patch("synthadoc.cli.demo._DEMOS", demos):
        from typer.testing import CliRunner
        from synthadoc.cli.demo import demo_app
        CliRunner().invoke(demo_app, ["sync", "test-wiki"])

    assert (inst / "raw_sources" / "source_a.txt").read_text() == "User edited\n"


def test_sync_updates_dashboard_body_preserves_frontmatter(tmp_path):
    tmpl = _make_template(tmp_path, "test-wiki")
    inst = _make_installed(tmp_path, "test-wiki")

    registry = {"test-wiki": {"path": str(inst)}}
    demos = {"test-wiki": tmpl}

    with patch("synthadoc.cli.demo._read_registry", return_value=registry), \
         patch("synthadoc.cli.demo._DEMOS", demos):
        from typer.testing import CliRunner
        from synthadoc.cli.demo import demo_app
        CliRunner().invoke(demo_app, ["sync", "test-wiki"])

    result = (inst / "wiki" / "dashboard.md").read_text(encoding="utf-8")
    assert "aliases: []" in result
    assert "categories:" in result
    assert "Overview" in result
    assert "New body." in result
    assert "Old body." not in result


def test_sync_dashboard_frontmatter_no_double_newline(tmp_path):
    tmpl = _make_template(tmp_path, "test-wiki")
    inst = _make_installed(tmp_path, "test-wiki")

    registry = {"test-wiki": {"path": str(inst)}}
    demos = {"test-wiki": tmpl}

    with patch("synthadoc.cli.demo._read_registry", return_value=registry), \
         patch("synthadoc.cli.demo._DEMOS", demos):
        from typer.testing import CliRunner
        from synthadoc.cli.demo import demo_app
        CliRunner().invoke(demo_app, ["sync", "test-wiki"])

    content = (inst / "wiki" / "dashboard.md").read_text(encoding="utf-8")
    assert not content.startswith("---\n\n"), "No blank line after opening ---"


def test_sync_is_idempotent(tmp_path):
    tmpl = _make_template(tmp_path, "test-wiki")
    inst = _make_installed(tmp_path, "test-wiki")

    registry = {"test-wiki": {"path": str(inst)}}
    demos = {"test-wiki": tmpl}

    from typer.testing import CliRunner
    from synthadoc.cli.demo import demo_app

    with patch("synthadoc.cli.demo._read_registry", return_value=registry), \
         patch("synthadoc.cli.demo._DEMOS", demos):
        CliRunner().invoke(demo_app, ["sync", "test-wiki"])
        after_first = (inst / "wiki" / "dashboard.md").read_text(encoding="utf-8")

    with patch("synthadoc.cli.demo._read_registry", return_value=registry), \
         patch("synthadoc.cli.demo._DEMOS", demos):
        result = CliRunner().invoke(demo_app, ["sync", "test-wiki"])
        after_second = (inst / "wiki" / "dashboard.md").read_text(encoding="utf-8")

    assert after_first == after_second
    assert "Already up to date" in result.output


def test_sync_copies_new_wiki_pages(tmp_path):
    tmpl = _make_template(tmp_path, "test-wiki")
    inst = _make_installed(tmp_path, "test-wiki")

    registry = {"test-wiki": {"path": str(inst)}}
    demos = {"test-wiki": tmpl}

    with patch("synthadoc.cli.demo._read_registry", return_value=registry), \
         patch("synthadoc.cli.demo._DEMOS", demos):
        from typer.testing import CliRunner
        from synthadoc.cli.demo import demo_app
        CliRunner().invoke(demo_app, ["sync", "test-wiki"])

    assert (inst / "wiki" / "new-page.md").exists()


def test_sync_skips_protected_wiki_pages(tmp_path):
    tmpl = _make_template(tmp_path, "test-wiki")
    inst = _make_installed(tmp_path, "test-wiki")
    (tmpl / "wiki" / "index.md").write_text("Template index\n", encoding="utf-8")
    (inst / "wiki" / "index.md").write_text("User index\n", encoding="utf-8")

    registry = {"test-wiki": {"path": str(inst)}}
    demos = {"test-wiki": tmpl}

    with patch("synthadoc.cli.demo._read_registry", return_value=registry), \
         patch("synthadoc.cli.demo._DEMOS", demos):
        from typer.testing import CliRunner
        from synthadoc.cli.demo import demo_app
        CliRunner().invoke(demo_app, ["sync", "test-wiki"])

    assert (inst / "wiki" / "index.md").read_text() == "User index\n"


def test_sync_unknown_wiki_exits_nonzero(tmp_path):
    registry = {}
    demos = {}

    with patch("synthadoc.cli.demo._read_registry", return_value=registry), \
         patch("synthadoc.cli.demo._DEMOS", demos):
        from typer.testing import CliRunner
        from synthadoc.cli.demo import demo_app
        result = CliRunner().invoke(demo_app, ["sync", "does-not-exist"])

    assert result.exit_code != 0
