# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
"""Tests for synthadoc.utils shared utilities."""
import pathlib
from unittest.mock import patch

from synthadoc.utils import atomic_write_text


def test_atomic_write_text_creates_file(tmp_path):
    target = tmp_path / "out.txt"
    atomic_write_text(target, "hello\nworld\n")
    assert target.read_text(encoding="utf-8") == "hello\nworld\n"


def test_atomic_write_text_no_crlf(tmp_path):
    target = tmp_path / "out.md"
    atomic_write_text(target, "line one\nline two\n")
    assert b"\r\n" not in target.read_bytes()


def test_atomic_write_text_no_tmp_left_behind(tmp_path):
    target = tmp_path / "out.json"
    atomic_write_text(target, "{}")
    assert not (tmp_path / "out.tmp").exists()


def test_atomic_write_text_overwrites_existing(tmp_path):
    target = tmp_path / "page.md"
    target.write_text("old content", encoding="utf-8")
    atomic_write_text(target, "new content")
    assert target.read_text(encoding="utf-8") == "new content"


def test_atomic_write_text_uses_unix_line_endings_via_spy(tmp_path):
    """Spy confirms newline='\\n' is passed even on platforms where it matters."""
    target = tmp_path / "page.md"
    real_write_text = pathlib.Path.write_text
    calls: list = []

    def spy(self, data, *args, **kwargs):
        calls.append(kwargs)
        return real_write_text(self, data, *args, **kwargs)

    with patch.object(pathlib.Path, "write_text", spy):
        atomic_write_text(target, "body\n")

    assert calls
    for kwargs in calls:
        assert kwargs.get("newline") == "\n"


# ---------------------------------------------------------------------------
# BUG-24 — WikiStorage.write_page must be atomic
# ---------------------------------------------------------------------------

def test_write_page_is_atomic(tmp_wiki):
    """BUG-24: write_page must write via a .tmp sibling then os.replace().

    No .tmp file should remain, and the target must never be partially written.
    We verify atomicity by confirming the .tmp file is absent after the call
    and that the on-disk content matches exactly what was written.
    """
    from synthadoc.storage.wiki import WikiStorage, WikiPage

    wiki_dir = tmp_wiki / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    store = WikiStorage(wiki_dir)
    page = WikiPage(title="Atomic", tags=[], content="body text",
                    status="draft", confidence="medium", sources=[])

    store.write_page("atomic-page", page)

    target = wiki_dir / "atomic-page.md"
    tmp = wiki_dir / "atomic-page.tmp"

    assert target.exists(), "page file must exist after write"
    assert not tmp.exists(), ".tmp file must not be left behind"
    assert "body text" in target.read_text(encoding="utf-8")
    assert b"\r\n" not in target.read_bytes()
