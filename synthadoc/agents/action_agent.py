# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from synthadoc.providers.base import LLMProvider, Message

logger = logging.getLogger(__name__)

# ── action detection ───────────────────────────────────────────────────────────
# Matches imperative action requests. Excludes interrogative phrases
# ("how do I run...", "can I run...") by anchoring verb+noun to the start.

_ACTION_RE = re.compile(
    r"^(please\s+)?(run|execute|start|trigger|perform)\b.{0,50}\b(lint|ingest|scaffold)\b"
    r"|(?<![a-zA-Z-])ingest\s+\S"
    r"|\b(rebuild|regenerate)\b.{0,20}\bscaffold\b"
    r"|\bschedule\s+(add|a|an|daily|weekly|hourly|every|at)\b"
    r"|\b(list|show)\b.{0,20}\bschedul"
    r"|\b(activate|archive|restore)\s+\w",
    re.IGNORECASE,
)

# ── extraction prompt ─────────────────────────────────────────────────────────

_EXTRACT_PROMPT_TEMPLATE = (
    "You are an action parser for Synthadoc. Extract the intended action and its "
    "parameters from the user request below.\n\n"
    "Return ONLY a JSON object — no explanation, no markdown fences.\n\n"
    'Schema: {{"action": "<lint|ingest|scaffold|schedule_add|schedule_list|'
    'lifecycle_activate|lifecycle_archive|lifecycle_restore|none>", "params": {{...}}}}\n\n'
    "params keys by action:\n"
    "  lint          : scope (all|contradictions|orphans|stale|citations), auto_resolve (bool)\n"
    "  ingest        : source (URL or path), force (bool)\n"
    "  scaffold      : domain (string or null)\n"
    "  schedule_add  : op (full synthadoc command, e.g. 'ingest --batch sources/'), "
    "cron (parsed cron expression), schedule_description (original natural language)\n"
    "  schedule_list : (no params)\n"
    "  lifecycle_activate / lifecycle_archive / lifecycle_restore : slug, reason\n"
    "  none          : (no params)\n\n"
    "Cron parsing: 'daily at 6am'='0 6 * * *', 'every Sunday at 7pm'='0 19 * * 0', "
    "'every weekday at 9am'='0 9 * * 1-5', 'every hour'='0 * * * *'\n\n"
    "User request: {question}"
)

# ── result ────────────────────────────────────────────────────────────────────

@dataclass
class ActionResult:
    action_type: str
    success: bool
    message: str
    job_id: Optional[str] = None
    data: dict = field(default_factory=dict)


# ── agent ─────────────────────────────────────────────────────────────────────

