# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Peter White / axoviq.com
"""The API-key store: ``auth.db`` in the wiki's private secret directory.

The database lives under ``paths.secret_dir("auth", wiki_id, wiki_root=...)``, outside the
wiki folder, so it is never synced, committed or backed up with the wiki. Only a hash of
each key's secret is stored. Connections are short-lived and always closed
(``contextlib.closing``: ``with conn:`` alone only commits). Callers on the event loop
must reach this module through ``asyncio.to_thread``.
"""
from __future__ import annotations

import getpass
import hmac
import json
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from synthadoc.auth import keys
from synthadoc.security import paths

SCHEMA_VERSION = 1
_BUSY_TIMEOUT_MS = 5000

_SCHEMA = """
CREATE TABLE schema_meta (version INTEGER NOT NULL);
CREATE TABLE api_keys (
    key_id       TEXT PRIMARY KEY,
    secret_hash  TEXT NOT NULL,
    name         TEXT NOT NULL,
    role         TEXT,
    scopes       TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    created_by   TEXT NOT NULL,
    expires_at   TEXT,
    revoked_at   TEXT,
    revoked_by   TEXT,
    last_used_at TEXT,
    last_used_ip TEXT
);
CREATE UNIQUE INDEX api_keys_active_name ON api_keys(name COLLATE NOCASE) WHERE revoked_at IS NULL;
CREATE TABLE key_events (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    at     TEXT NOT NULL,
    actor  TEXT NOT NULL,
    event  TEXT NOT NULL,
    key_id TEXT,
    detail TEXT
);
CREATE TRIGGER key_events_no_update BEFORE UPDATE ON key_events
    BEGIN SELECT RAISE(ABORT, 'key_events is append only'); END;
CREATE TRIGGER key_events_no_delete BEFORE DELETE ON key_events
    BEGIN SELECT RAISE(ABORT, 'key_events is append only'); END;
"""

# Compared against when a key id is unknown, so a miss costs the same as a wrong secret.
_DUMMY_HASH = keys.hash_secret("0" * 64)


class AuthStoreError(Exception):
    """A store problem whose message is safe to show to the operator."""


class NameInUse(AuthStoreError):
    pass


@dataclass(frozen=True)
class KeyRecord:
    key_id: str
    name: str
    role: Optional[str]
    scopes: tuple[str, ...]
    created_at: datetime
    created_by: str
    expires_at: Optional[datetime]
    revoked_at: Optional[datetime]
    revoked_by: Optional[str]
    last_used_at: Optional[datetime]
    last_used_ip: Optional[str]

    def status(self, now: Optional[datetime] = None) -> str:
        now = now or datetime.now(timezone.utc)
        if self.revoked_at is not None:
            return "revoked"
        if self.expires_at is not None and self.expires_at <= now:
            return "expired"
        return "active"


@dataclass(frozen=True)
class CreatedKey:
    """What ``create_key`` returns. ``key`` is the only copy of the secret there will ever be."""
    record: KeyRecord
    key: str


@dataclass(frozen=True)
class KeyEvent:
    id: int
    at: datetime
    actor: str
    event: str
    key_id: Optional[str]
    detail: dict


def cli_actor() -> str:
    """``cli:<os user>``. ``os.getlogin`` fails in containers, so use getpass, then the uid."""
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001 - no passwd entry, no env vars
        user = str(os.getuid()) if hasattr(os, "getuid") else "unknown"
    return f"cli:{user}"


def _opt_utc(text: Optional[str]) -> Optional[datetime]:
    return keys.parse_utc(text) if text else None


def _record(row: sqlite3.Row) -> KeyRecord:
    return KeyRecord(
        key_id=row["key_id"], name=row["name"], role=row["role"],
        scopes=tuple(s for s in row["scopes"].split(",") if s),
        created_at=keys.parse_utc(row["created_at"]), created_by=row["created_by"],
        expires_at=_opt_utc(row["expires_at"]), revoked_at=_opt_utc(row["revoked_at"]),
        revoked_by=row["revoked_by"], last_used_at=_opt_utc(row["last_used_at"]),
        last_used_ip=row["last_used_ip"])


