# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any, Optional
import aiosqlite

# Default cache version — overridden by [cache] version in config.toml.
# Users can bump this in config without touching source code.
CACHE_VERSION = "4"


def make_cache_key(operation: str, inputs: dict, version: str = CACHE_VERSION) -> str:
    payload = json.dumps(
        {"v": version, "op": operation, "inputs": inputs}, sort_keys=True
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def make_query_cache_key(question: str, epoch: int, model: str = "") -> str:
    normalized = " ".join(question.lower().split())
    payload = f"{normalized}|{epoch}|{model}"
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


class CacheManager:
    def __init__(self, db_path: Path) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS response_cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )""")
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS query_cache (
                cache_key    TEXT PRIMARY KEY,
                wiki_epoch   INTEGER NOT NULL,
                result_json  TEXT NOT NULL,
                created_at   TEXT NOT NULL DEFAULT (datetime('now'))
            )""")
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    def __del__(self) -> None:
        # Synchronous best-effort cleanup for GC scenarios (tests, CLI short-lived
        # instances). close() is preferred; this prevents file locks on Windows when
        # the async close() was never awaited.
        if self._conn is not None:
            try:
                raw = getattr(self._conn, "_connection", None)
                if raw is not None:
                    raw.close()
            except Exception:
                pass
            self._conn = None

    async def get(self, key: str) -> Any:
        async with self._conn.execute(
            "SELECT value FROM response_cache WHERE key=?", (key,)
        ) as cur:
            row = await cur.fetchone()
        return json.loads(row["value"]) if row else None

    async def set(self, key: str, value: Any) -> None:
        await self._conn.execute(
            "INSERT OR REPLACE INTO response_cache (key,value) VALUES (?,?)",
            (key, json.dumps(value)),
        )
        await self._conn.commit()

    async def clear(self) -> int:
        """Delete all cached entries (both response and query caches). Returns total rows removed."""
        cur1 = await self._conn.execute("DELETE FROM response_cache")
        cur2 = await self._conn.execute("DELETE FROM query_cache")
        await self._conn.commit()
        return cur1.rowcount + cur2.rowcount

    async def get_query(self, key: str) -> Optional[Any]:
        async with self._conn.execute(
            "SELECT result_json FROM query_cache WHERE cache_key=?", (key,)
        ) as cur:
            row = await cur.fetchone()
        return json.loads(row["result_json"]) if row else None

    async def set_query(self, key: str, epoch: int, result: Any) -> None:
        # INSERT OR REPLACE on PRIMARY KEY conflict: deletes the old row and inserts
        # a new one (resetting created_at). This is intentional — the result is new.
        await self._conn.execute(
            "INSERT OR REPLACE INTO query_cache (cache_key, wiki_epoch, result_json) VALUES (?,?,?)",
            (key, epoch, json.dumps(result)),
        )
        await self._conn.commit()

    async def cleanup_query_cache(self, current_epoch: int) -> int:
        """Remove stale cache entries (epoch < current_epoch - 5 or older than 7 days)."""
        cur = await self._conn.execute(
            """DELETE FROM query_cache
               WHERE wiki_epoch < ?
                  OR created_at < datetime('now', '-7 days')""",
            (current_epoch - 5,),
        )
        await self._conn.commit()
        return cur.rowcount
