# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Acceptance tests for ``synthadoc.security.paths`` (interface spec section 3).

Stdlib + pytest only, so the lean CI job runs this on every supported Python
version and on Linux, macOS and Windows. Platform-specific assertions (POSIX
modes, the Windows ACL) are real tests on their own platform, not skips of a
shared one.
"""
from __future__ import annotations

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


def test_a_failing_on_created_callback_does_not_block_or_repeat(wiki, caplog):
    """The id file already exists when the callback runs, so it can never be retried;
    an audit outage must not turn into a wiki that cannot get a secret directory."""
    calls = []

    def broken(new_id):
        calls.append(new_id)
        raise RuntimeError("audit database is down")

    with caplog.at_level("ERROR", logger="synthadoc.security.paths"):
        wid = P.ensure_wiki_id(wiki, on_created=broken)
    assert UUID_RE.match(wid) and calls == [wid]
    assert any("audit database is down" in (r.exc_text or r.getMessage()) or r.exc_info
               for r in caplog.records)
    assert P.ensure_wiki_id(wiki, on_created=broken) == wid       # later calls work
    assert calls == [wid]


@pytest.mark.parametrize("blank", ["", "  \n"])
def test_a_blank_wiki_id_file_from_a_crash_is_healed(wiki, blank):
    """A crash between creating the file and writing the id leaves it empty."""
    f = wiki / ".synthadoc" / "wiki_id"
    f.parent.mkdir()
    f.write_text(blank, encoding="utf-8")
    os.utime(f, (1_000_000_000, 1_000_000_000))        # long ago: nobody is still writing it
    wid = P.ensure_wiki_id(wiki)
    assert UUID_RE.match(wid)
    assert f.read_text(encoding="utf-8").strip() == wid
    assert P.ensure_wiki_id(wiki) == wid


@pytest.mark.parametrize("bad", ["not-a-uuid", "../../etc/passwd",
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


def test_a_different_spelling_of_the_path_is_judged_by_what_the_filesystem_says(home, wiki):
    """Windows and default macOS ignore case, so a case-variant IS the same folder and must be
    accepted. On a case-sensitive filesystem it is a different (here non-existent) folder and
    must be refused. The test asks the filesystem which one it is, so it runs everywhere."""
    wid = P.ensure_wiki_id(wiki)
    P.secret_dir("auth", wid, wiki_root=wiki)
    variant = Path(str(wiki).swapcase())
    if variant.exists() and os.path.samefile(variant, wiki):
        assert P.secret_dir("auth", wid, wiki_root=variant) == home / "auth" / wid
    else:
        with pytest.raises(P.SecretPathError):
            P.secret_dir("auth", wid, wiki_root=variant)


def _pretend_case_insensitive(monkeypatch, *pair: Path) -> None:
    """Make samefile report the given folders as one, as a case-insensitive filesystem
    (default macOS, Windows) does for /x/Wiki and /x/wiki. Deterministic on every OS."""
    real = os.path.samefile
    folders = {os.path.normcase(os.path.realpath(str(p))) for p in pair}

    def fake(a, b):
        ka, kb = (os.path.normcase(os.path.realpath(str(x))) for x in (a, b))
        return (ka in folders and kb in folders) or real(a, b)

    monkeypatch.setattr(os.path, "samefile", fake)


def test_binding_compares_folders_by_identity_not_by_spelling(home, tmp_path, wiki, monkeypatch):
    """On a case-insensitive filesystem the same folder can be spelled two ways that differ as
    strings. A string-only comparison refused the legitimate caller (seen on macOS CI)."""
    wid = P.ensure_wiki_id(wiki)
    P.secret_dir("auth", wid, wiki_root=wiki)
    spelled_differently = tmp_path / "wikis" / "W1-other-spelling"
    spelled_differently.mkdir()
    with pytest.raises(P.SecretPathError):             # without the filesystem's say-so: different
        P.secret_dir("auth", wid, wiki_root=spelled_differently)
    _pretend_case_insensitive(monkeypatch, wiki, spelled_differently)
    assert P.secret_dir("auth", wid, wiki_root=spelled_differently) == home / "auth" / wid


def test_a_missing_recorded_folder_is_a_mismatch_not_a_crash(home, tmp_path, wiki):
    import json
    wid = P.ensure_wiki_id(wiki)
    d = P.secret_dir("auth", wid, wiki_root=wiki)
    (d / "binding.json").write_text(
        json.dumps({"wiki_id": wid, "last_path": str(tmp_path / "gone")}), encoding="utf-8")
    with pytest.raises(P.SecretPathError):
        P.secret_dir("auth", wid, wiki_root=wiki)


def test_home_inside_the_wiki_is_refused(tmp_path, wiki, monkeypatch):
    monkeypatch.setenv("SYNTHADOC_HOME", str(wiki / "secrets"))
    wid = P.ensure_wiki_id(wiki)
    with pytest.raises(P.SecretPathError):
        P.secret_dir("auth", wid, wiki_root=wiki)


def test_home_inside_the_wiki_is_refused_even_when_spelled_differently(tmp_path, wiki, monkeypatch):
    """The fail-open direction: on a case-insensitive filesystem a home written as
    /x/Wiki/secrets is inside /x/wiki, but a string comparison says it is not."""
    alias = tmp_path / "alias"
    alias.mkdir()
    _pretend_case_insensitive(monkeypatch, alias, wiki)
    monkeypatch.setenv("SYNTHADOC_HOME", str(alias / "secrets"))
    wid = P.ensure_wiki_id(wiki)
    with pytest.raises(P.SecretPathError):
        P.secret_dir("auth", wid, wiki_root=wiki)
    assert not (alias / "secrets").exists()            # refused before creating anything


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


# ----------------------------------------- directory privacy: one test, every OS
#
# These run on Linux, macOS AND Windows with no skips. Only the mechanism behind the
# three helpers differs (mode bits and owner on POSIX, the ACL on Windows), and each
# helper reads the result back independently of the implementation under test.

def _icacls_entries(path: Path) -> list:
    out = subprocess.run(["icacls", str(path)], capture_output=True, text=True, check=True).stdout
    return [ln for ln in out.splitlines() if ":(" in ln]


def _assert_private(path: Path) -> None:
    """Only the current user can use *path*."""
    if WINDOWS:
        entries = _icacls_entries(path)
        assert len(entries) == 1, entries            # nobody else: no Users, Everyone, Administrators
        assert "(F)" in entries[0] and "(I)" not in entries[0], entries   # full control, not inherited
        who = subprocess.run(["whoami"], capture_output=True, text=True).stdout.strip().lower()
        assert who.split("\\")[-1] in entries[0].lower(), (who, entries)
        from synthadoc.security import _winacl      # an owner can rewrite the ACL later
        assert _winacl._owner_sid(str(path)) == _winacl.current_user_sid()
    else:
        st = path.lstat()
        assert (st.st_mode & 0o777) == 0o700, oct(st.st_mode)
        assert st.st_uid == os.getuid()


def _widen(path: Path) -> None:
    """Let others in, as a careless chmod or an inherited ACL would."""
    if WINDOWS:
        subprocess.run(["icacls", str(path), "/grant", "*S-1-1-0:(R)"], capture_output=True, check=True)
        assert len(_icacls_entries(path)) == 2       # the widening really happened
    else:
        os.chmod(path, 0o755)
        assert (path.lstat().st_mode & 0o077) != 0


def _is_widened(path: Path) -> bool:
    if WINDOWS:
        return len(_icacls_entries(path)) > 1
    return (path.lstat().st_mode & 0o077) != 0


def _link(link: Path, target: Path) -> None:
    """A symlink on POSIX, a junction on Windows (needs no privilege)."""
    if WINDOWS:
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                       capture_output=True, check=True)
    else:
        link.symlink_to(target, target_is_directory=True)


def test_secret_directories_are_private_to_the_current_user(home, wiki):
    d = P.secret_dir("auth", P.ensure_wiki_id(wiki), wiki_root=wiki)
    _assert_private(d)
    _assert_private(d.parent)


def test_widened_permissions_on_an_existing_directory_are_repaired(home, wiki):
    wid = P.ensure_wiki_id(wiki)
    d = P.secret_dir("auth", wid, wiki_root=wiki)
    _widen(d)
    _assert_private(P.secret_dir("auth", wid, wiki_root=wiki))


def _pretend_owned_by_someone_else(monkeypatch) -> None:
    """Make the owner of every directory look like another account's, on any OS."""
    if WINDOWS:
        from synthadoc.security import _winacl
        system_sid = bytes([1, 1, 0, 0, 0, 0, 0, 5, 18, 0, 0, 0])       # S-1-5-18, LocalSystem
        monkeypatch.setattr(_winacl, "_owner_sid", lambda path: system_sid)
    else:
        real = os.getuid()
        monkeypatch.setattr(os, "getuid", lambda: real + 1)


