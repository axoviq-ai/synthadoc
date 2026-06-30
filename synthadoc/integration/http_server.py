# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import asyncio
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from synthadoc.core.queue import JobStatus
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from typing import Optional

import logging
import re

logger = logging.getLogger(__name__)

_MAX_BODY_BYTES = 10 * 1024 * 1024  # 10 MB


def _install_win32_conn_reset_filter() -> None:
    """Downgrade spurious ConnectionResetError noise from asyncio on Windows.

    When a client abruptly closes a TCP connection (RST instead of FIN),
    Windows IOCP raises ConnectionResetError inside the cleanup callback
    _ProactorBasePipeTransport._call_connection_lost.  Python's asyncio logs
    this at ERROR level even though no request is dropped and nothing is wrong.
    We install a tight exception handler that downgrades only this specific case
    to DEBUG (still visible via --verbose / log file) and forwards everything
    else to the default handler unchanged.
    """
    loop = asyncio.get_event_loop()
    _prev = loop.get_exception_handler()

    def _handler(loop, context):
        exc = context.get("exception")
        if isinstance(exc, ConnectionResetError) and "_call_connection_lost" in context.get("message", ""):
            logger.debug("win32 socket closed by remote host (WinError 10054) — harmless")
            return
        (_prev or loop.default_exception_handler)(loop, context)

    loop.set_exception_handler(_handler)


def _install_shutdown_noise_filter() -> None:
    """Suppress CancelledError/KeyboardInterrupt tracebacks from uvicorn.error on Ctrl+C.

    On Python 3.14, uvicorn's signal re-raise interacts with Starlette's lifespan
    receive queue in a way that produces a CancelledError traceback logged at ERROR
    level — even though the server shut down cleanly.  The filter drops only these
    expected shutdown exceptions so the console stays quiet on normal Ctrl+C.
    """
    class _Filter(logging.Filter):
        _shutdown_types = (asyncio.CancelledError, KeyboardInterrupt)
        # uvicorn sometimes logs the full traceback as message text with no exc_info
        _shutdown_msg_markers = ("asyncio.exceptions.CancelledError", "asyncio.CancelledError")

        def filter(self, record: logging.LogRecord) -> bool:
            if record.exc_info and record.exc_info[0] is not None:
                if issubclass(record.exc_info[0], self._shutdown_types):
                    return False
                # ASGI protocol violation caused by SSE connections (query stream or
                # MCP /mcp/sse) that are still open when the server shuts down.
                # uvicorn cancels the task → CancelledError propagates through the
                # SSE generator → Starlette's error middleware tries to send a 500
                # response → uvicorn rejects it because headers were already sent.
                # This is always benign: the connection is already being torn down.
                if issubclass(record.exc_info[0], RuntimeError):
                    exc_val = record.exc_info[1]
                    if exc_val is not None and "Expected ASGI message" in str(exc_val):
                        return False
            if record.levelno >= logging.ERROR:
                msg = record.getMessage()
                if any(msg.rstrip().endswith(m) for m in self._shutdown_msg_markers):
                    return False
                if "Expected ASGI message" in msg and "http.response" in msg:
                    return False
            return True

    logging.getLogger("uvicorn.error").addFilter(_Filter())


def _classify_llm_error(exc: Exception) -> "HTTPException | None":
    """Return a meaningful HTTPException for known LLM API error codes, or None."""
    from synthadoc.errors import DailyQuotaExhaustedException, CodingToolQuotaExhaustedException
    _SWITCH = "Switch to another provider by editing [agents] in .synthadoc/config.toml and restarting the server (options: anthropic, openai, gemini, groq, minimax, deepseek, ollama)."
    if isinstance(exc, DailyQuotaExhaustedException):
        return HTTPException(
            status_code=503,
            detail=f"Daily quota exhausted for {exc.provider} — no requests possible until midnight UTC. {_SWITCH}",
        )
    if isinstance(exc, CodingToolQuotaExhaustedException):
        return HTTPException(
            status_code=503,
            detail=f"Coding tool quota exhausted — {exc}. {_SWITCH}",
        )

    # openai/anthropic SDKs set status_code directly on the exception;
    # httpx.HTTPStatusError (used by OllamaProvider) stores it on exc.response.
    code = getattr(exc, "status_code", None)
    if code is None:
        resp = getattr(exc, "response", None)
        code = getattr(resp, "status_code", None)

    if code == 401:
        msg = str(exc)
        if "deepseek" in msg.lower() or "api.deepseek.com" in msg.lower():
            var = "DEEPSEEK_API_KEY"
        elif "minimax" in msg.lower():
            var = "MINIMAX_API_KEY"
        elif "groq" in msg.lower():
            var = "GROQ_API_KEY"
        elif "generativelanguage" in msg.lower() or "gemini" in msg.lower():
            var = "GEMINI_API_KEY"
        elif "anthropic" in msg.lower():
            var = "ANTHROPIC_API_KEY"
        elif "openai" in msg.lower():
            var = "OPENAI_API_KEY"
        else:
            var = "your provider's API key env var"
        return HTTPException(
            status_code=401,
            detail=f"LLM provider rejected the API key (401). Check that {var} is set correctly and restart the server.",
        )
    if code == 402:
        body = getattr(exc, "body", None) or {}
        err_msg = ""
        if isinstance(body, dict):
            err_msg = body.get("error", {}).get("message", "")
        detail = err_msg or "Insufficient balance"
        return HTTPException(
            status_code=402,
            detail=f"LLM provider payment required (402): {detail}. Top up your account balance at your provider's billing page and retry.",
        )
    if code == 429:
        msg = str(exc)
        _SWITCH_429 = "Switch to another provider by editing [agents] in .synthadoc/config.toml and restarting the server (options: anthropic, openai, gemini, groq, minimax, deepseek, ollama)."
        if "generativelanguage.googleapis.com" in msg or "gemini" in msg.lower():
            hint = f"Gemini free-tier quota exhausted. Wait for the daily reset or switch providers. {_SWITCH_429}"
        elif "groq" in msg.lower():
            hint = f"Groq rate limit hit. Wait for the retry window or switch providers. {_SWITCH_429}"
        elif "anthropic" in msg.lower():
            hint = f"Anthropic rate limit hit. Wait a moment or switch providers. {_SWITCH_429}"
        elif "openai" in msg.lower():
            hint = f"OpenAI rate limit hit. Wait a moment or switch providers. {_SWITCH_429}"
        else:
            hint = f"LLM provider rate limit hit. Wait a moment or switch providers. {_SWITCH_429}"
        return HTTPException(
            status_code=429,
            detail=f"LLM quota exceeded (429). {hint}",
        )
    if code == 503:
        return HTTPException(
            status_code=503,
            detail="LLM provider temporarily overloaded (503). Retry in a moment.",
        )
    if code == 529:
        return HTTPException(
            status_code=503,
            detail="LLM provider temporarily overloaded (529). Retry in a moment.",
        )
    return None
_WORKER_POLL_SECONDS = 2
_SESSION_PURGE_INTERVAL_SECONDS = 3600
_HISTORY_OVERFLOW_NOTICE = (
    "Earlier conversation has been summarized to stay within context limits. "
    "To retain more context, increase conversation_history_turns in "
    ".synthadoc/config.toml."
)
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


