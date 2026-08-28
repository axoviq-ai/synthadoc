# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from synthadoc.cli.retract import retract_app

runner = CliRunner()


def _make_wiki(tmp_path: Path, pages: dict[str, str]) -> Path:
    """Create a minimal wiki directory with given {slug: content} pages.

    Returns ``wiki_root`` (the base directory).  Page .md files are placed in
    ``wiki_root/wiki/`` to match the real on-disk layout; ``_resolve_pages_dir``
    will resolve to that subdirectory at runtime.
    """
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    (wiki_root / ".synthadoc").mkdir()
    pages_dir = wiki_root / "wiki"
    pages_dir.mkdir()
    for slug, content in pages.items():
        (pages_dir / f"{slug}.md").write_text(content, encoding="utf-8")
    return wiki_root


def test_scan_dry_run_no_matches(tmp_path):
    """scan with no sensitive data → summary shows 0 matches."""
    wiki_root = _make_wiki(tmp_path, {"my-page": "# My Page\n\nNo secrets here.\n"})
    with patch("synthadoc.cli.retract._resolve_wiki_root", return_value=wiki_root), \
         patch("synthadoc.cli.retract._load_wiki_config") as mock_cfg:
        from synthadoc.config import SecurityConfig
        mock_cfg.return_value = MagicMock(security=SecurityConfig(sensitive_scan_enabled=True))
        result = runner.invoke(retract_app, ["scan", "-w", "wiki"])
    assert result.exit_code == 0
    assert "no sensitive data detected" in result.output.lower()


def test_scan_dry_run_with_matches(tmp_path):
    """scan finds an API key → reports slug and line number, no value."""
    wiki_root = _make_wiki(tmp_path, {
        "secret-page": "# Secret\n\napi_key = sk-abcdefghijklmnopqrst\n"
    })
    with patch("synthadoc.cli.retract._resolve_wiki_root", return_value=wiki_root), \
         patch("synthadoc.cli.retract._load_wiki_config") as mock_cfg:
        from synthadoc.config import SecurityConfig
        mock_cfg.return_value = MagicMock(security=SecurityConfig(sensitive_scan_enabled=True))
        result = runner.invoke(retract_app, ["scan", "-w", "wiki"])
    assert result.exit_code == 0
    assert "secret-page" in result.output
    # Value must NOT appear in output
    assert "sk-abcdefghijklmnopqrst" not in result.output
    assert "api_key" in result.output


def test_scan_apply_redacts_file(tmp_path):
    """scan --apply --yes writes [REDACTED] back to the file."""
    wiki_root = _make_wiki(tmp_path, {
        "pg": "# Page\n\nemail: user@example.com\n"
    })
    with patch("synthadoc.cli.retract._resolve_wiki_root", return_value=wiki_root), \
         patch("synthadoc.cli.retract._load_wiki_config") as mock_cfg, \
         patch("synthadoc.cli.retract._get_audit_db") as mock_db:
        from synthadoc.config import SecurityConfig
        mock_cfg.return_value = MagicMock(security=SecurityConfig(sensitive_scan_enabled=True))
        mock_db.return_value = MagicMock(
            init=AsyncMock(),
            record_retract_event=AsyncMock(),
        )
        result = runner.invoke(retract_app, ["scan", "-w", "wiki", "--apply", "--yes"])
    assert result.exit_code == 0
    content = (wiki_root / "wiki" / "pg.md").read_text(encoding="utf-8")
    assert "user@example.com" not in content
    assert "[REDACTED]" in content


def test_scan_apply_no_matches_skips_write(tmp_path):
    """scan --apply on clean pages does not call record_retract_event."""
    wiki_root = _make_wiki(tmp_path, {"clean": "# Clean page\n\nNo secrets.\n"})
    with patch("synthadoc.cli.retract._resolve_wiki_root", return_value=wiki_root), \
         patch("synthadoc.cli.retract._load_wiki_config") as mock_cfg, \
         patch("synthadoc.cli.retract._get_audit_db") as mock_db:
        from synthadoc.config import SecurityConfig
        mock_cfg.return_value = MagicMock(security=SecurityConfig(sensitive_scan_enabled=True))
        mock_db_inst = MagicMock(init=AsyncMock(), record_retract_event=AsyncMock())
        mock_db.return_value = mock_db_inst
        result = runner.invoke(retract_app, ["scan", "-w", "wiki", "--apply", "--yes"])
    assert result.exit_code == 0
    mock_db_inst.record_retract_event.assert_not_called()


