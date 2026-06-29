# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from synthadoc.storage.wiki import SourceRef, _sources_to_dicts, _sources_from_dicts


def test_source_ref_truncated_default_false():
    s = SourceRef(file="a.pdf", hash="abc", size=100, ingested="2026-01-01")
    assert s.truncated is False


def test_sources_to_dicts_truncated_true_included():
    s = SourceRef(file="a.pdf", hash="abc", size=100, ingested="2026-01-01", truncated=True)
    d = _sources_to_dicts([s])
    assert d[0]["truncated"] is True


def test_sources_to_dicts_truncated_false_omitted():
    s = SourceRef(file="a.pdf", hash="abc", size=100, ingested="2026-01-01", truncated=False)
    d = _sources_to_dicts([s])
    assert "truncated" not in d[0]


def test_sources_from_dicts_truncated_true_roundtrip():
    raw = [{"file": "a.pdf", "hash": "abc", "size": 100, "ingested": "2026-01-01", "truncated": True}]
    refs = _sources_from_dicts(raw)
    assert refs[0].truncated is True


def test_sources_from_dicts_truncated_missing_defaults_false():
    raw = [{"file": "a.pdf", "hash": "abc", "size": 100, "ingested": "2026-01-01"}]
    refs = _sources_from_dicts(raw)
    assert refs[0].truncated is False
