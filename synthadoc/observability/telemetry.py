# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

_tracer: Optional[trace.Tracer] = None


class _JsonlExporter(SpanExporter):
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def export(self, spans):
        with open(self._path, "a", newline="\n") as f:
            for span in spans:
                if span.context is None:
                    continue
                f.write(json.dumps({
                    "name": span.name,
                    "trace_id": format(span.context.trace_id, "032x"),
                    "start_time": span.start_time,
                    "end_time": span.end_time,
                    "attributes": dict(span.attributes or {}),
                }) + "\n")
        return SpanExportResult.SUCCESS

    def shutdown(self): pass
    def force_flush(self, timeout_millis=30000): return True


def setup_telemetry(trace_path: Optional[Path] = None) -> None:
    global _tracer
    provider = TracerProvider()
    if trace_path:
        provider.add_span_processor(SimpleSpanProcessor(_JsonlExporter(Path(trace_path))))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("synthadoc")


def get_tracer() -> trace.Tracer:
    global _tracer
    if _tracer is None:
        setup_telemetry()
    assert _tracer is not None
    return _tracer


def record_cost(tokens: int, cost_usd: float, operation: str) -> None:
    with get_tracer().start_as_current_span(f"cost.{operation}") as span:
        span.set_attribute("tokens", tokens)
        span.set_attribute("cost_usd", cost_usd)
        span.set_attribute("operation", operation)