def test_scan_slug_filter(tmp_path):
    """--slug restricts scan to one page."""
    wiki_root = _make_wiki(tmp_path, {
        "pg-a": "api_key = sk-abcdefghijklmnopqrst",
        "pg-b": "password = hunter2superlongpass",
    })
    with patch("synthadoc.cli.retract._resolve_wiki_root", return_value=wiki_root), \
         patch("synthadoc.cli.retract._load_wiki_config") as mock_cfg:
        from synthadoc.config import SecurityConfig
        mock_cfg.return_value = MagicMock(security=SecurityConfig(sensitive_scan_enabled=True))
        result = runner.invoke(retract_app, ["scan", "-w", "wiki", "--slug", "pg-a"])
    assert result.exit_code == 0
    assert "pg-a" in result.output
    assert "pg-b" not in result.output


def test_status_json(tmp_path):
    """status --json returns parseable JSON with 'cycle' and 'events' keys."""
    wiki_root = _make_wiki(tmp_path, {})
    with patch("synthadoc.cli.retract._resolve_wiki_root", return_value=wiki_root), \
         patch("synthadoc.cli.retract._load_wiki_config") as mock_cfg, \
         patch("synthadoc.cli.retract._get_audit_db") as mock_db:
        from synthadoc.config import SecurityConfig
        mock_cfg.return_value = MagicMock(security=SecurityConfig(sensitive_scan_enabled=True))
        mock_db_inst = MagicMock()
        mock_db_inst.init = AsyncMock()
        mock_db_inst.get_last_retract_cycle = AsyncMock(return_value=None)
        mock_db_inst.list_retract_events = AsyncMock(return_value=[])
        mock_db.return_value = mock_db_inst
        result = runner.invoke(retract_app, ["status", "-w", "wiki", "--json"])
    assert result.exit_code == 0
    # Click 8.2+ mixes stderr into result.output; use result.stdout for pure JSON
    data = json.loads(result.stdout)
    assert isinstance(data, dict)
    assert "cycle" in data
    assert "events" in data


# ---------------------------------------------------------------------------
# Additional tests for branch coverage
# ---------------------------------------------------------------------------

def test_resolve_wiki_root_helper(tmp_path):
    """_resolve_wiki_root calls install.resolve_wiki_path and returns the result."""
    from synthadoc.cli.retract import _resolve_wiki_root
    with patch("synthadoc.cli.install.resolve_wiki_path", return_value=tmp_path) as mock_rwp:
        result = _resolve_wiki_root("my-wiki")
    mock_rwp.assert_called_once_with("my-wiki")
    assert result == tmp_path


def test_load_wiki_config_helper_no_config_file(tmp_path):
    """_load_wiki_config returns a Config even when config.toml is absent."""
    from synthadoc.cli.retract import _load_wiki_config
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    (wiki_root / ".synthadoc").mkdir()
    cfg = _load_wiki_config(wiki_root)
    assert cfg is not None
    assert hasattr(cfg, "security")


def test_get_audit_db_helper(tmp_path):
    """_get_audit_db returns an AuditDB pointed at the right path."""
    from synthadoc.cli.retract import _get_audit_db
    from synthadoc.storage.log import AuditDB
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    (wiki_root / ".synthadoc").mkdir()
    db = _get_audit_db(wiki_root)
    assert isinstance(db, AuditDB)


def test_scan_slug_nonexistent_warns(tmp_path):
    """--slug with a page that does not exist prints a warning."""
    wiki_root = _make_wiki(tmp_path, {})
    with patch("synthadoc.cli.retract._resolve_wiki_root", return_value=wiki_root), \
         patch("synthadoc.cli.retract._load_wiki_config") as mock_cfg:
        from synthadoc.config import SecurityConfig
        mock_cfg.return_value = MagicMock(security=SecurityConfig(sensitive_scan_enabled=True))
        result = runner.invoke(retract_app, ["scan", "-w", "wiki", "--slug", "nonexistent"])
    assert result.exit_code == 0
    assert "not found" in result.output.lower() or "warning" in result.output.lower()


