# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Stored timestamps are UTC; anything shown to the user must be local time.

No test here depends on the platform's timezone tooling (Windows has no ``tzset``):
the conversion is proven with a fixed UTC offset, and the default is proven to be
exactly what the system's own local conversion gives.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from synthadoc.utils import fmt_ts

UTC_EVENING = "2026-11-25T03:00:00+00:00"          # 03:00 UTC on the 25th ...
LOS_ANGELES = timezone(timedelta(hours=-8))        # ... is still the evening of the 24th there


def test_fmt_ts_converts_to_the_target_zone_not_the_utc_date():
    assert fmt_ts(UTC_EVENING, "%Y-%m-%d", tz=LOS_ANGELES) == "2026-11-24"
    assert fmt_ts(UTC_EVENING, "%Y-%m-%d %H:%M", tz=LOS_ANGELES) == "2026-11-24 19:00"


def test_fmt_ts_defaults_to_the_machines_local_time():
    expected = datetime.fromisoformat(UTC_EVENING).astimezone().strftime("%Y-%m-%d %H:%M")
    assert fmt_ts(UTC_EVENING) == expected


def test_fmt_ts_treats_a_bare_timestamp_as_utc():
    assert fmt_ts("2026-11-25 03:00:00", "%Y-%m-%d", tz=LOS_ANGELES) == "2026-11-24"


def test_fmt_ts_empty_input_is_a_dash():
    assert fmt_ts(None) == "—" and fmt_ts("") == "—"


def test_query_agent_does_not_slice_raw_utc_timestamps_for_display():
    src = Path(__file__).resolve().parents[2] / "synthadoc" / "agents" / "query_agent.py"
    text = src.read_text(encoding="utf-8")
    for needle in ('("ingested_at") or "")[:10]', '"updated_at", "")[:10]', "created_at or '')[:19]"):
        assert needle not in text, needle
