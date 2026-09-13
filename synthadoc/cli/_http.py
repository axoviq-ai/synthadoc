# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

"""Shared HTTP client helpers for CLI thin-client commands."""

import httpx
import typer
from typing import NoReturn

from synthadoc.config import load_config, Config as _Config
from synthadoc.cli._wiki import resolve_wiki_path
from synthadoc import errors as E


def server_url(wiki: str) -> str:
    """Return the base URL for the wiki's server."""
    return _server_info(wiki)[0]


def _server_info(wiki: str) -> tuple[str, _Config]:
    """Return (base_url, config) for the wiki's server."""
    root = resolve_wiki_path(wiki)
    config_path = root / ".synthadoc" / "config.toml"
    if not config_path.exists():
        E.cli_error(
            E.WIKI_NOT_REGISTERED,
            f"Wiki '{wiki}' is not installed.",
            f"Make sure wiki '{wiki}' was installed with 'synthadoc install'.",
        )
    try:
        cfg = load_config(project_config=config_path)
    except E.ConfigError as exc:
        E.cli_error(exc.code, str(exc), exc.hint)
    return f"http://127.0.0.1:{cfg.server.port}", cfg


def get(wiki: str, path: str, timeout: int | None = None, **params) -> dict:
    url, cfg = _server_info(wiki)
    t = timeout if timeout is not None else cfg.server.client_timeout_seconds
    try:
        resp = httpx.get(f"{url}{path}", params=params, timeout=t)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        _no_server(wiki)
    except httpx.ReadTimeout:
        _timeout_error(path, t)
    except httpx.HTTPStatusError as e:
        E.cli_error(E.SRV_HTTP_ERROR,
                    f"Server returned {e.response.status_code}: {_detail(e.response)}")


def post(wiki: str, path: str, body: dict, timeout: int | None = None,
         *, llm: bool = False) -> dict:
    """POST *body* to *path* and return the JSON response.

    *timeout* overrides the config value when given.
    *llm=True* selects ``client_llm_timeout_seconds`` (default 180 s) instead of
    the general ``client_timeout_seconds`` (default 60 s) — use it for endpoints
    that block on a full LLM call (e.g. ``/analyse``, ``/context/build``).
    """
    url, cfg = _server_info(wiki)
    if timeout is not None:
        t = timeout
    elif llm:
        t = cfg.server.client_llm_timeout_seconds
    else:
        t = cfg.server.client_timeout_seconds
    try:
        resp = httpx.post(f"{url}{path}", json=body, timeout=t)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        _no_server(wiki)
    except httpx.ReadTimeout:
        _timeout_error(path, t)
    except httpx.HTTPStatusError as e:
        E.cli_error(E.SRV_HTTP_ERROR,
                    f"Server returned {e.response.status_code}: {_detail(e.response)}")


def delete(wiki: str, path: str) -> dict:
    url, cfg = _server_info(wiki)
    try:
        resp = httpx.delete(f"{url}{path}", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        _no_server(wiki)
    except httpx.HTTPStatusError as e:
        E.cli_error(E.SRV_HTTP_ERROR,
                    f"Server returned {e.response.status_code}: {_detail(e.response)}")


def get_stream(wiki: str, path: str, timeout: int | None = None, **params):
    """Yield (event_name, data_dict) tuples from an SSE endpoint.

    *timeout* overrides the config value when given; otherwise uses
    ``client_stream_timeout_seconds`` (default 120 s).
    """
    import json as _json
    url, cfg = _server_info(wiki)
    t = timeout if timeout is not None else cfg.server.client_stream_timeout_seconds
    full_url = f"{url}{path}"
    try:
        with httpx.Client(timeout=t) as client:
            with client.stream("GET", full_url, params=params) as resp:
                resp.raise_for_status()
                event_name = "message"
                for line in resp.iter_lines():
                    if line.startswith("event:"):
                        event_name = line[6:].strip()
                    elif line.startswith("data:"):
                        raw = line[5:].strip()
                        try:
                            data = _json.loads(raw)
                        except _json.JSONDecodeError:
                            data = {"raw": raw}
                        yield event_name, data
                        event_name = "message"
    except httpx.ConnectError:
        _no_server(wiki)
    except httpx.ReadTimeout:
        _timeout_error(path, t)
    except httpx.HTTPStatusError as e:
        E.cli_error(E.SRV_HTTP_ERROR,
                    f"Server returned {e.response.status_code}: {_detail(e.response)}")


def _timeout_error(path: str, timeout: int) -> NoReturn:
    if "/query" in path:
        E.cli_error(
            E.QUERY_TIMEOUT,
            f"The query timed out waiting for the LLM to respond ({timeout} s).",
            f"The wiki server is still running. Try again with --timeout {timeout * 2}. "
            "Local models on CPU-only machines are significantly slower than GPU-accelerated "
            "or cloud inference — consider switching to a cloud provider (e.g. gemini-2.5-flash-lite, free).",
        )
    elif "/jobs" in path:
        E.cli_error(
            E.QUERY_TIMEOUT,
            f"The server did not respond to '{path}' within {timeout} s.",
            "The server may be busy processing a large file (e.g. a PDF). "
            "Wait a moment and try again.",
        )
    else:
        E.cli_error(
            E.QUERY_TIMEOUT,
            f"The request timed out waiting for the server to respond ({timeout} s).",
            "The wiki server is still running. Try again, or raise "
            "client_llm_timeout_seconds in [server] of .synthadoc/config.toml.",
        )


def _detail(response: httpx.Response) -> str:
    """Extract FastAPI's detail string from a JSON error response, or return raw text."""
    try:
        return response.json()["detail"]
    except Exception:
        return response.text.strip()


def _no_server(wiki: str) -> NoReturn:
    E.cli_error(
        E.SRV_NOT_RUNNING,
        f"No synthadoc server is running for wiki '{wiki}'.",
        f"Start it with:\n  synthadoc serve -w {wiki}",
    )