def test_scan_apply_confirm_yes(tmp_path):
    """scan --apply without --yes redacts when user answers 'y'."""
    wiki_root = _make_wiki(tmp_path, {
        "pg": "# Page\n\nemail: user@example.com\n"
    })
    with patch("synthadoc.cli.retract._resolve_wiki_root", return_value=wiki_root), \
         patch("synthadoc.cli.retract._load_wiki_config") as mock_cfg, \
         patch("synthadoc.cli.retract._get_audit_db") as mock_db:
        from synthadoc.config import SecurityConfig
        mock_cfg.return_value = MagicMock(security=SecurityConfig(sensitive_scan_enabled=True))
        mock_db.return_value = MagicMock(
            init=AsyncMock(),
            record_retract_event=AsyncMock(),
        )
        result = runner.invoke(retract_app, ["scan", "-w", "wiki", "--apply"], input="y\n")
    assert result.exit_code == 0
    content = (wiki_root / "wiki" / "pg.md").read_text(encoding="utf-8")
    assert "user@example.com" not in content
    assert "[REDACTED]" in content


def test_scan_apply_abort_on_no(tmp_path):
    """scan --apply without --yes aborts when user answers 'n'."""
    wiki_root = _make_wiki(tmp_path, {
        "pg": "# Page\n\nemail: user@example.com\n"
    })
    with patch("synthadoc.cli.retract._resolve_wiki_root", return_value=wiki_root), \
         patch("synthadoc.cli.retract._load_wiki_config") as mock_cfg, \
         patch("synthadoc.cli.retract._get_audit_db") as mock_db:
        from synthadoc.config import SecurityConfig
        mock_cfg.return_value = MagicMock(security=SecurityConfig(sensitive_scan_enabled=True))
        mock_db.return_value = MagicMock(init=AsyncMock(), record_retract_event=AsyncMock())
        result = runner.invoke(retract_app, ["scan", "-w", "wiki", "--apply"], input="n\n")
    assert result.exit_code == 0
    assert "Aborted" in result.output


def test_scan_apply_zero_lines_changed(tmp_path):
    """When mask_page reports 0 changed lines no file is written and no audit event logged."""
    wiki_root = _make_wiki(tmp_path, {
        "pg": "# Page\n\nemail: user@example.com\n"
    })
    with patch("synthadoc.cli.retract._resolve_wiki_root", return_value=wiki_root), \
         patch("synthadoc.cli.retract._load_wiki_config") as mock_cfg, \
         patch("synthadoc.cli.retract._get_audit_db") as mock_db, \
         patch("synthadoc.core.retract.SensitiveScanner.mask_page", return_value=("unchanged", 0)):
        from synthadoc.config import SecurityConfig
        mock_cfg.return_value = MagicMock(security=SecurityConfig(sensitive_scan_enabled=True))
        mock_db_inst = MagicMock(init=AsyncMock(), record_retract_event=AsyncMock())
        mock_db.return_value = mock_db_inst
        result = runner.invoke(retract_app, ["scan", "-w", "wiki", "--apply", "--yes"])
    assert result.exit_code == 0
    mock_db_inst.record_retract_event.assert_not_called()


def test_status_table_with_events(tmp_path):
    """status without --json renders schedule header and per-page Rich table."""
    wiki_root = _make_wiki(tmp_path, {})
    fake_events = [
        {
            "event": "retract_scan",
            "timestamp": "2026-08-27T12:00:00+00:00",
            "metadata": json.dumps({
                "slug": "my-page",
                "matches_count": 2,
                "pattern_names": ["email", "api_key"],
                "applied": True,
            }),
        }
    ]
    fake_cycle = {
        "event": "retract_cycle",
        "timestamp": "2026-08-27T12:00:00+00:00",
        "metadata": json.dumps({
            "pages_scanned": 10,
            "pages_with_matches": 1,
            "next_run_at": "2026-09-03T12:00:00+00:00",
        }),
    }
    with patch("synthadoc.cli.retract._resolve_wiki_root", return_value=wiki_root), \
         patch("synthadoc.cli.retract._load_wiki_config") as mock_cfg, \
         patch("synthadoc.cli.retract._get_audit_db") as mock_db:
        from synthadoc.config import SecurityConfig
        mock_cfg.return_value = MagicMock(security=SecurityConfig(sensitive_scan_enabled=True))
        mock_db_inst = MagicMock()
        mock_db_inst.init = AsyncMock()
        mock_db_inst.get_last_retract_cycle = AsyncMock(return_value=fake_cycle)
        mock_db_inst.list_retract_events = AsyncMock(return_value=fake_events)
        mock_db.return_value = mock_db_inst
        result = runner.invoke(retract_app, ["status", "-w", "wiki"])
    assert result.exit_code == 0
    assert "my-page" in result.output
    assert "10" in result.output  # pages_scanned shown in header


