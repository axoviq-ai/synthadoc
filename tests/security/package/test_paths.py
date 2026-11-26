# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Acceptance tests for ``synthadoc.security.paths`` (interface spec section 3).

Stdlib + pytest only, so the lean CI job runs this on every supported Python
version and on Linux, macOS and Windows. Platform-specific assertions (POSIX
modes, the Windows ACL) are real tests on their own platform, not skips of a
shared one.
"""
from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path

import pytest

from synthadoc.security import paths as P

WINDOWS = sys.platform == "win32"
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    h = tmp_path / "home"
    monkeypatch.setenv("SYNTHADOC_HOME", str(h))
    return h


@pytest.fixture
def wiki(tmp_path) -> Path:
    w = tmp_path / "wikis" / "w1"
    w.mkdir(parents=True)
    return w


# ---------------------------------------------------------------- synthadoc_home

def test_home_uses_the_environment_override(home):
    assert P.synthadoc_home() == home


def test_home_defaults_to_dot_synthadoc_in_the_user_home(tmp_path, monkeypatch):
    monkeypatch.delenv("SYNTHADOC_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert P.synthadoc_home() == tmp_path / ".synthadoc"


def test_empty_override_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("SYNTHADOC_HOME", "  ")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert P.synthadoc_home() == tmp_path / ".synthadoc"


def test_relative_override_fails_closed(monkeypatch):
    monkeypatch.setenv("SYNTHADOC_HOME", "relative/secrets")
    with pytest.raises(P.SecretPathError):
        P.synthadoc_home()


# ----------------------------------------------------------------- ensure_wiki_id

def test_wiki_id_is_a_random_uuid4_stored_in_the_wiki(wiki):
    wid = P.ensure_wiki_id(wiki)
    assert UUID_RE.match(wid)
    assert (wiki / ".synthadoc" / "wiki_id").read_text(encoding="utf-8").strip() == wid


def test_wiki_id_is_stable_and_created_once(wiki):
    created = []
    first = P.ensure_wiki_id(wiki, on_created=created.append)
    second = P.ensure_wiki_id(wiki, on_created=created.append)
    assert first == second
    assert created == [first]          # the audit hook fires only on creation


def test_two_wikis_get_different_ids(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    assert P.ensure_wiki_id(a) != P.ensure_wiki_id(b)


def test_concurrent_first_use_agrees_on_one_id(wiki):
    results, barrier = [], threading.Barrier(8)

    def worker():
        barrier.wait()
        results.append(P.ensure_wiki_id(wiki))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(results) == 8 and len(set(results)) == 1


@pytest.mark.parametrize("bad", ["", "not-a-uuid", "../../etc/passwd",
                                 "12345678-1234-1234-1234-123456789012/../x",
                                 str(uuid.uuid4()).upper()])
def test_a_corrupt_wiki_id_file_fails_closed_and_is_not_overwritten(wiki, bad):
    f = wiki / ".synthadoc" / "wiki_id"
    f.parent.mkdir()
    f.write_text(bad, encoding="utf-8")
    with pytest.raises(P.SecretPathError):
        P.ensure_wiki_id(wiki)
    assert f.read_text(encoding="utf-8") == bad


def test_wiki_id_file_tolerates_a_trailing_newline(wiki):
    f = wiki / ".synthadoc" / "wiki_id"
    f.parent.mkdir()
    wid = str(uuid.uuid4())
    f.write_text(wid + "\n", encoding="utf-8")
    assert P.ensure_wiki_id(wiki) == wid


def test_missing_wiki_folder_fails_closed(tmp_path):
    with pytest.raises(P.SecretPathError):
        P.ensure_wiki_id(tmp_path / "does-not-exist")


def test_unwritable_wiki_folder_fails_closed(wiki, monkeypatch):
    def deny(*a, **k):
        raise PermissionError("read-only")
    monkeypatch.setattr(P, "_create_exclusive", deny)
    with pytest.raises(P.SecretPathError):
        P.ensure_wiki_id(wiki)


def test_synthadoc_entry_that_is_a_file_fails_closed(wiki):
    (wiki / ".synthadoc").write_text("x", encoding="utf-8")
    with pytest.raises(P.SecretPathError):
        P.ensure_wiki_id(wiki)


# --------------------------------------------------------------------- secret_dir

def test_secret_dir_creates_the_directory_under_home(home, wiki):
    wid = P.ensure_wiki_id(wiki)
    d = P.secret_dir("auth", wid, wiki_root=wiki)
    assert d == home / "auth" / wid and d.is_dir()


def test_secret_dir_is_idempotent(home, wiki):
    wid = P.ensure_wiki_id(wiki)
    assert P.secret_dir("peers", wid, wiki_root=wiki) == P.secret_dir("peers", wid, wiki_root=wiki)


def test_binding_records_the_wiki_id_and_last_path(home, wiki):
    import json
    wid = P.ensure_wiki_id(wiki)
    d = P.secret_dir("auth", wid, wiki_root=wiki)
    data = json.loads((d / "binding.json").read_text(encoding="utf-8"))
    assert data["wiki_id"] == wid
    assert os.path.normcase(os.path.realpath(data["last_path"])) == \
        os.path.normcase(os.path.realpath(wiki))


@pytest.mark.parametrize("area", ["", "providers", "../auth", "AUTH", "other", "auth/x"])
def test_unknown_or_unsafe_areas_are_refused(home, wiki, area):
    wid = P.ensure_wiki_id(wiki)
    with pytest.raises(P.SecretPathError):
        P.secret_dir(area, wid, wiki_root=wiki)


@pytest.mark.parametrize("bad", ["", "..", "../x", "a/b", "a\\b", "not-a-uuid",
                                 "12345678-1234-1234-1234-123456789012/.."])
def test_unsafe_wiki_ids_are_refused(home, wiki, bad):
    with pytest.raises(P.SecretPathError):
        P.secret_dir("auth", bad, wiki_root=wiki)


def test_a_copied_folder_with_the_same_id_is_refused(home, tmp_path, wiki):
    wid = P.ensure_wiki_id(wiki)
    P.secret_dir("auth", wid, wiki_root=wiki)
    copy = tmp_path / "wikis" / "copy-of-w1"
    shutil.copytree(wiki, copy)
    assert P.ensure_wiki_id(copy) == wid            # the id travels with the folder
    with pytest.raises(P.SecretPathError):
        P.secret_dir("auth", wid, wiki_root=copy)


def test_the_binding_error_text_leaks_no_paths(home, tmp_path, wiki):
    wid = P.ensure_wiki_id(wiki)
    P.secret_dir("auth", wid, wiki_root=wiki)
    copy = tmp_path / "wikis" / "copy-of-w1"
    shutil.copytree(wiki, copy)
    with pytest.raises(P.SecretPathError) as info:
        P.secret_dir("auth", wid, wiki_root=copy)
    assert str(tmp_path) not in str(info.value) and str(tmp_path) not in info.value.public_message
    assert info.value.detail                          # operator detail exists for the log


def test_the_same_folder_spelled_differently_is_accepted(home, wiki):
    wid = P.ensure_wiki_id(wiki)
    P.secret_dir("auth", wid, wiki_root=wiki)
    roundabout = wiki / ".." / wiki.name
    assert P.secret_dir("auth", wid, wiki_root=roundabout) == home / "auth" / wid


@pytest.mark.skipif(not WINDOWS, reason="Windows path rules")
def test_windows_drive_and_folder_case_do_not_defeat_the_binding(home, wiki):
    wid = P.ensure_wiki_id(wiki)
    P.secret_dir("auth", wid, wiki_root=wiki)
    assert P.secret_dir("auth", wid, wiki_root=Path(str(wiki).swapcase())) == home / "auth" / wid


def test_home_inside_the_wiki_is_refused(tmp_path, wiki, monkeypatch):
    monkeypatch.setenv("SYNTHADOC_HOME", str(wiki / "secrets"))
    wid = P.ensure_wiki_id(wiki)
    with pytest.raises(P.SecretPathError):
        P.secret_dir("auth", wid, wiki_root=wiki)


def test_home_inside_a_git_work_tree_is_refused_and_names_the_fix(tmp_path, wiki, monkeypatch):
    repo = tmp_path / "dotfiles"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setenv("SYNTHADOC_HOME", str(repo / "sub" / "home"))
    wid = P.ensure_wiki_id(wiki)
    with pytest.raises(P.SecretPathError) as info:
        P.secret_dir("auth", wid, wiki_root=wiki)
    assert "SYNTHADOC_HOME" in info.value.hint
    assert not (repo / "sub").exists()               # nothing was created before refusing


def test_a_git_file_marker_counts_as_a_work_tree(tmp_path, wiki, monkeypatch):
    repo = tmp_path / "worktree"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
    monkeypatch.setenv("SYNTHADOC_HOME", str(repo / "home"))
    with pytest.raises(P.SecretPathError):
        P.secret_dir("auth", P.ensure_wiki_id(wiki), wiki_root=wiki)


def test_areas_are_separate_directories(home, wiki):
    wid = P.ensure_wiki_id(wiki)
    dirs = {a: P.secret_dir(a, wid, wiki_root=wiki) for a in ("auth", "live", "peers")}
    assert len(set(dirs.values())) == 3


# ---------------------------------------------------- POSIX permissions (real test)

@pytest.mark.skipif(WINDOWS, reason="POSIX modes; the Windows ACL has its own test")
def test_posix_directories_are_0700_and_owned_by_the_user(home, wiki):
    wid = P.ensure_wiki_id(wiki)
    d = P.secret_dir("auth", wid, wiki_root=wiki)
    for p in (d, d.parent):
        st = p.lstat()
        assert (st.st_mode & 0o777) == 0o700 and st.st_uid == os.getuid()


@pytest.mark.skipif(WINDOWS, reason="POSIX modes")
def test_posix_loose_existing_modes_are_tightened(home, wiki):
    wid = P.ensure_wiki_id(wiki)
    d = P.secret_dir("auth", wid, wiki_root=wiki)
    os.chmod(d, 0o755)
    assert (P.secret_dir("auth", wid, wiki_root=wiki).lstat().st_mode & 0o077) == 0


@pytest.mark.skipif(WINDOWS, reason="POSIX symlink semantics")
def test_posix_a_symlinked_secret_dir_is_refused(home, tmp_path, wiki):
    wid = P.ensure_wiki_id(wiki)
    (home / "auth").mkdir(parents=True, mode=0o700)
    target = tmp_path / "elsewhere"
    target.mkdir()
    (home / "auth" / wid).symlink_to(target, target_is_directory=True)
    with pytest.raises(P.SecretPathError):
        P.secret_dir("auth", wid, wiki_root=wiki)


# ------------------------------------------------------- Windows ACL (real test)

def _icacls_entries(path: Path) -> list:
    """Independent read-back of the ACL (does not use the implementation's own code)."""
    out = subprocess.run(["icacls", str(path)], capture_output=True, text=True, check=True).stdout
    return [ln for ln in out.splitlines() if ":(" in ln]


@pytest.mark.skipif(not WINDOWS, reason="Windows ACL")
def test_windows_acl_grants_only_the_current_user_and_is_not_inherited(home, wiki):
    wid = P.ensure_wiki_id(wiki)
    d = P.secret_dir("auth", wid, wiki_root=wiki)
    for p in (d, d.parent):
        entries = _icacls_entries(p)
        assert len(entries) == 1, entries            # nobody else: no Users, Everyone, Administrators
        assert "(F)" in entries[0] and "(I)" not in entries[0], entries
        who = subprocess.run(["whoami"], capture_output=True, text=True).stdout.strip().lower()
        assert who.split("\\")[-1] in entries[0].lower(), (who, entries)


@pytest.mark.skipif(not WINDOWS, reason="Windows ACL")
def test_windows_a_widened_acl_is_repaired_or_refused(home, wiki):
    wid = P.ensure_wiki_id(wiki)
    d = P.secret_dir("auth", wid, wiki_root=wiki)
    subprocess.run(["icacls", str(d), "/grant", "*S-1-1-0:(R)"], capture_output=True, check=True)  # Everyone
    assert len(_icacls_entries(d)) == 2
    try:
        d2 = P.secret_dir("auth", wid, wiki_root=wiki)
    except P.SecretPathError:
        return                                        # refusing is acceptable (fail closed)
    assert len(_icacls_entries(d2)) == 1              # or it was repaired


# ------------------------------------------------------------------------- rebind

def test_rebind_moves_the_binding_to_a_new_location(home, tmp_path, wiki):
    wid = P.ensure_wiki_id(wiki)
    P.secret_dir("auth", wid, wiki_root=wiki)
    P.secret_dir("peers", wid, wiki_root=wiki)
    moved = tmp_path / "wikis" / "moved"
    shutil.copytree(wiki, moved)
    with pytest.raises(P.SecretPathError):
        P.secret_dir("auth", wid, wiki_root=moved)    # refused until explicit
    P.rebind(wid, moved)
    assert P.secret_dir("auth", wid, wiki_root=moved)
    assert P.secret_dir("peers", wid, wiki_root=moved)
    with pytest.raises(P.SecretPathError):            # and the old place no longer matches
        P.secret_dir("auth", wid, wiki_root=wiki)


def test_rebind_restores_a_missing_wiki_id_file(home, tmp_path, wiki):
    wid = P.ensure_wiki_id(wiki)
    P.secret_dir("auth", wid, wiki_root=wiki)
    fresh = tmp_path / "wikis" / "restored"
    fresh.mkdir()
    P.rebind(wid, fresh)
    assert P.ensure_wiki_id(fresh) == wid


def test_rebind_refuses_a_folder_with_a_different_id(home, tmp_path, wiki):
    wid = P.ensure_wiki_id(wiki)
    P.secret_dir("auth", wid, wiki_root=wiki)
    other = tmp_path / "wikis" / "other"
    other.mkdir()
    P.ensure_wiki_id(other)
    with pytest.raises(P.SecretPathError):
        P.rebind(wid, other)


def test_rebind_of_an_unknown_id_is_an_error_not_a_silent_no_op(home, wiki):
    with pytest.raises(P.SecretPathError):
        P.rebind(str(uuid.uuid4()), wiki)


def test_rebind_rejects_unsafe_ids(home, wiki):
    with pytest.raises(P.SecretPathError):
        P.rebind("../x", wiki)


# ------------------------------------------------------------- package discipline

def test_paths_is_a_leaf_module():
    """Stdlib only: no synthadoc.core/config/agents/storage/integration (interface spec section 0)."""
    banned = ("synthadoc.core", "synthadoc.config", "synthadoc.agents",
              "synthadoc.storage", "synthadoc.integration", "synthadoc.skills")
    root = Path(__file__).resolve().parents[3] / "synthadoc" / "security"
    for name in ("paths.py", "_winacl.py"):
        src = root / name
        if not src.exists():
            continue
        for node in ast.walk(ast.parse(src.read_text(encoding="utf-8"))):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                    else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            for m in mods:
                assert not m.startswith(banned), f"{name} imports {m}"
