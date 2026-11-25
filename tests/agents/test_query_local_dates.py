# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Stored timestamps are UTC; anything shown to the user must be local time."""
import os
import time

from synthadoc.utils import fmt_ts


def test_fmt_ts_shows_the_local_date_not_the_utc_date(monkeypatch):
    if not hasattr(time, "tzset"):
        import pytest
        pytest.skip("tzset unavailable on this platform")
    monkeypatch.setenv("TZ", "America/Los_Angeles")
    time.tzset()
    try:
        # 03:00 UTC on the 25th is still the evening of the 24th in Los Angeles.
        assert fmt_ts("2026-11-25T03:00:00+00:00", "%Y-%m-%d") == "2026-11-24"
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()


def test_query_agent_does_not_slice_raw_utc_timestamps_for_display():
    from pathlib import Path
    src = Path(__file__).resolve().parents[2] / "synthadoc" / "agents" / "query_agent.py"
    text = src.read_text(encoding="utf-8")
    for needle in ('("ingested_at") or "")[:10]', '"updated_at", "")[:10]', "created_at or '')[:19]"):
        assert needle not in text, needle