def test_a_directory_owned_by_someone_else_is_refused(home, wiki, monkeypatch):
    """Whoever owns a directory can rewrite its permissions later, so a correct ACL or
    mode on a directory somebody else owns proves nothing. Same rule on every OS."""
    wid = P.ensure_wiki_id(wiki)
    d = P.secret_dir("auth", wid, wiki_root=wiki)
    _widen(d.parent)                           # the first folder checked; a wrongly attempted
    _widen(d)                                  # repair would be visible on both
    _pretend_owned_by_someone_else(monkeypatch)
    with pytest.raises(P.SecretPathError):
        P.secret_dir("auth", wid, wiki_root=wiki)
    monkeypatch.undo()
    assert _is_widened(d.parent) and _is_widened(d)    # refused, not adopted and quietly "fixed"


def test_blank_wiki_id_file_that_is_still_fresh_is_left_alone(wiki):
    """Another process may be mid-write; only a stale blank file is healed."""
    f = wiki / ".synthadoc" / "wiki_id"
    f.parent.mkdir()
    f.write_text("", encoding="utf-8")
    with pytest.raises(P.SecretPathError):
        P.ensure_wiki_id(wiki)
    assert f.exists() and f.read_text(encoding="utf-8") == ""


def test_widened_permissions_are_repaired_with_a_warning(home, wiki, caplog):
    wid = P.ensure_wiki_id(wiki)
    d = P.secret_dir("auth", wid, wiki_root=wiki)
    with caplog.at_level("WARNING", logger="synthadoc.security.paths"):
        P.secret_dir("auth", wid, wiki_root=wiki)
    assert not caplog.records                          # a healthy directory is silent
    _widen(d)
    with caplog.at_level("WARNING", logger="synthadoc.security.paths"):
        P.secret_dir("auth", wid, wiki_root=wiki)
    assert any("repaired" in r.getMessage() for r in caplog.records)


def test_creating_a_directory_is_not_reported_as_a_repair(home, wiki, caplog):
    wid = P.ensure_wiki_id(wiki)
    with caplog.at_level("WARNING", logger="synthadoc.security.paths"):
        P.secret_dir("auth", wid, wiki_root=wiki)
    assert not caplog.records


def test_a_link_in_place_of_the_secret_directory_is_refused(home, tmp_path, wiki):
    wid = P.ensure_wiki_id(wiki)
    (home / "auth").mkdir(parents=True)
    target = tmp_path / "elsewhere"
    target.mkdir()
    _link(home / "auth" / wid, target)
    with pytest.raises(P.SecretPathError):
        P.secret_dir("auth", wid, wiki_root=wiki)
    assert not (target / "binding.json").exists()     # nothing was written through the link


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
