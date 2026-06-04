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

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS response_cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )""")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS query_cache (
                    cache_key    TEXT PRIMARY KEY,
                    wiki_epoch   INTEGER NOT NULL,
                    result_json  TEXT NOT NULL,
                    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
                )""")
            await db.commit()

    async def get(self, key: str) -> Any:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT value FROM response_cache WHERE key=?", (key,)
            ) as cur:
                row = await cur.fetchone()
            return json.loads(row["value"]) if row else None

    async def set(self, key: str, value: Any) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO response_cache (key,value) VALUES (?,?)",
                (key, json.dumps(value)),
            )
            await db.commit()

    async def clear(self) -> int:
        """Delete all cached entries. Returns the number of rows removed."""
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute("DELETE FROM response_cache")
            await db.commit()
            return cur.rowcount

    async def get_query(self, key: str) -> Optional[Any]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT result_json FROM query_cache WHERE cache_key=?", (key,)
            ) as cur:
                row = await cur.fetchone()
            return json.loads(row["result_json"]) if row else None

    async def set_query(self, key: str, epoch: int, result: Any) -> None:
        # INSERT OR REPLACE on PRIMARY KEY conflict: deletes the old row and inserts
        # a new one (resetting created_at). This is intentional — the result is new.
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO query_cache (cache_key, wiki_epoch, result_json) VALUES (?,?,?)",
                (key, epoch, json.dumps(result)),
            )
            await db.commit()

    async def cleanup_query_cache(self, current_epoch: int) -> int:
        """Remove stale cache entries (epoch < current_epoch - 5 or older than 7 days)."""
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                """DELETE FROM query_cache
                   WHERE wiki_epoch < ?
                      OR created_at < datetime('now', '-7 days')""",
                (current_epoch - 5,),
            )
            await db.commit()
            return cur.rowcount