class ContentSizeLimitMiddleware:
    """Reject requests whose body exceeds the configured limit.

    Checks Content-Length header first (fast path). For chunked transfers that
    omit Content-Length, counts bytes as they arrive and rejects mid-stream.
    """

    def __init__(self, app, max_bytes: int = _MAX_BODY_BYTES) -> None:
        self.app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and not scope.get("path", "").startswith("/mcp"):
            headers = dict(scope.get("headers", []))
            content_length = headers.get(b"content-length")
            if content_length is not None:
                if int(content_length) > self._max_bytes:
                    response = Response(content="Request body too large", status_code=413)
                    await response(scope, receive, send)
                    return
            else:
                # Chunked transfer body check: only applies to request methods that
                # carry a body (POST/PUT/PATCH).  GET/HEAD/DELETE have no body; buffering
                # them would intercept SSE disconnect receive() calls and prematurely
                # terminate streaming responses.
                method = scope.get("method", "").upper()
                if method in ("POST", "PUT", "PATCH"):
                    total = 0
                    messages: list = []
                    while True:
                        message = await receive()
                        total += len(message.get("body", b""))
                        if total > self._max_bytes:
                            response = Response(content="Request body too large", status_code=413)
                            await response(scope, receive, send)
                            return
                        messages.append(message)
                        if not message.get("more_body", False):
                            break
                    idx = 0

                    async def _replay():
                        nonlocal idx
                        if idx < len(messages):
                            msg = messages[idx]
                            idx += 1
                            return msg
                        return {"type": "http.disconnect"}

                    await self.app(scope, _replay, send)
                    return
        await self.app(scope, receive, send)


class QueryRequest(BaseModel):
    question: str
    save: bool = False
    timeout_seconds: int = 60
    no_cache: bool = False

    @field_validator("question")
    @classmethod
    def question_not_empty(cls, v):
        if not v.strip():
            raise ValueError("question must not be empty")
        return v


class IngestRequest(BaseModel):
    source: str
    force: bool = False
    max_results: int | None = None
    max_source_chars: int | None = None   # overrides [ingest] max_source_chars for this run

    @field_validator("source")
    @classmethod
    def source_not_empty(cls, v):
        if not v.strip():
            raise ValueError("source must not be empty")
        return v


class LintRequest(BaseModel):
    scope: str = "all"
    auto_resolve: bool = False
    adversarial: bool = True
    lifecycle: bool = True
    check_url_availability: Optional[bool] = None  # None = use server config


class ScaffoldRequest(BaseModel):
    domain: str

    @field_validator("domain")
    @classmethod
    def domain_not_empty(cls, v):
        if not v.strip():
            raise ValueError("domain must not be empty")
        return v


class ContextBuildRequest(BaseModel):
    goal: str
    token_budget: int | None = None   # falls back to cfg.query.context_token_budget


class AnalyseRequest(BaseModel):
    source: str

    @field_validator("source")
    @classmethod
    def source_not_empty(cls, v):
        if not v.strip():
            raise ValueError("source must not be empty")
        return v


class StagingPolicyRequest(BaseModel):
    policy: str
    confidence_min: str | None = None


class LifecycleTransitionRequest(BaseModel):
    slug: str
    to_state: str
    reason: str


class ExportRequest(BaseModel):
    format: str
    status_filter: str = "all"
    context_pack: str | None = None


