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
from synthadoc.storage.wiki import LifecycleState

logger = logging.getLogger(__name__)

# ── lifecycle constants ───────────────────────────────────────────────────────
# Defined at module level so _do_lifecycle() doesn't rebuild them on every call.

_TO_STATE: dict[str, LifecycleState] = {
    "lifecycle_activate": LifecycleState.ACTIVE,
    "lifecycle_archive":  LifecycleState.ARCHIVED,
    "lifecycle_restore":  LifecycleState.DRAFT,
}
_SOURCE_STATES: dict[str, list[LifecycleState]] = {
    "lifecycle_activate": [LifecycleState.DRAFT],
    "lifecycle_archive":  [LifecycleState.ACTIVE, LifecycleState.STALE,
                           LifecycleState.DRAFT, LifecycleState.CONTRADICTED],
    "lifecycle_restore":  [LifecycleState.ARCHIVED],
}
_VERB: dict[str, str] = {
    "lifecycle_activate": "activate",
    "lifecycle_archive":  "archive",
    "lifecycle_restore":  "restore",
}
_MAX_CLARIFY_CANDIDATES = 15

_SCHEDULE_CRON_PROMPT = (
    "What schedule should this run on? (e.g. 'every night at 9 PM', 'daily at 6 AM')"
)

_MSG_LINT_ALL_CLEAR = (
    "All clear — no contradictions, orphan pages, or adversarial warnings."
)
_MSG_NO_LIFECYCLE_DATA = (
    "No lifecycle data yet. Run `synthadoc lint run` to initialise lifecycle states."
)
_MSG_NO_INGEST_SOURCE = "No source specified. Please provide a URL or file path."
_MSG_NO_SCHEDULE_PARAMS = (
    "Could not parse the schedule — please provide the command and time."
)
_MSG_NO_SCHEDULE_HISTORY = (
    "No scheduled run history yet — jobs will appear here after their first run."
)
_MSG_NO_LIFECYCLE_CANDIDATES = "No page slug provided and no eligible pages found."

_STATE_FILTER_MAP: dict[str, LifecycleState] = {
    "draft":        LifecycleState.DRAFT,
    "active":       LifecycleState.ACTIVE,
    "stale":        LifecycleState.STALE,
    "contradicted": LifecycleState.CONTRADICTED,
    "archived":     LifecycleState.ARCHIVED,
}

_ALLOWED: set[tuple[LifecycleState, LifecycleState]] = {
    (LifecycleState.DRAFT,        LifecycleState.ACTIVE),
    (LifecycleState.DRAFT,        LifecycleState.ARCHIVED),
    (LifecycleState.ACTIVE,       LifecycleState.ARCHIVED),
    (LifecycleState.ACTIVE,       LifecycleState.STALE),
    (LifecycleState.CONTRADICTED, LifecycleState.ARCHIVED),
    (LifecycleState.STALE,        LifecycleState.DRAFT),
    (LifecycleState.STALE,        LifecycleState.ARCHIVED),
    (LifecycleState.ARCHIVED,     LifecycleState.DRAFT),
}

# ── action detection ───────────────────────────────────────────────────────────

# Prefix written into the stored assistant message for every clarify turn so
# detect() can recognise a chip-reply in the very next turn without a regex match.
CLARIFY_STORE_PREFIX = "[clarify] "

_REPEAT_RE = re.compile(
    r"^(run|do|execute|try)\s+(it\s+)?(again|once\s+more)\b"
    r"|^(repeat|redo)\b"
    r"|\bagain\b$"
    r"|^(run|do)\s+that\b",
    re.IGNORECASE,
)

