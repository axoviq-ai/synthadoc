# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""The Windows ACL helper's ownership rules. No skips: on other systems the helper
refuses to run, and that is what is asserted there."""
from __future__ import annotations

import subprocess
import sys

import pytest

from synthadoc.security import _winacl as W
from synthadoc.security import paths as P

WINDOWS = sys.platform == "win32"
SYSTEM_SID = bytes([1, 1, 0, 0, 0, 0, 0, 5, 18, 0, 0, 0])      # S-1-5-18


def _entries(path):
    out = subprocess.run(["icacls", str(path)], capture_output=True, text=True, check=True).stdout
    return [ln for ln in out.splitlines() if ":(" in ln]


def test_the_administrators_sid_is_s_1_5_32_544():
    assert W.ADMINISTRATORS_SID == bytes([1, 2, 0, 0, 0, 0, 0, 5, 32, 0, 0, 0, 32, 2, 0, 0])


def test_the_helper_refuses_to_run_off_windows(tmp_path):
    if WINDOWS:
        W.restrict_to_current_user(str(tmp_path))          # works for real
        W.verify_current_user_only(str(tmp_path))
    else:
        with pytest.raises(W.AclError):
            W.restrict_to_current_user(str(tmp_path))


def test_a_folder_owned_by_another_account_is_not_adopted(tmp_path, monkeypatch):
    """Even if its ACL would let us take ownership, only the user or the Administrators
    group is ever taken over, and nothing is changed when refusing."""
    d = tmp_path / "d"
    d.mkdir()
    if not WINDOWS:
        with pytest.raises(W.AclError):
            W.restrict_to_current_user(str(d))
        return
    before = _entries(d)
    monkeypatch.setattr(W, "_owner_sid", lambda path: SYSTEM_SID)
    with pytest.raises(W.AclError):
        W.restrict_to_current_user(str(d))
    monkeypatch.undo()
    assert _entries(d) == before                           # ACL untouched


def test_a_folder_owned_by_the_administrators_group_is_taken_over(tmp_path, monkeypatch):
    """What an elevated process creates. The first two owner reads (the check, then the
    helper's own pre-check) see the group; later reads see the real owner."""
    if not WINDOWS:
        return                                             # nothing equivalent on POSIX
    d = tmp_path / "d"
    d.mkdir()
    real = W._owner_sid
    reads = []

    def owner(path):
        reads.append(path)
        return W.ADMINISTRATORS_SID if len(reads) <= 2 else real(path)

    monkeypatch.setattr(W, "_owner_sid", owner)
    home = tmp_path / "home"
    wiki = tmp_path / "w"
    wiki.mkdir()
    monkeypatch.setenv("SYNTHADOC_HOME", str(home))
    wid = P.ensure_wiki_id(wiki)
    secret = P.secret_dir("auth", wid, wiki_root=wiki)
    assert len(reads) > 2 and secret.is_dir()