def _load_blocked_domains(wiki_root: Path) -> set[str]:
    """Return the set of auto-blocked domains from .synthadoc/blocked_domains.json."""
    import json as _json_mod
    p = wiki_root / ".synthadoc" / "blocked_domains.json"
    if not p.exists():
        return set()
    try:
        return set(_json_mod.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return set()


_SUGGESTION_URL_RE = re.compile(r"^https?://([^/]+)", re.IGNORECASE)


def _filter_blocked_suggestions(suggestions: list[str], blocked: set[str]) -> list[str]:
    """Remove URL suggestions whose domain is in the blocked set; keep search queries."""
    if not blocked:
        return suggestions
    filtered = []
    for s in suggestions:
        m = _SUGGESTION_URL_RE.match(s)
        if m and m.group(1).lower().lstrip("www.") in blocked:
            continue
        filtered.append(s)
    return filtered


def _parse_retry_after(exc: Exception, default: float = 60.0) -> float:
    """Parse 'Please try again in Xm Y.Zs' from a rate-limit error message."""
    m = re.search(r"Please try again in (?:(\d+)m\s*)?(\d+(?:\.\d+)?)s", str(exc))
    if m:
        return float(m.group(1) or 0) * 60 + float(m.group(2))
    return default


async def _worker_loop(orch) -> None:
    """Background task: poll jobs.db and execute pending jobs."""
    sleep_secs = _WORKER_POLL_SECONDS
    _last_purge_time: float = 0.0
    while True:
        try:
            job = await orch.queue.dequeue()
            sleep_secs = _WORKER_POLL_SECONDS  # reset after a successful dequeue
            if job:
                if job.operation == "ingest":
                    source = job.payload.get("source", "")
                    force = job.payload.get("force", False)
                    max_results = job.payload.get("max_results")
                    max_source_chars = job.payload.get("max_source_chars")
                    await orch._run_ingest(job.id, source, auto_confirm=True, force=force,
                                           max_results=max_results,
                                           max_source_chars=max_source_chars)
                elif job.operation == "lint":
                    scope = job.payload.get("scope", "all")
                    auto_resolve = job.payload.get("auto_resolve", False)
                    adversarial = job.payload.get("adversarial", True)
                    lifecycle = job.payload.get("lifecycle", True)
                    check_url_availability = job.payload.get("check_url_availability")  # None = use config
                    await orch._run_lint(job.id, scope=scope, auto_resolve=auto_resolve,
                                         adversarial=adversarial, lifecycle=lifecycle,
                                         check_url_availability=check_url_availability)
                elif job.operation == "scaffold":
                    domain = job.payload.get("domain", "")
                    await orch._run_scaffold(job.id, domain=domain)
        except Exception as exc:
            known = _classify_llm_error(exc)
            if known and known.status_code == 503 and (
                "Daily quota" in (known.detail or "") or "Coding tool quota" in (known.detail or "")
            ):
                # Quota exhausted — no point retrying pending jobs until the user
                # tops up credits or waits for the reset. Log once and keep polling.
                logger.error("Quota exhausted — pending jobs will fail. %s", known.detail)
                sleep_secs = _WORKER_POLL_SECONDS
            elif known and known.status_code == 429:
                sleep_secs = _parse_retry_after(exc)
                logger.warning(
                    "Rate limit hit in worker — pausing %.0f s before next job. "
                    "(%d pending jobs will wait.) %s",
                    sleep_secs,
                    len([j for j in asyncio.all_tasks() if not j.done()]),
                    known.detail,
                )
            else:
                logger.exception("Worker loop error — job recorded in jobs.db; continuing")
                sleep_secs = _WORKER_POLL_SECONDS

        # Periodic session purge — throttled to once per hour
        if time.monotonic() - _last_purge_time >= _SESSION_PURGE_INTERVAL_SECONDS:
            try:
                _retention = orch._cfg.chat.session_retention_days
                if _retention > 0:
                    _purged = await orch._audit.purge_old_sessions(_retention)
                    if _purged:
                        logger.info("Purged %d stale sessions.", _purged)
                        _session_state.clear()
                _last_purge_time = time.monotonic()
            except Exception as _pe:
                logger.error("Session purge failed: %s", _pe)

        await asyncio.sleep(sleep_secs)


_graph_computing = False  # module-level flag prevents duplicate background tasks


def create_app(wiki_root: Path, max_body_bytes: int = _MAX_BODY_BYTES, enable_mcp: bool = True) -> FastAPI:
    import os
    import synthadoc
    from synthadoc.config import load_config
    from synthadoc.core.orchestrator import Orchestrator
    from synthadoc.storage.log import AuditDB as _AuditDB
    from synthadoc.storage.wiki import LifecycleState, TriggerSource

    # Expose wiki root so skills (e.g. web_search) can load the dynamic blocked-domains list
    os.environ["SYNTHADOC_WIKI_ROOT"] = str(wiki_root)

    cfg = load_config(project_config=wiki_root / ".synthadoc" / "config.toml")

    # Create Orchestrator here so MCP server can reference it at mount time.
    # init() is called inside the lifespan (requires event loop).
    orch = Orchestrator(wiki_root=wiki_root, config=cfg)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if sys.platform == "win32":
            _install_win32_conn_reset_filter()
        _install_shutdown_noise_filter()
        await orch.init()
        app.state.orch = orch
        from synthadoc.agents.hint_engine import HintEngine as _HE
        _HE.configure(wiki_root / "hints.json")
        worker = asyncio.create_task(_worker_loop(orch))

        from synthadoc.core.scheduler import run_scheduler_loop
        audit_db = _AuditDB(wiki_root / ".synthadoc" / "audit.db")
        await audit_db.init()
        scheduler = asyncio.create_task(
            run_scheduler_loop(wiki_root.name, wiki_root, audit_db)
        )

        try:
            yield
        finally:
            worker.cancel()
            scheduler.cancel()
            for task in (worker, scheduler):
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            await orch.close()

    app = FastAPI(title="synthadoc", version=synthadoc.__version__, lifespan=lifespan)
    app.add_middleware(ContentSizeLimitMiddleware, max_bytes=max_body_bytes)

    # Per-session state: mode + hint rotation cursor
    _session_state: dict[str, dict] = {}  # session_id -> {"mode": str, "cursor": int}

    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "app://obsidian.md",
            "http://localhost", "http://localhost:3000", "http://localhost:5173", "http://localhost:7070",
            "http://127.0.0.1", "http://127.0.0.1:3000", "http://127.0.0.1:5173", "http://127.0.0.1:7070",
        ],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )

    if enable_mcp:
        from synthadoc.integration.mcp_server import create_mcp_server
        _mcp = create_mcp_server(orchestrator=orch)
        app.mount("/mcp", _mcp.sse_app())

    @app.get("/", response_class=Response)
    async def index():
        from synthadoc.cli.logo import banner_text
        import synthadoc
        text = banner_text(version=synthadoc.__version__)
        text += (
            f"  Endpoints\n"
            f"  ---------------------------------\n"
            f"  GET  /health          liveness probe\n"
            f"  GET  /status          wiki stats\n"
            f"  POST /analyse         analyse source without writing pages\n"
            f"  POST /jobs/ingest     enqueue ingest job\n"
            f"  POST /jobs/lint       enqueue lint job\n"
            f"  GET  /jobs            list jobs\n"
            f"  GET  /jobs/{{id}}       job detail\n"
            f"  POST /query           query the wiki\n"
            f"  GET  /lint/report     orphans + contradictions\n"
        )
        return Response(content=text, media_type="text/plain; charset=utf-8")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/status")
    async def status():
        from synthadoc.agents.lint_agent import LINT_SKIP_SLUGS
        orch = app.state.orch
        jobs = await orch.queue.list_jobs()
        pending = sum(1 for j in jobs if j.status == JobStatus.PENDING)
        pages = [s for s in orch._store.list_pages() if s not in LINT_SKIP_SLUGS]
        return {
            "wiki": str(wiki_root),
            "pages": len(pages),
            "jobs_pending": pending,
            "jobs_total": len(jobs),
        }

    @app.get("/config")
    async def config_info():
        return {
            "domain": cfg.wiki.domain,
            "check_url_availability": cfg.lint.check_url_availability,
        }

    async def _run_query(question: str, timeout_seconds: int = 60) -> dict:
        try:
            result = await app.state.orch.query(question, timeout_seconds=timeout_seconds)
        except TimeoutError as exc:
            raise HTTPException(status_code=504, detail=f"Query timed out after {timeout_seconds}s") from exc
        except Exception as exc:
            known = _classify_llm_error(exc)
            if known:
                logger.warning("LLM rate limit during query: %s", exc)
                raise known from exc
            if isinstance(exc, (EnvironmentError, OSError)) and "[ERR-PROV-" in str(exc):
                logger.warning("Provider not available: %s", exc)
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            logger.exception("Query failed")
            raise HTTPException(status_code=502, detail="LLM provider unavailable") from exc
        return {
            "answer": result.answer,
            "citations": result.citations,
            "knowledge_gap": result.knowledge_gap,
            "suggested_searches": result.suggested_searches,
            "cacheable": result.cacheable,
        }

    _NO_STORE = {"Cache-Control": "no-store"}

    @app.get("/query")
    async def query(q: str, timeout_seconds: int = 60, no_cache: bool = False):
        if not q.strip():
            raise HTTPException(status_code=400, detail="q must not be empty")
        orch = app.state.orch
        from synthadoc.core.cache import make_query_cache_key
        _qcfg = orch._cfg.agents.resolve("query")
        _query_model = f"{_qcfg.provider}/{_qcfg.model}"
        cache_key = make_query_cache_key(q, orch._wiki_epoch, _query_model)
        if not no_cache:
            cached = await orch._cache.get_query(cache_key)
            if cached is not None:
                return JSONResponse(content=cached, headers=_NO_STORE)
        result = await _run_query(q, timeout_seconds=timeout_seconds)
        if result.get("cacheable", True):
            await orch._cache.set_query(cache_key, orch._wiki_epoch, result)
        return JSONResponse(content=result, headers=_NO_STORE)

    @app.post("/query")
    async def query_post(req: QueryRequest):
        orch = app.state.orch
        from synthadoc.core.cache import make_query_cache_key
        _qcfg = orch._cfg.agents.resolve("query")
        _query_model = f"{_qcfg.provider}/{_qcfg.model}"
        cache_key = make_query_cache_key(req.question, orch._wiki_epoch, _query_model)
        if not req.no_cache:
            cached = await orch._cache.get_query(cache_key)
            if cached is not None:
                return JSONResponse(content=cached, headers=_NO_STORE)
        result = await _run_query(req.question, timeout_seconds=req.timeout_seconds)
        if result.get("cacheable", True):
            await orch._cache.set_query(cache_key, orch._wiki_epoch, result)
        return JSONResponse(content=result, headers=_NO_STORE)

    @app.get("/query/stream")
    async def query_stream(q: str, session_id: str | None = None, no_cache: bool = False, timeout_seconds: int = 60):
        import asyncio as _asyncio
        import json as _json
        from fastapi.responses import StreamingResponse
        if not q.strip():
            raise HTTPException(status_code=400, detail="q must not be empty")
        orch = app.state.orch
        _audit = orch._audit
        _chat_cfg = cfg.chat  # ChatConfig instance

        _sstate = _session_state.get(session_id or "", {"mode": "POWER_USER", "cursor": 0})
        session_mode: str = _sstate["mode"]

        # Load conversation history and detect overflow in a single guard block
        _history: list[dict] = []
        _summary_notice: str | None = None
        if session_id and _chat_cfg.conversation_history_turns > 0:
            from synthadoc.agents.summarize_agent import SummarizeAgent as _SummarizeAgent
            from synthadoc.providers import make_provider as _make_provider
            turns = _chat_cfg.conversation_history_turns
            try:
                _all_messages = await _audit.get_all_messages(session_id)
                _history = _all_messages[-(turns * 2):]
                _existing_summary, _summary_turn_count = await _audit.get_summary(session_id)
                _total_turns = len(_all_messages) // 2  # rough: pairs of user/assistant
                _overflow_turns = _total_turns - turns
                if _overflow_turns > 0 and _overflow_turns > _summary_turn_count:
                    # New overflow since last summary — compress
                    _overflow_msgs = _all_messages[: len(_all_messages) - turns * 2]
                    try:
                        _provider = _make_provider("query", cfg)
                        _new_summary = await _SummarizeAgent(_provider).summarize(_overflow_msgs)
                        if _new_summary:
                            await _audit.update_summary(session_id, _new_summary, _overflow_turns)
                            if not _existing_summary:
                                _summary_notice = _HISTORY_OVERFLOW_NOTICE
                            logger.info(
                                "Session %s: history compressed (%d turns → summary).",
                                session_id, _total_turns
                            )
                    except Exception as _se:
                        logger.warning("SummarizeAgent failed for session %s: %s", session_id, _se)
            except Exception as _oe:
                logger.warning("Overflow check failed for session %s: %s", session_id, _oe)
                _history = []

        # Actions and repeat intents must never be served from cache — they run live
        # operations whose result depends on current wiki state and session context.
        from synthadoc.agents.action_agent import _ACTION_RE as _ARE, _REPEAT_RE as _RRE
        _looks_like_action = bool(_ARE.search(q) or (_RRE.search(q) and _history))
        if not no_cache and not _looks_like_action:
            from synthadoc.core.cache import make_query_cache_key
            _qcfg = orch._cfg.agents.resolve("query")
            _query_model = f"{_qcfg.provider}/{_qcfg.model}"
            cache_key = make_query_cache_key(q, orch._wiki_epoch, _query_model)
            cached = await orch._cache.get_query(cache_key)
            if cached is not None:
                async def _cached_stream():
                    if _summary_notice:
                        yield f"event: notice\ndata: {_json.dumps({'text': _summary_notice})}\n\n"
                    events = [
                        {"event": "status", "data": {"phase": "synthesizing", "sources": len(cached.get("citations", []))}},
                    ]
                    for word in cached["answer"].split(" "):
                        events.append({"event": "token", "data": {"text": word + " "}})
                    events.append({"event": "citations", "data": {"citations": cached.get("citations", [])}})
                    if cached.get("knowledge_gap") and cached.get("suggested_searches"):
                        _filtered_cached = _filter_blocked_suggestions(
                            cached["suggested_searches"], _load_blocked_domains(orch._root))
                        if _filtered_cached:
                            events.append({"event": "gap", "data": {"suggested_searches": _filtered_cached}})
                    from synthadoc.agents.hint_engine import HintEngine
                    _ss = _session_state.get(session_id or "", {})
                    cursor = _ss.get("cursor", 0)
                    prev_hints = _ss.get("last_hints", [])
                    next_hints, new_cursor = HintEngine.after_response_windowed(
                        cached.get("answer", ""), session_mode, cursor,
                        previous_hints=prev_hints,
                    )
                    if session_id and session_id in _session_state:
                        _session_state[session_id]["cursor"] = new_cursor
                        _session_state[session_id]["last_hints"] = next_hints
                    # Persist before done so the client's sidebar refresh sees fresh data
                    try:
                        if session_id:
                            await orch._audit.append_message(session_id, "user", q)
                            await orch._audit.append_message(
                                session_id, "assistant", cached.get("answer", ""),
                                citations=cached.get("citations") or None,
                                gap_suggestions=cached.get("suggested_searches") or None,
                            )
                    except _asyncio.CancelledError:
                        return  # server shutdown or client disconnect — stop cleanly
                    events.append({"event": "done", "data": {"next_hints": next_hints}})
                    for evt in events:
                        yield f"event: {evt['event']}\ndata: {_json.dumps(evt['data'])}\n\n"
                return StreamingResponse(_cached_stream(), media_type="text/event-stream")

        async def _live_stream():
            nonlocal _summary_notice
            full_answer = ""
            citations = []
            _is_cacheable = True
            _knowledge_gap = False
            _suggested_searches: list[str] = []
            try:
                async with _asyncio.timeout(timeout_seconds if timeout_seconds > 0 else None):
                    async for evt in orch.query_stream(q, session_id=session_id,
                                                       session_mode=session_mode,
                                                       history=_history):
                        # Change 4: emit notice SSE before first token/clarify
                        if _summary_notice:
                            yield f"event: notice\ndata: {_json.dumps({'text': _summary_notice})}\n\n"
                            _summary_notice = None

                        if evt["event"] == "clarify":
                            if session_id:
                                from synthadoc.agents.action_agent import CLARIFY_STORE_PREFIX
                                await orch._audit.append_message(session_id, "user", q)
                                clarify_text = evt["data"].get("prompt", "")
                                cands = evt["data"].get("candidates", [])
                                if cands:
                                    clarify_text += "\n" + "\n".join(
                                        f"{i+1}. {c}" for i, c in enumerate(cands)
                                    )
                                await orch._audit.append_message(
                                    session_id, "assistant",
                                    CLARIFY_STORE_PREFIX + clarify_text,
                                )
                            yield f"event: clarify\ndata: {_json.dumps(evt['data'])}\n\n"
                            continue
                        elif evt["event"] == "token":
                            full_answer += evt["data"].get("text", "")
                        elif evt["event"] == "citations":
                            citations = evt["data"].get("citations", [])
                        elif evt["event"] == "gap":
                            _knowledge_gap = True
                            _raw = evt["data"].get("suggested_searches", [])
                            _suggested_searches = _filter_blocked_suggestions(
                                _raw, _load_blocked_domains(orch._root))
                            evt["data"]["suggested_searches"] = _suggested_searches
                        elif evt["event"] == "done":
                            _is_cacheable = evt["data"].get("cacheable", True)
                            from synthadoc.agents.hint_engine import HintEngine
                            _ss = _session_state.get(session_id or "", {})
                            cursor = _ss.get("cursor", 0)
                            prev_hints = _ss.get("last_hints", [])
                            next_hints, new_cursor = HintEngine.after_response_windowed(
                                full_answer, session_mode, cursor,
                                previous_hints=prev_hints,
                            )
                            if session_id and session_id in _session_state:
                                _session_state[session_id]["cursor"] = new_cursor
                                _session_state[session_id]["last_hints"] = next_hints
                            # Persist before yielding done so the client's sidebar refresh sees fresh data
                            if session_id and full_answer:
                                await orch._audit.append_message(session_id, "user", q)
                                await orch._audit.append_message(
                                    session_id, "assistant", full_answer,
                                    citations=citations or None,
                                    gap_suggestions=_suggested_searches if _knowledge_gap else None,
                                )
                            yield f"event: done\ndata: {_json.dumps({'next_hints': next_hints})}\n\n"
                            continue
                        yield f"event: {evt['event']}\ndata: {_json.dumps(evt['data'])}\n\n"
            except _asyncio.CancelledError:
                return  # server shutdown or client disconnect — stop cleanly
            except TimeoutError:
                yield f"event: error\ndata: {_json.dumps({'message': f'Query timed out after {timeout_seconds}s.'})}\n\n"
                return
            except Exception as exc:
                known = _classify_llm_error(exc)
                if not known:
                    logger.exception("Streaming query failed")
                msg = known.detail if known else "LLM provider unavailable"
                yield f"event: error\ndata: {_json.dumps({'message': msg})}\n\n"
                return
            # Strip [GAP] sentinel the LLM may have prepended (guard B, streaming path)
            if full_answer.startswith("[GAP]"):
                full_answer = full_answer[len("[GAP]"):].lstrip("\n")
            if full_answer and _is_cacheable:
                from synthadoc.core.cache import make_query_cache_key
                _qcfg = orch._cfg.agents.resolve("query")
                _query_model = f"{_qcfg.provider}/{_qcfg.model}"
                cache_key = make_query_cache_key(q, orch._wiki_epoch, _query_model)
                await orch._cache.set_query(cache_key, orch._wiki_epoch, {
                    "answer": full_answer, "citations": citations,
                    "knowledge_gap": _knowledge_gap,
                    "suggested_searches": _suggested_searches,
                })

        return StreamingResponse(_live_stream(), media_type="text/event-stream")

    @app.post("/sessions")
    async def create_session():
        import uuid as _uuid
        orch = app.state.orch
        session_id = str(_uuid.uuid4())
        page_count = len(orch._store.list_pages())
        if page_count < 5:
            mode = "NEW_WIKI"
        elif not await orch._audit.has_prior_sessions():
            mode = "EXPLORER"
        else:
            pages = [orch._store.read_page(s) for s in orch._store.list_pages()]
            has_health_issues = any(
                p and p.status in ("stale", "contradicted")
                for p in pages
            )
            mode = "HEALTH_CHECK" if has_health_issues else "POWER_USER"
        await orch._audit.create_session(session_id, mode)
        from synthadoc.agents.hint_engine import HintEngine
        _session_state[session_id] = {"mode": mode, "cursor": 0, "last_hints": []}
        return {
            "session_id": session_id,
            "mode": mode,
            "initial_hints": HintEngine.initial_hints(mode),
            "wiki_name": wiki_root.name,
        }

    @app.get("/sessions")
    async def list_sessions(limit: int = 20):
        from fastapi.responses import JSONResponse
        data = await app.state.orch._audit.list_sessions(limit=limit)
        return JSONResponse(content=data, headers={"Cache-Control": "no-store"})

    @app.get("/sessions/{session_id}/messages")
    async def get_session_messages(session_id: str):
        return await app.state.orch._audit.get_all_messages(session_id)

    @app.get("/hints")
    async def get_hints(mode: str = "POWER_USER"):
        from synthadoc.agents.hint_engine import HintEngine
        return {"hints": HintEngine.initial_hints(mode)}

    @app.get("/graph")
    async def get_graph():
        global _graph_computing
        orch = app.state.orch
        graph_data = await orch._audit.read_graph()
        if graph_data is None:
            if not _graph_computing:
                _graph_computing = True
                logger.info("[graph] computation started (lazy hydration)")
                asyncio.create_task(_background_build_graph())
            return JSONResponse(content={"status": "computing"}, headers=_NO_STORE)
        enriched_nodes = []
        for n in graph_data["nodes"]:
            page = orch._store.read_page(n["slug"])
            enriched_nodes.append({
                "slug": n["slug"],
                "title": page.title if page else n["slug"],
                "type": (page.type if page else None) or "concept",
                "state": (page.status if page else "active"),
                "cluster_id": n["cluster_id"],
            })
        clusters = len({n["cluster_id"] for n in graph_data["nodes"]}) if graph_data["nodes"] else 0
        return JSONResponse(content={
            "status": "ready",
            "node_count": len(enriched_nodes),
            "edge_count": len(graph_data["edges"]),
            "cluster_count": clusters,
            "nodes": enriched_nodes,
            "edges": [
                {"from": e["from_slug"], "to": e["to_slug"], "weight": e["weight"]}
                for e in graph_data["edges"]
            ],
        }, headers=_NO_STORE)

    async def _background_build_graph():
        global _graph_computing
        try:
            from synthadoc.agents.lint_agent import LintAgent
            from synthadoc.providers import make_provider as _make_provider
            _orch = app.state.orch
            lint = LintAgent(
                provider=_make_provider("lint", _orch._cfg),
                store=_orch._store,
                log_writer=_orch._log,
                audit_db=_orch._audit,
                cfg=_orch._cfg,
            )
            nodes, edges = lint._build_graph()
            await _orch._audit.write_graph(nodes, edges)
            logger.info(
                "[graph] complete — %d nodes, %d edges, %d clusters",
                len(nodes), len(edges),
                len({n["cluster_id"] for n in nodes}) if nodes else 0,
            )
        except Exception as exc:
            logger.error("[graph] build failed: %s", exc)
        finally:
            _graph_computing = False

    @app.post("/analyse")
    async def analyse_source(req: AnalyseRequest):
        """Run analysis pass on a source and return structured result without writing pages."""
        from synthadoc.agents.ingest_agent import IngestAgent
        from synthadoc.providers import make_provider
        from synthadoc.agents.skill_agent import SkillAgent, SkillNotFoundError
        orch = app.state.orch
        agent = IngestAgent(
            provider=make_provider("ingest", orch._cfg),
            store=orch._store, search=orch._search,
            log_writer=orch._log, audit_db=orch._audit,
            cache=orch._cache, max_pages=orch._cfg.ingest.max_pages_per_ingest,
            wiki_root=orch._root,
            cache_version=orch._cfg.cache.version,
            fetch_timeout=orch._cfg.ingest.fetch_timeout_seconds,
        )
        skill = SkillAgent()
        try:
            extracted = await skill.extract(req.source)
        except SkillNotFoundError:
            raise HTTPException(
                status_code=422,
                detail="No matching source type for the given input. Provide a URL, file path, or search query.",
            )
        text = extracted.text[:8000]
        analysis = await agent._analyse(text, bust_cache=False)
        analysis.pop("_tokens", None)
        return {"source": req.source, "analysis": analysis}

    @app.post("/jobs/ingest")
    async def enqueue_ingest(req: IngestRequest):
        from pathlib import Path as _Path
        from synthadoc.agents.skill_agent import SkillAgent
        source = req.source
        # Normalise backslash URLs so Windows-pasted forms (e.g. "https:\example.com\path")
        # are stored as proper URLs and are not mistakenly path-resolved.
        from synthadoc.agents.skill_agent import _normalize_url
        _normalised = _normalize_url(source)
        if _normalised.lower().startswith(("http://", "https://")):
            source = _normalised
        if SkillAgent().needs_path_resolution(source):
            p = _Path(source)
            if not p.is_absolute():
                # Resolve vault-relative paths (e.g. "raw_sources/file.pdf") against
                # wiki root so they work regardless of server working directory.
                source = str((wiki_root / source).resolve())
        payload: dict = {"source": source, "force": req.force}
        if req.max_results is not None:
            payload["max_results"] = req.max_results
        if req.max_source_chars is not None:
            payload["max_source_chars"] = req.max_source_chars
        job_id = await app.state.orch.queue.enqueue("ingest", payload)
        return {"job_id": job_id}

    @app.post("/jobs/lint")
    async def enqueue_lint(req: LintRequest):
        payload: dict = {
            "scope": req.scope,
            "auto_resolve": req.auto_resolve,
            "adversarial": req.adversarial,
            "lifecycle": req.lifecycle,
        }
        if req.check_url_availability is not None:
            payload["check_url_availability"] = req.check_url_availability
        job_id = await app.state.orch.queue.enqueue("lint", payload)
        return {"job_id": job_id}

    @app.get("/lint/report")
    async def lint_report():
        import yaml as _yaml
        from synthadoc.agents.lint_agent import find_orphan_slugs, LINT_SKIP_SLUGS
        from synthadoc.cli.lint import _is_reingestable
        wiki_dir = wiki_root / "wiki"
        pages = list(wiki_dir.glob("*.md"))

        page_texts: dict[str, str] = {p.stem: p.read_text(encoding="utf-8") for p in pages}

        contradiction_details = []
        for stem, text in page_texts.items():
            if stem not in LINT_SKIP_SLUGS and "status: contradicted" in text:
                fm_m = _FM_RE.match(text)
                fm: dict = {}
                if fm_m:
                    try:
                        fm = _yaml.safe_load(fm_m.group(1)) or {}
                    except Exception:
                        pass
                contradiction_details.append({
                    "slug": stem,
                    "contradiction_note": fm.get("contradiction_note") or None,
                    "unresolved_note": fm.get("unresolved_note") or None,
                })

        page_bodies: dict[str, str] = {
            slug: (text[m.end():] if (m := _FM_RE.match(text)) else text)
            for slug, text in page_texts.items()
        }
        orphan_slugs = find_orphan_slugs(page_bodies)

        orphan_details = []
        for slug in orphan_slugs:
            fm_m = _FM_RE.match(page_texts.get(slug, ""))
            fm = {}
            if fm_m:
                try:
                    fm = _yaml.safe_load(fm_m.group(1)) or {}
                except Exception:
                    pass
            title = fm.get("title") or slug.replace("-", " ").title()
            tags = fm.get("tags") or []
            if isinstance(tags, list) and tags:
                hint = ", ".join(str(t) for t in tags[:4])
            else:
                hint = title
            orphan_details.append({
                "slug": slug,
                "index_suggestion": f"- [[{slug}]] — {hint}",
            })

        # Build adversarial_warnings via WikiStorage.read_page() — same parse path
        # as LintAgent._run_adversarial_pass() which writes the warnings.
        orch = app.state.orch
        wiki_name = wiki_root.name
        adversarial_warnings = []
        for slug in page_texts:
            if slug in LINT_SKIP_SLUGS:
                continue
            page = orch._store.read_page(slug)
            if not page or not page.lint_warnings:
                continue
            suggested_reingests = [
                f'synthadoc ingest "{s.file}" -w {wiki_name}'
                for s in page.sources
                if s.file and _is_reingestable(s.file)
            ]
            adversarial_warnings.append({
                "slug": slug,
                "warnings": page.lint_warnings,
                "suggested_reingests": suggested_reingests,
            })

        return {
            "contradictions": [d["slug"] for d in contradiction_details],
            "contradiction_details": contradiction_details,
            "orphans": [d["slug"] for d in orphan_details],
            "orphan_details": orphan_details,
            "adversarial_warnings": adversarial_warnings,
        }

    _VALID_JOB_SORT = {"created_at", "status", "operation"}
    _VALID_JOB_ORDER = {"asc", "desc"}

    @app.get("/jobs")
    async def list_jobs(status: str | None = None, sort: str = "created_at", order: str = "asc"):
        if sort not in _VALID_JOB_SORT:
            raise HTTPException(status_code=400, detail=f"Invalid sort {sort!r}. Valid: {sorted(_VALID_JOB_SORT)}")
        if order not in _VALID_JOB_ORDER:
            raise HTTPException(status_code=400, detail=f"Invalid order {order!r}. Valid: asc, desc")
        try:
            job_status = JobStatus(status) if status else None
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status {status!r}. Valid values: {[s.value for s in JobStatus]}")
        jobs = await app.state.orch.queue.list_jobs(status=job_status, sort_by=sort, order=order)
        return [{"id": j.id, "status": j.status, "operation": j.operation,
                 "created_at": str(j.created_at), "payload": j.payload,
                 "error": j.error, "result": j.result, "progress": j.progress} for j in jobs]

    @app.get("/jobs/{job_id}")
    async def get_job(job_id: str):
        # O(n) scan — acceptable for typical queue sizes (< 1000 active jobs); add an index if needed
        jobs = await app.state.orch.queue.list_jobs()
        for j in jobs:
            if j.id == job_id:
                return {"id": j.id, "status": j.status, "operation": j.operation,
                        "created_at": str(j.created_at), "payload": j.payload,
                        "error": j.error, "result": j.result, "progress": j.progress}
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")

    @app.delete("/jobs/{job_id}")
    async def delete_job(job_id: str):
        jobs = await app.state.orch.queue.list_jobs()
        job = next((j for j in jobs if j.id == job_id), None)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
        if job.status in (JobStatus.PENDING, JobStatus.IN_PROGRESS):
            raise HTTPException(status_code=409, detail=f"Cannot delete a job with status {job.status!r}")
        await app.state.orch.queue.delete(job_id, app.state.orch._audit)
        return {"deleted": job_id}

    @app.post("/jobs/{job_id}/retry")
    async def retry_job(job_id: str):
        jobs = await app.state.orch.queue.list_jobs()
        if not any(j.id == job_id for j in jobs):
            raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
        await app.state.orch.queue.retry(job_id)
        return {"retried": job_id}

    @app.post("/jobs/cancel-pending")
    async def cancel_pending_jobs():
        count = await app.state.orch.queue.cancel_pending()
        return {"cancelled": count}

    @app.delete("/jobs")
    async def purge_jobs(older_than: int = 7):
        count = await app.state.orch.queue.purge(older_than_days=older_than)
        return {"purged": count, "older_than_days": older_than}

    @app.post("/jobs/scaffold")
    async def enqueue_scaffold(req: ScaffoldRequest):
        job_id = await app.state.orch.queue.enqueue(
            "scaffold", {"domain": req.domain}
        )
        return {"job_id": job_id}

    @app.get("/audit/history")
    async def audit_history(limit: int = 50):
        records = await app.state.orch._audit.list_ingests(limit=limit)
        return {"records": records, "count": len(records)}

    @app.get("/audit/costs")
    async def audit_costs(days: int = 30):
        return await app.state.orch._audit.cost_summary(days=days)

    @app.get("/audit/queries")
    async def audit_queries(limit: int = 50):
        records = await app.state.orch._audit.list_queries(limit=limit)
        return {"records": records, "count": len(records)}

    @app.get("/audit/events")
    async def audit_events(limit: int = 100):
        records = await app.state.orch._audit.list_events(limit=limit)
        return {"records": records, "count": len(records)}

    @app.post("/context/build")
    async def context_build(req: ContextBuildRequest):
        from synthadoc.agents.context_agent import ContextAgent
        from synthadoc.providers import make_provider
        orch = app.state.orch
        budget = req.token_budget if req.token_budget is not None \
            else orch._cfg.query.context_token_budget
        agent = ContextAgent(
            provider=make_provider("query", orch._cfg),
            store=orch._store,
            search=orch._search,
            token_budget=budget,
        )
        pack = await agent.build(req.goal, token_budget=budget)
        return pack.to_dict()

    # ── Routing ───────────────────────────────────────────────────────────────
    from synthadoc.core.routing import RoutingIndex as _RI

    def _routing_paths() -> tuple[Path, Path]:
        root = app.state.orch._root
        return root, root / "ROUTING.md"

    @app.get("/routing/status")
    async def routing_status():
        root, routing_path = _routing_paths()
        ri = _RI.parse(routing_path)
        exists = routing_path.exists()
        content = routing_path.read_text(encoding="utf-8") if exists else ""
        return {
            "exists": exists,
            "branches": len(ri.branches),
            "slugs": sum(len(v) for v in ri.branches.values()),
            "content": content,
        }

    @app.post("/routing/init")
    async def routing_init():
        root, routing_path = _routing_paths()
        index_path = root / "wiki" / "index.md"
        if routing_path.exists():
            raise HTTPException(409, "ROUTING.md already exists. Delete it first to re-init.")
        if not index_path.exists():
            raise HTTPException(400, "index.md not found — run scaffold first.")
        ri = _RI.from_index_md(index_path)
        ri.save(routing_path)
        content = routing_path.read_text(encoding="utf-8")
        return {
            "branches": len(ri.branches),
            "slugs": sum(len(v) for v in ri.branches.values()),
            "content": content,
        }

    @app.post("/routing/validate")
    async def routing_validate():
        root, routing_path = _routing_paths()
        if not routing_path.exists():
            raise HTTPException(404, "ROUTING.md not found — run Init first.")
        ri = _RI.parse(routing_path)
        existing = {p.stem for p in (root / "wiki").glob("*.md")}
        dangling = ri.validate(existing)
        return {
            "clean": len(dangling) == 0,
            "dangling": [{"branch": b, "slug": s} for b, s in dangling],
        }

    @app.post("/routing/clean")
    async def routing_clean():
        root, routing_path = _routing_paths()
        if not routing_path.exists():
            raise HTTPException(404, "ROUTING.md not found — run Init first.")
        ri = _RI.parse(routing_path)
        existing = {p.stem for p in (root / "wiki").glob("*.md")}
        removed = ri.clean(existing)
        ri.save(routing_path)
        content = routing_path.read_text(encoding="utf-8")
        return {
            "removed": [{"branch": b, "slug": s} for b, s in removed],
            "content": content,
        }

    # ── Staging policy ────────────────────────────────────────────────────────
    def _staging_cfg_path() -> Path:
        return app.state.orch._root / ".synthadoc" / "config.toml"

    @app.get("/staging/policy")
    async def staging_policy_get():
        import tomllib as _tomllib
        cfg_path = _staging_cfg_path()
        raw = _tomllib.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
        ig = raw.get("ingest", {})
        return {
            "policy": ig.get("staging_policy", "off"),
            "confidence_min": ig.get("staging_confidence_min", "high"),
        }

    @app.post("/staging/policy")
    async def staging_policy_set(req: StagingPolicyRequest):
        import tomllib as _tomllib
        from synthadoc.cli.candidates import _patch_toml as _cand_patch_toml
        if req.policy not in ("off", "all", "threshold"):
            raise HTTPException(400, "policy must be off, all, or threshold")
        if req.confidence_min and req.confidence_min not in ("high", "medium", "low"):
            raise HTTPException(400, "confidence_min must be high, medium, or low")
        cfg_path = _staging_cfg_path()
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        updates: dict = {"staging_policy": req.policy}
        if req.confidence_min:
            updates["staging_confidence_min"] = req.confidence_min
        _cand_patch_toml(cfg_path, "ingest", updates)
        raw = _tomllib.loads(cfg_path.read_text(encoding="utf-8"))
        ig = raw.get("ingest", {})
        return {
            "policy": ig.get("staging_policy", "off"),
            "confidence_min": ig.get("staging_confidence_min", "high"),
        }

    # ── Candidates ────────────────────────────────────────────────────────────
    def _cand_dir() -> Path:
        return app.state.orch._root / "wiki" / "candidates"

    def _wiki_dir() -> Path:
        return app.state.orch._root / "wiki"

    @app.get("/candidates")
    async def candidates_list():
        from synthadoc.cli.candidates import _read_frontmatter as _cand_read_fm
        cd = _cand_dir()
        pages = sorted(cd.glob("*.md")) if cd.exists() else []
        result = []
        for p in pages:
            fm = _cand_read_fm(p)
            result.append({
                "slug": p.stem,
                "title": fm.get("title") or p.stem.replace("-", " ").title(),
                "confidence": fm.get("confidence", ""),
                "created": fm.get("created", ""),
            })
        return result

    @app.post("/candidates/promote-all")
    async def candidates_promote_all():
        from synthadoc.cli.candidates import _read_frontmatter as _cand_read_fm
        from synthadoc.cli.candidates import _add_to_index as _cand_add_to_index
        from synthadoc.cli.candidates import _page_title as _cand_page_title
        import shutil as _shutil
        cd = _cand_dir()
        wd = _wiki_dir()
        pages = sorted(cd.glob("*.md")) if cd.exists() else []
        promoted = []
        new_pages = []  # only pages that didn't already exist in wiki/
        for src in pages:
            dest = wd / src.name
            is_new = not dest.exists()
            title = _cand_page_title(src)
            _shutil.move(str(src), str(dest))
            promoted.append((src.stem, title))
            if is_new:
                new_pages.append((src.stem, title))
        if new_pages:
            _cand_add_to_index(wd, new_pages)
        return {"promoted": [s for s, _ in promoted], "count": len(promoted)}

    @app.post("/candidates/discard-all")
    async def candidates_discard_all():
        cd = _cand_dir()
        pages = sorted(cd.glob("*.md")) if cd.exists() else []
        discarded = []
        for src in pages:
            src.unlink(missing_ok=True)
            discarded.append(src.stem)
        return {"discarded": discarded, "count": len(discarded)}

    @app.post("/candidates/{slug}/promote")
    async def candidates_promote_one(slug: str):
        import shutil as _shutil
        from synthadoc.cli.candidates import _add_to_index as _cand_add_to_index
        from synthadoc.cli.candidates import _page_title as _cand_page_title
        cd = _cand_dir()
        wd = _wiki_dir()
        src = cd / f"{slug}.md"
        if not src.exists():
            raise HTTPException(404, f"Candidate '{slug}' not found.")
        dest = wd / src.name
        is_new = not dest.exists()
        title = _cand_page_title(src)
        _shutil.move(str(src), str(dest))
        if is_new:
            _cand_add_to_index(wd, [(slug, title)])
        return {"slug": slug, "promoted": True, "updated": not is_new}

    @app.post("/candidates/{slug}/discard")
    async def candidates_discard_one(slug: str):
        cd = _cand_dir()
        src = cd / f"{slug}.md"
        if not src.exists():
            raise HTTPException(404, f"Candidate '{slug}' not found.")
        src.unlink()
        return {"slug": slug, "discarded": True}

    # ── Provenance ────────────────────────────────────────────────────────────
    @app.get("/provenance/citations")
    async def provenance_citations(
        page: str = "",
        source: str = "",
        broken: bool = False,
        limit: int = 50,
        offset: int = 0,
        sort: str = "ingested_at",
        order: str = "desc",
    ):
        audit = app.state.orch._audit
        if broken:
            all_failures = await audit.list_citation_failures(limit=100_000, offset=0)
            rows = await audit.list_citation_failures(limit=limit, offset=offset)
            return {"total": len(all_failures), "citations": rows}
        rows = await audit.list_citations(
            page_slug=page or None,
            source_file=source or None,
            limit=limit,
            offset=offset,
            sort=sort,
            order=order,
        )
        # Total count without limit
        all_rows = await audit.list_citations(
            page_slug=page or None,
            source_file=source or None,
            limit=100_000,
            offset=0,
        )
        return {"total": len(all_rows), "citations": rows}

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    @app.get("/lifecycle/pages")
    async def lifecycle_pages():
        audit = app.state.orch._audit
        pages = await audit.get_all_page_states()
        cdir = _cand_dir()
        pages = [p for p in pages if not (cdir / f"{p['slug']}.md").exists()]
        return {"pages": pages}

    @app.get("/lifecycle/status")
    async def lifecycle_status():
        from synthadoc.agents.lint_agent import LINT_SKIP_SLUGS
        orch = app.state.orch
        audit = orch._audit
        counts = await audit.get_lifecycle_summary()
        # Split draft into wiki-domain drafts vs staged-in-candidates drafts.
        if counts.get("draft", 0) > 0:
            cdir = _cand_dir()
            all_states = await audit.get_all_page_states()
            in_cand = sum(1 for p in all_states
                          if p["state"] == "draft" and (cdir / f"{p['slug']}.md").exists())
            if in_cand:
                counts["draft"] = counts["draft"] - in_cand
                counts["draft_candidates"] = in_cand
        # Pages on disk that have never been linted have no page_states row.
        all_pages = [s for s in orch._store.list_pages() if s not in LINT_SKIP_SLUGS]
        unlinted = len(all_pages) - sum(counts.values())
        if unlinted > 0:
            counts["unlinted"] = unlinted
        return counts

    @app.get("/lifecycle/events")
    async def lifecycle_events(
        slug: str = "",
        to_state: str = "",
        limit: int = 50,
        offset: int = 0,
    ):
        audit = app.state.orch._audit
        events, total = await audit.get_lifecycle_events(
            slug=slug or None,
            to_state=to_state or None,
            limit=limit,
            offset=offset,
        )
        return {"events": events, "total": total}

    @app.post("/lifecycle/transition")
    async def lifecycle_transition(req: LifecycleTransitionRequest):
        orch = app.state.orch
        if (_cand_dir() / f"{req.slug}.md").exists():
            raise HTTPException(
                status_code=422,
                detail=(
                    f"'{req.slug}' is in candidates/ and has not been promoted yet. "
                    f"Run: synthadoc candidates promote {req.slug}"
                ),
            )
        page = orch._store.read_page(req.slug)
        if not page:
            raise HTTPException(status_code=404, detail=f"Page not found: {req.slug}")
        from_state = page.status
        from synthadoc.storage.wiki import validate_lifecycle_transition
        err = validate_lifecycle_transition(from_state, req.to_state)
        if err:
            raise HTTPException(status_code=422, detail=err)
        page.status = req.to_state
        orch._store.write_page(req.slug, page)
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()
        audit = app.state.orch._audit
        await audit.set_page_state(req.slug, req.to_state, TriggerSource.USER)
        await audit.record_lifecycle_event(req.slug, from_state, req.to_state,
                                            req.reason, TriggerSource.USER)
        orch._bump_epoch()
        return {"slug": req.slug, "from_state": from_state, "to_state": req.to_state, "timestamp": ts}

    # ── Export ────────────────────────────────────────────────────────────────
    @app.post("/export")
    async def export_wiki(req: ExportRequest):
        from synthadoc.agents.export_agent import ExportAgent, ExportOptions, EXPORT_FORMATS
        if req.format not in EXPORT_FORMATS:
            raise HTTPException(status_code=422,
                                detail=f"Unknown format: {req.format!r}")
        agent = ExportAgent(
            store=app.state.orch._store,
            wiki_name=wiki_root.name,
            audit_db_path=wiki_root / ".synthadoc" / "audit.db",
            routing_path=wiki_root / "ROUTING.md",
        )
        opts = ExportOptions(
            format=req.format,
            status_filter=req.status_filter,
            context_pack=req.context_pack,
        )
        content = await agent.export(opts)
        if req.format == "okf":
            import json as _json
            return Response(
                content=_json.dumps(content, ensure_ascii=False),
                media_type="application/json",
            )
        _CONTENT_TYPES = {
            "llms.txt":      "text/plain; charset=utf-8",
            "llms-full.txt": "text/plain; charset=utf-8",
            "graphml":       "application/xml",
            "json":          "application/json",
        }
        return Response(content=content, media_type=_CONTENT_TYPES[req.format])

    # Serve the React web UI for /app and /app/* paths.
    # pip-installed: dist is bundled under synthadoc/data/web-ui/dist/
    # dev (editable install): fall back to the source tree web-ui/dist/
    _pkg_web_dist = Path(__file__).parent.parent / "data" / "web-ui" / "dist"
    _src_web_dist = Path(__file__).parent.parent.parent / "web-ui" / "dist"
    _web_dist = _pkg_web_dist if (_pkg_web_dist / "index.html").is_file() else _src_web_dist
    if _web_dist.exists() and (_web_dist / "index.html").is_file():
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import FileResponse, RedirectResponse
        _assets = _web_dist / "assets"
        if _assets.exists():
            app.mount("/app/assets", StaticFiles(directory=str(_assets)), name="web_assets")

        @app.get("/app")
        async def spa_root():
            return RedirectResponse(url="/app/", status_code=307)

        @app.get("/app/")
        @app.get("/app/{path:path}")
        async def spa(path: str = ""):
            return FileResponse(
                str(_web_dist / "index.html"),
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )
    else:
        @app.get("/app")
        @app.get("/app/{path:path}")
        async def spa_not_built(path: str = ""):
            return Response(
                content="Web UI not built. Run: cd web-ui && npm run build",
                status_code=503,
                media_type="text/plain",
            )

    return app
