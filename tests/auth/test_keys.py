# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Peter White / axoviq.com
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from synthadoc.auth import keys
from synthadoc.security.redact import redact_text

MASK = "[REDACTED]"

NOW = datetime(2026, 11, 27, 12, 0, 0, tzinfo=timezone.utc)


def test_a_generated_key_has_the_documented_shape_and_round_trips():
    new = keys.generate_key()
    assert len(new.key_id) == 12 and len(new.secret) == 64
    assert new.key == f"sd_{new.key_id}_{new.secret}"
    assert keys.parse_key(new.key) == (new.key_id, new.secret)
    assert keys.parse_key("  " + new.key + "\n") == (new.key_id, new.secret)
    assert new.secret_hash == keys.hash_secret(new.secret) and new.secret_hash != new.secret


def test_two_keys_differ():
    assert keys.generate_key().key != keys.generate_key().key


@pytest.mark.parametrize("bad", [
    "", "sd", "sd_", "sd__", "xx_" + "a" * 12 + "_" + "b" * 64, "sd_" + "a" * 11 + "_" + "b" * 64,
    "sd_" + "a" * 13 + "_" + "b" * 64, "sd_" + "a" * 12 + "_" + "b" * 63,
    "sd_" + "A" * 12 + "_" + "b" * 64, "sd_" + "g" * 12 + "_" + "b" * 64,
    "sd_" + "a" * 12 + "_" + "b" * 64 + "_extra", "sd_" + "a" * 12 + "-" + "b" * 64, None, 123,
])
def test_a_malformed_key_is_rejected(bad):
    assert keys.parse_key(bad) is None


@pytest.mark.parametrize("name", ["ci", "alice", "a.b_c-d@e", "x" * 64, "Key1"])
def test_good_names(name):
    assert keys.validate_name(name) == name


@pytest.mark.parametrize("name", [
    "", "x" * 65, "has space", "tab\there", "new\nline", "esc\x1b[31m", "semi;colon",
    "unicodé", "0123456789ab", "0123456789AB",
])
def test_bad_names(name):
    with pytest.raises(ValueError):
        keys.validate_name(name)


def test_roles_expand_to_cumulative_scopes():
    assert keys.scopes_for_role("viewer") == ("read",)
    assert keys.scopes_for_role("Contributor") == ("read", "write")
    assert keys.scopes_for_role("operator") == ("read", "write", "operate")
    assert keys.scopes_for_role("admin") == ("read", "write", "operate", "admin")
    with pytest.raises(ValueError, match="Unknown role"):
        keys.scopes_for_role("root")


def test_scopes_are_canonical_and_unknown_ones_are_errors():
    assert keys.parse_scopes("write, read,read") == ("read", "write")
    with pytest.raises(ValueError, match="Unknown scope: root"):
        keys.parse_scopes("read,root")
    with pytest.raises(ValueError):
        keys.parse_scopes(" , ")


def test_relative_expiry():
    assert keys.parse_expiry("30d", now=NOW) == NOW + timedelta(days=30)
    assert keys.parse_expiry("12h", now=NOW) == NOW + timedelta(hours=12)


def test_a_date_is_the_end_of_that_day_in_local_time():
    est = timezone(timedelta(hours=-5))
    got = keys.parse_expiry("2027-03-01", now=NOW, local_tz=est)
    assert got == datetime(2027, 3, 2, 4, 59, 59, tzinfo=timezone.utc)   # 23:59:59 at UTC-5


@pytest.mark.parametrize("text", ["", "soon", "0d", "-3d", "2027-13-01", "2020-01-01", "30", "d30"])
def test_bad_or_past_expiry(text):
    with pytest.raises(ValueError):
        keys.parse_expiry(text, now=NOW)


def test_utc_storage_format_round_trips():
    assert keys.format_utc(NOW) == "2026-11-27T12:00:00Z"
    assert keys.parse_utc("2026-11-27T12:00:00Z") == NOW
    est = timezone(timedelta(hours=-5))
    assert keys.format_utc(NOW.astimezone(est)) == "2026-11-27T12:00:00Z"


def test_a_generated_key_is_masked_by_the_redactor():
    """Guards drift between this key format and the pattern in security/redact.py."""
    new = keys.generate_key()
    for text in (f"created {new.key}", f"key={new.key}&x=1", f"MY_KEY_{new.key}", f'"{new.key}"'):
        out = redact_text(text)
        assert new.secret not in out and MASK in out
