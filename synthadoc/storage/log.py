# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite

CITATION_EXCERPT_LEN = 100


class LogWriter:
    def __init__(self, log_path: Path) -> None:
        self._path = Path(log_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text("# Activity Log\n\n", encoding="utf-8", newline="\n")

    def _append(self, text: str) -> None:
        with open(self._path, "a", encoding="utf-8", newline="\n") as f:
            f.write(text + "\n")

    def log_ingest(self, source: str, pages_created: list, pages_updated: list,
                   pages_flagged: list, tokens: int, cost_usd: float, cache_hits: int) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        self._append(
            f"\n## {ts} | INGEST | {source}\n"
            f"- Created: {pages_created or 'none'}\n"
            f"- Updated: {pages_updated or 'none'}\n"
            f"- Flagged: {pages_flagged or 'none'}\n"
            f"- Tokens: {tokens:,} | Cost: ${cost_usd:.4f} | Cache hits: {cache_hits}\n"
        )

    def log_lint(self, resolved: int, flagged: int, orphans: int,
                 dangling_removed: int = 0) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        dangling_part = f" | Dangling links removed: {dangling_removed}" if dangling_removed else ""
        self._append(
            f"\n## {ts} | LINT\n"
            f"- Resolved: {resolved} | Flagged: {flagged} | Orphans: {orphans}{dangling_part}\n"
        )

    def log_query(self, question: str, sub_questions: int,
                  citations: list, tokens: int, cost_usd: float) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        self._append(
            f"\n## {ts} | QUERY\n"
            f"- Question: {question[:120]}\n"
            f"- Sub-questions: {sub_questions} | Citations: {citations or 'none'}\n"
            f"- Tokens: {tokens:,} | Cost: ${cost_usd:.4f}\n"
        )


class AuditDB:
    def __init__(self, db_path: Path) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ingests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_hash TEXT NOT NULL,
                    source_size INTEGER NOT NULL,
                    source_path TEXT NOT NULL,
                    wiki_page TEXT NOT NULL,
                    tokens INTEGER,
                    cost_usd REAL,
                    ingested_at TEXT NOT NULL
                )""")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT,
                    event TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    metadata TEXT
                )""")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS queries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT NOT NULL,
                    sub_questions_count INTEGER NOT NULL DEFAULT 1,
                    tokens INTEGER,
                    cost_usd REAL,
                    queried_at TEXT NOT NULL
                )""")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS claim_citations (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    page_slug   TEXT NOT NULL,
                    source_file TEXT NOT NULL,
                    line_start  INTEGER NOT NULL,
                    line_end    INTEGER NOT NULL,
                    claim_excerpt TEXT,
                    ingested_at TEXT NOT NULL
                )""")
            await db.commit()

    async def record_ingest(self, source_hash: str, source_size: int,
                            source_path: str, wiki_page: str,
                            tokens: int, cost_usd: float) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO ingests (source_hash,source_size,source_path,wiki_page,"
                "tokens,cost_usd,ingested_at) VALUES (?,?,?,?,?,?,?)",
                (source_hash, source_size, source_path, wiki_page, tokens, cost_usd, ts),
            )
            await db.commit()

    async def find_by_hash_only(self, source_hash: str) -> Optional[dict]:
        """Return the first ingest record matching source_hash, or None.

        The returned dict uses key ``size`` (mapped from ``source_size``) so
        callers can compare ``existing["size"]`` against the current file size.
        """
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM ingests WHERE source_hash=? LIMIT 1",
                (source_hash,),
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                return None
            d = dict(row)
            # Expose "size" alias so callers can do existing["size"]
            d.setdefault("size", d.get("source_size"))
            return d

    async def find_by_hash(self, source_hash: str, source_size: int) -> Optional[dict]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM ingests WHERE source_hash=? AND source_size=? LIMIT 1",
                (source_hash, source_size),
            ) as cur:
                row = await cur.fetchone()
            return dict(row) if row else None

    async def list_ingests(self, limit: int = 50) -> list[dict]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT source_path, wiki_page, tokens, cost_usd, ingested_at "
                "FROM ingests ORDER BY id ASC LIMIT ?",
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def list_events(self, limit: int = 100) -> list[dict]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT job_id, event, timestamp, metadata "
                "FROM audit_events ORDER BY id ASC LIMIT ?",
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def record_query(self, question: str, sub_questions_count: int,
                           tokens: int, cost_usd: float) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO queries (question,sub_questions_count,tokens,cost_usd,queried_at)"
                " VALUES (?,?,?,?,?)",
                (question, sub_questions_count, tokens, cost_usd, ts),
            )
            await db.commit()

    async def list_queries(self, limit: int = 50) -> list[dict]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT question, sub_questions_count, tokens, cost_usd, queried_at"
                " FROM queries ORDER BY id DESC LIMIT ?",
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def cost_summary(self, days: int = 30) -> dict:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT day, SUM(day_tokens) as day_tokens, SUM(day_cost) as day_cost FROM (
                    SELECT DATE(ingested_at) as day, tokens as day_tokens, cost_usd as day_cost
                    FROM ingests WHERE ingested_at >= ?
                    UNION ALL
                    SELECT DATE(queried_at) as day, tokens as day_tokens, cost_usd as day_cost
                    FROM queries WHERE queried_at >= ?
                ) GROUP BY day ORDER BY day DESC
            """, (cutoff, cutoff)) as cur:
                rows = await cur.fetchall()

        total_tokens = 0
        total_cost = 0.0
        daily = []
        for r in rows:
            rd = dict(r)
            total_tokens += rd.get("day_tokens") or 0
            total_cost += rd.get("day_cost") or 0.0
            daily.append({"day": rd["day"], "cost_usd": rd.get("day_cost") or 0.0})

        return {"total_tokens": total_tokens, "total_cost_usd": total_cost, "daily": daily}

    async def record_claim_citations(
        self, page_slug: str, citations: list[dict]
    ) -> None:
        """Record claim-level citations produced by Pass 4."""
        if not citations:
            return
        ts = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._path) as db:
            await db.executemany(
                "INSERT INTO claim_citations "
                "(page_slug,source_file,line_start,line_end,claim_excerpt,ingested_at) "
                "VALUES (?,?,?,?,?,?)",
                [
                    (page_slug, c["source_file"], c["line_start"], c["line_end"],
                     (c.get("claim_excerpt") or "")[:CITATION_EXCERPT_LEN], ts)
                    for c in citations
                ],
            )
            await db.commit()

    async def list_citations(
        self,
        page_slug: str | None = None,
        source_file: str | None = None,
        limit: int = 50,
        offset: int = 0,
        sort: str = "ingested_at",
        order: str = "desc",
    ) -> list[dict]:
        """Return citations from claim_citations."""
        _ALLOWED_SORT = {"page_slug", "source_file", "line_start", "ingested_at"}
        if sort not in _ALLOWED_SORT:
            sort = "ingested_at"
        order = "asc" if order.lower() == "asc" else "desc"

        wheres, params = [], []
        if page_slug:
            wheres.append("page_slug=?")
            params.append(page_slug)
        if source_file:
            wheres.append("source_file=?")
            params.append(source_file)
        where = ("WHERE " + " AND ".join(wheres)) if wheres else ""
        params += [limit, offset]
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                f"SELECT page_slug, source_file, line_start, line_end, "
                f"claim_excerpt, ingested_at FROM claim_citations "
                f"{where} ORDER BY {sort} {order} LIMIT ? OFFSET ?",
                params,
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def list_citation_failures(
        self,
        page_slug: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Return citation validation failures from audit_events.

        Each returned dict has keys: page_slug, source_file, citation, reason,
        event_time.
        """
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT timestamp, metadata FROM audit_events "
                "WHERE event='citation_validation_failed' "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ) as cur:
                rows = await cur.fetchall()
        result = []
        for r in rows:
            try:
                m = json.loads(r["metadata"] or "{}")
            except Exception:
                m = {}
            entry = {
                "page_slug": m.get("page_slug") or m.get("slug"),
                "source_file": m.get("source_file"),
                "citation": m.get("citation"),
                "reason": m.get("reason"),
                "event_time": r["timestamp"],
            }
            if page_slug is not None and entry["page_slug"] != page_slug:
                continue
            result.append(entry)
        return result

    async def write_event(self, event: str, job_id: str = "",
                          metadata: dict | None = None) -> None:
        """Write a single audit event."""
        meta_str = json.dumps(metadata or {})
        ts = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO audit_events (job_id,event,timestamp,metadata) VALUES (?,?,?,?)",
                (job_id or None, event, ts, meta_str),
            )
            await db.commit()

    async def record_audit_event(self, job_id: str, event: str, metadata: dict) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO audit_events (job_id,event,timestamp,metadata) VALUES (?,?,?,?)",
                (job_id, event, ts, json.dumps(metadata)),
            )
            await db.commit()
