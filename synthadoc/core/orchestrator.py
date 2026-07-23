# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import logging

from synthadoc.config import Config, load_config
from synthadoc.errors import DomainBlockedException
from synthadoc.core.cache import CacheManager
from synthadoc.core.cost_guard import CostGuard, CostEstimate, CostGateError, CostEstimate, CostGateError
from synthadoc.core.hooks import HookExecutor
from synthadoc.core.queue import JobQueue
from synthadoc.observability.telemetry import get_tracer, setup_telemetry
from synthadoc.providers import make_provider
from synthadoc.providers.pricing import estimate_cost
from synthadoc.storage.log import AuditDB, LogWriter
from synthadoc.storage.search import HybridSearch
from synthadoc.storage.wiki import WikiStorage

logger = logging.getLogger(__name__)

# Intent prefixes accepted on manifest lines (matched case-insensitively).
_MANIFEST_INTENT_PREFIXES = (
    "search for:", "find on the web:", "look up:", "web search:",
    "browse:", "fetch url:", "web page:", "website:",
)


def _read_manifest(path: Path) -> list[str] | None:
    """Return source lines from a .txt manifest, or None if the file is not a manifest.

    A file qualifies as a manifest when every non-empty, non-comment line is one of:
    - an http/https URL
    - a recognised intent phrase (e.g. "search for: …")
    - a file path that exists on disk (resolved relative to the manifest's directory)

    A file with no content lines does NOT qualify (avoid treating empty .txt as manifest).
    """
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return None

    content_lines = [l.strip() for l in raw_lines if l.strip() and not l.strip().startswith("#")]
    if not content_lines:
        return None

    base = path.parent
    for line in content_lines:
        lower = line.lower()
        if line.startswith(("http://", "https://")):
            continue
        if any(lower.startswith(p) for p in _MANIFEST_INTENT_PREFIXES):
            continue
        candidate = Path(line)
        resolved = candidate if candidate.is_absolute() else (base / candidate)
        try:
            path_exists = resolved.exists()
        except OSError:
            # ENAMETOOLONG (errno 63) or other OS error — line can't be a valid path
            path_exists = False
        if path_exists:
            continue
        return None  # line is not a URL, intent, or valid path — not a manifest

    return content_lines


def _resolve_manifest_source(line: str, base: Path) -> str:
    """Convert a manifest line to the absolute form expected by the ingest pipeline."""
    lower = line.lower()
    if line.startswith(("http://", "https://")) or any(
        lower.startswith(p) for p in _MANIFEST_INTENT_PREFIXES
    ):
        return line  # URLs and intent phrases pass through unchanged
    candidate = Path(line)
    return str(candidate if candidate.is_absolute() else (base / candidate).resolve())


