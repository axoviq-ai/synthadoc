# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import httpx
import pytest
from unittest.mock import MagicMock, patch, call

import typer

import synthadoc.cli._http as _http_module


# ── shared helpers ────────────────────────────────────────────────────────────

def _make_status_error(status: int, method: str, url: str) -> httpx.HTTPStatusError:
    req = httpx.Request(method, url)
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.json.return_value = {"detail": f"HTTP {status}"}
    resp.text = f"HTTP {status}"
    return httpx.HTTPStatusError(str(status), request=req, response=resp)


def _fake_server_info(
    *,
    client_timeout: int = 60,
    client_llm_timeout: int = 180,
    client_stream_timeout: int = 120,
    port: int = 7070,
) -> tuple[str, MagicMock]:
    """Return a (url, cfg_mock) pair suitable for patching _server_info."""
    cfg = MagicMock()
    cfg.server.client_timeout_seconds = client_timeout
    cfg.server.client_llm_timeout_seconds = client_llm_timeout
    cfg.server.client_stream_timeout_seconds = client_stream_timeout
    cfg.server.port = port
    return (f"http://127.0.0.1:{port}", cfg)


# ── _detail() ────────────────────────────────────────────────────────────────

def test_detail_extracts_json_detail():
    from synthadoc.cli._http import _detail
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = {"detail": "Page not found"}
    assert _detail(resp) == "Page not found"


def test_detail_falls_back_to_text():
    from synthadoc.cli._http import _detail
    resp = MagicMock(spec=httpx.Response)
    resp.json.side_effect = ValueError("not JSON")
    resp.text = "  internal server error  "
    assert _detail(resp) == "internal server error"


# ── _timeout_error() ─────────────────────────────────────────────────────────

def test_timeout_error_query_path_exits():
    from synthadoc.cli._http import _timeout_error
    with pytest.raises(typer.Exit):
        _timeout_error("/query", 60)


def test_timeout_error_jobs_path_exits():
    from synthadoc.cli._http import _timeout_error
    with pytest.raises(typer.Exit):
        _timeout_error("/jobs/123", 10)


def test_timeout_error_other_path_exits():
    from synthadoc.cli._http import _timeout_error
    with pytest.raises(typer.Exit):
        _timeout_error("/status", 30)


# ── get() ────────────────────────────────────────────────────────────────────

def test_get_connect_error_exits():
    with patch.object(_http_module, "_server_info", return_value=_fake_server_info()), \
         patch.object(httpx, "get", side_effect=httpx.ConnectError("refused")):
        with pytest.raises(typer.Exit):
            _http_module.get("my-wiki", "/status")


def test_get_read_timeout_exits():
    with patch.object(_http_module, "_server_info", return_value=_fake_server_info()), \
         patch.object(httpx, "get", side_effect=httpx.ReadTimeout("timeout")):
        with pytest.raises(typer.Exit):
            _http_module.get("my-wiki", "/query")


def test_get_http_status_error_exits():
    err = _make_status_error(500, "GET", "http://127.0.0.1:7070/status")
    with patch.object(_http_module, "_server_info", return_value=_fake_server_info()), \
         patch.object(httpx, "get", side_effect=err):
        with pytest.raises(typer.Exit):
            _http_module.get("my-wiki", "/status")


# ── post() ───────────────────────────────────────────────────────────────────

def test_post_connect_error_exits():
    with patch.object(_http_module, "_server_info", return_value=_fake_server_info()), \
         patch.object(httpx, "post", side_effect=httpx.ConnectError("refused")):
        with pytest.raises(typer.Exit):
            _http_module.post("my-wiki", "/ingest", {})


def test_post_read_timeout_exits():
    with patch.object(_http_module, "_server_info", return_value=_fake_server_info()), \
         patch.object(httpx, "post", side_effect=httpx.ReadTimeout("timeout")):
        with pytest.raises(typer.Exit):
            _http_module.post("my-wiki", "/jobs/cancel", {})