class AuthStore:
    def __init__(self, db_path: Path, *, clock: Optional[Callable[[], datetime]] = None) -> None:
        self._db = Path(db_path)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def path(self) -> Path:
        return self._db

    # ------------------------------------------------------------------- opening

    @classmethod
    def open(cls, wiki_root: Path, *, create: bool = True,
             clock: Optional[Callable[[], datetime]] = None) -> Optional["AuthStore"]:
        """Open the store for *wiki_root*.

        With ``create=True`` the wiki id, the secret directory and ``auth.db`` are created
        as needed, and ``wiki_id_created`` is recorded when this call made the id.
        ``paths.secret_dir`` is called exactly once. With ``create=False`` nothing is ever
        created: if there is no wiki id or no ``auth.db`` yet, the result is ``None``
        ("no keys").
        """
        wiki_root = Path(wiki_root)
        if not create:
            wiki_id = paths.read_wiki_id(wiki_root)
            if wiki_id is None:
                return None
            if not (paths.synthadoc_home() / "auth" / wiki_id / "auth.db").is_file():
                return None
            directory = paths.secret_dir("auth", wiki_id, wiki_root=wiki_root)
            store = cls(directory / "auth.db", clock=clock)
            store._init_schema()
            return store

        created: list[str] = []
        wiki_id = paths.ensure_wiki_id(wiki_root, on_created=created.append)
        directory = paths.secret_dir("auth", wiki_id, wiki_root=wiki_root)
        store = cls(directory / "auth.db", clock=clock)
        store._init_schema()
        if created:
            with closing(store._connect()) as conn:
                store._event(conn, cli_actor(), "wiki_id_created", None, {})
        return store

    def _connect(self) -> sqlite3.Connection:
        if not self._db.exists() and os.name != "nt":
            os.close(os.open(self._db, os.O_CREAT | os.O_WRONLY, 0o600))
        conn = sqlite3.connect(self._db, timeout=_BUSY_TIMEOUT_MS / 1000, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                has_meta = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_meta'"
                ).fetchone()
                if not has_meta:
                    for statement in _split_statements(_SCHEMA):
                        conn.execute(statement)
                    conn.execute("INSERT INTO schema_meta(version) VALUES (?)", (SCHEMA_VERSION,))
                else:
                    version = conn.execute("SELECT version FROM schema_meta").fetchone()[0]
                    if version > SCHEMA_VERSION:
                        raise AuthStoreError(
                            "auth.db was written by a newer Synthadoc; upgrade Synthadoc to use it.")
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise

    # -------------------------------------------------------------------- writes

    def _event(self, conn: sqlite3.Connection, actor: str, event: str,
               key_id: Optional[str], detail: dict) -> None:
        conn.execute(
            "INSERT INTO key_events(at, actor, event, key_id, detail) VALUES (?,?,?,?,?)",
            (keys.format_utc(self._clock()), actor, event, key_id, json.dumps(detail, sort_keys=True)))

    def create_key(self, name: str, scopes: tuple[str, ...], *, role: Optional[str] = None,
                   expires_at: Optional[datetime] = None, actor: Optional[str] = None) -> CreatedKey:
        keys.validate_name(name)
        actor = actor or cli_actor()
        now = keys.format_utc(self._clock())
        expires = keys.format_utc(expires_at) if expires_at else None
        scope_text = ",".join(scopes)
        with closing(self._connect()) as conn:
            for _attempt in range(5):
                new = keys.generate_key()
                conn.execute("BEGIN IMMEDIATE")
                try:
                    conn.execute(
                        "INSERT INTO api_keys(key_id, secret_hash, name, role, scopes, created_at,"
                        " created_by, expires_at) VALUES (?,?,?,?,?,?,?,?)",
                        (new.key_id, new.secret_hash, name, role, scope_text, now, actor, expires))
                    self._event(conn, actor, "key_created", new.key_id,
                                {"name": name, "role": role, "scopes": scope_text, "expires_at": expires})
                    conn.execute("COMMIT")
                except sqlite3.IntegrityError as exc:
                    conn.execute("ROLLBACK")
                    if "api_keys.key_id" in str(exc):
                        continue                      # one-in-2^48 id collision: draw again
                    raise NameInUse(f"A key named '{name}' is already in use. "
                                    "Revoke it first or pick another name.") from None
                except BaseException:
                    conn.execute("ROLLBACK")
                    raise
                row = conn.execute("SELECT * FROM api_keys WHERE key_id = ?", (new.key_id,)).fetchone()
                return CreatedKey(_record(row), new.key)
        raise AuthStoreError("Could not generate a unique key id; try again.")

    def revoke_key(self, ident: str, *, actor: Optional[str] = None) -> Optional[tuple[KeyRecord, bool]]:
        """Revoke by key id or by name. ``(record, changed)``; ``changed`` is False when the
        key was already revoked. ``None`` when nothing matches."""
        actor = actor or cli_actor()
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if keys.looks_like_key_id(ident):
                    row = conn.execute("SELECT * FROM api_keys WHERE key_id = ?", (ident.lower(),)).fetchone()
                else:
                    row = conn.execute(
                        "SELECT * FROM api_keys WHERE name = ? COLLATE NOCASE AND revoked_at IS NULL",
                        (ident,)).fetchone()
                if row is None:
                    conn.execute("ROLLBACK")
                    return None
                if row["revoked_at"] is not None:
                    conn.execute("ROLLBACK")
                    return _record(row), False
                conn.execute("UPDATE api_keys SET revoked_at = ?, revoked_by = ? WHERE key_id = ?",
                             (keys.format_utc(self._clock()), actor, row["key_id"]))
                self._event(conn, actor, "key_revoked", row["key_id"], {"name": row["name"]})
                conn.execute("COMMIT")
            except BaseException:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.OperationalError:
                    pass                              # already rolled back above
                raise
            row = conn.execute("SELECT * FROM api_keys WHERE key_id = ?", (row["key_id"],)).fetchone()
            return _record(row), True

    # --------------------------------------------------------------------- reads

    def verify_key(self, presented: object) -> Optional[KeyRecord]:
        """The key's record when *presented* is a live key, else ``None`` (one answer for
        every failure: malformed, unknown, wrong secret, revoked, expired)."""
        parsed = keys.parse_key(presented)
        if parsed is None:
            return None
        key_id, secret = parsed
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM api_keys WHERE key_id = ?", (key_id,)).fetchone()
        stored = row["secret_hash"] if row is not None else _DUMMY_HASH
        matched = hmac.compare_digest(stored, keys.hash_secret(secret))
        if row is None or not matched:
            return None
        record = _record(row)
        return record if record.status(self._clock()) == "active" else None

    def list_keys(self, *, include_inactive: bool = False) -> list[KeyRecord]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM api_keys ORDER BY rowid").fetchall()
        records = [_record(r) for r in rows]
        if include_inactive:
            return records
        now = self._clock()
        return [r for r in records if r.status(now) == "active"]

    def events(self) -> list[KeyEvent]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM key_events ORDER BY id").fetchall()
        return [KeyEvent(r["id"], keys.parse_utc(r["at"]), r["actor"], r["event"], r["key_id"],
                         json.loads(r["detail"] or "{}")) for r in rows]


def _split_statements(script: str) -> list[str]:
    """Split the schema on top-level semicolons (triggers contain one inside BEGIN...END)."""
    statements, current, depth = [], [], 0
    for line in script.strip().splitlines():
        current.append(line)
        upper = line.strip().upper()
        if upper.startswith("BEGIN"):
            depth += 1
        if upper.endswith("END;"):
            depth -= 1
        if depth <= 0 and line.rstrip().endswith(";"):
            statements.append("\n".join(current))
            current = []
    return statements
