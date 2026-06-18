# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from pathlib import Path
from unittest.mock import patch

from synthadoc.cli.demo import (
    _extract_body,
    _extract_frontmatter_block,
    _inject_type_if_missing,
    _strip_bom,
    sync_demo,
)


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


def test_strip_bom_removes_bom():
    assert _strip_bom("﻿---\ntitle: T\n") == "---\ntitle: T\n"


def test_strip_bom_no_bom_unchanged():
    assert _strip_bom("---\ntitle: T\n") == "---\ntitle: T\n"


def test_extract_frontmatter_block_handles_bom():
    text = "﻿---\ntitle: Test\nstatus: active\n---\n\n# Body\n"
    fm = _extract_frontmatter_block(text)
    assert fm == "\ntitle: Test\nstatus: active\n"


def test_extract_body_handles_bom():
    text = "﻿---\ntitle: Test\n---\n\n# Body\n"
    body = _extract_body(text)
    assert "# Body" in body
    assert "﻿" not in body


def test_inject_type_if_missing_handles_bom_in_template(tmp_path):
    """Template file with UTF-8 BOM must still have its type: field detected."""
    tmpl = tmp_path / "tmpl.md"
    inst = tmp_path / "inst.md"
    tmpl.write_bytes(
        b"\xef\xbb\xbf---\ntitle: T\nconfidence: high\ntype: technology\n---\n\nBody.\n"
    )
    inst.write_text("---\ntitle: T\nconfidence: high\n---\n\nBody.\n", encoding="utf-8")

    changed = _inject_type_if_missing(inst, tmpl)

    assert changed is True
    assert "type: technology" in inst.read_text(encoding="utf-8")


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
    assert "already up to date" in result.output.lower()


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


def test_sync_name_not_in_demos_exits_nonzero(tmp_path):
    """Registry has the wiki but no bundled template exists for it."""
    registry = {"test-wiki": {"path": str(tmp_path)}}
    demos = {}  # no template

    with patch("synthadoc.cli.demo._read_registry", return_value=registry), \
         patch("synthadoc.cli.demo._DEMOS", demos):
        from typer.testing import CliRunner
        from synthadoc.cli.demo import demo_app
        result = CliRunner().invoke(demo_app, ["sync", "test-wiki"])

    assert result.exit_code != 0
    assert "No bundled demo template" in result.output


def test_sync_all_no_installed_demos(tmp_path):
    """Omitting name when no demo wikis are installed prints a message and exits 0."""
    registry = {"my-wiki": {"path": str(tmp_path)}}
    demos = {}  # registry entry is not a demo

    with patch("synthadoc.cli.demo._read_registry", return_value=registry), \
         patch("synthadoc.cli.demo._DEMOS", demos):
        from typer.testing import CliRunner
        from synthadoc.cli.demo import demo_app
        result = CliRunner().invoke(demo_app, ["sync"])

    assert result.exit_code == 0
    assert "No installed demo wikis found" in result.output


def test_sync_all_syncs_every_installed_demo(tmp_path):
    """Omitting name syncs all demo wikis found in the registry."""
    tmpl_a = _make_template(tmp_path, "wiki-a")
    tmpl_b = _make_template(tmp_path, "wiki-b")
    inst_a = _make_installed(tmp_path, "wiki-a")
    inst_b = _make_installed(tmp_path, "wiki-b")
    # Add a new raw_source to each template so sync has something to copy
    (tmpl_a / "raw_sources" / "extra_a.txt").write_text("A\n", encoding="utf-8")
    (tmpl_b / "raw_sources" / "extra_b.txt").write_text("B\n", encoding="utf-8")

    registry = {
        "wiki-a": {"path": str(inst_a)},
        "wiki-b": {"path": str(inst_b)},
    }
    demos = {"wiki-a": tmpl_a, "wiki-b": tmpl_b}

    with patch("synthadoc.cli.demo._read_registry", return_value=registry), \
         patch("synthadoc.cli.demo._DEMOS", demos):
        from typer.testing import CliRunner
        from synthadoc.cli.demo import demo_app
        result = CliRunner().invoke(demo_app, ["sync"])

    assert result.exit_code == 0
    assert (inst_a / "raw_sources" / "extra_a.txt").exists()
    assert (inst_b / "raw_sources" / "extra_b.txt").exists()
    assert "wiki-a" in result.output
    assert "wiki-b" in result.output


def test_inject_type_if_missing_adds_type(tmp_path):
    tmpl = tmp_path / "tmpl.md"
    inst = tmp_path / "inst.md"
    tmpl.write_text("---\ntitle: T\nconfidence: high\ntype: person\n---\n\nBody.\n", encoding="utf-8")
    inst.write_text("---\ntitle: T\nconfidence: high\n---\n\nBody.\n", encoding="utf-8")

    changed = _inject_type_if_missing(inst, tmpl)

    assert changed is True
    assert "type: person" in inst.read_text(encoding="utf-8")


def test_inject_type_if_missing_skips_when_already_present(tmp_path):
    tmpl = tmp_path / "tmpl.md"
    inst = tmp_path / "inst.md"
    tmpl.write_text("---\ntitle: T\ntype: person\n---\n\nBody.\n", encoding="utf-8")
    inst.write_text("---\ntitle: T\ntype: concept\n---\n\nBody.\n", encoding="utf-8")

    changed = _inject_type_if_missing(inst, tmpl)

    assert changed is False
    assert "type: concept" in inst.read_text(encoding="utf-8")


def test_inject_type_if_missing_skips_when_template_has_no_type(tmp_path):
    tmpl = tmp_path / "tmpl.md"
    inst = tmp_path / "inst.md"
    tmpl.write_text("---\ntitle: T\n---\n\nBody.\n", encoding="utf-8")
    inst.write_text("---\ntitle: T\n---\n\nBody.\n", encoding="utf-8")

    changed = _inject_type_if_missing(inst, tmpl)

    assert changed is False


def test_sync_backfills_type_in_existing_page(tmp_path):
    """Step 4: existing pages missing type: get it injected from the template."""
    tmpl = _make_template(tmp_path, "test-wiki")
    inst = _make_installed(tmp_path, "test-wiki")
    # Template page has type:, installed page does not
    (tmpl / "wiki" / "alan-turing.md").write_text(
        "---\ntitle: Alan Turing\nconfidence: high\ntype: person\n---\n\nContent.\n",
        encoding="utf-8",
    )
    (inst / "wiki" / "alan-turing.md").write_text(
        "---\ntitle: Alan Turing\nconfidence: high\n---\n\nContent.\n",
        encoding="utf-8",
    )

    registry = {"test-wiki": {"path": str(inst)}}
    demos = {"test-wiki": tmpl}

    with patch("synthadoc.cli.demo._read_registry", return_value=registry), \
         patch("synthadoc.cli.demo._DEMOS", demos):
        from typer.testing import CliRunner
        from synthadoc.cli.demo import demo_app
        result = CliRunner().invoke(demo_app, ["sync", "test-wiki"])

    assert result.exit_code == 0
    content = (inst / "wiki" / "alan-turing.md").read_text(encoding="utf-8")
    assert "type: person" in content
    assert "backfilled" in result.output