def test_post_http_status_error_exits():
    err = _make_status_error(422, "POST", "http://127.0.0.1:7070/ingest")
    with patch.object(_http_module, "_server_info", return_value=_fake_server_info()), \
         patch.object(httpx, "post", side_effect=err):
        with pytest.raises(typer.Exit):
            _http_module.post("my-wiki", "/ingest", {"source": "x"})


def test_post_default_timeout_uses_client_timeout():
    """post() with no flags uses client_timeout_seconds from config."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.json.return_value = {"ok": True}
    with patch.object(_http_module, "_server_info",
                      return_value=_fake_server_info(client_timeout=55)), \
         patch.object(httpx, "post", return_value=mock_resp) as mock_post:
        _http_module.post("my-wiki", "/jobs/ingest", {"source": "x"})
    _, kwargs = mock_post.call_args
    assert kwargs["timeout"] == 55


def test_post_llm_flag_uses_llm_timeout():
    """post(..., llm=True) uses client_llm_timeout_seconds from config."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.json.return_value = {"ok": True}
    with patch.object(_http_module, "_server_info",
                      return_value=_fake_server_info(client_llm_timeout=200)), \
         patch.object(httpx, "post", return_value=mock_resp) as mock_post:
        _http_module.post("my-wiki", "/analyse", {"source": "x"}, llm=True)
    _, kwargs = mock_post.call_args
    assert kwargs["timeout"] == 200