_ACTION_RE = re.compile(
    r"^(please\s+)?(run|execute|start|trigger|perform)\b.{0,50}\b(lint|ingest|scaffold)\b"
    # "can/could you (please) run lint …"
    r"|^(can|could|would)\s+(you\s+)?(please\s+)?(run|execute|start|trigger|perform)\b.{0,50}\b(lint|ingest|scaffold)\b"
    # "auto-resolve" / "auto resolve" in any context → lint action
    r"|\bauto.?resolv\b"
    # "resolve contradiction(s)" / "resolve the contradicted page"
    r"|\bresolv\w*.{0,50}\bcontradict"
    # "fix/clear contradictions"
    r"|\b(fix|clear)\b.{0,40}\bcontradict"
    r"|(?<![a-zA-Z-])ingest\s+\S"
    r"|\b(rebuild|regenerate)\b.{0,20}\bscaffold\b"
    r"|\bschedule\s+(add|a|an|daily|weekly|hourly|every|at)\b"
    r"|\b(add|create|register)\b.{0,80}\bschedul"
    r"|\b(list|show|display|view)\b.{0,20}\bschedul"
    r"|\bschedul\w*.{0,30}\b(histor|run|log)\w*\b"
    r"|(?<![a-zA-Z0-9])schedul\w*.{0,150}(?<![a-zA-Z0-9])(scaffold|ingest|lint)(?![a-zA-Z0-9])"
    r"|(?<![a-zA-Z0-9])(scaffold|ingest|lint)(?![a-zA-Z0-9]).{0,150}(?<![a-zA-Z0-9])schedul\w*"
    r"|\b(activate|archive|restore)\s+\w"
    r"|\borphan\s+page"
    r"|\bpage\w*.{0,20}\borphan"
    r"|\b(list|show|what|which|find|are there).{0,60}\b(orphan|contradict|adversarial).{0,40}\bpage"
    r"|\blint\s+(report|state|status|result|summary)"
    r"|\b(show|display|view|get)\b.{0,30}\blint\s+report"
    r"|\bwhat.{0,30}\b(orphan|contradict|adversarial)"
    r"|\bsynthadoc\s+status\b"
    r"|\b(show|display|view|get)\b.{0,40}\b(wiki|synthadoc)\s+status\b"
    r"|\b(wiki|page)\s+(health|summary|overview|status)\b"
    r"|\bhow many pages.{0,40}\b(draft|active|stale|contradict|archive)"
    r"|\b(draft|active|stale|contradicted|archived)\s+page\w*\s+(count|summary|stat)"
    # job status / job list
    r"|\bjob\w*\s+(status|detail|list|progress|result)\b"
    r"|\b(show|list|display|view|check|get)\b.{0,30}\bjob\w*\b"
    r"|\bwhat.{0,20}\b(status|progress).{0,20}\bjob\b",
    re.IGNORECASE,
)

# ── extraction prompt ─────────────────────────────────────────────────────────