class ActionAgent:
    """Detects action-intent queries and dispatches them to the Synthadoc orchestrator."""

    def __init__(
        self,
        provider: LLMProvider,
        orchestrator: Any,
        wiki_root: Path,
    ) -> None:
        self._provider = provider
        self._orch = orchestrator
        self._wiki_root = wiki_root

    # ── public ────────────────────────────────────────────────────────────────

    def detect(self, question: str) -> bool:
        """Fast regex pre-check — True if the question looks like an action request."""
        return bool(_ACTION_RE.search(question))

    async def run(self, question: str) -> Optional[ActionResult]:
        """Extract action + params from question and execute. Returns None if not an action."""
        extraction = await self._extract(question)
        if not extraction:
            return None
        action = extraction.get("action", "none")
        params = extraction.get("params", {})
        if action == "none":
            return None
        try:
            return await self._dispatch(action, params)
        except Exception as exc:
            logger.warning("action dispatch failed (%s): %s", action, exc)
            return ActionResult(
                action_type=action,
                success=False,
                message=f"Could not complete the action: {exc}",
            )

    # ── private ───────────────────────────────────────────────────────────────

    async def _extract(self, question: str) -> Optional[dict]:
        prompt = _EXTRACT_PROMPT_TEMPLATE.format(question=question)
        resp = await self._provider.complete(
            messages=[Message(role="user", content=prompt)],
            temperature=0.0,
        )
        try:
            text = resp.text.strip()
            # Strip markdown fences if present
            if text.startswith("```"):
                text = re.sub(r"^```[a-z]*\n?", "", text)
                text = re.sub(r"\n?```$", "", text.strip())
            return json.loads(text)
        except Exception as exc:
            logger.debug("action extraction JSON parse failed: %s — raw: %r", exc, resp.text[:200])
            return None

    async def _dispatch(self, action: str, params: dict) -> ActionResult:
        if action == "lint":
            return await self._do_lint(params)
        if action == "ingest":
            return await self._do_ingest(params)
        if action == "scaffold":
            return await self._do_scaffold(params)
        if action == "schedule_add":
            return self._do_schedule_add(params)
        if action == "schedule_list":
            return self._do_schedule_list()
        if action in ("lifecycle_activate", "lifecycle_archive", "lifecycle_restore"):
            return await self._do_lifecycle(action, params)
        return ActionResult(action_type=action, success=False,
                            message=f"Unknown action type: `{action}`")

    async def _do_lint(self, params: dict) -> ActionResult:
        scope = params.get("scope", "all")
        auto_resolve = bool(params.get("auto_resolve", False))
        job_id = await self._orch.lint(scope=scope, auto_resolve=auto_resolve)
        flags = []
        if scope != "all":
            flags.append(f"--scope {scope}")
        if auto_resolve:
            flags.append("--auto-resolve")
        flag_str = " " + " ".join(flags) if flags else ""
        return ActionResult(
            action_type="lint",
            success=True,
            job_id=job_id,
            message=(
                f"Lint job started (`synthadoc lint run{flag_str}`).\n\n"
                f"**Job ID:** `{job_id}`\n\n"
                f"Check progress with `synthadoc jobs list` or ask "
                f"\"What is the status of my jobs?\""
            ),
        )

    async def _do_ingest(self, params: dict) -> ActionResult:
        source = params.get("source", "")
        if not source:
            return ActionResult(action_type="ingest", success=False,
                                message="No source specified. Please provide a URL or file path.")
        force = bool(params.get("force", False))
        job_id = await self._orch.ingest(source=source, force=force)
        flag_str = " --force" if force else ""
        return ActionResult(
            action_type="ingest",
            success=True,
            job_id=job_id,
            message=(
                f"Ingest job started for `{source}`{flag_str}.\n\n"
                f"**Job ID:** `{job_id}`\n\n"
                f"Check progress with `synthadoc jobs list`."
            ),
        )

    async def _do_scaffold(self, params: dict) -> ActionResult:
        domain = params.get("domain") or getattr(
            getattr(self._orch, "_cfg", None), "wiki", None
        ) and self._orch._cfg.wiki.domain or ""
        job_id = await self._orch._queue.enqueue("scaffold", {"domain": domain or ""})
        return ActionResult(
            action_type="scaffold",
            success=True,
            job_id=job_id,
            message=(
                f"Scaffold job started.\n\n"
                f"**Job ID:** `{job_id}`\n\n"
                f"Check progress with `synthadoc jobs list`."
            ),
        )

    def _do_schedule_add(self, params: dict) -> ActionResult:
        from synthadoc.core.scheduler import Scheduler as ScheduleDB
        op = params.get("op", "")
        cron = params.get("cron", "")
        desc = params.get("schedule_description", cron)
        if not op or not cron:
            return ActionResult(action_type="schedule_add", success=False,
                                message="Could not parse the schedule — please provide the command and time.")
        wiki_name = self._wiki_root.name
        db = ScheduleDB(wiki=wiki_name, wiki_root=str(self._wiki_root))
        entry_id = db.add(op=op, cron=cron)
        schedule_table = _format_schedule_list(db.list())
        return ActionResult(
            action_type="schedule_add",
            success=True,
            data={"entry_id": entry_id},
            message=(
                f"Scheduled **`{op}`** {desc} (`cron: {cron}`).\n\n"
                f"**Schedule ID:** `{entry_id}`\n\n"
                f"{schedule_table}\n\n"
                f"Manage with `synthadoc schedule list` or `synthadoc schedule remove {entry_id}`."
            ),
        )

    def _do_schedule_list(self) -> ActionResult:
        from synthadoc.core.scheduler import Scheduler as ScheduleDB
        wiki_name = self._wiki_root.name
        db = ScheduleDB(wiki=wiki_name, wiki_root=str(self._wiki_root))
        entries = db.list()
        schedule_table = _format_schedule_list(entries)
        return ActionResult(
            action_type="schedule_list",
            success=True,
            message=schedule_table,
        )

    async def _do_lifecycle(self, action: str, params: dict) -> ActionResult:
        from synthadoc.storage.log import AuditDB
        from synthadoc.storage.wiki import LifecycleState

        slug = params.get("slug", "").strip()
        reason = params.get("reason", "requested via chat")
        if not slug:
            return ActionResult(action_type=action, success=False,
                                message="No page slug provided.")

        _TO_STATE = {
            "lifecycle_activate": LifecycleState.ACTIVE,
            "lifecycle_archive":  LifecycleState.ARCHIVED,
            "lifecycle_restore":  LifecycleState.DRAFT,
        }
        _ALLOWED: set[tuple[str, str]] = {
            (LifecycleState.DRAFT,        LifecycleState.ACTIVE),
            (LifecycleState.DRAFT,        LifecycleState.ARCHIVED),
            (LifecycleState.ACTIVE,       LifecycleState.ARCHIVED),
            (LifecycleState.ACTIVE,       LifecycleState.STALE),
            (LifecycleState.CONTRADICTED, LifecycleState.ARCHIVED),
            (LifecycleState.STALE,        LifecycleState.DRAFT),
            (LifecycleState.STALE,        LifecycleState.ARCHIVED),
            (LifecycleState.ARCHIVED,     LifecycleState.DRAFT),
        }

        to_state = _TO_STATE[action]
        page = self._orch._store.read_page(slug)
        if not page:
            return ActionResult(action_type=action, success=False,
                                message=f"Page not found: `{slug}`")
        from_state = page.status
        if (from_state, to_state) not in _ALLOWED:
            return ActionResult(
                action_type=action, success=False,
                message=(
                    f"Cannot transition `{slug}` from **{from_state}** to **{to_state}**. "
                    f"That transition is not permitted."
                ),
            )
        page.status = to_state
        self._orch._store.write_page(slug, page)
        audit = AuditDB(self._wiki_root / ".synthadoc" / "audit.db")
        await audit.init()
        await audit.set_page_state(slug, to_state, "user")
        await audit.record_lifecycle_event(slug, from_state, to_state, reason, "user")
        self._orch._bump_epoch()
        return ActionResult(
            action_type=action,
            success=True,
            message=(
                f"Page **`{slug}`** transitioned from **{from_state}** → **{to_state}**.\n\n"
                f"Reason: {reason}"
            ),
        )


# ── helpers ───────────────────────────────────────────────────────────────────

def _format_schedule_list(entries: list) -> str:
    if not entries:
        return "**Scheduled tasks:** none. Add one with `synthadoc schedule add`."
    lines = ["**Scheduled tasks:**\n", "| ID | Command | Cron | Next run | Last result |",
             "|---|---|---|---|---|"]
    for e in entries:
        lines.append(
            f"| `{e.id}` | `{e.op}` | `{e.cron}` "
            f"| {e.next_run or '—'} | {e.last_result or '—'} |"
        )
    return "\n".join(lines)