def test_post_explicit_timeout_wins_over_config():
    """An explicit timeout= always takes precedence over both config values."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.json.return_value = {"ok": True}
    with patch.object(_http_module, "_server_info",
                      return_value=_fake_server_info(client_timeout=60, client_llm_timeout=180)), \
         patch.object(httpx, "post", return_value=mock_resp) as mock_post:
        _http_module.post("my-wiki", "/analyse", {"source": "x"}, timeout=42, llm=True)
    _, kwargs = mock_post.call_args
    assert kwargs["timeout"] == 42


# ── delete() ─────────────────────────────────────────────────────────────────

def test_delete_connect_error_exits():
    with patch.object(_http_module, "_server_info", return_value=_fake_server_info()), \
         patch.object(httpx, "delete", side_effect=httpx.ConnectError("refused")):
        with pytest.raises(typer.Exit):
            _http_module.delete("my-wiki", "/jobs/abc")


def test_delete_http_status_error_exits():
    err = _make_status_error(404, "DELETE", "http://127.0.0.1:7070/jobs/abc")
    with patch.object(_http_module, "_server_info", return_value=_fake_server_info()), \
         patch.object(httpx, "delete", side_effect=err):
        with pytest.raises(typer.Exit):
            _http_module.delete("my-wiki", "/jobs/abc")


# ── get_stream() ─────────────────────────────────────────────────────────────

def test_get_stream_yields_events():
    """get_stream must yield (event_name, data) tuples for SSE lines."""
    sse_body = "event: token\ndata: {\"text\": \"hello\"}\n\nevent: done\ndata: {}\n\n"

    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.raise_for_status = MagicMock()
    mock_resp.iter_lines = MagicMock(return_value=iter(sse_body.splitlines()))

    mock_client = MagicMock()
    mock_client.__enter__ = lambda s: s
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.stream = MagicMock(return_value=mock_resp)

    with patch.object(_http_module, "_server_info", return_value=_fake_server_info()), \
         patch.object(_http_module.httpx, "Client", return_value=mock_client):
        events = list(_http_module.get_stream("my-wiki", "/query/stream", q="test"))

    assert events[0] == ("token", {"text": "hello"})
    assert events[1] == ("done", {})


def test_get_stream_default_timeout_uses_stream_timeout():
    """get_stream() with no explicit timeout uses client_stream_timeout_seconds."""
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.raise_for_status = MagicMock()
    mock_resp.iter_lines = MagicMock(return_value=iter([]))

    mock_client = MagicMock()
    mock_client.__enter__ = lambda s: s
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.stream = MagicMock(return_value=mock_resp)

    captured = {}

    def fake_client(timeout):
        captured["timeout"] = timeout
        return mock_client

    with patch.object(_http_module, "_server_info",
                      return_value=_fake_server_info(client_stream_timeout=99)), \
         patch.object(_http_module.httpx, "Client", side_effect=fake_client):
        list(_http_module.get_stream("my-wiki", "/query/stream"))

    assert captured["timeout"] == 99


def test_get_stream_connect_error_exits():
    """get_stream ConnectError must call _no_server."""
    mock_client = MagicMock()
    mock_client.__enter__ = lambda s: s
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.stream = MagicMock(side_effect=httpx.ConnectError("refused"))

    with patch.object(_http_module, "_server_info", return_value=_fake_server_info()), \
         patch.object(_http_module.httpx, "Client", return_value=mock_client):
        with pytest.raises(typer.Exit):
            list(_http_module.get_stream("my-wiki", "/query/stream", q="test"))


def test_get_stream_read_timeout_exits():
    """get_stream ReadTimeout must call _timeout_error."""
    mock_client = MagicMock()
    mock_client.__enter__ = lambda s: s
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.stream = MagicMock(side_effect=httpx.ReadTimeout("timeout"))

    with patch.object(_http_module, "_server_info", return_value=_fake_server_info()), \
         patch.object(_http_module.httpx, "Client", return_value=mock_client):
        with pytest.raises(typer.Exit):
            list(_http_module.get_stream("my-wiki", "/query/stream", q="test"))


def test_get_stream_http_status_error_exits():
    """get_stream HTTPStatusError must call cli_error."""
    mock_resp_inner = MagicMock()
    mock_resp_inner.__enter__ = lambda s: s
    mock_resp_inner.__exit__ = MagicMock(return_value=False)
    err = _make_status_error(500, "GET", "http://127.0.0.1:7070/query/stream")
    mock_resp_inner.raise_for_status = MagicMock(side_effect=err)

    mock_client = MagicMock()
    mock_client.__enter__ = lambda s: s
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.stream = MagicMock(return_value=mock_resp_inner)

    with patch.object(_http_module, "_server_info", return_value=_fake_server_info()), \
         patch.object(_http_module.httpx, "Client", return_value=mock_client):
        with pytest.raises(typer.Exit):
            list(_http_module.get_stream("my-wiki", "/query/stream", q="test"))


def test_get_stream_malformed_json_yields_raw():
    """get_stream must yield raw string dict when data line is not valid JSON."""
    sse_body = "event: token\ndata: not-json\n\n"

    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.raise_for_status = MagicMock()
    mock_resp.iter_lines = MagicMock(return_value=iter(sse_body.splitlines()))

    mock_client = MagicMock()
    mock_client.__enter__ = lambda s: s
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.stream = MagicMock(return_value=mock_resp)

    with patch.object(_http_module, "_server_info", return_value=_fake_server_info()), \
         patch.object(_http_module.httpx, "Client", return_value=mock_client):
        events = list(_http_module.get_stream("my-wiki", "/query/stream", q="test"))

    assert events[0] == ("token", {"raw": "not-json"})


# ── config parsing ────────────────────────────────────────────────────────────

def test_server_config_client_timeouts_parsed(tmp_path):
    """[server] client_*_timeout_seconds are parsed from config.toml."""
    from synthadoc.config import load_config
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        '[agents]\ndefault = { provider = "gemini", model = "gemini-2.5-flash-lite" }\n'
        "[server]\n"
        "client_timeout_seconds = 90\n"
        "client_llm_timeout_seconds = 300\n"
        "client_stream_timeout_seconds = 200\n"
    )
    cfg = load_config(project_config=cfg_file)
    assert cfg.server.client_timeout_seconds == 90
    assert cfg.server.client_llm_timeout_seconds == 300
    assert cfg.server.client_stream_timeout_seconds == 200


def test_server_config_client_timeouts_default(tmp_path):
    """Omitting client_*_timeout_seconds from config.toml gives the correct defaults."""
    from synthadoc.config import load_config
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        '[agents]\ndefault = { provider = "gemini", model = "gemini-2.5-flash-lite" }\n'
    )
    cfg = load_config(project_config=cfg_file)
    assert cfg.server.client_timeout_seconds == 60
    assert cfg.server.client_llm_timeout_seconds == 180
    assert cfg.server.client_stream_timeout_seconds == 120
