# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import httpx
import pytest
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from synthadoc.cli.main import app

runner = CliRunner()


def _patch_resolve_wiki(name="my-wiki"):
    return patch("synthadoc.cli.export.resolve_wiki", return_value=name)


def _patch_server_url(url="http://127.0.0.1:7070"):
    return patch("synthadoc.cli.export.server_url", return_value=url)


def _patch_httpx_post_ok(content="wiki content"):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = content
    mock_resp.raise_for_status = MagicMock()
    return patch("synthadoc.cli.export.httpx.post", return_value=mock_resp)


def test_export_cmd_stdout_by_default():
    """export without --output must print content to stdout."""
    with _patch_resolve_wiki(), _patch_server_url(), _patch_httpx_post_ok("# Wiki Export\npage content"):
        result = runner.invoke(app, ["export", "-f", "llms.txt", "-w", "my-wiki"])
    assert result.exit_code == 0
    assert "Wiki Export" in result.output


def test_export_cmd_writes_to_file(tmp_path):
    """export --output must write content to the file and print confirmation."""
    out_file = tmp_path / "output.txt"
    with _patch_resolve_wiki(), _patch_server_url(), _patch_httpx_post_ok("exported text"):
        result = runner.invoke(app, [
            "export", "-f", "llms.txt", "-w", "my-wiki",
            "-o", str(out_file),
        ])
    assert result.exit_code == 0
    assert out_file.read_text(encoding="utf-8") == "exported text"
    assert "Exported to" in result.output


def test_export_cmd_connect_error_exits():
    """ConnectError must produce a useful error message and non-zero exit."""
    with _patch_resolve_wiki(), _patch_server_url(), \
         patch("synthadoc.cli.export.httpx.post", side_effect=httpx.ConnectError("refused")):
        result = runner.invoke(app, ["export", "-f", "llms.txt", "-w", "my-wiki"])
    assert result.exit_code != 0


def test_export_cmd_http_status_error_exits():
    """HTTPStatusError must produce an error message and non-zero exit."""
    req = httpx.Request("POST", "http://127.0.0.1:7070/export")
    bad_resp = MagicMock(spec=httpx.Response)
    bad_resp.status_code = 422
    bad_resp.text = "Unprocessable Entity"
    bad_resp.json.return_value = {"detail": "bad format"}
    exc = httpx.HTTPStatusError("422", request=req, response=bad_resp)

    with _patch_resolve_wiki(), _patch_server_url(), \
         patch("synthadoc.cli.export.httpx.post", side_effect=exc):
        result = runner.invoke(app, ["export", "-f", "invalid-fmt", "-w", "my-wiki"])
    assert result.exit_code != 0


def test_export_cmd_http_status_error_non_json():
    """HTTPStatusError with non-JSON body must fall back to raw text."""
    req = httpx.Request("POST", "http://127.0.0.1:7070/export")
    bad_resp = MagicMock(spec=httpx.Response)
    bad_resp.status_code = 500
    bad_resp.text = "Internal Server Error"
    bad_resp.json.side_effect = ValueError("not JSON")
    exc = httpx.HTTPStatusError("500", request=req, response=bad_resp)

    with _patch_resolve_wiki(), _patch_server_url(), \
         patch("synthadoc.cli.export.httpx.post", side_effect=exc):
        result = runner.invoke(app, ["export", "-f", "llms.txt", "-w", "my-wiki"])
    assert result.exit_code != 0


def test_export_cmd_context_pack_forwarded():
    """--context-pack must be included in the POST body."""
    captured_body = {}

    def _fake_post(url, json, timeout):
        captured_body.update(json)
        mock_resp = MagicMock()
        mock_resp.text = "content"
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    with _patch_resolve_wiki(), _patch_server_url(), \
         patch("synthadoc.cli.export.httpx.post", side_effect=_fake_post):
        result = runner.invoke(app, [
            "export", "-f", "json", "-w", "my-wiki",
            "--context-pack", "my-pack",
        ])
    assert result.exit_code == 0
    assert captured_body.get("context_pack") == "my-pack"


def test_export_cmd_status_filter_forwarded():
    """--status must be forwarded as status_filter in the POST body."""
    captured_body = {}

    def _fake_post(url, json, timeout):
        captured_body.update(json)
        mock_resp = MagicMock()
        mock_resp.text = "content"
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    with _patch_resolve_wiki(), _patch_server_url(), \
         patch("synthadoc.cli.export.httpx.post", side_effect=_fake_post):
        result = runner.invoke(app, [
            "export", "-f", "llms.txt", "-w", "my-wiki",
            "--status", "active",
        ])
    assert result.exit_code == 0
    assert captured_body.get("status_filter") == "active"


# ── OKF CLI tests ──────────────────────────────────────────────────────────────

import json as _json


def _patch_httpx_post_okf(files: dict):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = _json.dumps(files)
    mock_resp.json.return_value = files
    mock_resp.raise_for_status = MagicMock()
    return patch("synthadoc.cli.export.httpx.post", return_value=mock_resp)


def test_export_okf_writes_directory(tmp_path):
    """--format okf must write each file in the manifest into the output directory."""
    out_dir = tmp_path / "bundle"
    manifest = {
        "index.md": "---\ntype: index\n---\n\n# Wiki\n",
        "wiki/alan-turing.md": "---\ntype: person\n---\n\nContent.\n",
    }
    with _patch_resolve_wiki(), _patch_server_url(), _patch_httpx_post_okf(manifest):
        result = runner.invoke(app, [
            "export", "-f", "okf", "-w", "my-wiki",
            "-o", str(out_dir),
        ])
    assert result.exit_code == 0
    assert (out_dir / "index.md").read_text(encoding="utf-8") == manifest["index.md"]
    assert (out_dir / "wiki" / "alan-turing.md").read_text(encoding="utf-8") == manifest["wiki/alan-turing.md"]


def test_export_okf_requires_output_flag():
    """--format okf without --output must exit with a clear error message."""
    manifest = {"index.md": "---\ntype: index\n---\n"}
    with _patch_resolve_wiki(), _patch_server_url(), _patch_httpx_post_okf(manifest):
        result = runner.invoke(app, ["export", "-f", "okf", "-w", "my-wiki"])
    assert result.exit_code != 0
    assert "--output" in result.output or "--output" in (result.stderr or "")


def test_export_okf_creates_nested_directories(tmp_path):
    """OKF export must create intermediate directories (wiki/) automatically."""
    out_dir = tmp_path / "bundle"
    manifest = {
        "index.md": "---\ntype: index\n---\n",
        "log.md": "---\ntype: log\n---\n",
        "wiki/grace-hopper.md": "---\ntype: person\n---\n\nContent.\n",
    }
    with _patch_resolve_wiki(), _patch_server_url(), _patch_httpx_post_okf(manifest):
        runner.invoke(app, ["export", "-f", "okf", "-w", "my-wiki", "-o", str(out_dir)])
    assert (out_dir / "wiki" / "grace-hopper.md").exists()
