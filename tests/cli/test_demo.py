# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from synthadoc.cli.main import app


@pytest.fixture
def mock_registry(tmp_path):
    """Return a factory: call it with a dict to patch _read_registry."""
    def _make(registry: dict):
        return patch("synthadoc.cli.demo._read_registry", return_value=registry)
    return _make


@pytest.fixture
def demo_template(tmp_path):
    """Create a minimal demo template directory."""
    template = tmp_path / "template" / "history-of-computing"
    (template / "raw_sources").mkdir(parents=True)
    (template / "wiki").mkdir(parents=True)
    (template / "raw_sources" / "source1.md").write_text("source content", encoding="utf-8")
    (template / "wiki" / "dashboard.md").write_text(
        "---\ntitle: Dashboard\n---\n# Dashboard body", encoding="utf-8"
    )
    (template / "wiki" / "page1.md").write_text(
        "---\ntitle: Page 1\n---\ncontent from template^[source1.md:1-2]", encoding="utf-8"
    )
    return template


def test_sync_demo_does_not_overwrite_existing_page(tmp_path, mock_registry, demo_template):
    """Without --force, existing wiki pages must NOT be overwritten."""
    installed = tmp_path / "installed" / "history-of-computing"
    (installed / "wiki").mkdir(parents=True)
    (installed / "raw_sources").mkdir(parents=True)
    # Pre-existing page with old content
    (installed / "wiki" / "page1.md").write_text("OLD CONTENT", encoding="utf-8")

    registry = {"history-of-computing": {"path": str(installed)}}
    with mock_registry(registry), \
         patch("synthadoc.cli.demo._DEMOS", {"history-of-computing": demo_template}):
        runner = CliRunner()
        result = runner.invoke(app, ["demo", "sync", "history-of-computing"])

    assert result.exit_code == 0
    assert (installed / "wiki" / "page1.md").read_text() == "OLD CONTENT"


def test_sync_demo_force_overwrites_existing_page(tmp_path, mock_registry, demo_template):
    """With --force, existing wiki pages ARE overwritten from the template."""
    installed = tmp_path / "installed" / "history-of-computing"
    (installed / "wiki").mkdir(parents=True)
    (installed / "raw_sources").mkdir(parents=True)
    (installed / "wiki" / "page1.md").write_text("OLD CONTENT", encoding="utf-8")

    registry = {"history-of-computing": {"path": str(installed)}}
    with mock_registry(registry), \
         patch("synthadoc.cli.demo._DEMOS", {"history-of-computing": demo_template}):
        runner = CliRunner()
        result = runner.invoke(app, ["demo", "sync", "history-of-computing", "--force"])

    assert result.exit_code == 0
    content = (installed / "wiki" / "page1.md").read_text()
    assert "OLD CONTENT" not in content
    assert "template" in content  # content from demo_template


def test_sync_demo_always_copies_new_page(tmp_path, mock_registry, demo_template):
    """New pages (not in installed wiki) are always copied, regardless of --force."""
    installed = tmp_path / "installed" / "history-of-computing"
    (installed / "wiki").mkdir(parents=True)
    (installed / "raw_sources").mkdir(parents=True)
    # page1.md does NOT exist in installed wiki

    registry = {"history-of-computing": {"path": str(installed)}}
    with mock_registry(registry), \
         patch("synthadoc.cli.demo._DEMOS", {"history-of-computing": demo_template}):
        runner = CliRunner()
        result = runner.invoke(app, ["demo", "sync", "history-of-computing"])

    assert result.exit_code == 0
    assert (installed / "wiki" / "page1.md").exists()


def test_sync_demo_registry_miss_exits_1(mock_registry):
    """Syncing an unregistered wiki name must exit with code 1."""
    with mock_registry({}):
        runner = CliRunner()
        result = runner.invoke(app, ["demo", "sync", "nonexistent-demo"])
    assert result.exit_code == 1


def test_sync_demo_no_installed_demos_exits_0(mock_registry):
    """With no installed demos, sync exits 0 with a clear message."""
    with mock_registry({}):
        runner = CliRunner()
        result = runner.invoke(app, ["demo", "sync"])
    assert result.exit_code == 0


def test_sync_demo_force_all_demos(tmp_path, mock_registry, demo_template):
    """--force without a name updates all installed demos."""
    installed = tmp_path / "installed" / "history-of-computing"
    (installed / "wiki").mkdir(parents=True)
    (installed / "raw_sources").mkdir(parents=True)
    (installed / "wiki" / "page1.md").write_text("OLD CONTENT", encoding="utf-8")

    registry = {"history-of-computing": {"path": str(installed)}}
    with mock_registry(registry), \
         patch("synthadoc.cli.demo._DEMOS", {"history-of-computing": demo_template}):
        runner = CliRunner()
        result = runner.invoke(app, ["demo", "sync", "--force"])

    assert result.exit_code == 0
    assert "OLD CONTENT" not in (installed / "wiki" / "page1.md").read_text()