class Orchestrator:
    def __init__(self, wiki_root: Path, config: Optional[Config] = None) -> None:
        self._root = wiki_root
        self._cfg = config or load_config(
            project_config=wiki_root / ".synthadoc" / "config.toml")
        sd = wiki_root / ".synthadoc"
        sd.mkdir(parents=True, exist_ok=True)
        (sd / "logs").mkdir(exist_ok=True)

        self._queue  = JobQueue(sd / "jobs.db", max_retries=self._cfg.queue.max_retries)
        self.queue   = self._queue
        self._audit  = AuditDB(sd / "audit.db")
        self._cache  = CacheManager(sd / "cache.db")
        self._store  = WikiStorage(wiki_root / "wiki")
        self._search = HybridSearch(
            self._store, sd / "embeddings.db",
            search_cfg=self._cfg.search,
        )
        self._log    = LogWriter(wiki_root / "log.md")
        self._cost   = CostGuard(self._cfg.cost)
        self._hooks  = HookExecutor(self._cfg.hooks)
        self._wiki_epoch: int = 0
        self._migration_task: "asyncio.Task[None] | None" = None
        setup_telemetry(sd / "logs" / "traces.jsonl")

    def _bump_epoch(self) -> None:
        self._wiki_epoch += 1

    async def init(self) -> None:
        await self._queue.init(stale_pending_seconds=self._cfg.server.job_timeout_seconds * 2)
        await self._audit.init()
        await self._cache.init()
        self._log_agent_config()
        if self._cfg.search.vector:
            logger.info("Vector search: enabled (model: BAAI/bge-small-en-v1.5) — initialising…")
            try:
                await self._search.init_vector()
                self._migration_task = asyncio.create_task(self._run_vector_migration())
            except ImportError:
                logger.warning(
                    "Vector search requires 'fastembed' which is not installed. "
                    "Run: pip install fastembed  then restart the server. "
                    "Falling back to BM25 search."
                )

    async def close(self) -> None:
        if self._migration_task and not self._migration_task.done():
            self._migration_task.cancel()
            try:
                await self._migration_task
            except asyncio.CancelledError:
                pass
        await self._cache.close()
        await asyncio.sleep(0.05)  # allow in-flight aiosqlite thread callbacks to post before loop teardown

    async def __aenter__(self) -> "Orchestrator":
        await self.init()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def _run_vector_migration(self) -> None:
        """Embed all existing wiki pages not yet in embeddings.db (background task)."""
        import time
        if not self._cfg.search.vector or self._search._vector_store is None:
            return
        slugs = self._store.list_pages()
        embedded = set(await self._search._vector_store.list_slugs())
        to_embed = [s for s in slugs if s not in embedded]
        if not to_embed:
            logger.info("Vector search: all %d page(s) already embedded — ready", len(embedded))
            return
        logger.info(
            "Vector search: %d page(s) to embed (%d already done) — running background migration, BM25 active meanwhile",
            len(to_embed), len(embedded),
        )
        start = time.monotonic()
        for i, slug in enumerate(to_embed, 1):
            page = self._store.read_page(slug)
            if page:
                text = f"{page.title} {' '.join(page.tags)} {page.content}"
                await self._search.embed_page(slug, text)
            if i % 50 == 0:
                logger.info("Vector migration: %d/%d pages embedded…", i, len(to_embed))
            await asyncio.sleep(0)
        logger.info(
            "Vector migration complete — %d pages, %.0fs",
            len(to_embed), time.monotonic() - start,
        )

    def _log_agent_config(self) -> None:
        """Log the effective provider/model for each named agent slot at startup."""
        slots = ["default", "ingest", "query", "lint", "skill", "adversarial"]
        parts = []
        seen: dict[str, str] = {}
        for slot in slots:
            cfg = self._cfg.agents.resolve(slot)
            label = f"{cfg.provider}/{cfg.model}"
            raw = getattr(self._cfg.agents, slot, None)
            if slot == "default" or raw is not None:
                parts.append(f"{slot}={label}")
                seen[slot] = label
        logger.info("LLM agents — %s", " | ".join(parts))

    async def ingest(self, source: str, force: bool = False,
                     max_results: int | None = None,
                     max_source_chars: int | None = None) -> str:
        """Enqueue an ingest job. The server worker loop executes it."""
        payload: dict = {"source": source, "force": force}
        if max_results is not None:
            payload["max_results"] = max_results
        if max_source_chars is not None:
            payload["max_source_chars"] = max_source_chars
        return await self._queue.enqueue("ingest", payload)

    async def resume(self) -> int:
        """Re-enqueue all pending and failed jobs."""
        from synthadoc.core.queue import JobStatus
        jobs = await self._queue.list_jobs(status=JobStatus.PENDING)
        jobs += await self._queue.list_jobs(status=JobStatus.FAILED)
        for job in jobs:
            await self._queue.retry(job.id)
        return len(jobs)

    async def _run_ingest(self, job_id: str, source: str, auto_confirm: bool,
                          force: bool = False, max_results: int | None = None,
                          max_source_chars: int | None = None,
                          allow_external_paths: bool = False) -> None:
        # auto_confirm is reserved for when user-facing confirmation prompts are added.
        from synthadoc.agents.ingest_agent import IngestAgent
        from synthadoc.skills.web_search.scripts.main import _INTENT_RE as _WEB_SEARCH_RE
        try:
            # Reload config from disk so staging_policy and other runtime settings
            # take effect without a server restart.
            _cfg_path = self._root / ".synthadoc" / "config.toml"
            cfg = load_config(project_config=_cfg_path) if _cfg_path.exists() else self._cfg
            # Apply per-run override without mutating the global config object.
            if max_source_chars is not None:
                import copy as _copy
                cfg = _copy.deepcopy(cfg)
                cfg.ingest.max_source_chars = max_source_chars

            # Manifest expansion: a .txt file where every line is a URL / intent / path
            # is treated as a batch source list — fan out into one child job per line.
            _src_path = Path(source) if not source.startswith(("http://", "https://")) else None
            if _src_path and _src_path.suffix.lower() == ".txt" and _src_path.exists():
                _manifest_lines = _read_manifest(_src_path)
                if _manifest_lines is not None:
                    await self._queue.update_progress(job_id, {"phase": "expanding_manifest"})
                    _resolved = [_resolve_manifest_source(l, _src_path.parent)
                                 for l in _manifest_lines]
                    if max_results is not None:
                        _resolved = _resolved[:max_results]
                    child_ids = await self._queue.enqueue_many(
                        "ingest",
                        [{"source": s, "force": force} for s in _resolved],
                    )
                    await self._queue.complete(job_id, result={
                        "pages_created": [], "pages_updated": [], "pages_flagged": [],
                        "child_sources_enqueued": len(_resolved),
                        "child_job_ids": child_ids,
                        "tokens_used": 0, "cost_usd": 0.0,
                        "manifest": str(_src_path),
                    })
                    logger.info("Manifest %s expanded into %d child jobs", _src_path, len(_resolved))
                    return

            _is_web_search = bool(_WEB_SEARCH_RE.match(source))
            if _is_web_search:
                await self._queue.update_progress(job_id, {"phase": "searching"})

            if await self._pre_check_ingest_cost(job_id, source, cfg):
                return

            # Resolve agent config for post-call pricing.
            _agent_cfg = cfg.agents.resolve("ingest")
            _is_local = _agent_cfg.is_local

            _routing_path = self._root / "ROUTING.md"
            agent = IngestAgent(
                provider=make_provider("ingest", cfg),
                store=self._store, search=self._search,
                log_writer=self._log, audit_db=self._audit,
                cache=self._cache, max_pages=cfg.ingest.max_pages_per_ingest,
                cache_version=cfg.cache.version,
                fetch_timeout=cfg.ingest.fetch_timeout_seconds,
                wiki_root=self._root,
                routing_path=_routing_path if _routing_path.exists() else None,
                cfg=cfg,
                allow_external_paths=allow_external_paths,
            )
            result = await agent.ingest(source, force=force, bust_cache=force)
            result.cost_usd = estimate_cost(
                _agent_cfg.model,
                result.input_tokens,
                result.output_tokens,
                is_local=_is_local,
            )
            await self._audit.update_ingest_cost(source, result.cost_usd)
            await self._guard_ingest_cost(job_id, source, result.tokens_used, result.cost_usd)
            if max_results is not None and result.child_sources:
                result.child_sources = result.child_sources[:max_results]
            if _is_web_search and result.child_sources:
                await self._queue.update_progress(job_id, {
                    "phase": "found_urls",
                    "total": len(result.child_sources),
                })
            # Fan out web search child sources — batch insert in one transaction
            if result.child_sources:
                child_ids = await self._queue.enqueue_many(
                    "ingest",
                    [{"source": s, "force": False} for s in result.child_sources],
                )
            else:
                child_ids = []

            job_result: dict = {
                "pages_created": result.pages_created,
                "pages_updated": result.pages_updated,
                "pages_flagged": result.pages_flagged,
                "child_sources_enqueued": len(result.child_sources),
                "child_job_ids": child_ids,
                "tokens_used": result.tokens_used,
                "cost_usd": result.cost_usd,
            }
            if result.skipped:
                await self._queue.skip(job_id, result.skip_reason or "skipped")
            else:
                await self._queue.complete(job_id, result=job_result)
                self._bump_epoch()
                # Embed newly written pages for vector search
                if self._cfg.search.vector:
                    for slug in result.pages_created + result.pages_updated:
                        page = self._store.read_page(slug)
                        if page:
                            text = f"{page.title} {' '.join(page.tags)} {page.content}"
                            await self._search.embed_page(slug, text)
                self._hooks.fire("on_ingest_complete", {
                    "event": "on_ingest_complete", "wiki": str(self._root),
                    "source": source,
                    "pages_created": result.pages_created,
                    "pages_updated": result.pages_updated,
                    "pages_flagged": result.pages_flagged,
                    "tokens_used": result.tokens_used,
                    "cost_usd": result.cost_usd,
                })
        except (NotImplementedError, FileNotFoundError) as e:
            # Permanent failures — source is invalid, retry can never help
            await self._queue.fail_permanent(job_id, str(e))
        except EnvironmentError as e:
            # Provider binary not installed (ERR-PROV-003) — log cleanly, no traceback
            logging.getLogger(__name__).warning("%s", e)
            await self._queue.fail_permanent(job_id, str(e))
        except Exception as e:
            import httpx
            from synthadoc.errors import (
                DomainBlockedException, DailyQuotaExhaustedException,
                CodingToolQuotaExhaustedException,
            )
            # Check for LLM rate limits (openai SDK used by Groq/Gemini, and Anthropic SDK)
            _status = getattr(e, "status_code", None) or getattr(
                getattr(e, "response", None), "status_code", None)
            if isinstance(e, DailyQuotaExhaustedException):
                # Daily quota exhaustion is permanent for the rest of the day —
                # permanently fail the job so the worker does NOT sleep-and-retry.
                logging.getLogger(__name__).error(
                    "Daily quota exhausted — permanently failing job %s "
                    "(quota resets at midnight UTC)", job_id
                )
                await self._queue.fail_permanent(job_id, str(e))
            elif isinstance(e, CodingToolQuotaExhaustedException):
                logging.getLogger(__name__).error(
                    "Coding tool quota exhausted — permanently failing job %s", job_id
                )
                await self._queue.fail_permanent(job_id, str(e))
                # Do NOT raise: letting the worker continue drains the pending
                # queue quickly rather than looping every 60 s.
            elif _status == 429:
                # Per-minute rate limit — requeue without burning a retry; worker will sleep
                logging.getLogger(__name__).warning(
                    "LLM rate limit for job %s — requeued without retry penalty", job_id
                )
                await self._queue.requeue(job_id, f"rate_limit: {e}")
                raise
            elif isinstance(e, DomainBlockedException):
                await self._auto_block_domain(e)
                await self._queue.skip(job_id, str(e))
            elif isinstance(e, (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout,
                                   httpx.ConnectError, httpx.ReadError)):
                # Transient network error (timeout, connection refused, dropped) — retry with backoff.
                logging.getLogger(__name__).warning(
                    "URL fetch failed for job %s (%s: %s) — will retry", job_id, source,
                    type(e).__name__
                )
                await self._queue.fail(job_id, f"{type(e).__name__}: {source}")
            elif isinstance(e, httpx.HTTPStatusError):
                status = e.response.status_code
                if 400 <= status < 500:
                    # Permanent client error (404, 410, 451, etc.) — skip, no retry, no traceback.
                    logging.getLogger(__name__).warning(
                        "HTTP %s fetching %s — skipping job %s", status, source, job_id
                    )
                    await self._queue.skip(job_id, f"HTTP {status}: {source}")
                else:
                    # 5xx server error — transient, retry with backoff, no traceback.
                    logging.getLogger(__name__).warning(
                        "HTTP %s fetching %s — will retry job %s", status, source, job_id
                    )
                    await self._queue.fail(job_id, f"HTTP {status}: {source}")
            else:
                await self._queue.fail(job_id, str(e))
                raise

    async def _pre_check_ingest_cost(
        self, job_id: str, source: str, cfg: "Config"
    ) -> bool:
        """Enforce the hard gate BEFORE any LLM call using a worst-case cost estimate.

        Estimate: max_source_chars // 4 input tokens, // 16 output tokens (~4 chars/token).
        Returns True if the job was permanently blocked — caller must return immediately.
        """
        _agent_cfg = cfg.agents.resolve("ingest")
        _is_local = _agent_cfg.is_local
        _pre_input = cfg.ingest.max_source_chars // 4
        _pre_output = _pre_input // 4
        _pre_cost = estimate_cost(_agent_cfg.model, _pre_input, _pre_output, is_local=_is_local)
        _pre_estimate = CostEstimate(
            tokens=_pre_input + _pre_output,
            cost_usd=_pre_cost,
            operation=f"pre-check:ingest:{source}",
        )
        try:
            self._cost.check(_pre_estimate, interactive=False)
            return False
        except CostGateError as e:
            logger.error("Ingest job %s blocked by pre-call cost check: %s", job_id, e)
            await self._audit.record_audit_event(
                job_id=job_id,
                event="cost_gate_exceeded",
                metadata={
                    "source": source,
                    "cost_usd": _pre_cost,
                    "hard_gate_usd": self._cfg.cost.hard_gate_usd,
                    "tokens": _pre_input + _pre_output,
                    "stage": "pre_call",
                },
            )
            await self._queue.fail_permanent(job_id, f"cost_gate_exceeded: {e}")
            return True

    async def _guard_ingest_cost(
        self, job_id: str, source: str, tokens: int, cost_usd: float
    ) -> None:
        """Emit a soft-cost warning if actual ingest cost exceeds soft_warn_usd.

        The hard gate is enforced pre-call via _pre_check_ingest_cost before any LLM spend.
        """
        if cost_usd >= self._cfg.cost.soft_warn_usd:
            logger.warning(
                "Ingest cost $%.4f exceeds soft_warn_usd $%.2f for job %s",
                cost_usd, self._cfg.cost.soft_warn_usd, job_id,
            )

    async def _auto_block_domain(self, exc: DomainBlockedException) -> None:
        """Persist a newly discovered blocked domain and record an audit event."""
        import json
        import logging
        from datetime import datetime, timezone

        blocked_path = self._root / ".synthadoc" / "blocked_domains.json"
        try:
            existing: list = json.loads(blocked_path.read_text(encoding="utf-8")) \
                if blocked_path.exists() else []
            if exc.domain not in existing:
                existing.append(exc.domain)
                blocked_path.write_text(
                    json.dumps(existing, indent=2), encoding="utf-8"
                )
        except Exception as write_err:
            logging.getLogger(__name__).warning(
                "Could not persist blocked domain %s: %s", exc.domain, write_err
            )

        try:
            await self._audit.record_audit_event(
                job_id="system",
                event="domain_auto_blocked",
                metadata={
                    "domain": exc.domain,
                    "url": exc.url,
                    "status_code": exc.status_code,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception:
            pass

    async def query(self, question: str, timeout_seconds: int = 60):
        import asyncio
        from synthadoc.agents.query_agent import QueryAgent
        _provider = make_provider("query", self._cfg)
        _query_cfg = self._cfg.agents.resolve("query")
        result = await asyncio.wait_for(
            QueryAgent(
                provider=_provider,
                store=self._store, search=self._search,
                query_config=self._cfg.query,
                model=_query_cfg.model,
                gap_score_threshold=self._cfg.query.gap_score_threshold,
                orchestrator=self,
                max_tokens=self._cfg.agents.query_max_tokens,
            ).query(question),
            timeout=timeout_seconds if timeout_seconds > 0 else None,
        )
        cost_usd = estimate_cost(
            _query_cfg.model,
            result.input_tokens,
            result.output_tokens,
            is_local=_query_cfg.is_local,
        )
        await self._audit.record_query(
            question=question,
            sub_questions_count=result.sub_questions_count or 1,
            tokens=result.tokens_used,
            cost_usd=cost_usd,
        )
        self._log.log_query(
            question=question,
            sub_questions=len(result.citations) or 1,
            citations=result.citations,
            tokens=result.tokens_used,
            cost_usd=cost_usd,
        )
        return result

    async def query_stream(
        self, question: str, session_id: str | None = None,
        session_mode: str = "POWER_USER",
        history: list[dict] | None = None,
    ):
        """Async generator yielding SSE event dicts for streaming query response."""
        from synthadoc.agents.query_agent import QueryAgent
        _provider = make_provider("query", self._cfg)
        _routing_path = self._root / "ROUTING.md"
        _model = self._cfg.agents.resolve("query").model
        agent = QueryAgent(
            provider=_provider,
            store=self._store, search=self._search,
            query_config=self._cfg.query,
            model=_model,
            gap_score_threshold=self._cfg.query.gap_score_threshold,
            routing_path=_routing_path if _routing_path.exists() else None,
            orchestrator=self,
            max_tokens=self._cfg.agents.query_max_tokens,
        )
        async for evt in agent.run_stream(
            question, session_id=session_id, session_mode=session_mode,
            history=history or [],
        ):
            if evt.get("event") == "done":
                sub_q_count = evt.get("data", {}).get("sub_questions_count", 1)
                await self._audit.record_query(
                    question=question,
                    sub_questions_count=sub_q_count,
                    tokens=0,
                    cost_usd=0.0,
                )
            yield evt

    async def lint(self, scope: str = "all", auto_resolve: bool = False) -> str:
        """Enqueue a lint job. The server worker loop executes it."""
        return await self._queue.enqueue("lint", {"scope": scope, "auto_resolve": auto_resolve})

    async def _run_scaffold(self, job_id: str, domain: str) -> None:
        from synthadoc.agents.scaffold_agent import ScaffoldAgent, preserve_user_zone
        import re as _re
        _WIKILINK_RE = _re.compile(r"\[\[([^\]|#]+?)(?:\|[^\]]*)?\]\]")
        try:
            wiki_dir = self._root / "wiki"
            from synthadoc.agents.lint_agent import LINT_SKIP_SLUGS
            protected_slugs = [
                p.stem for p in wiki_dir.glob("*.md")
                if p.stem not in LINT_SKIP_SLUGS
            ]
            result = await ScaffoldAgent(
                provider=make_provider("ingest", self._cfg),
                max_tokens=self._cfg.agents.scaffold_max_tokens,
            ).scaffold(
                domain=domain,
                protected_slugs=protected_slugs or None,
                port=self._cfg.server.port,
            )

            index_path = self._root / "wiki" / "index.md"
            existing = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
            final_index = preserve_user_zone(existing, result.index_md)
            index_path.write_text(final_index, encoding="utf-8", newline="\n")
            for _filename, _content in (
                ("AGENTS.md", result.agents_md),
                ("CLAUDE.md", result.claude_md),
                ("GEMINI.md", result.gemini_md),
            ):
                (self._root / _filename).write_text(_content, encoding="utf-8", newline="\n")
            purpose_path = self._root / "wiki" / "purpose.md"
            existing_purpose = purpose_path.read_text(encoding="utf-8") if purpose_path.exists() else ""
            final_purpose = preserve_user_zone(existing_purpose, result.purpose_md)
            purpose_path.write_text(final_purpose, encoding="utf-8", newline="\n")

            # Scaffold rewrites index.md — regenerate ROUTING.md so routing stays in sync.
            routing_path = self._root / "ROUTING.md"
            routing_regenerated = False
            if routing_path.exists():
                from synthadoc.core.routing import RoutingIndex as _RoutingIndex
                from synthadoc.agents.scaffold_agent import _validate_routing_md
                _ri_new = _RoutingIndex.from_index_md(index_path)
                _ri_new.save(routing_path)
                _validate_routing_md(routing_path.read_text(encoding="utf-8"))
                routing_regenerated = True
                logger.info(
                    "scaffold: regenerated ROUTING.md (%d branches, %d slugs)",
                    len(_ri_new.branches),
                    sum(len(v) for v in _ri_new.branches.values()),
                )

            # Stamp categories from index.md section headings onto linked pages
            slug_cats: dict[str, list[str]] = {}
            current_section: str | None = None
            for line in result.index_md.splitlines():
                h2 = _re.match(r"^## (.+)", line)
                if h2:
                    current_section = h2.group(1).strip()
                    continue
                if current_section:
                    for m in _WIKILINK_RE.finditer(line):
                        slug = m.group(1).strip()
                        slug_cats.setdefault(slug, [])
                        if current_section not in slug_cats[slug]:
                            slug_cats[slug].append(current_section)
            categories_updated = 0
            for slug, cats in slug_cats.items():
                if slug not in LINT_SKIP_SLUGS and self._store.page_exists(slug):
                    self._store.set_page_categories(slug, cats)
                    categories_updated += 1

            await self._queue.complete(job_id, result={
                "domain": domain,
                "categories_updated": categories_updated,
                "routing_regenerated": routing_regenerated,
            })
        except Exception as e:
            await self._queue.fail(job_id, str(e))
            raise

    async def _run_lint(self, job_id: str, scope: str = "all", auto_resolve: bool = False,
                        adversarial: bool = True, lifecycle: bool = True,
                        check_url_availability: Optional[bool] = None) -> None:
        from synthadoc.agents.lint_agent import LintAgent
        try:
            adv_provider = make_provider("adversarial", self._cfg) if adversarial else None
            if adversarial:
                adv_cfg = self._cfg.agents.resolve("adversarial")
                if self._cfg.agents.adversarial is None:
                    logger.info(
                        "Adversarial pass: %s/%s (default — tip: set [agents].adversarial in "
                        "config.toml to use a dedicated judge model)",
                        adv_cfg.provider, adv_cfg.model,
                    )
                else:
                    logger.info(
                        "Adversarial pass: %s/%s (dedicated judge)",
                        adv_cfg.provider, adv_cfg.model,
                    )
            report = await LintAgent(
                provider=make_provider("lint", self._cfg),
                adversarial_provider=adv_provider,
                store=self._store, log_writer=self._log,
                confidence_threshold=self._cfg.cost.auto_resolve_confidence_threshold,
                audit_db=self._audit,
                adversarial_max_per_page=self._cfg.lint.adversarial_max_per_page,
                adversarial_concurrency=self._cfg.lint.adversarial_concurrency,
                wiki_root=self._root,
                cfg=self._cfg,
            ).lint(scope=scope, auto_resolve=auto_resolve, adversarial=adversarial,
                   lifecycle=lifecycle, check_url_availability=check_url_availability,
                   job_id=job_id)
            await self._queue.complete(job_id, result={
                "contradictions_found": report.contradictions_found,
                "contradictions_resolved": report.contradictions_resolved,
                "contradictions_unresolved": report.contradictions_unresolved,
                "orphans": report.orphan_slugs,
                "dangling_links_removed": report.dangling_links_removed,
                "adversarial_warnings": sum(len(w["warnings"]) for w in report.adversarial_warnings),
                "tokens_used": report.tokens_used,
            })
            self._hooks.fire("on_lint_complete", {
                "event": "on_lint_complete", "wiki": str(self._root),
                "contradictions_found": report.contradictions_found,
                "orphans": report.orphan_slugs,
            })
        except Exception as e:
            from synthadoc.errors import DailyQuotaExhaustedException, CodingToolQuotaExhaustedException
            if isinstance(e, (DailyQuotaExhaustedException, CodingToolQuotaExhaustedException)):
                await self._queue.fail_permanent(job_id, str(e))
            else:
                await self._queue.fail(job_id, str(e))
                raise
