# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import asyncio
import logging
import logging.handlers
import json
from pathlib import Path
from synthadoc.config import LogsConfig


def _reset_root_logger():
    """Remove all handlers from the root logger so setup_logging() can re-run."""
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()


def _cfg(**kwargs) -> LogsConfig:
    return LogsConfig(
        level=kwargs.get("level", "INFO"),
        max_file_mb=kwargs.get("max_file_mb", 1),
        backup_count=kwargs.get("backup_count", 3),
    )


def test_setup_creates_log_file(tmp_path):
    _reset_root_logger()
    from synthadoc.core.logging_config import setup_logging
    setup_logging(tmp_path, cfg=_cfg())
    log_path = tmp_path / ".synthadoc" / "logs" / "synthadoc.log"
    assert log_path.exists(), "synthadoc.log should be created on setup"
    _reset_root_logger()


def test_log_file_contains_json_lines(tmp_path):
    _reset_root_logger()
    from synthadoc.core.logging_config import setup_logging
    setup_logging(tmp_path, cfg=_cfg())
    logger = logging.getLogger("synthadoc.test_module")
    logger.info("test event %s", "hello")
    for h in logging.getLogger().handlers:
        h.flush()
    log_path = tmp_path / ".synthadoc" / "logs" / "synthadoc.log"
    lines = [l for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert lines, "log file should have at least one entry"
    for line in lines:
        record = json.loads(line)
        assert "ts" in record
        assert "level" in record
        assert "msg" in record
    _reset_root_logger()


def test_get_job_logger_injects_extras(tmp_path):
    _reset_root_logger()
    from synthadoc.core.logging_config import setup_logging, get_job_logger
    setup_logging(tmp_path, cfg=_cfg())
    log = get_job_logger("synthadoc.agents.ingest_agent",
                         job_id="abc123", operation="ingest", wiki="test-wiki")
    log.info("page created: alan-turing")
    for h in logging.getLogger().handlers:
        h.flush()
    log_path = tmp_path / ".synthadoc" / "logs" / "synthadoc.log"
    records = [json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    job_records = [r for r in records if r.get("job_id") == "abc123"]
    assert job_records, "job_id should appear in at least one log record"
    assert job_records[-1]["operation"] == "ingest"
    assert job_records[-1]["wiki"] == "test-wiki"
    _reset_root_logger()


def test_setup_idempotent(tmp_path):
    """Calling setup_logging twice must not add duplicate handlers."""
    _reset_root_logger()
    from synthadoc.core.logging_config import setup_logging
    setup_logging(tmp_path, cfg=_cfg())
    handler_count_first = len(logging.getLogger().handlers)
    setup_logging(tmp_path, cfg=_cfg())
    assert len(logging.getLogger().handlers) == handler_count_first
    _reset_root_logger()


def test_console_level_from_config(tmp_path):
    """cfg.level controls the console handler threshold."""
    _reset_root_logger()
    from synthadoc.core.logging_config import setup_logging
    setup_logging(tmp_path, cfg=_cfg(level="WARNING"))
    console = next(h for h in logging.getLogger().handlers
                   if isinstance(h, logging.StreamHandler)
                   and not isinstance(h, logging.handlers.RotatingFileHandler))
    assert console.level == logging.WARNING
    _reset_root_logger()


def test_verbose_overrides_config_level(tmp_path):
    """--verbose forces DEBUG on the console even if config says INFO."""
    _reset_root_logger()
    from synthadoc.core.logging_config import setup_logging
    setup_logging(tmp_path, cfg=_cfg(level="INFO"), verbose=True)
    console = next(h for h in logging.getLogger().handlers
                   if isinstance(h, logging.StreamHandler)
                   and not isinstance(h, logging.handlers.RotatingFileHandler))
    assert console.level == logging.DEBUG
    _reset_root_logger()


def test_rotation_settings_applied(tmp_path):
    """RotatingFileHandler uses max_file_mb and backup_count from config."""
    _reset_root_logger()
    from synthadoc.core.logging_config import setup_logging
    setup_logging(tmp_path, cfg=_cfg(max_file_mb=2, backup_count=7))
    fh = next(h for h in logging.getLogger().handlers
              if isinstance(h, logging.handlers.RotatingFileHandler))
    assert fh.maxBytes == 2 * 1024 * 1024
    assert fh.backupCount == 7
    _reset_root_logger()


def test_suppress_shutdown_noise_blocks_cancelled_error(tmp_path):
    """CancelledError tracebacks from uvicorn.error are silenced on shutdown."""
    _reset_root_logger()
    from synthadoc.core.logging_config import setup_logging
    setup_logging(tmp_path, cfg=_cfg())
    uvicorn_logger = logging.getLogger("uvicorn.error")

    class _Sink(logging.Handler):
        records: list[logging.LogRecord] = []
        def emit(self, r: logging.LogRecord) -> None:
            self.records.append(r)

    sink = _Sink()
    sink.setLevel(logging.DEBUG)
    uvicorn_logger.addHandler(sink)

    try:
        raise asyncio.CancelledError()
    except asyncio.CancelledError:
        uvicorn_logger.error("lifespan receive failed", exc_info=True)

    assert not sink.records, "CancelledError record should be filtered out"
    _reset_root_logger()


def test_suppress_shutdown_noise_passes_other_errors(tmp_path):
    """Non-shutdown errors from uvicorn.error are still visible."""
    _reset_root_logger()
    from synthadoc.core.logging_config import setup_logging
    setup_logging(tmp_path, cfg=_cfg())
    uvicorn_logger = logging.getLogger("uvicorn.error")

    class _Sink(logging.Handler):
        records: list[logging.LogRecord] = []
        def emit(self, r: logging.LogRecord) -> None:
            self.records.append(r)

    sink = _Sink()
    sink.setLevel(logging.DEBUG)
    uvicorn_logger.addHandler(sink)

    try:
        raise OSError("address already in use")
    except OSError:
        uvicorn_logger.error("startup failed", exc_info=True)

    assert len(sink.records) == 1, "OSError should not be filtered"
    _reset_root_logger()
