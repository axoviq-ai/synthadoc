# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import json
from pathlib import Path

import pytest

from synthadoc.cli.main import app  # noqa: F401 - prevents circular import
from synthadoc.cli.plugin import _set_reading_view_default, _patch_workspace_reading_view


def test_set_reading_view_default_creates_app_json(tmp_path):
    """When app.json is absent, it is created with all three Obsidian settings."""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / ".obsidian").mkdir()

    result = _set_reading_view_default(wiki)
    assert result is True

    app_json = wiki / ".obsidian" / "app.json"
    assert app_json.exists()
    data = json.loads(app_json.read_text(encoding="utf-8"))
    assert data["defaultViewMode"] == "preview"
    assert data["newFileLocation"] == "folder"
    assert data["newFileFolderPath"] == "wiki"


def test_set_reading_view_default_preserves_other_keys(tmp_path):
    """Existing keys in app.json are preserved alongside the three managed settings."""
    wiki = tmp_path / "wiki"
    (wiki / ".obsidian").mkdir(parents=True)
    app_json = wiki / ".obsidian" / "app.json"
    app_json.write_text(
        json.dumps({"theme": "obsidian", "fontSize": 14}), encoding="utf-8"
    )

    _set_reading_view_default(wiki)

    data = json.loads(app_json.read_text(encoding="utf-8"))
    assert data["defaultViewMode"] == "preview"
    assert data["newFileLocation"] == "folder"
    assert data["newFileFolderPath"] == "wiki"
    assert data["theme"] == "obsidian"
    assert data["fontSize"] == 14


def test_set_reading_view_default_idempotent(tmp_path):
    """Returns False (no-op) when all three managed settings are already correct."""
    wiki = tmp_path / "wiki"
    (wiki / ".obsidian").mkdir(parents=True)
    app_json = wiki / ".obsidian" / "app.json"
    original = json.dumps({
        "defaultViewMode": "preview",
        "newFileLocation": "folder",
        "newFileFolderPath": "wiki",
        "theme": "dark",
    })
    app_json.write_text(original, encoding="utf-8")

    result = _set_reading_view_default(wiki)
    assert result is False
    data = json.loads(app_json.read_text(encoding="utf-8"))
    assert data["defaultViewMode"] == "preview"
    assert data["theme"] == "dark"


def test_set_reading_view_default_writes_when_new_file_settings_missing(tmp_path):
    """Returns True and writes when defaultViewMode is correct but new-file settings are absent."""
    wiki = tmp_path / "wiki"
    (wiki / ".obsidian").mkdir(parents=True)
    app_json = wiki / ".obsidian" / "app.json"
    app_json.write_text(json.dumps({"defaultViewMode": "preview"}), encoding="utf-8")

    result = _set_reading_view_default(wiki)
    assert result is True
    data = json.loads(app_json.read_text(encoding="utf-8"))
    assert data["newFileLocation"] == "folder"
    assert data["newFileFolderPath"] == "wiki"


def test_set_reading_view_default_malformed_json(tmp_path):
    """Malformed app.json is healed: treated as empty dict, written with all three settings."""
    wiki = tmp_path / "wiki"
    (wiki / ".obsidian").mkdir(parents=True)
    app_json = wiki / ".obsidian" / "app.json"
    app_json.write_text("{ not valid json }", encoding="utf-8")

    result = _set_reading_view_default(wiki)
    assert result is True
    data = json.loads(app_json.read_text(encoding="utf-8"))
    assert data["defaultViewMode"] == "preview"
    assert data["newFileLocation"] == "folder"
    assert data["newFileFolderPath"] == "wiki"


def test_set_reading_view_default_creates_obsidian_dir(tmp_path):
    """If .obsidian/ does not exist, it is created."""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    # .obsidian does NOT exist

    result = _set_reading_view_default(wiki)
    assert result is True
    assert (wiki / ".obsidian" / "app.json").exists()


# ---------------------------------------------------------------------------
# _patch_workspace_reading_view
# ---------------------------------------------------------------------------

def _make_workspace(leaves: list[dict]) -> dict:
    """Build a minimal workspace.json structure with the given leaf state dicts."""
    children = [
        {
            "id": f"leaf{i}",
            "type": "leaf",
            "state": {
                "type": leaf.get("type", "markdown"),
                "state": {k: v for k, v in leaf.items() if k != "type"},
            },
        }
        for i, leaf in enumerate(leaves)
    ]
    return {"main": {"id": "root", "type": "split", "children": children}}


def test_patch_workspace_no_file(tmp_path):
    """Returns False when workspace.json does not exist."""
    wiki = tmp_path / "wiki"
    (wiki / ".obsidian").mkdir(parents=True)
    assert _patch_workspace_reading_view(wiki) is False


def test_patch_workspace_patches_source_leaves(tmp_path):
    """Markdown leaves with mode=source are switched to mode=preview."""
    wiki = tmp_path / "wiki"
    (wiki / ".obsidian").mkdir(parents=True)
    ws_json = wiki / ".obsidian" / "workspace.json"
    workspace = _make_workspace([{"mode": "source", "file": "wiki/note.md"}])
    ws_json.write_text(json.dumps(workspace), encoding="utf-8")

    result = _patch_workspace_reading_view(wiki)
    assert result is True
    data = json.loads(ws_json.read_text(encoding="utf-8"))
    leaf_state = data["main"]["children"][0]["state"]["state"]
    assert leaf_state["mode"] == "preview"


def test_patch_workspace_idempotent(tmp_path):
    """Already-preview leaves are left unchanged; returns False."""
    wiki = tmp_path / "wiki"
    (wiki / ".obsidian").mkdir(parents=True)
    ws_json = wiki / ".obsidian" / "workspace.json"
    workspace = _make_workspace([{"mode": "preview", "file": "wiki/note.md"}])
    ws_json.write_text(json.dumps(workspace), encoding="utf-8")

    result = _patch_workspace_reading_view(wiki)
    assert result is False


def test_patch_workspace_skips_non_markdown_leaves(tmp_path):
    """Non-markdown leaves (e.g. file-explorer) are not touched."""
    wiki = tmp_path / "wiki"
    (wiki / ".obsidian").mkdir(parents=True)
    ws_json = wiki / ".obsidian" / "workspace.json"
    workspace = _make_workspace([{"type": "file-explorer"}])
    ws_json.write_text(json.dumps(workspace), encoding="utf-8")

    result = _patch_workspace_reading_view(wiki)
    assert result is False


def test_patch_workspace_malformed_json(tmp_path):
    """Malformed workspace.json is left untouched; returns False."""
    wiki = tmp_path / "wiki"
    (wiki / ".obsidian").mkdir(parents=True)
    ws_json = wiki / ".obsidian" / "workspace.json"
    ws_json.write_text("{ not valid }", encoding="utf-8")

    result = _patch_workspace_reading_view(wiki)
    assert result is False
    assert ws_json.read_text(encoding="utf-8") == "{ not valid }"
