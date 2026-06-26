# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import json
from unittest.mock import MagicMock, patch

from synthadoc.observability.telemetry import (
    _JsonlExporter,
    setup_telemetry,
    get_tracer,
    record_cost,
)


def _make_span(name: str, trace_id: int = 0xABCD1234, attrs: dict | None = None):
    span = MagicMock()
    span.name = name
    span.context.trace_id = trace_id
    span.start_time = 1_000_000_000
    span.end_time = 2_000_000_000
    span.attributes = attrs or {}
    return span


def test_tracer_created(tmp_path):
    setup_telemetry(trace_path=tmp_path / "traces.jsonl")
    assert get_tracer() is not None


def test_record_cost_does_not_raise():
    record_cost(tokens=1000, cost_usd=0.01, operation="ingest")


def test_traces_written_to_file(tmp_path):
    trace_file = tmp_path / "traces.jsonl"
    exporter = _JsonlExporter(trace_file)

    exporter.export([_make_span("test.span")])

    assert trace_file.exists(), "traces.jsonl should be created after export()"
    lines = [l for l in trace_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert lines, "traces.jsonl should contain at least one entry"
    record = json.loads(lines[0])
    assert record["name"] == "test.span"
    assert "trace_id" in record
    assert "start_time" in record
    assert "end_time" in record


def test_traces_skips_span_with_no_context(tmp_path):
    trace_file = tmp_path / "traces.jsonl"
    exporter = _JsonlExporter(trace_file)

    span = MagicMock()
    span.context = None
    exporter.export([span])

    # File may not exist at all, or be empty — either is correct
    if trace_file.exists():
        lines = [l for l in trace_file.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert not lines, "span with no context should not be written"


def test_traces_appends_multiple_spans(tmp_path):
    trace_file = tmp_path / "traces.jsonl"
    exporter = _JsonlExporter(trace_file)

    exporter.export([_make_span("span.one")])
    exporter.export([_make_span("span.two")])

    lines = [l for l in trace_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    assert json.loads(lines[0])["name"] == "span.one"
    assert json.loads(lines[1])["name"] == "span.two"


def test_record_cost_span_name_and_attributes():
    mock_span = MagicMock()
    mock_tracer = MagicMock()
    mock_tracer.start_as_current_span.return_value.__enter__ = lambda s: mock_span
    mock_tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)

    with patch("synthadoc.observability.telemetry.get_tracer", return_value=mock_tracer):
        record_cost(tokens=500, cost_usd=0.05, operation="query")

    mock_tracer.start_as_current_span.assert_called_once_with("cost.query")
    mock_span.set_attribute.assert_any_call("tokens", 500)
    mock_span.set_attribute.assert_any_call("cost_usd", 0.05)
    mock_span.set_attribute.assert_any_call("operation", "query")