def test_status_no_events_message(tmp_path):
    """status without --json and no events prints the schedule header and 'none found' message."""
    wiki_root = _make_wiki(tmp_path, {})
    with patch("synthadoc.cli.retract._resolve_wiki_root", return_value=wiki_root), \
         patch("synthadoc.cli.retract._load_wiki_config") as mock_cfg, \
         patch("synthadoc.cli.retract._get_audit_db") as mock_db:
        from synthadoc.config import SecurityConfig
        mock_cfg.return_value = MagicMock(security=SecurityConfig(sensitive_scan_enabled=True))
        mock_db_inst = MagicMock()
        mock_db_inst.init = AsyncMock()
        mock_db_inst.get_last_retract_cycle = AsyncMock(return_value=None)
        mock_db_inst.list_retract_events = AsyncMock(return_value=[])
        mock_db.return_value = mock_db_inst
        result = runner.invoke(retract_app, ["status", "-w", "wiki"])
    assert result.exit_code == 0
    assert "Not yet run" in result.output
    assert "No per-page redaction records found" in result.output


# ---------------------------------------------------------------------------
# --changed-only flag
# ---------------------------------------------------------------------------

def test_scan_changed_only_no_previous_cycle(tmp_path):
    """--changed-only with no prior cycle record scans all pages and notes it."""
    wiki_root = _make_wiki(tmp_path, {"pg": "api_key = sk-abcdefghijklmnopqrst"})
    with patch("synthadoc.cli.retract._resolve_wiki_root", return_value=wiki_root), \
         patch("synthadoc.cli.retract._load_wiki_config") as mock_cfg, \
         patch("synthadoc.cli.retract._last_cycle_cutoff", return_value=None):
        from synthadoc.config import SecurityConfig
        mock_cfg.return_value = MagicMock(security=SecurityConfig(sensitive_scan_enabled=True))
        result = runner.invoke(retract_app, ["scan", "-w", "wiki", "--changed-only"])
    assert result.exit_code == 0
    # Should note "no previous scan" and still find the match
    assert "no previous scan" in result.output.lower()
    assert "pg" in result.output


def test_scan_changed_only_skips_old_files(tmp_path):
    """--changed-only skips pages that have not been modified since the last scan."""
    from datetime import timezone
    wiki_root = _make_wiki(tmp_path, {
        "old-page": "api_key = sk-abcdefghijklmnopqrst",
        "new-page": "normal content",
    })
    # Simulate: cutoff is in the future — all pages are "old"
    future_cutoff = datetime(2099, 1, 1, tzinfo=timezone.utc)
    with patch("synthadoc.cli.retract._resolve_wiki_root", return_value=wiki_root), \
         patch("synthadoc.cli.retract._load_wiki_config") as mock_cfg, \
         patch("synthadoc.cli.retract._last_cycle_cutoff", return_value=future_cutoff):
        from synthadoc.config import SecurityConfig
        mock_cfg.return_value = MagicMock(security=SecurityConfig(sensitive_scan_enabled=True))
        result = runner.invoke(retract_app, ["scan", "-w", "wiki", "--changed-only"])
    assert result.exit_code == 0
    # All pages are older than the future cutoff — nothing to scan
    assert "No pages modified since the last scan" in result.output


def test_scan_changed_only_scans_recent_files(tmp_path):
    """--changed-only scans pages that are newer than the cutoff."""
    from datetime import timezone
    wiki_root = _make_wiki(tmp_path, {
        "recent-page": "api_key = sk-abcdefghijklmnopqrst",
    })
    # Cutoff is in the distant past — all current files are "newer"
    old_cutoff = datetime(2000, 1, 1, tzinfo=timezone.utc)
    with patch("synthadoc.cli.retract._resolve_wiki_root", return_value=wiki_root), \
         patch("synthadoc.cli.retract._load_wiki_config") as mock_cfg, \
         patch("synthadoc.cli.retract._last_cycle_cutoff", return_value=old_cutoff):
        from synthadoc.config import SecurityConfig
        mock_cfg.return_value = MagicMock(security=SecurityConfig(sensitive_scan_enabled=True))
        result = runner.invoke(retract_app, ["scan", "-w", "wiki", "--changed-only"])
    assert result.exit_code == 0
    # Page is newer than 2000 cutoff — should appear in results
    assert "recent-page" in result.output
