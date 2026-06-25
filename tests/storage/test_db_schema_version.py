# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import asyncio
import sqlite3
from pathlib import Path
import pytest
from synthadoc.storage.log import AuditDB, DB_SCHEMA_VERSION


def test_db_schema_version_constant_is_int():
    assert isinstance(DB_SCHEMA_VERSION, int)
    assert DB_SCHEMA_VERSION >= 1


def test_audit_db_sets_pragma_user_version(tmp_path):
    db_path = tmp_path / "audit.db"
    db = AuditDB(db_path)
    asyncio.run(db.init())
    conn = sqlite3.connect(str(db_path))
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    assert version == DB_SCHEMA_VERSION
