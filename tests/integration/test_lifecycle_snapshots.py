# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import pytest
import aiosqlite
from pathlib import Path

from synthadoc.storage.log import AuditDB, DB_SCHEMA_VERSION


# ── Task 1 tests ────────────────────────────────────────────────────────────

def test_schema_version_is_4():
    assert DB_SCHEMA_VERSION == 4


@pytest.mark.asyncio
async def test_schema_migration_adds_column(tmp_path: Path):
    """An existing v3 DB gains content_snapshot after AuditDB.init()."""
    db_path = tmp_path / "audit.db"
    # Seed a v3 schema (no content_snapshot column)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE lifecycle_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL,
                from_state TEXT,
                to_state TEXT NOT NULL,
                reason TEXT,
                triggered_by TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )""")
        await db.execute("PRAGMA user_version = 3")
        await db.commit()

    audit = AuditDB(db_path)
    await audit.init()

    async with aiosqlite.connect(db_path) as db:
        async with db.execute("PRAGMA table_info(lifecycle_events)") as cur:
            cols = [row[1] for row in await cur.fetchall()]
    assert "content_snapshot" in cols


@pytest.mark.asyncio
async def test_record_event_with_snapshot(tmp_path: Path):
    db_path = tmp_path / "audit.db"
    audit = AuditDB(db_path)
    await audit.init()

    await audit.record_lifecycle_event(
        "quantum-computing", "draft", "active", "reviewed", "user",
        content_snapshot="# Quantum Computing\n\nContent here.",
    )

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT content_snapshot FROM lifecycle_events"
        ) as cur:
            row = await cur.fetchone()
    assert row["content_snapshot"] == "# Quantum Computing\n\nContent here."


@pytest.mark.asyncio
async def test_record_event_without_snapshot_defaults_null(tmp_path: Path):
    db_path = tmp_path / "audit.db"
    audit = AuditDB(db_path)
    await audit.init()

    await audit.record_lifecycle_event(
        "my-page", "draft", "active", "reason", "user"
    )

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT content_snapshot FROM lifecycle_events"
        ) as cur:
            row = await cur.fetchone()
    assert row["content_snapshot"] is None


# ── Task 2 tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_page_snapshots_empty(tmp_path: Path):
    audit = AuditDB(tmp_path / "audit.db")
    await audit.init()
    assert await audit.list_page_snapshots("no-such-slug") == []


@pytest.mark.asyncio
async def test_list_page_snapshots_newest_first(tmp_path: Path):
    audit = AuditDB(tmp_path / "audit.db")
    await audit.init()
    for i, state in enumerate(["active", "archived", "draft"]):
        await audit.record_lifecycle_event(
            "my-page", "draft", state, f"r{i}", "user",
            content_snapshot=f"content {i}",
        )
    snapshots = await audit.list_page_snapshots("my-page")
    assert len(snapshots) == 3
    assert snapshots[0]["index"] == 1          # index 1 = newest
    assert snapshots[0]["to_state"] == "draft"  # third insert = newest


@pytest.mark.asyncio
async def test_list_page_snapshots_excludes_null(tmp_path: Path):
    audit = AuditDB(tmp_path / "audit.db")
    await audit.init()
    await audit.record_lifecycle_event("my-page", "draft", "active", "r", "user")  # NULL
    await audit.record_lifecycle_event(
        "my-page", "active", "archived", "r", "user", content_snapshot="content A"
    )
    snapshots = await audit.list_page_snapshots("my-page")
    assert len(snapshots) == 1
    assert snapshots[0]["to_state"] == "archived"


@pytest.mark.asyncio
async def test_list_page_snapshots_excludes_other_slugs(tmp_path: Path):
    audit = AuditDB(tmp_path / "audit.db")
    await audit.init()
    await audit.record_lifecycle_event(
        "page-a", "draft", "active", "r", "user", content_snapshot="A content"
    )
    await audit.record_lifecycle_event(
        "page-b", "draft", "active", "r", "user", content_snapshot="B content"
    )
    snapshots = await audit.list_page_snapshots("page-a")
    assert len(snapshots) == 1
    assert snapshots[0]["content_length"] == len("A content")


@pytest.mark.asyncio
async def test_get_snapshot_by_index_valid(tmp_path: Path):
    audit = AuditDB(tmp_path / "audit.db")
    await audit.init()
    await audit.record_lifecycle_event(
        "p", "draft", "active", "r", "user", content_snapshot="older body"
    )
    await audit.record_lifecycle_event(
        "p", "active", "archived", "r", "user", content_snapshot="newer body"
    )
    snap = await audit.get_snapshot_by_index("p", 1)  # 1 = newest
    assert snap is not None
    assert snap["content_snapshot"] == "newer body"
    assert snap["index"] == 1


@pytest.mark.asyncio
async def test_get_snapshot_by_index_out_of_range(tmp_path: Path):
    audit = AuditDB(tmp_path / "audit.db")
    await audit.init()
    await audit.record_lifecycle_event(
        "p", "draft", "active", "r", "user", content_snapshot="content"
    )
    assert await audit.get_snapshot_by_index("p", 99) is None


# ── Task 3 tests ────────────────────────────────────────────────────────────


def test_transition_stores_content_snapshot(tmp_wiki):
    """POST /lifecycle/transition captures page.content in the snapshot column."""
    import asyncio
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    from synthadoc.storage.log import AuditDB

    wiki_dir = tmp_wiki / "wiki"
    page_body = "The page body that should be snapshotted."
    (wiki_dir / "snap-test.md").write_text(
        f"---\ntitle: Snap Test\nstatus: draft\nconfidence: medium\n"
        f"tags: []\nsources: []\n---\n\n{page_body}\n",
        encoding="utf-8",
    )

    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.post("/lifecycle/transition", json={
            "slug": "snap-test",
            "to_state": "active",
            "reason": "verified",
        })
    assert resp.status_code == 200

    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")

    async def _check():
        await audit.init()
        snapshots = await audit.list_page_snapshots("snap-test")
        assert len(snapshots) == 1
        snap = await audit.get_snapshot_by_index("snap-test", 1)
        assert page_body in snap["content_snapshot"]

    asyncio.run(_check())


# ── Task 4 tests ────────────────────────────────────────────────────────────

def _make_wiki_with_snapshots(tmp_wiki):
    """Write a page with two lifecycle transitions so the audit DB has snapshots."""
    import asyncio
    from synthadoc.storage.log import AuditDB

    wiki_dir = tmp_wiki / "wiki"
    (wiki_dir / "hist-page.md").write_text(
        "---\ntitle: Hist\nstatus: draft\nconfidence: medium\ntags: []\nsources: []\n---\n\nBody v1.\n",
        encoding="utf-8",
    )
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")

    async def _seed():
        await audit.init()
        await audit.record_lifecycle_event(
            "hist-page", "draft", "active", "r1", "user",
            content_snapshot="Body v1.",
        )
        await audit.record_lifecycle_event(
            "hist-page", "active", "archived", "r2", "user",
            content_snapshot="Body v2.",
        )
    asyncio.run(_seed())


def test_history_endpoint_list(tmp_wiki):
    """GET /pages/{slug}/history returns a summary list, newest first."""
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    _make_wiki_with_snapshots(tmp_wiki)
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/pages/hist-page/history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["slug"] == "hist-page"
    snaps = data["snapshots"]
    assert len(snaps) == 2
    assert snaps[0]["index"] == 1          # newest first
    assert snaps[0]["to_state"] == "archived"
    assert "content_snapshot" not in snaps[0]  # content not in list view
    assert "content_length" in snaps[0]
    assert resp.headers.get("cache-control") == "no-store"


def test_history_endpoint_single_no_content(tmp_wiki):
    """GET /pages/{slug}/history?index=1 without include_content omits the body."""
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    _make_wiki_with_snapshots(tmp_wiki)
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/pages/hist-page/history?index=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["index"] == 1
    assert "content" not in data


def test_history_endpoint_single_with_content(tmp_wiki):
    """GET /pages/{slug}/history?index=1&include_content=true returns Markdown."""
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    _make_wiki_with_snapshots(tmp_wiki)
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/pages/hist-page/history?index=1&include_content=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data["index"] == 1
    assert "Body v2." in data["content"]  # index 1 = newest = archived snapshot


# ── Task 5 tests ────────────────────────────────────────────────────────────

def test_rollback_endpoint_restores_file(tmp_wiki):
    """POST /pages/{slug}/rollback writes the snapshot body back to the .md file."""
    import asyncio
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    from synthadoc.storage.log import AuditDB

    wiki_dir = tmp_wiki / "wiki"
    original_body = "This is the original body before editing."
    (wiki_dir / "rollback-page.md").write_text(
        f"---\ntitle: Rollback Test\nstatus: draft\nconfidence: medium\n"
        f"tags: []\nsources: []\n---\n\n{original_body}\n",
        encoding="utf-8",
    )

    # Seed one snapshot in the audit DB
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    async def _seed():
        await audit.init()
        await audit.record_lifecycle_event(
            "rollback-page", "draft", "active", "activated", "user",
            content_snapshot=original_body,
        )
    asyncio.run(_seed())

    # Now "accidentally edit" the page on disk
    (wiki_dir / "rollback-page.md").write_text(
        "---\ntitle: Rollback Test\nstatus: active\nconfidence: medium\n"
        "tags: []\nsources: []\n---\n\nThis is the WRONG body after editing.\n",
        encoding="utf-8",
    )

    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.post("/pages/rollback-page/rollback", json={
            "index": 1,
            "reason": "reverting accidental edit",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["slug"] == "rollback-page"
    assert data["snapshot_index"] == 1
    assert data["restored_chars"] == len(original_body)

    # Verify the file on disk now contains the original body
    on_disk = (wiki_dir / "rollback-page.md").read_text(encoding="utf-8")
    assert original_body in on_disk
    assert "WRONG body" not in on_disk


def test_rollback_endpoint_records_pre_rollback_snapshot(tmp_wiki):
    """The rollback event itself has content_snapshot = the pre-rollback body."""
    import asyncio
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    from synthadoc.storage.log import AuditDB

    wiki_dir = tmp_wiki / "wiki"
    pre_rollback_body = "Body that will be overwritten by rollback."
    (wiki_dir / "rb2-page.md").write_text(
        f"---\ntitle: RB2\nstatus: active\nconfidence: medium\ntags: []\nsources: []\n"
        f"---\n\n{pre_rollback_body}\n",
        encoding="utf-8",
    )
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    async def _seed():
        await audit.init()
        await audit.record_lifecycle_event(
            "rb2-page", "draft", "active", "activated", "user",
            content_snapshot="original snap body",
        )
    asyncio.run(_seed())

    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.post("/pages/rb2-page/rollback", json={
            "index": 1,
            "reason": "testing undo",
        })
    assert resp.status_code == 200
    rb_event_index = resp.json()["rollback_event_index"]

    async def _check():
        await audit.init()
        snap = await audit.get_snapshot_by_index("rb2-page", rb_event_index)
        assert snap is not None
        assert pre_rollback_body in snap["content_snapshot"]
    asyncio.run(_check())


def test_rollback_strips_frontmatter_from_old_snapshot(tmp_wiki):
    """Rollback from a snapshot that contains YAML frontmatter must not produce
    a double-frontmatter file on disk.

    Before the fix, vault-monitor snapshots stored the full .md file content
    (frontmatter + body).  Rolling back such a snapshot set page.content to
    'frontmatter + body', then write_page wrapped it again with its own
    frontmatter, resulting in a corrupted page file.  The fix calls
    strip_frontmatter() on the snapshot content before restoring.
    """
    import asyncio
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    from synthadoc.storage.log import AuditDB

    wiki_dir = tmp_wiki / "wiki"
    body = "Body before the bad edit."
    # Simulate a pre-fix snapshot: stored with frontmatter still present
    snap_with_frontmatter = (
        "---\ntitle: Snap Test\nstatus: active\nconfidence: medium\n"
        "tags: []\nsources: []\n---\n\n" + body
    )
    (wiki_dir / "snap-fm-page.md").write_text(
        "---\ntitle: Snap Test\nstatus: active\nconfidence: medium\n"
        "tags: []\nsources: []\n---\n\nThis is the wrong body.\n",
        encoding="utf-8",
    )
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    async def _seed():
        await audit.init()
        await audit.record_lifecycle_event(
            "snap-fm-page", "draft", "active", "activated", "user",
            content_snapshot=snap_with_frontmatter,
        )
    asyncio.run(_seed())

    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.post("/pages/snap-fm-page/rollback", json={
            "index": 1,
            "reason": "restoring old snapshot",
        })
    assert resp.status_code == 200

    on_disk = (wiki_dir / "snap-fm-page.md").read_text(encoding="utf-8")
    # Body must be present
    assert body in on_disk
    # Must not contain double frontmatter (second --- block inside the body)
    body_part = on_disk.split("---\n", 2)[-1]  # everything after the closing ---
    assert "---" not in body_part, (
        "File has double frontmatter after rollback — strip_frontmatter not applied"
    )


# ── Task 6 tests (v1.2 backend) ─────────────────────────────────────────────

def test_get_snapshots_returns_all(tmp_wiki):
    """GET /snapshots returns every event that has a non-NULL content_snapshot."""
    import asyncio
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    from synthadoc.storage.log import AuditDB

    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    async def _seed():
        await audit.init()
        await audit.record_lifecycle_event(
            "page-a", "draft", "active", "r1", "user",
            content_snapshot="body a1",
        )
        await audit.record_lifecycle_event(
            "page-a", "active", "archived", "r2", "user",
            content_snapshot="body a2",
        )
        await audit.record_lifecycle_event(
            "page-b", "draft", "active", "r3", "user",
            content_snapshot="body b1",
        )
        # NULL snapshot — must NOT appear
        await audit.record_lifecycle_event(
            "page-b", "active", "archived", "r4", "user",
        )
    asyncio.run(_seed())

    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/snapshots")
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == "no-store"
    data = resp.json()
    assert "snapshots" in data
    slugs = [s["slug"] for s in data["snapshots"]]
    assert "page-a" in slugs
    assert "page-b" in slugs
    # 3 events with snapshots, 1 null
    assert len(data["snapshots"]) == 3
    # snap_index is present and is an integer
    for snap in data["snapshots"]:
        assert isinstance(snap["snap_index"], int)
        assert "content_snapshot" not in snap  # full body not in list


def test_get_snapshots_slug_filter(tmp_wiki):
    """GET /snapshots?slug=page-a returns only page-a rows."""
    import asyncio
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    from synthadoc.storage.log import AuditDB

    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    async def _seed():
        await audit.init()
        await audit.record_lifecycle_event(
            "page-a", "draft", "active", "r", "user", content_snapshot="a"
        )
        await audit.record_lifecycle_event(
            "page-b", "draft", "active", "r", "user", content_snapshot="b"
        )
    asyncio.run(_seed())

    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/snapshots?slug=page-a")
    data = resp.json()
    assert all(s["slug"] == "page-a" for s in data["snapshots"])
    assert len(data["snapshots"]) == 1


def test_get_snapshots_empty(tmp_wiki):
    """GET /snapshots returns an empty list when no snapshots exist."""
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/snapshots")
    assert resp.status_code == 200
    assert resp.json() == {"snapshots": []}


def test_purge_endpoint_keep_latest(tmp_wiki):
    """POST /lifecycle/events/purge with keep_latest deletes old events."""
    import asyncio
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    from synthadoc.storage.log import AuditDB

    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    async def _seed():
        await audit.init()
        for i in range(5):
            await audit.record_lifecycle_event(
                "p", "draft", "active", f"r{i}", "user",
                content_snapshot=f"body {i}",
            )
    asyncio.run(_seed())

    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.post("/lifecycle/events/purge", json={"keep_latest": 2})
    assert resp.status_code == 200
    assert resp.json() == {"purged": True}
    assert resp.headers.get("cache-control") == "no-store"

    # Verify that only 2 remain
    async def _check():
        await audit.init()
        snaps = await audit.list_page_snapshots("p")
        assert len(snaps) == 2
    asyncio.run(_check())


def test_purge_endpoint_before_date(tmp_wiki):
    """POST /lifecycle/events/purge with before_date removes older events."""
    import asyncio
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    from synthadoc.storage.log import AuditDB

    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    async def _seed():
        await audit.init()
        await audit.record_lifecycle_event(
            "p", "draft", "active", "r", "user", content_snapshot="body"
        )
    asyncio.run(_seed())

    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.post(
            "/lifecycle/events/purge", json={"before_date": "2099-01-01"}
        )
    assert resp.status_code == 200
    assert resp.json() == {"purged": True}


def test_purge_endpoint_rejects_both_params(tmp_wiki):
    """POST /lifecycle/events/purge with both params returns 422."""
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.post(
            "/lifecycle/events/purge",
            json={"keep_latest": 10, "before_date": "2026-01-01"},
        )
    assert resp.status_code == 422


def test_purge_endpoint_rejects_neither_param(tmp_wiki):
    """POST /lifecycle/events/purge with no params returns 422."""
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.post("/lifecycle/events/purge", json={})
    assert resp.status_code == 422


def test_purge_endpoint_rejects_invalid_date_format(tmp_wiki):
    """POST /lifecycle/events/purge with a malformed date returns 422."""
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    for bad_date in ["foobar", "2026/01/01", "26-01-01", "2026-1-1"]:
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.post("/lifecycle/events/purge", json={"before_date": bad_date})
        assert resp.status_code == 422, f"Expected 422 for before_date={bad_date!r}, got {resp.status_code}"


# ── snapshot_if_changed unit tests ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_snapshot_if_changed_records_on_first_call(tmp_path: Path):
    """snapshot_if_changed() creates a snapshot when there is no prior snapshot."""
    audit = AuditDB(tmp_path / "audit.db")
    await audit.init()
    await audit.set_page_state("p", "active", "user")

    recorded = await audit.snapshot_if_changed("p", "body v1", "MANUAL_EDIT", "edit")
    assert recorded is True

    snaps = await audit.list_page_snapshots("p")
    assert len(snaps) == 1
    full = await audit.get_snapshot_by_index("p", 1)
    assert full is not None
    assert full["content_snapshot"] == "body v1"


@pytest.mark.asyncio
async def test_snapshot_if_changed_skips_when_unchanged(tmp_path: Path):
    """snapshot_if_changed() returns False and records nothing when content is identical."""
    audit = AuditDB(tmp_path / "audit.db")
    await audit.init()
    await audit.set_page_state("p", "active", "user")

    await audit.snapshot_if_changed("p", "same body", "MANUAL_EDIT", "edit 1")
    result = await audit.snapshot_if_changed("p", "same body", "MANUAL_EDIT", "edit 2")
    assert result is False

    snaps = await audit.list_page_snapshots("p")
    assert len(snaps) == 1  # still only one snapshot


@pytest.mark.asyncio
async def test_snapshot_if_changed_records_when_content_differs(tmp_path: Path):
    """snapshot_if_changed() records a new snapshot when content changes."""
    audit = AuditDB(tmp_path / "audit.db")
    await audit.init()
    await audit.set_page_state("p", "active", "user")

    await audit.snapshot_if_changed("p", "v1", "MANUAL_EDIT", "e1")
    recorded = await audit.snapshot_if_changed("p", "v2", "MANUAL_EDIT", "e2")
    assert recorded is True

    snaps = await audit.list_page_snapshots("p")
    assert len(snaps) == 2


@pytest.mark.asyncio
async def test_snapshot_if_changed_strips_frontmatter_before_compare(tmp_path: Path):
    """snapshot_if_changed() treats raw .md content the same as body-only content.

    Lifecycle transitions store body-only content (WikiPage.content).  The vault
    monitor sends full .md file content including YAML frontmatter.  Both must
    deduplicate correctly against each other.
    """
    audit = AuditDB(tmp_path / "audit.db")
    await audit.init()
    await audit.set_page_state("p", "active", "user")

    body = "Body content here."
    raw_with_frontmatter = f"---\ntitle: P\nstatus: active\n---\n\n{body}"

    # First call: store via body-only (as lifecycle transitions do)
    r1 = await audit.snapshot_if_changed("p", body, "lifecycle", "r1")
    assert r1 is True

    # Second call: same body wrapped in frontmatter (as vault monitor previously sent)
    # must be deduplicated — content is unchanged
    r2 = await audit.snapshot_if_changed("p", raw_with_frontmatter, "manual_edit", "r2")
    assert r2 is False, "frontmatter wrapper must not fool deduplication"

    snaps = await audit.list_page_snapshots("p")
    assert len(snaps) == 1, "only one snapshot should exist"
    # Verify stored content is body-only (frontmatter was stripped before storage)
    snap = await audit.get_snapshot_by_index("p", 1)
    assert snap["content_snapshot"] == body


@pytest.mark.asyncio
async def test_snapshot_if_changed_uses_current_state(tmp_path: Path):
    """snapshot_if_changed() records from_state = to_state = current page state."""
    audit = AuditDB(tmp_path / "audit.db")
    await audit.init()
    await audit.set_page_state("p", "active", "user")

    await audit.snapshot_if_changed("p", "content", "MANUAL_EDIT", "reason")
    snaps = await audit.list_page_snapshots("p")
    assert len(snaps) == 1
    assert snaps[0]["from_state"] == "active"
    assert snaps[0]["to_state"] == "active"


# ── POST /pages/{slug}/snapshot endpoint tests ───────────────────────────────

def test_snapshot_endpoint_records_new_content(tmp_wiki):
    """POST /pages/{slug}/snapshot returns {recorded: true} for new content."""
    import asyncio
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    from synthadoc.storage.log import AuditDB

    wiki_dir = tmp_wiki / "wiki"
    (wiki_dir / "snap-manual.md").write_text(
        "---\ntitle: Manual\nstatus: active\nconfidence: medium\ntags: []\nsources: []\n---\n\nbody v1\n",
        encoding="utf-8",
    )
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    asyncio.run(audit.init())
    asyncio.run(audit.set_page_state("snap-manual", "active", "user"))

    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.post("/pages/snap-manual/snapshot", json={"content": "body v1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["recorded"] is True
    assert data["slug"] == "snap-manual"


def test_snapshot_endpoint_skips_unchanged_content(tmp_wiki):
    """POST /pages/{slug}/snapshot returns {recorded: false} when content is identical."""
    import asyncio
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    from synthadoc.storage.log import AuditDB

    wiki_dir = tmp_wiki / "wiki"
    (wiki_dir / "snap-dedup.md").write_text(
        "---\ntitle: Dedup\nstatus: active\nconfidence: medium\ntags: []\nsources: []\n---\n\nsame\n",
        encoding="utf-8",
    )
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    asyncio.run(audit.init())
    asyncio.run(audit.set_page_state("snap-dedup", "active", "user"))

    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        client.post("/pages/snap-dedup/snapshot", json={"content": "same"})
        resp = client.post("/pages/snap-dedup/snapshot", json={"content": "same"})
    assert resp.status_code == 200
    assert resp.json()["recorded"] is False


def test_snapshot_endpoint_rejects_non_wiki_slug(tmp_wiki):
    """POST /pages/{slug}/snapshot returns {recorded: false} for slugs with no wiki file.

    Vault-root scaffold files (AGENTS.md, CLAUDE.md, ROUTING.md, log.md) have
    no corresponding wiki/{slug}.md — rejected by page_exists() check.
    """
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app

    for scaffold_slug in ("AGENTS", "CLAUDE", "ROUTING", "log"):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.post(
                f"/pages/{scaffold_slug}/snapshot",
                json={"content": "scaffold content"},
            )
        assert resp.status_code == 200, f"Expected 200 for slug={scaffold_slug!r}"
        data = resp.json()
        assert data["recorded"] is False, f"Expected recorded=false for slug={scaffold_slug!r}"
        assert data["slug"] == scaffold_slug


def test_snapshot_endpoint_rejects_system_page_slugs(tmp_wiki):
    """POST /pages/{slug}/snapshot returns {recorded: false} for system page slugs.

    System pages (dashboard, overview, purpose, index) live inside wiki/ so
    page_exists() returns True for them — but the LINT_SKIP_SLUGS guard must
    reject them before snapshot_if_changed() is called.
    """
    import asyncio
    from fastapi.testclient import TestClient
    from synthadoc.integration.http_server import create_app
    from synthadoc.storage.log import AuditDB

    wiki_dir = tmp_wiki / "wiki"
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")

    async def _seed(slug: str) -> None:
        await audit.init()
        await audit.set_page_state(slug, "active", "user")

    for system_slug in ("dashboard", "overview", "purpose", "index"):
        (wiki_dir / f"{system_slug}.md").write_text(
            f"---\ntitle: {system_slug}\nstatus: active\n---\n\nbody\n",
            encoding="utf-8",
        )
        asyncio.run(_seed(system_slug))
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.post(
                f"/pages/{system_slug}/snapshot",
                json={"content": "some body"},
            )
        assert resp.status_code == 200, f"Expected 200 for slug={system_slug!r}"
        data = resp.json()
        assert data["recorded"] is False, f"Expected recorded=false for slug={system_slug!r}"


# ── Lint snapshot tests ──────────────────────────────────────────────────────

def test_lint_transition_captures_snapshot(tmp_wiki):
    """A lint-driven _transition() records content_snapshot in the lifecycle event."""
    import asyncio
    from synthadoc.agents.lint_agent import LintAgent
    from synthadoc.storage.log import AuditDB
    from synthadoc.storage.wiki import WikiStorage

    wiki_dir = tmp_wiki / "wiki"
    page_body = "Content that lint will mark stale."
    (wiki_dir / "lint-snap.md").write_text(
        f"---\ntitle: Lint Snap\nstatus: active\nconfidence: medium\n"
        f"tags: []\nsources: []\n---\n\n{page_body}\n",
        encoding="utf-8",
    )

    store = WikiStorage(wiki_dir)
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")

    async def run():
        await audit.init()
        await audit.set_page_state("lint-snap", "active", "user")
        agent = LintAgent(
            provider=None,
            store=store,
            log_writer=None,
            audit_db=audit,
            wiki_root=tmp_wiki,
        )
        page = store.read_page("lint-snap")
        await agent._transition("lint-snap", page, "active", "stale", "source changed")

    asyncio.run(run())

    async def check():
        await audit.init()
        snaps = await audit.list_page_snapshots("lint-snap")
        assert len(snaps) == 1, f"Expected 1 snapshot, got {len(snaps)}"
        full = await audit.get_snapshot_by_index("lint-snap", 1)
        assert full is not None
        assert page_body in full["content_snapshot"]

    asyncio.run(check())