_EXTRACT_PROMPT_TEMPLATE = (
    "You are an action parser for Synthadoc. Extract the intended action and its "
    "parameters from the user request below.\n\n"
    "Return ONLY a JSON object — no explanation, no markdown fences.\n\n"
    'Schema: {{"action": "<lint|lint_report|wiki_status|ingest|scaffold|schedule_add|schedule_list|'
    'schedule_history|lifecycle_activate|lifecycle_archive|lifecycle_restore|job_list|job_status|none>", "params": {{...}}}}\n\n'
    "params keys by action:\n"
    "  lint          : scope (all|contradictions|orphans|stale|citations), auto_resolve (bool)\n"
    "                  Use lint for ANY request to RUN the linter or auto-resolve issues:\n"
    "                  'run lint', 'run lint and auto resolve', 'auto-resolve', 'auto resolve contradictions',\n"
    "                  'resolve contradictions', 'fix contradictions', 'clear contradictions'.\n"
    "                  When 'auto-resolve' / 'auto resolve' / 'resolve' appears → set auto_resolve=true.\n"
    "                  When 'contradiction' appears → set scope='contradictions'.\n"
    "  lint_report   : focus (optional: 'contradicted'|'orphans'|'adversarial'|'truncated'|null)\n"
    "                  Shows current lint state; no server needed. Set focus to the specific category the user asks about.\n"
    "                  Use lint_report for ANY question asking what orphan/contradicted/adversarial/truncated pages exist NOW.\n"
    "                  Examples: 'list contradicted pages' → focus='contradicted'\n"
    "                            'what pages are orphans?' → focus='orphans'\n"
    "                            'show adversarial warnings' → focus='adversarial'\n"
    "                            'which sources were truncated?' → focus='truncated'\n"
    "                            'show lint report' / 'full lint report' → focus=null (show all)\n"
    "  wiki_status   : (no params — live page counts grouped by lifecycle state: draft/active/stale/contradicted/archived)\n"
    "                  Use wiki_status for: 'show synthadoc status', 'wiki health', 'how many pages are active?',\n"
    "                  'page lifecycle summary', 'synthadoc status result'\n"
    "  ingest        : source (URL or path), force (bool)\n"
    "  scaffold      : domain (string or null)\n"
    "                  Use scaffold for: 'run scaffold', 'rebuild scaffold', 'regenerate scaffold',\n"
    "                  'scaffold a computing wiki', 'please scaffold'\n"
    "  schedule_add  : op (full synthadoc subcommand, e.g. 'scaffold', 'lint run', "
    "'ingest --batch sources/'; NOTE: lint requires the 'run' subcommand — op must be "
    "'lint run', never just 'lint'), "
    "cron (parsed cron expression), schedule_description (original natural language)\n"
    "  schedule_list    : (no params) — use for 'list schedules', 'show scheduled tasks', 'what schedules exist'\n"
    "  schedule_history : (no params) — use for 'schedule history', 'show schedule history',\n"
    "                     'view scheduled run history', 'recent scheduled runs'\n"
    "                     IMPORTANT: if the word 'history' or 'run' or 'log' appears with 'schedule', use schedule_history not schedule_list\n"
    "  lifecycle_activate / lifecycle_archive / lifecycle_restore : slug, reason, "
    "state_filter (optional — set only when user explicitly names a lifecycle state; "
    "valid: draft|active|stale|contradicted|archived)\n"
    "  IMPORTANT: 'Activate/Archive/Restore a/an <state> page' is ALWAYS a lifecycle action, never a question.\n"
    "  Examples: 'Activate a draft page' → lifecycle_activate, state_filter='draft'\n"
    "            'Archive a stale page'  → lifecycle_archive,  state_filter='stale'\n"
    "            'Restore an archived page' → lifecycle_restore, state_filter='archived'\n"
    "            'Archive the alan-turing page' → lifecycle_archive, slug='alan-turing'\n"
    "  job_list      : status_filter (list of pending|running|completed|failed|dead|skipped, or null) —\n"
    "                  use for 'list jobs', 'show failed jobs', 'show failed and skipped jobs'.\n"
    "                  Set status_filter to a JSON array when user names one or more states, e.g.\n"
    "                  'failed jobs' → [\"failed\"], 'failed and skipped' → [\"failed\",\"skipped\"].\n"
    "                  Use null for 'all jobs'.\n"
    "  job_status    : job_id (string or null) — use for 'show job status', 'check job <id>',\n"
    "                  'what is the status of my last job'. Resolve job_id from history when the user\n"
    "                  says 'the last job', 'that job', or picks a number from a previous list.\n"
    "                  Leave job_id null when no specific job is mentioned.\n"
    "  none          : (no params)\n\n"
    "Cron parsing: 'daily at 6am'='0 6 * * *', 'every Sunday at 7pm'='0 19 * * 0', "
    "'every weekday at 9am'='0 9 * * 1-5', 'every hour'='0 * * * *'\n\n"
    "Repeat intents: if the user says 'run it again', 'do it again', 'again', 'repeat', "
    "'try again', 'once more', 'do that', 'redo' etc. — look at the conversation history "
    "to identify the last action performed and return that same action with the same params. "
    "If you cannot determine the previous action from history, return action='none'.\n\n"
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
    needs_clarification: bool = False
    clarify_prompt: str = ""
    clarify_candidates: list[str] = field(default_factory=list)


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

    def detect(self, question: str, history: list[dict] | None = None) -> bool:
        """Fast regex pre-check — True if question looks like an action request.

        Also returns True when a recent assistant turn was a clarify (stored with
        CLARIFY_STORE_PREFIX), so chip replies route back to the action agent
        even after one or more answers have been appended to the history.
        """
        if _ACTION_RE.search(question):
            return True
        if history and _REPEAT_RE.search(question):
            # "run it again" / "repeat" / "again" — route to action agent so the
            # LLM can look at history and re-run the previous action.
            return True
        if history:
            lookback = (
                self._orch._cfg.chat.clarify_lookback
                if self._orch is not None and hasattr(self._orch, "_cfg")
                else 5
            )
            checked = 0
            for msg in reversed(history):
                if msg.get("role") == "assistant":
                    if msg.get("content", "").startswith(CLARIFY_STORE_PREFIX):
                        return True
                    checked += 1
                    if checked >= lookback:
                        break
        return False

    async def run(self, question: str, history: list[dict] | None = None) -> Optional[ActionResult]:
        """Extract action + params from question and execute. Returns None if not an action."""
        # For repeat intents ("run it again", "repeat", etc.) resolve the previous action
        # from history before calling the LLM, which cannot reliably infer it from vague phrasing.
        effective_question = question
        if _REPEAT_RE.search(question) and history:
            for msg in reversed(history):
                if msg.get("role") == "user" and _ACTION_RE.search(msg.get("content", "")):
                    effective_question = msg["content"]
                    break
        extraction = await self._extract(effective_question, history=history or [])
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

    async def _extract(self, question: str, history: list[dict] | None = None) -> Optional[dict]:
        history_block = ""
        if history:
            lines = "\n".join(f"{m['role'].capitalize()}: {m['content']}" for m in history)
            history_block = (
                f"\nConversation history (use to resolve references like '1', '2', page names, "
                f"or to identify the last action when the user says 'again' / 'repeat'):\n"
                f"{lines}\n"
            )
        prompt = _EXTRACT_PROMPT_TEMPLATE.format(question=question) + history_block
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
        if action == "lint_report":
            return await self._do_lint_report(params)
        if action == "wiki_status":
            return await self._do_wiki_status()
        if action == "ingest":
            return await self._do_ingest(params)
        if action == "scaffold":
            return await self._do_scaffold(params)
        if action == "schedule_add":
            return self._do_schedule_add(params)
        if action == "schedule_list":
            return self._do_schedule_list()
        if action == "schedule_history":
            return await self._do_schedule_history()
        if action in ("lifecycle_activate", "lifecycle_archive", "lifecycle_restore"):
            return await self._do_lifecycle(action, params)
        if action == "job_list":
            return await self._do_job_list(params)
        if action == "job_status":
            return await self._do_job_status(params)
        return ActionResult(action_type=action, success=False,
                            message=f"Unknown action type: `{action}`")

    async def _do_lint_report(self, params: dict | None = None) -> ActionResult:
        from synthadoc.agents.lint_agent import LintFocus, read_current_lint_state
        state = read_current_lint_state(self._orch._store)
        focus = (params or {}).get("focus") or None
        parts: list[str] = []

        if focus in (None, LintFocus.CONTRADICTED):
            if state.contradicted:
                lines = [
                    f"**Contradicted pages ({len(state.contradicted)})** — "
                    f"resolve conflict and set `status: active`:\n"
                ]
                for slug in state.contradicted:
                    lines.append(f"- `{slug}`")
                parts.append("\n".join(lines))
            elif focus == LintFocus.CONTRADICTED:
                parts.append("**Contradicted pages (0)** — no contradictions found.")

        if focus in (None, LintFocus.ORPHANS):
            if state.orphans:
                lines = [f"**Orphan pages ({len(state.orphans)})** — no inbound links:\n"]
                for slug in state.orphans:
                    lines.append(f"- `{slug}`")
                parts.append("\n".join(lines))
            else:
                parts.append("**Orphan pages (0)** — all pages have at least one inbound link.")

        if focus in (None, LintFocus.ADVERSARIAL):
            if state.adv_pages:
                total = sum(len(p["warnings"]) for p in state.adv_pages)
                lines = [
                    f"**Adversarial warnings** ({total} across {len(state.adv_pages)} pages):\n"
                ]
                for entry in state.adv_pages:
                    lines.append(f"- `{entry['slug']}`:")
                    for w in entry["warnings"]:
                        claim = w.get("claim") or ""
                        concern = w.get("concern") or ""
                        if claim:
                            lines.append(f'  - "{claim}" — {concern}')
                        else:
                            lines.append(f"  - {concern}")
                parts.append("\n".join(lines))
            elif focus == LintFocus.ADVERSARIAL:
                parts.append("**Adversarial warnings (0)** — no adversarial warnings found.")

        if focus in (None, LintFocus.TRUNCATED):
            if state.truncated_pages:
                lines = [
                    f"**Truncated sources ({len(state.truncated_pages)})** — "
                    f"source exceeded max_source_chars at ingest time:\n"
                ]
                for entry in state.truncated_pages:
                    lines.append(
                        f"- `{entry['slug']}` ← `{entry['file']}` ({entry['size']:,} chars)"
                    )
                parts.append("\n".join(lines))
            elif focus == LintFocus.TRUNCATED:
                parts.append("**Truncated sources (0)** — no sources were truncated.")

        _any_issues = bool(
            state.contradicted or state.orphans or state.adv_pages or state.truncated_pages
        )
        if not _any_issues:
            message = _MSG_LINT_ALL_CLEAR
        else:
            message = "\n\n".join(parts)
        return ActionResult(action_type="lint_report", success=True, message=message)

    async def _do_wiki_status(self) -> ActionResult:
        from synthadoc.storage.log import AuditDB
        from synthadoc.storage.wiki import LifecycleState
        audit_path = self._wiki_root / ".synthadoc" / "audit.db"
        if not audit_path.exists():
            total = len(self._orch._store.list_pages())
            return ActionResult(
                action_type="wiki_status",
                success=True,
                message=(
                    f"**Wiki status** — {total} page{'s' if total != 1 else ''} total\n\n"
                    + _MSG_NO_LIFECYCLE_DATA
                ),
            )
        from synthadoc.agents.lint_agent import LINT_SKIP_SLUGS
        audit = AuditDB(audit_path)
        await audit.init()
        counts = await audit.get_lifecycle_summary()
        all_pages = [s for s in self._orch._store.list_pages() if s not in LINT_SKIP_SLUGS]
        total = len(all_pages)
        unlinted = total - sum(counts.values())
        if unlinted > 0:
            counts["unlinted"] = unlinted
        state_order = [
            LifecycleState.DRAFT,
            LifecycleState.ACTIVE,
            LifecycleState.STALE,
            LifecycleState.CONTRADICTED,
            LifecycleState.ARCHIVED,
        ]
        _NOTES = {
            LifecycleState.DRAFT:        "awaiting lint review",
            LifecycleState.ACTIVE:       "published, included in queries and exports",
            LifecycleState.STALE:        "source changed — re-ingest to refresh",
            LifecycleState.CONTRADICTED: "conflicting sources — manual review required",
            LifecycleState.ARCHIVED:     "excluded from queries and exports",
            "unlinted":                  "never linted — run `synthadoc lint run`",
        }
        lines = [f"**Wiki status** — {total} page{'s' if total != 1 else ''} total\n",
                 "| State | Count | Note |", "|---|---|---|"]
        for state in state_order:
            n = counts.get(state, 0)
            lines.append(f"| {state} | {n} | {_NOTES[state]} |")
        if unlinted > 0:
            lines.append(f"| unlinted | {unlinted} | {_NOTES['unlinted']} |")
        return ActionResult(action_type="wiki_status", success=True, message="\n".join(lines))

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
                                message=_MSG_NO_INGEST_SOURCE)
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
        # Normalise known ops that require a subcommand: "lint" → "lint run"
        if op.strip() == "lint":
            op = "lint run"
        cron = (params.get("cron") or "").strip()
        if not cron:
            return ActionResult(
                action_type="schedule_add",
                success=False,
                needs_clarification=True,
                clarify_prompt=_SCHEDULE_CRON_PROMPT,
                clarify_candidates=[],
                message=_SCHEDULE_CRON_PROMPT,
            )
        desc = params.get("schedule_description", cron)
        if not op:
            return ActionResult(action_type="schedule_add", success=False,
                                message=_MSG_NO_SCHEDULE_PARAMS)
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

    async def _do_schedule_history(self) -> ActionResult:
        from synthadoc.storage.log import AuditDB
        audit_path = self._wiki_root / ".synthadoc" / "audit.db"
        if not audit_path.exists():
            return ActionResult(
                action_type="schedule_history",
                success=True,
                message=_MSG_NO_SCHEDULE_HISTORY,
            )
        audit = AuditDB(audit_path)
        await audit.init()
        runs = await audit.list_scheduled_runs(limit=20)
        if not runs:
            return ActionResult(
                action_type="schedule_history",
                success=True,
                message=_MSG_NO_SCHEDULE_HISTORY,
            )
        lines = [
            "**Recent scheduled runs:**\n",
            "| Run ID | Op | Started | Duration | Status |",
            "|---|---|---|---|---|",
        ]
        for r in runs:
            started = (r.get("started_at") or "")[:16].replace("T", " ")
            dur = f"{r['duration_s']:.1f}s" if r.get("duration_s") is not None else "—"
            status = r.get("status") or "—"
            err = r.get("error") or ""
            if status == "failed" and err:
                status_cell = f"❌ {err[:60]}"
            elif status == "success":
                status_cell = "✅"
            else:
                status_cell = status
            lines.append(
                f"| `{r['run_id']}` | `{r['op']}` | {started} | {dur} | {status_cell} |"
            )
        return ActionResult(action_type="schedule_history", success=True, message="\n".join(lines))

    async def _do_lifecycle(self, action: str, params: dict) -> ActionResult:
        from synthadoc.storage.log import AuditDB

        slug = (params.get("slug") or "").strip()
        reason = (params.get("reason") or "requested via chat").strip() or "requested via chat"

        if not slug:
            state_filter_str = (params.get("state_filter") or "").strip().lower()
            source_states = _SOURCE_STATES[action]
            filtered_state = _STATE_FILTER_MAP.get(state_filter_str)
            if filtered_state is not None and filtered_state in source_states:
                source_states = [filtered_state]

            all_candidates = sorted(
                s for s in self._orch._store.list_pages()
                if (pg := self._orch._store.read_page(s)) and pg.status in source_states
            )

            if not all_candidates:
                if filtered_state is not None:
                    return ActionResult(
                        action_type=action, success=False,
                        message=(
                            f"There are no **{state_filter_str}** pages to {_VERB[action]}. "
                            f"Run `synthadoc lint run` to update lifecycle states."
                        ),
                    )
                return ActionResult(action_type=action, success=False,
                                    message=_MSG_NO_LIFECYCLE_CANDIDATES)

            overflow = len(all_candidates) - _MAX_CLARIFY_CANDIDATES
            candidates = all_candidates[:_MAX_CLARIFY_CANDIDATES]

            article = "an" if state_filter_str[:1].lower() in "aeiou" else "a"
            state_label = f"{article} {state_filter_str} " if filtered_state is not None else "a "
            overflow_note = (
                f" ({_MAX_CLARIFY_CANDIDATES} of {len(all_candidates)} shown —"
                f" type a name if yours is not listed)"
                if overflow > 0 else ""
            )
            prompt = (
                f"Select {state_label}page to {_VERB[action]} below, "
                f"or type a name or number in the box above.{overflow_note}"
            )
            return ActionResult(
                action_type=action,
                success=False,
                needs_clarification=True,
                clarify_prompt=prompt,
                clarify_candidates=candidates,
                message=prompt,
            )

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

    # ── job helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _fmt_job_ts(ts: str | None) -> str:
        from datetime import datetime, timezone
        if not ts:
            return "—"
        try:
            dt = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
            return dt.astimezone().strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return ts

    async def _fetch_jobs(self):
        return await self._orch.queue.list_jobs()

    async def _do_job_list(self, params: dict | None = None) -> ActionResult:
        from synthadoc.core.queue import JobStatus
        raw_filter = (params or {}).get("status_filter")
        if isinstance(raw_filter, str):
            raw_filter = [raw_filter]
        statuses: list[JobStatus] | None = None
        if raw_filter:
            statuses = [JobStatus(s) for s in raw_filter if s in JobStatus._value2member_map_]
        jobs = await self._orch.queue.list_jobs(status=statuses or None)
        label = "/".join(s.value for s in statuses) + " " if statuses else ""
        if not jobs:
            return ActionResult(action_type="job_list", success=True,
                                message=f"No {label}jobs found.")
        has_errors = any(j.error for j in jobs)
        if has_errors:
            lines = ["| ID | Operation | Status | Started | Error |", "|---|---|---|---|---|"]
            for j in jobs:
                err = (j.error or "").replace("|", "\\|")
                lines.append(
                    f"| `{j.id}` | {j.operation} | {j.status}"
                    f" | {self._fmt_job_ts(str(j.created_at))} | {err} |"
                )
        else:
            lines = ["| ID | Operation | Status | Started |", "|---|---|---|---|"]
            for j in jobs:
                lines.append(
                    f"| `{j.id}` | {j.operation} | {j.status} | {self._fmt_job_ts(str(j.created_at))} |"
                )
        return ActionResult(action_type="job_list", success=True,
                            message="\n".join(lines))

    async def _do_job_status(self, params: dict) -> ActionResult:
        job_id = (params.get("job_id") or "").strip()
        jobs = await self._fetch_jobs()
        if not jobs:
            return ActionResult(action_type="job_status", success=True,
                                message="No jobs found.")

        if job_id:
            job = next((j for j in jobs if j.id == job_id), None)
            if not job:
                return ActionResult(action_type="job_status", success=False,
                                    message=f"Job `{job_id}` not found.")
            lines = [
                f"**Job `{job.id}`**\n",
                f"- **Operation:** {job.operation}",
                f"- **Status:** {job.status}",
                f"- **Started:** {self._fmt_job_ts(str(job.created_at))}",
            ]
            if job.error:
                lines.append(f"- **Error:** {job.error}")
            result = job.result or {}
            if result.get("pages_created"):
                lines.append(f"- **Pages created:** {', '.join(f'`{p}`' for p in result['pages_created'])}")
            if result.get("pages_updated"):
                lines.append(f"- **Pages updated:** {', '.join(f'`{p}`' for p in result['pages_updated'])}")
            if result.get("pages_flagged"):
                lines.append(f"- **Pages flagged:** {', '.join(f'`{p}`' for p in result['pages_flagged'])}")
            if result.get("tokens_used"):
                lines.append(f"- **Tokens used:** {result['tokens_used']}")
            return ActionResult(action_type="job_status", success=True,
                                message="\n".join(lines))

        # No job_id — show table and ask which one
        table_lines = ["| ID | Operation | Status | Started |", "|---|---|---|---|"]
        candidates: list[str] = []
        for j in jobs:
            table_lines.append(
                f"| `{j.id}` | {j.operation} | {j.status} | {self._fmt_job_ts(str(j.created_at))} |"
            )
            candidates.append(j.id)
        prompt = "Which job would you like to see the status for?"
        message = "\n".join(table_lines) + f"\n\n{prompt}"
        return ActionResult(
            action_type="job_status",
            success=False,
            needs_clarification=True,
            clarify_prompt=prompt,
            clarify_candidates=candidates[:_MAX_CLARIFY_CANDIDATES],
            message=message,
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
