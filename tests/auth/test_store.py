# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Peter White / axoviq.com
from __future__ import annotations

import logging
import os
import sqlite3
import stat
import threading
from contextlib import closing
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from synthadoc.auth import keys
from synthadoc.auth.store import AuthStore, AuthStoreError, NameInUse
from synthadoc.security import paths

T0 = datetime(2026, 11, 27, 12, 0, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    monkeypatch.setenv("SYNTHADOC_HOME", str(home))
    return home, wiki


@pytest.fixture
def store(env):
    clock = Clock()
    s = AuthStore.open(env[1], clock=clock)
    s.clock = clock
    return s


def test_create_then_verify(store):
    made = store.create_key("ci", ("read",))
    assert made.key.startswith("sd_") and made.record.name == "ci"
    got = store.verify_key(made.key)
    assert got is not None and got.key_id == made.record.key_id and got.scopes == ("read",)


def test_every_verify_failure_is_the_same_none(store):
    made = store.create_key("ci", ("read",))
    kid, secret = keys.parse_key(made.key)
    wrong = f"sd_{kid}_{'0' * 64}"
    unknown = f"sd_{'f' * 12}_{secret}"
    assert [store.verify_key(x) for x in (wrong, unknown, "garbage", "", None)] == [None] * 5


def test_unknown_id_still_does_one_comparison(store):
    with patch("synthadoc.auth.store.hmac.compare_digest", wraps=__import__("hmac").compare_digest) as spy:
        store.verify_key(f"sd_{'f' * 12}_{'a' * 64}")
    assert spy.call_count == 1


def test_revoked_and_expired_keys_fail(store):
    k1 = store.create_key("a", ("read",))
    k2 = store.create_key("b", ("read",), expires_at=T0 + timedelta(hours=1))
    store.revoke_key("a")
    assert store.verify_key(k1.key) is None
    assert store.verify_key(k2.key) is not None
    store.clock.now = T0 + timedelta(hours=1)
    assert store.verify_key(k2.key) is None


def test_names_are_unique_ignoring_case_among_active_keys_and_reusable_after_revoke(store):
    store.create_key("Alice", ("read",))
    with pytest.raises(NameInUse, match="already in use"):
        store.create_key("alice", ("read",))
    store.revoke_key("ALICE")
    store.create_key("alice", ("read",))


def test_bad_names_are_refused(store):
    for bad in ("", "x y", "0123456789ab", "esc\x1b[0m", "x" * 65):
        with pytest.raises(ValueError):
            store.create_key(bad, ("read",))


def test_list_hides_inactive_by_default_and_never_returns_a_hash(store):
    store.create_key("a", ("read",))
    store.create_key("b", ("read", "write"), role="contributor")
    store.revoke_key("a")
    assert [r.name for r in store.list_keys()] == ["b"]
    assert [r.name for r in store.list_keys(include_inactive=True)] == ["a", "b"]
    assert not any(hasattr(r, "secret_hash") for r in store.list_keys(include_inactive=True))


def test_revoke_by_id_by_name_and_idempotently(store):
    a = store.create_key("a", ("read",))
    record, changed = store.revoke_key(a.record.key_id)
    assert changed and record.status() == "revoked"
    record, changed = store.revoke_key(a.record.key_id)
    assert not changed
    assert store.revoke_key("nope") is None
    assert store.revoke_key("a") is None              # by name only finds active keys
    assert [e.event for e in store.events()].count("key_revoked") == 1


def test_events_hold_no_secret_or_hash(store):
    made = store.create_key("ci", ("read",))
    kid, secret = keys.parse_key(made.key)
    store.revoke_key("ci")
    with closing(sqlite3.connect(store.path)) as conn:
        rows = conn.execute("SELECT detail FROM key_events").fetchall()
    blob = " ".join(r[0] for r in rows)
    assert secret not in blob and keys.hash_secret(secret) not in blob
    assert [e.event for e in store.events()] == ["wiki_id_created", "key_created", "key_revoked"]


def test_key_events_is_append_only(store):
    store.create_key("ci", ("read",))
    with closing(sqlite3.connect(store.path)) as conn:
        with pytest.raises(sqlite3.DatabaseError, match="append only"):
            conn.execute("UPDATE key_events SET actor = 'x'")
        with pytest.raises(sqlite3.DatabaseError, match="append only"):
            conn.execute("DELETE FROM key_events")


def test_open_records_wiki_id_created_once(env):
    first = AuthStore.open(env[1])
    second = AuthStore.open(env[1])
    assert [e.event for e in second.events()] == ["wiki_id_created"]
    assert first.path == second.path


def test_secret_dir_is_called_exactly_once_per_open(env):
    with patch("synthadoc.auth.store.paths.secret_dir", wraps=paths.secret_dir) as spy:
        AuthStore.open(env[1])
    assert spy.call_count == 1


def test_read_only_open_creates_nothing(env):
    home, wiki = env
    assert AuthStore.open(wiki, create=False) is None
    assert not home.exists() and not (wiki / ".synthadoc").exists()
    paths.ensure_wiki_id(wiki)                         # an id but still no auth.db
    assert AuthStore.open(wiki, create=False) is None
    assert not (home / "auth").exists()


def test_read_only_open_finds_an_existing_store(env):
    AuthStore.open(env[1]).create_key("ci", ("read",))
    ro = AuthStore.open(env[1], create=False)
    assert [r.name for r in ro.list_keys()] == ["ci"]


def test_a_newer_schema_is_refused(env):
    s = AuthStore.open(env[1])
    with closing(sqlite3.connect(s.path)) as conn:
        conn.execute("UPDATE schema_meta SET version = 99")
        conn.commit()
    with pytest.raises(AuthStoreError, match="newer Synthadoc"):
        AuthStore.open(env[1])


def test_the_database_is_private_to_the_user(store):
    """POSIX: the file is mode 0600 inside a 0700 directory. Windows has no modes: the file
    inherits the private directory's access list (only the user), so check the directory,
    the same check ``paths.secret_dir`` makes."""
    directory = store.path.parent
    if os.name == "nt":
        assert paths._private_ok_windows(directory)
    else:
        assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
        assert paths._private_ok_posix(directory)
    assert store.path.is_file() and store.path.parent.parent.parent == paths.synthadoc_home()


def test_wal_mode_is_on(store):
    with closing(sqlite3.connect(store.path)) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_concurrent_creates_with_one_name_yield_exactly_one_key(store):
    results, errors = [], []

    def worker():
        try:
            results.append(AuthStore(store.path).create_key("ci", ("read",)))
        except NameInUse as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(results) == 1 and len(errors) == 5


def test_no_secret_reaches_logs_or_errors_on_failure_paths(store, caplog):
    made = store.create_key("ci", ("read",))
    kid, secret = keys.parse_key(made.key)
    caught = []
    with caplog.at_level(logging.DEBUG):
        for call in (lambda: store.create_key("ci", ("read",)),
                     lambda: store.create_key("bad name", ("read",))):
            try:
                call()
            except Exception as exc:  # noqa: BLE001
                caught.append(str(exc))
        store.verify_key(f"sd_{kid}_{'0' * 64}")
        store.revoke_key("ci")
        store.verify_key(made.key)
    text = " ".join(caught) + caplog.text
    assert secret not in text and made.key not in text
