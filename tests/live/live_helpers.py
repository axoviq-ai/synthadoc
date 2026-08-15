# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Shared helpers for Synthadoc live test scripts."""
import shutil
import tempfile
from pathlib import Path


def backup_wiki(wiki_root: Path) -> Path | None:
    """Snapshot wiki/ and .synthadoc/ into a temp directory.

    Returns the snapshot path on success, or None if the copy fails (a warning
    is printed but the caller's test run continues).
    """
    snap = Path(tempfile.mkdtemp(prefix="synthadoc-live-backup-"))
    try:
        shutil.copytree(wiki_root / "wiki", snap / "wiki")
        if (wiki_root / ".synthadoc").exists():
            shutil.copytree(wiki_root / ".synthadoc", snap / ".synthadoc")
        return snap
    except Exception as exc:
        print(f"  [WARN] snapshot failed ({exc}) — wiki will not be auto-restored")
        shutil.rmtree(snap, ignore_errors=True)
        return None


def restore_wiki(snap: Path, wiki_root: Path, wiki_name: str) -> None:
    """Restore wiki/ and .synthadoc/ from a snapshot created by backup_wiki().

    Deletes the snapshot directory on success.  Preserves it on failure so the
    developer can restore manually.  Always prints a reminder to restart the
    server after restore.
    """
    try:
        if (wiki_root / "wiki").exists():
            shutil.rmtree(wiki_root / "wiki")
        shutil.copytree(snap / "wiki", wiki_root / "wiki")
        if (snap / ".synthadoc").exists():
            if (wiki_root / ".synthadoc").exists():
                shutil.rmtree(wiki_root / ".synthadoc")
            shutil.copytree(snap / ".synthadoc", wiki_root / ".synthadoc")
        shutil.rmtree(snap, ignore_errors=True)
        print()
        print("=" * 64)
        print("  Wiki restored to pre-test state.")
        print("  Restart the server to pick up the restored DB:")
        print(f"    synthadoc serve -w {wiki_name}")
        print("=" * 64)
    except Exception as exc:
        print()
        print("=" * 64)
        print(f"  Restore failed: {exc}")
        print(f"  Snapshot preserved at: {snap}")
        print(f"  Restore manually, then: synthadoc serve -w {wiki_name}")
        print("=" * 64)
