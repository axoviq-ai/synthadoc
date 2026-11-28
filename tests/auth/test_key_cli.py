# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Peter White / axoviq.com
from __future__ import annotations

import re

import pytest
from typer.testing import CliRunner

from synthadoc.auth import keys
from synthadoc.auth.store import AuthStore
from synthadoc.cli.main import app
from synthadoc.security import paths

runner = CliRunner()
KEY_RE = re.compile(r"sd_[0-9a-f]{12}_[0-9a-f]{64}")


@pytest.fixture
def env(tmp_path, monkeypatch):
    home, wiki = tmp_path / "home", tmp_path / "wiki"
    wiki.mkdir()
    monkeypatch.setenv("SYNTHADOC_HOME", str(home))
    return home, wiki


def run(wiki, *args):
    return runner.invoke(app, [*args, "-w", str(wiki)])


def test_create_prints_the_key_once_and_it_verifies(env):
    _home, wiki = env
    res = run(wiki, "key", "create", "--name", "alice", "--role", "contributor")
    assert res.exit_code == 0, res.output
    key = KEY_RE.search(res.output).group(0)
    assert "cannot be shown again" in res.output
    store = AuthStore.open(wiki, create=False)
    rec = store.verify_key(key)
    assert rec.name == "alice" and rec.role == "contributor" and rec.scopes == ("read", "write")


def test_quiet_prints_only_the_key(env):
    res = run(env[1], "key", "create", "--name", "ci", "--scopes", "read", "--quiet")
    assert res.exit_code == 0
    assert KEY_RE.fullmatch(res.stdout.strip())


@pytest.mark.parametrize("extra", [[], ["--role", "admin", "--scopes", "read"]])
def test_exactly_one_of_role_or_scopes(env, extra):
    res = run(env[1], "key", "create", "--name", "x", *extra)
    assert res.exit_code == 2 and "exactly one" in res.output


@pytest.mark.parametrize("args, message", [
    (["--role", "root"], "Unknown role"),
    (["--scopes", "read,root"], "Unknown scope"),
    (["--scopes", "read", "--expires", "soon"], "expiry"),
])
def test_bad_options_are_errors_and_create_nothing(env, args, message):
    home, wiki = env
    res = run(wiki, "key", "create", "--name", "x", *args)
    assert res.exit_code == 2 and message in res.output
    assert AuthStore.open(wiki, create=False) is None


def test_bad_name_is_an_error(env):
    res = run(env[1], "key", "create", "--name", "0123456789ab", "--role", "viewer")
    assert res.exit_code == 2 and "key id" in res.output


def test_duplicate_name_is_a_clear_error(env):
    run(env[1], "key", "create", "--name", "ci", "--role", "viewer")
    res = run(env[1], "key", "create", "--name", "CI", "--role", "viewer")
    assert res.exit_code == 1 and "already in use" in res.output


def test_list_shows_keys_and_never_a_secret_or_hash(env):
    made = run(env[1], "key", "create", "--name", "ci", "--role", "operator", "--expires", "30d")
    key = KEY_RE.search(made.output).group(0)
    _, _, secret = key.split("_")
    res = run(env[1], "key", "list")
    assert res.exit_code == 0
    assert "ci" in res.output and "operator" in res.output and "active" in res.output
    assert secret not in res.output and keys.hash_secret(secret) not in res.output


def test_list_and_revoke_on_a_wiki_with_no_store_create_nothing(env):
    home, wiki = env
    res = run(wiki, "key", "list")
    assert res.exit_code == 0 and "No keys" in res.output
    res = run(wiki, "key", "revoke", "ci")
    assert res.exit_code == 1 and "No keys" in res.output
    assert not home.exists() and not (wiki / ".synthadoc").exists()


def test_revoke_by_name_and_by_id_and_twice(env):
    _home, wiki = env
    a = run(wiki, "key", "create", "--name", "a", "--role", "viewer")
    b = run(wiki, "key", "create", "--name", "b", "--role", "viewer")
    b_id = KEY_RE.search(b.output).group(0).split("_")[1]
    assert "Revoked: 'a'" in run(wiki, "key", "revoke", "a").output
    assert "Revoked: 'b'" in run(wiki, "key", "revoke", b_id).output
    assert "Already revoked" in run(wiki, "key", "revoke", b_id).output
    missing = run(wiki, "key", "revoke", "nope")
    assert missing.exit_code == 1 and "No active key" in missing.output
    assert "No keys" in run(wiki, "key", "list").output
    assert "revoked" in run(wiki, "key", "list", "--all").output


def test_revoking_the_last_admin_key_says_so(env):
    _home, wiki = env
    run(wiki, "key", "create", "--name", "root", "--role", "admin")
    out = run(wiki, "key", "revoke", "root").output
    assert "no active admin key is left" in out
    assert "synthadoc key create --name <name> --role admin" in out     # a command that actually works


def test_rebind_after_a_move_uses_the_id_in_the_folder(env, tmp_path):
    home, wiki = env
    run(wiki, "key", "create", "--name", "ci", "--role", "viewer")
    moved = tmp_path / "moved"
    wiki.rename(moved)
    res = run(moved, "key", "list")                    # refused: bound to the old folder
    assert res.exit_code == 1
    res = run(moved, "wiki", "rebind")
    assert res.exit_code == 0 and "Rebound" in res.output
    assert "ci" in run(moved, "key", "list").output


def test_rebind_needs_an_id_for_a_folder_without_one(env):
    res = run(env[1], "wiki", "rebind")
    assert res.exit_code == 2 and "--wiki-id" in res.output


def test_rebind_refuses_a_mismatched_id(env):
    _home, wiki = env
    run(wiki, "key", "create", "--name", "ci", "--role", "viewer")
    res = run(wiki, "wiki", "rebind", "--wiki-id", "00000000-0000-4000-8000-000000000000")
    assert res.exit_code == 1


def test_a_secret_path_error_shows_only_the_public_message(env, tmp_path, monkeypatch):
    home, wiki = env
    monkeypatch.setenv("SYNTHADOC_HOME", str(wiki / "inside"))     # a home inside the wiki is refused
    res = run(wiki, "key", "create", "--name", "x", "--role", "viewer")
    assert res.exit_code == 1
    assert paths.SecretPathError.public_message in res.output
    assert "inside the wiki folder" not in res.output        # the log-only detail
    assert str(wiki / "inside") not in res.output


def test_when_uses_a_fixed_width_utc_offset_not_a_zone_name():
    from datetime import datetime, timedelta, timezone
    from synthadoc.cli.auth import _when
    moment = datetime(2026, 12, 28, 1, 59, tzinfo=timezone.utc)
    assert _when(moment, timezone(timedelta(hours=-5))) == "2026-12-27 20:59 UTC-05:00"
    assert _when(moment, timezone(timedelta(hours=5, minutes=30))) == "2026-12-28 07:29 UTC+05:30"
    assert _when(None) == "never"


def test_list_columns_never_run_together(env):
    run(env[1], "key", "create", "--name", "ci", "--scopes", "read", "--expires", "30d")
    row = run(env[1], "key", "list").stdout.splitlines()[-1]
    assert re.search(r"UTC[+-]\d\d:\d\d +never$", row), row
