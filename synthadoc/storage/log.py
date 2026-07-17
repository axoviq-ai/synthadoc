# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import aiosqlite

DB_SCHEMA_VERSION: int = 3

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
            await db.execute("""
                CREATE TABLE IF NOT EXISTS page_states (
                    slug         TEXT PRIMARY KEY,
                    state        TEXT NOT NULL,
                    updated_at   TEXT NOT NULL,
                    triggered_by TEXT NOT NULL
                )""")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS lifecycle_events (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug         TEXT NOT NULL,
                    from_state   TEXT,
                    to_state     TEXT NOT NULL,
                    reason       TEXT,
                    triggered_by TEXT NOT NULL,
                    timestamp    TEXT NOT NULL
                )""")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_runs (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id      TEXT NOT NULL,
                    entry_id    TEXT NOT NULL DEFAULT '',
                    op          TEXT NOT NULL,
                    wiki        TEXT NOT NULL,
                    started_at  TEXT NOT NULL,
                    finished_at TEXT,
                    status      TEXT,
                    duration_s  REAL,
                    error       TEXT,
                    output      TEXT DEFAULT ''
                )""")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id   TEXT PRIMARY KEY,
                    mode         TEXT NOT NULL,
                    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
                    last_active  TEXT NOT NULL DEFAULT (datetime('now'))
                )""")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id   TEXT NOT NULL REFERENCES chat_sessions(session_id),
                    role         TEXT NOT NULL,
                    content      TEXT NOT NULL,
                    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
                )""")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS graph_nodes (
                    slug        TEXT PRIMARY KEY,
                    cluster_id  INTEGER NOT NULL,
                    updated_at  TEXT NOT NULL
                )""")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS graph_edges (
                    from_slug   TEXT NOT NULL,
                    to_slug     TEXT NOT NULL,
                    weight      INTEGER NOT NULL DEFAULT 1,
                    edge_type   TEXT NOT NULL DEFAULT 'mixed',
                    PRIMARY KEY (from_slug, to_slug)
                )""")
            # Migrations for existing installs
            for migration in (
                "ALTER TABLE scheduled_runs ADD COLUMN entry_id TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE scheduled_runs ADD COLUMN output TEXT DEFAULT ''",
                "ALTER TABLE chat_sessions ADD COLUMN history_summary TEXT DEFAULT NULL",
                "ALTER TABLE chat_sessions ADD COLUMN summary_turn_count INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE chat_messages ADD COLUMN citations TEXT DEFAULT NULL",
                "ALTER TABLE chat_messages ADD COLUMN gap_suggestions TEXT DEFAULT NULL",
                "ALTER TABLE graph_edges ADD COLUMN edge_type TEXT NOT NULL DEFAULT 'mixed'",
            ):
                try:
                    await db.execute(migration)
                    await db.commit()
                except Exception:
                    pass  # column already exists
            await db.execute(f"PRAGMA user_version = {DB_SCHEMA_VERSION}")
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

    async def update_ingest_cost(self, source_path: str, cost_usd: float) -> None:
        """Patch cost_usd on the most recent ingest record for source_path.

        Called by the orchestrator after estimate_cost() so the audit row
        reflects the real computed cost rather than the 0.0 placeholder written
        by IngestAgent before the orchestrator has run pricing.
        """
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE ingests SET cost_usd = ? WHERE id = ("
                "  SELECT id FROM ingests WHERE source_path = ? ORDER BY id DESC LIMIT 1"
                ")",
                (cost_usd, source_path),
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

    async def find_by_source_path(self, source_path: str) -> Optional[dict]:
        """Return the most recent ingest record for the given source path, or None."""
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM ingests WHERE source_path=? ORDER BY id DESC LIMIT 1",
                (source_path,),
            ) as cur:
                row = await cur.fetchone()
        return dict(row) if row else None

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
                "FROM ingests ORDER BY id DESC LIMIT ?",
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def list_ingests_since(self, days: int = 7) -> list[dict]:
        """Return ingest records from the last `days` days, newest first."""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT source_path, wiki_page, ingested_at "
                "FROM ingests WHERE ingested_at >= ? ORDER BY id DESC",
                (since,),
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

    async def set_page_state(self, slug: str, state: str, triggered_by: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO page_states (slug,state,updated_at,triggered_by) VALUES (?,?,?,?)"
                " ON CONFLICT(slug) DO UPDATE SET state=excluded.state,"
                " updated_at=excluded.updated_at, triggered_by=excluded.triggered_by",
                (slug, state, ts, triggered_by),
            )
            await db.commit()

    async def get_page_state(self, slug: str) -> Optional[dict]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT slug,state,updated_at,triggered_by FROM page_states WHERE slug=?",
                (slug,),
            ) as cur:
                row = await cur.fetchone()
        return dict(row) if row else None

    async def record_lifecycle_event(
        self, slug: str, from_state: Optional[str], to_state: str,
        reason: str, triggered_by: str,
    ) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO lifecycle_events"
                " (slug,from_state,to_state,reason,triggered_by,timestamp)"
                " VALUES (?,?,?,?,?,?)",
                (slug, from_state, to_state, reason or "", triggered_by, ts),
            )
            await db.commit()

    async def get_lifecycle_events(
        self,
        slug: Optional[str] = None,
        to_state: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """Return (events, total_count) where total_count is the full DB count before pagination."""
        wheres, filter_params = [], []
        if slug:
            wheres.append("slug=?")
            filter_params.append(slug)
        if to_state:
            wheres.append("to_state=?")
            filter_params.append(to_state)
        where = ("WHERE " + " AND ".join(wheres)) if wheres else ""
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                f"SELECT COUNT(*) as cnt FROM lifecycle_events {where}",
                filter_params,
            ) as cur:
                total = (await cur.fetchone())["cnt"]
            async with db.execute(
                f"SELECT id,slug,from_state,to_state,reason,triggered_by,timestamp"
                f" FROM lifecycle_events {where} ORDER BY id ASC LIMIT ? OFFSET ?",
                filter_params + [limit, offset],
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows], total

    async def get_all_page_states(self) -> list:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT slug, state, updated_at, triggered_by FROM page_states ORDER BY slug ASC"
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_live_page_states(self, page_exists: Callable[[str], bool]) -> list:
        """Return page states filtered to slugs whose files still exist on disk.

        Excludes entries for pages deleted externally (e.g. via Obsidian UI) that
        were never removed from the audit DB through the lifecycle API.
        """
        all_states = await self.get_all_page_states()
        return [p for p in all_states if page_exists(p["slug"])]

    async def get_live_lifecycle_summary(self, page_exists: Callable[[str], bool]) -> dict:
        """Return lifecycle counts filtered to slugs that still exist on disk."""
        live = await self.get_live_page_states(page_exists)
        counts: dict[str, int] = {}
        for p in live:
            counts[p["state"]] = counts.get(p["state"], 0) + 1
        return counts

    async def get_lifecycle_summary(self) -> dict:
        """Return counts for all 5 lifecycle states; missing states default to 0."""
        base = {"draft": 0, "active": 0, "contradicted": 0, "stale": 0, "archived": 0}
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT state, COUNT(*) as cnt FROM page_states GROUP BY state"
            ) as cur:
                rows = await cur.fetchall()
        for r in rows:
            if r["state"] in base:
                base[r["state"]] = r["cnt"]
        return base

    async def purge_lifecycle_events(
        self,
        before_date: Optional[str] = None,
        keep_latest: Optional[int] = None,
    ) -> None:
        async with aiosqlite.connect(self._path) as db:
            if before_date:
                await db.execute(
                    "DELETE FROM lifecycle_events WHERE timestamp < ?", (before_date,)
                )
            elif keep_latest is not None:
                await db.execute("""
                    DELETE FROM lifecycle_events WHERE id NOT IN (
                        SELECT id FROM (
                            SELECT id,
                                   ROW_NUMBER() OVER (PARTITION BY slug ORDER BY id DESC) AS rn
                            FROM lifecycle_events
                        ) WHERE rn <= ?
                    )
                """, (keep_latest,))
            await db.commit()

    async def record_scheduled_run_start(
        self, run_id: str, op: str, wiki: str, entry_id: str = ""
    ) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO scheduled_runs (run_id,entry_id,op,wiki,started_at,status)"
                " VALUES (?,?,?,?,?,'running')",
                (run_id, entry_id, op, wiki, ts),
            )
            await db.commit()

    async def record_scheduled_run_finish(
        self, run_id: str, status: str, duration_s: float,
        error: Optional[str] = None, output: str = "",
    ) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE scheduled_runs"
                " SET finished_at=?, status=?, duration_s=?, error=?, output=?"
                " WHERE run_id=?",
                (ts, status, round(duration_s, 2), error, output, run_id),
            )
            await db.commit()

    async def list_scheduled_runs(self, limit: int = 20) -> list[dict]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT run_id,entry_id,op,wiki,started_at,finished_at,"
                "       status,duration_s,error,output"
                " FROM scheduled_runs ORDER BY id DESC LIMIT ?",
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_last_run_per_entry(self) -> dict[str, dict]:
        """Return {entry_id: {started_at, status}} for the most recent run per entry."""
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT sr.entry_id, sr.started_at, sr.status
                FROM scheduled_runs sr
                INNER JOIN (
                    SELECT entry_id, MAX(id) AS max_id
                    FROM scheduled_runs
                    WHERE entry_id != ''
                    GROUP BY entry_id
                ) latest ON sr.id = latest.max_id
                """
            ) as cur:
                rows = await cur.fetchall()
        return {r["entry_id"]: dict(r) for r in rows}

    async def create_session(self, session_id: str, mode: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO chat_sessions (session_id, mode) VALUES (?,?)",
                (session_id, mode),
            )
            await db.commit()

    async def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        citations: list[str] | None = None,
        gap_suggestions: list[str] | None = None,
    ) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO chat_messages (session_id, role, content, citations, gap_suggestions)"
                " VALUES (?,?,?,?,?)",
                (
                    session_id, role, content,
                    json.dumps(citations) if citations else None,
                    json.dumps(gap_suggestions) if gap_suggestions else None,
                ),
            )
            await db.execute(
                "UPDATE chat_sessions SET last_active=datetime('now') WHERE session_id=?",
                (session_id,),
            )
            await db.commit()

    async def get_session_messages(self, session_id: str, limit: int = 20) -> list[dict]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT role, content FROM chat_messages WHERE session_id=? "
                "ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ) as cur:
                rows = await cur.fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    async def has_prior_sessions(self) -> bool:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute("SELECT COUNT(*) FROM chat_sessions") as cur:
                row = await cur.fetchone()
        return (row[0] if row else 0) > 0

    async def get_history(self, session_id: str, turns: int) -> list[dict]:
        """Return last `turns` conversation turns (user+assistant pairs), oldest first."""
        if turns <= 0:
            return []
        limit = turns * 2  # each turn = 1 user + 1 assistant message
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT role, content FROM chat_messages WHERE session_id=? "
                "ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ) as cur:
                rows = await cur.fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    async def get_all_messages(self, session_id: str) -> list[dict]:
        """Return all messages for a session, oldest first, including citations and gap suggestions."""
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT role, content, citations, gap_suggestions"
                " FROM chat_messages WHERE session_id=? ORDER BY id ASC",
                (session_id,),
            ) as cur:
                rows = await cur.fetchall()
        return [
            {
                "role": r["role"],
                "content": r["content"],
                "citations": json.loads(r["citations"]) if r["citations"] else [],
                "gap_suggestions": json.loads(r["gap_suggestions"]) if r["gap_suggestions"] else [],
            }
            for r in rows
        ]

    async def get_summary(self, session_id: str) -> tuple[str | None, int]:
        """Return (history_summary, summary_turn_count) for a session."""
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT history_summary, summary_turn_count FROM chat_sessions WHERE session_id=?",
                (session_id,),
            ) as cur:
                row = await cur.fetchone()
        if row is None:
            return None, 0
        return row["history_summary"], row["summary_turn_count"]

    async def update_summary(self, session_id: str, summary: str, covered_turns: int) -> None:
        """Store the conversation summary and how many turns it covers."""
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE chat_sessions SET history_summary=?, summary_turn_count=? WHERE session_id=?",
                (summary, covered_turns, session_id),
            )
            await db.commit()

    async def list_sessions(self, limit: int = 20) -> list[dict]:
        """Return recent sessions that have messages.

        Shape: {session_id, mode, first_q, last_active, turn_count, questions: [str]}
        """
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT DISTINCT s.session_id, s.mode, s.last_active
                   FROM chat_sessions s
                   INNER JOIN chat_messages m ON s.session_id = m.session_id
                   ORDER BY s.last_active DESC LIMIT ?""",
                (limit,),
            ) as cur:
                sessions = [dict(r) for r in await cur.fetchall()]

            if not sessions:
                return []

            sids = [s["session_id"] for s in sessions]
            placeholders = ",".join("?" * len(sids))
            async with db.execute(
                f"SELECT session_id, content FROM chat_messages "
                f"WHERE session_id IN ({placeholders}) AND role='user' ORDER BY id ASC",
                sids,
            ) as cur:
                rows = await cur.fetchall()

        questions_by_session: dict[str, list[str]] = {}
        for row in rows:
            questions_by_session.setdefault(row["session_id"], []).append(row["content"])

        result = []
        for s in sessions:
            qs = questions_by_session.get(s["session_id"], [])
            if not qs:
                continue
            result.append({
                "session_id": s["session_id"],
                "mode": s["mode"],
                "first_q": qs[0],
                "last_active": s["last_active"],
                "turn_count": len(qs),
                "questions": qs,
            })
        return result

    async def purge_old_sessions(self, retention_days: int) -> int:
        """Delete sessions inactive for more than retention_days. Returns count deleted."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "DELETE FROM chat_messages WHERE session_id IN "
                "(SELECT session_id FROM chat_sessions WHERE last_active < ?)",
                (cutoff,),
            )
            async with db.execute(
                "DELETE FROM chat_sessions WHERE last_active < ?", (cutoff,)
            ) as cur:
                count = cur.rowcount
            await db.commit()
        return count

    async def write_graph(self, nodes: list[dict], edges: list[dict]) -> None:
        """Full replace of graph_nodes and graph_edges."""
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._path) as db:
            await db.execute("DELETE FROM graph_nodes")
            await db.execute("DELETE FROM graph_edges")
            await db.executemany(
                "INSERT INTO graph_nodes (slug, cluster_id, updated_at) VALUES (?,?,?)",
                [(n["slug"], n["cluster_id"], ts) for n in nodes],
            )
            await db.executemany(
                "INSERT INTO graph_edges (from_slug, to_slug, weight, edge_type) VALUES (?,?,?,?)",
                [(e["from_slug"], e["to_slug"], e["weight"], e.get("edge_type", "mixed")) for e in edges],
            )
            await db.commit()

    async def read_graph(self) -> dict | None:
        """Return graph data or None if tables are empty (graph not yet computed)."""
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT slug, cluster_id FROM graph_nodes")
            nodes = [dict(r) for r in await cur.fetchall()]
            if not nodes:
                return None
            cur = await db.execute("SELECT from_slug, to_slug, weight, edge_type FROM graph_edges")
            edges = [dict(r) for r in await cur.fetchall()]
        return {"nodes": nodes, "edges": edges}

    async def delete_graph_node(self, slug: str) -> None:
        """Remove a single node and all its incident edges from the graph tables.

        Called immediately after a page is archived so the graph stays consistent
        without waiting for the next full lint rebuild.
        """
        async with aiosqlite.connect(self._path) as db:
            await db.execute("DELETE FROM graph_nodes WHERE slug = ?", (slug,))
            await db.execute(
                "DELETE FROM graph_edges WHERE from_slug = ? OR to_slug = ?",
                (slug, slug),
            )
            await db.commit()
