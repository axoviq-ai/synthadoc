# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from synthadoc.agents._utils import parse_json_string_array
from synthadoc.agents.action_agent import ActionAgent
from synthadoc.agents.hint_engine import HintEngine, SessionMode
from synthadoc.agents.rewrite_agent import RewriteAgent
from synthadoc.agents.search_decompose_agent import SearchDecomposeAgent
from synthadoc.providers.base import LLMProvider, Message
from synthadoc.storage.log import AuditDB
from synthadoc.storage.search import HybridSearch, SearchResult
from synthadoc.storage.wiki import WikiStorage

logger = logging.getLogger(__name__)

_MAX_SUB_QUESTIONS = 4
_MIN_TERM_FREQ = 2

# ── bundled system knowledge (answers Synthadoc product questions) ────────────
_KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"


@dataclass
class _SystemPage:
    keywords: list[str]
    title: str
    content: str


def _load_system_knowledge() -> list[_SystemPage]:
    """Load bundled knowledge pages from synthadoc/knowledge/ once at import."""
    pages: list[_SystemPage] = []
    if not _KNOWLEDGE_DIR.exists():
        return pages
    for md_file in sorted(_KNOWLEDGE_DIR.glob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
            keywords: list[str] = []
            title = md_file.stem
            content = text
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    fm = parts[1]
                    content = parts[2].strip()
                    for line in fm.splitlines():
                        if line.startswith("title:"):
                            title = line[6:].strip()
                        elif line.startswith("keywords:"):
                            kw_raw = line[9:].strip()
                            if kw_raw.startswith("["):
                                keywords = [
                                    k.strip().strip("\"'")
                                    for k in kw_raw.strip("[]").split(",")
                                    if k.strip()
                                ]
            pages.append(_SystemPage(keywords=keywords, title=title, content=content))
        except Exception as exc:
            logger.warning("system knowledge: could not load %s (%s)", md_file, exc)
    return pages


_SYSTEM_KNOWLEDGE: list[_SystemPage] = _load_system_knowledge()
_MAX_QUESTION_CHARS = 4000


def _history_block(history: list[dict]) -> str:
    """Format conversation history as a preamble block for the synthesis prompt."""
    if not history:
        return ""
    lines = "\n".join(f"{m['role'].capitalize()}: {m['content']}" for m in history)
    return f"\n[Conversation so far]\n{lines}\n"

# Stopwords excluded when extracting key terms for the content-overlap gap check.
# Keep this list lean — a false positive (treating a content word as a stopword)
# suppresses gap detection; a false negative (missing a stopword) is harmless.
_STOPWORDS = frozenset({
    "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
    "should", "would", "could", "will", "does", "have", "with", "that", "this",
    "they", "them", "their", "there", "then", "than", "also", "well", "just",
    "some", "more", "very", "much", "many", "most", "from", "into", "onto",
    "about", "after", "before", "between", "during", "through",
    "these", "those", "each", "both", "your", "mine", "ours",
    "start", "grow", "good", "best", "make", "need", "want",
    # Relational verbs/nouns used in queries to describe how topics connect
    # ("how did X shape Y?", "what drove Z?", "Unix's influence on...") but
    # never recurring content words in wiki pages — spurious signal gaps result.
    # CJK queries bypass key-term extraction entirely, so these are English-only.
    "shape", "drive", "change", "enable", "allow", "improve", "evolve",
    "influence", "affect", "impact", "cause", "result", "matter", "relate",
    "connect", "involve", "emerge", "remain",
    # Contribution/achievement verbs common in biographical queries
    # ("What did X contribute to Y?", "What did X achieve?") — wiki pages
    # describe actions with specific verbs ("invented", "built") instead.
    "contribute", "achieve", "accomplish", "pioneer", "introduce",
    # Meta-wiki query words: "What topics does this wiki cover?" — "topic" and
    # "cover" describe the wiki's own structure, not page content, so they never
    # appear frequently in pages and always trigger false-positive gap detection.
    "topic", "cover", "scope", "about",
})


@dataclass
class QueryResult:
    question: str
    answer: str
    citations: list[str]
    tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    knowledge_gap: bool = False
    suggested_searches: list[str] = field(default_factory=list)
    sub_questions_count: int = 0
    cacheable: bool = True  # False for action results and live-data answers


# Keywords that indicate the question is asking about live wiki state
_LIVE_DATA_TRIGGERS: frozenset[str] = frozenset({
    "stale", "archived", "archive", "draft", "active", "contradicted",
    "contradictions", "contradiction", "review", "lifecycle", "lifecycle state",
    "pages marked", "which pages", "how many pages", "page count",
    "changed", "this week", "recently", "recent changes", "what's new",
    "whats new", "updated", "new pages", "added", "last week", "past week",
    "this month", "last month", "past month", "this year", "last year", "past year",
    "adversarial", "adversarial warning", "flagged", "overstated", "claim concern",
    "lint warning", "warnings",
    "job", "jobs", "job id", "job status", "ingest job", "queue",
    "pending jobs", "failed job", "dead job",
})

_RECENT_CHANGE_TRIGGERS: frozenset[str] = frozenset({
    "changed", "this week", "recently", "recent changes", "what's new",
    "whats new", "updated", "new pages", "added", "last week", "past week",
    "this month", "last month", "past month", "this year", "last year", "past year",
})

_ADVERSARIAL_TRIGGERS: frozenset[str] = frozenset({
    "adversarial", "adversarial warning", "flagged", "overstated", "claim concern",
    "lint warning", "warnings",
})

_JOB_TRIGGERS: frozenset[str] = frozenset({
    "job", "jobs", "job id", "job status", "ingest job", "queue",
    "pending jobs", "failed job", "dead job",
})

# Phrase fragments that identify meta/introspective questions about the wiki's own
# content or scope ("What topics does this wiki cover?"). These can never be gaps:
# the answer is precisely the retrieved wiki pages. Gap detection would fire here
# because all content words (topic, cover, scope, wiki) are either stopwords or
# too short, leaving _key_terms empty and candidates < 3 (signal 1 fires).
# CLI subcommands — if the question starts with "synthadoc <subcommand>" or
# contains known CLI patterns, treat it as a system knowledge query and suppress
# gap. This prevents wiki-miss false positives when users paste CLI commands.
_SYNTHADOC_CLI_SUBCOMMANDS: frozenset[str] = frozenset({
    "synthadoc ingest", "synthadoc jobs", "synthadoc job",
    "synthadoc lifecycle", "synthadoc lint", "synthadoc status",
    "synthadoc export", "synthadoc candidates", "synthadoc web",
    "synthadoc query", "synthadoc config",
})

_WIKI_INTROSPECTIVE_TRIGGERS: frozenset[str] = frozenset({
    "what topics",
    "what subject",
    "what does this wiki",
    "what's in this wiki",
    "whats in this wiki",
    "what is in this wiki",
    "what does my wiki",
    "what does your wiki",
    "what pages",
    "wiki cover",
    "wiki contain",
    "wiki includ",
    "wiki know about",
    "topics covered",
    "subjects covered",
    "this wiki cover",
    "this wiki know",
    "this wiki includ",
    "this wiki contain",
})

# ── Hints used in _fetch_live_wiki_data for lifecycle state display ────────────
_HINTS: dict[str, str] = {
    "draft":        "← run `synthadoc lint run` to promote",
    "stale":        "← re-ingest needed",
    "contradicted": "← review required",
}


def _is_introspective(question: str) -> bool:
    """Return True when a question asks about the wiki's own content or scope,
    or is a Synthadoc CLI invocation — both should suppress gap detection."""
    q = question.lower()
    return any(t in q for t in _WIKI_INTROSPECTIVE_TRIGGERS) or any(
        q.startswith(c) for c in _SYNTHADOC_CLI_SUBCOMMANDS
    )


def _parse_lookback_days(question: str) -> int:
    """Return a lookback window in days parsed from natural language time phrases.

    Recognises "last N months/weeks", month/year keywords, and falls back to 7 days
    (one week) for bare "recently", "this week", "last week", etc.
    """
    q = question.lower()
    m = re.search(r'(?:last|past)\s+(\d+)\s+months?', q)
    if m:
        return int(m.group(1)) * 30
    m = re.search(r'(?:last|past)\s+(\d+)\s+weeks?', q)
    if m:
        return int(m.group(1)) * 7
    if any(kw in q for kw in ("this year", "last year", "past year")):
        return 365
    if any(kw in q for kw in ("this month", "last month", "past month")):
        return 30
    return 7  # week / recently / default


class QueryAgent:
    def __init__(self, provider: LLMProvider, store: WikiStorage,
                 search: HybridSearch, top_n: int = 8,
                 gap_score_threshold: float = 2.0,
                 routing_path: Path | None = None,
                 orchestrator: object | None = None,
                 max_tokens: int = 8192) -> None:
        self._provider = provider
        self._store = store
        self._search = search
        self._top_n = top_n
        self._gap_score_threshold = gap_score_threshold
        self._orchestrator = orchestrator
        self._max_tokens = max_tokens
        self._routing = None
        if routing_path:
            from synthadoc.core.routing import RoutingIndex
            self._routing = RoutingIndex.parse(routing_path)

    async def _routing_branch_pick(self, question: str) -> list[str]:
        """Ask LLM to select top 1-2 branch names from ROUTING.md relevant to question."""
        if not self._routing or not self._routing.branches:
            return []
        from synthadoc.agents._routing import pick_routing_branches
        return await pick_routing_branches(
            self._provider, self._routing.branches,
            f"Question: {question}", multi=True,
        )

    @staticmethod
    def _get_relevant_system_pages(question: str) -> str:
        """Return formatted system knowledge pages whose keywords match the question.

        CLI command prefix ("synthadoc <subcommand>") is treated as an implicit
        system-knowledge match — all bundled pages are included so the LLM has
        full context for the command being asked about.
        """
        q_lower = question.lower()
        matched: list[str] = []
        for page in _SYSTEM_KNOWLEDGE:
            # Use ASCII-only boundaries so English keywords adjacent to CJK characters
            # (e.g. "调度器scheduler") still match — Unicode \b treats CJK as word chars.
            if any(re.search(r'(?<![a-zA-Z0-9])' + re.escape(kw) + r'(?![a-zA-Z0-9])',
                             q_lower) for kw in page.keywords):
                matched.append(f"### {page.title}\n{page.content}")
        # If no keyword matched but question looks like a CLI invocation, include
        # all system pages so the LLM can answer from bundled documentation.
        if not matched and any(cmd in q_lower for cmd in _SYNTHADOC_CLI_SUBCOMMANDS):
            matched = [f"### {p.title}\n{p.content}" for p in _SYSTEM_KNOWLEDGE]
        return "\n\n".join(matched)

    async def _fetch_live_wiki_data(self, question: str) -> str:
        """Return a formatted snapshot of live wiki lifecycle data if the question asks for it.

        Queries AuditDB directly — no HTTP round-trip. Returns empty string if the DB
        does not exist yet (fresh install before first ingest).
        """
        q_lower = question.lower()
        if not any(kw in q_lower for kw in _LIVE_DATA_TRIGGERS):
            return ""

        audit_path = self._store._root.parent / ".synthadoc" / "audit.db"
        if not audit_path.exists():
            return ""

        try:
            audit = AuditDB(audit_path)
            await audit.init()
            counts: dict[str, int] = await audit.get_lifecycle_summary()

            lines: list[str] = []

            if counts:
                lines.append("### Current page counts")
                for state in ("active", "draft", "stale", "contradicted", "archived"):
                    n = counts.get(state, 0)
                    hint = f"  {_HINTS[state]}" if state in _HINTS and n > 0 else ""
                    lines.append(f"  {state:<14} {n}{hint}")

                # For specific state questions, list the actual page slugs
                detected_state: str | None = None
                for state in ("stale", "archived", "draft", "contradicted", "active"):
                    if state in q_lower or (state == "contradicted" and "contradiction" in q_lower):
                        detected_state = state
                        break

                if detected_state:
                    all_pages = await audit.get_all_page_states()
                    matching = [p for p in all_pages if p["state"] == detected_state]
                    if matching:
                        lines.append(f"\n### Pages currently marked '{detected_state}'")
                        for p in matching:
                            ts = p.get("updated_at", "")[:10]
                            lines.append(f"  - {p['slug']}  (since {ts})" if ts else f"  - {p['slug']}")
                    else:
                        lines.append(f"\n### Pages currently marked '{detected_state}'\n  (none)")

            # Adversarial warnings — read directly from page frontmatter
            if any(kw in q_lower for kw in _ADVERSARIAL_TRIGGERS):
                warned: list[tuple[str, int]] = []
                for slug in self._store.list_pages():
                    page = self._store.read_page(slug)
                    if page and page.lint_warnings:
                        warned.append((slug, len(page.lint_warnings)))
                warned.sort(key=lambda x: x[1], reverse=True)
                if warned:
                    lines.append("\n### Pages with adversarial warnings")
                    for slug, n in warned:
                        lines.append(f"  - [[{slug}]]  ({n} warning{'s' if n != 1 else ''})")
                else:
                    lines.append("\n### Pages with adversarial warnings\n  (none — run `synthadoc lint run` to check)")

            # Recent ingest history when question asks about changes/updates
            if any(kw in q_lower for kw in _RECENT_CHANGE_TRIGGERS):
                _days = _parse_lookback_days(question)
                _window_label = (
                    f"{_days // 365} year{'s' if _days // 365 > 1 else ''}" if _days >= 365
                    else f"{_days // 30} month{'s' if _days // 30 > 1 else ''}" if _days >= 30
                    else f"{_days} day{'s' if _days > 1 else ''}"
                )
                recent = await audit.list_ingests_since(days=_days)
                if recent:
                    lines.append(f"\n### Pages ingested or updated in the last {_window_label}")
                    seen: set[str] = set()
                    for r in recent:
                        slug = r.get("wiki_page") or ""
                        src = r.get("source_path") or ""
                        date = (r.get("ingested_at") or "")[:10]
                        if slug and slug not in seen:
                            seen.add(slug)
                            lines.append(f"  - [[{slug}]]  (from {src}, {date})" if src else f"  - [[{slug}]]  ({date})")
                else:
                    lines.append(f"\n### Pages ingested or updated in the last {_window_label}\n  (none)")

            # Job status — detect a specific 8-char hex job ID or list recent jobs
            if any(kw in q_lower for kw in _JOB_TRIGGERS) and self._orchestrator is not None:
                _queue = self._orchestrator._queue
                _job_id_match = re.search(r'\b([0-9a-f]{8})\b', q_lower)
                if _job_id_match:
                    _job_id = _job_id_match.group(1)
                    _job = await _queue.get_job(_job_id)
                    if _job:
                        lines.append(f"\n### Job {_job_id}")
                        lines.append(f"  operation : {_job.operation}")
                        lines.append(f"  status    : {_job.status.value}")
                        lines.append(f"  retries   : {_job.retries}")
                        if _job.error:
                            lines.append(f"  error     : {_job.error}")
                        if _job.created_at:
                            lines.append(f"  created   : {(_job.created_at or '')[:19]}")
                    else:
                        lines.append(f"\n### Job {_job_id}\n  (not found)")
                else:
                    _recent_jobs = await _queue.list_jobs(order="desc")
                    if _recent_jobs:
                        lines.append("\n### Recent jobs")
                        for _j in _recent_jobs[:10]:
                            _ts = (_j.created_at or "")[:10]
                            _err = f"  — {_j.error}" if _j.error else ""
                            lines.append(f"  - [{_j.id}] {_j.operation}  {_j.status.value}  {_ts}{_err}")
                    else:
                        lines.append("\n### Jobs\n  (no jobs found)")

            return "\n".join(lines) if lines else ""
        except Exception as exc:
            logger.debug("live wiki data fetch failed: %s", exc)
            return ""

    def _build_synthesis_prompt(
        self,
        question: str,
        context: str,
        *,
        gap: bool,
        system_ctx: str,
        is_live_data: bool,
        gap_sentinel: bool = False,
        history: list[dict] | None = None,
    ) -> str:
        """Build the LLM synthesis prompt. gap_sentinel=True adds the [GAP] marker
        instruction used by run() for post-synthesis gap override; run_stream() omits it.
        When history is provided it is prepended as a conversation context block."""
        prefix = _history_block(history) if history else ""
        if gap:
            return prefix + (
                f"The wiki does not yet have a page on this topic. "
                f"Answer the question using your general knowledge, then note in one sentence "
                f"that the wiki does not currently cover this topic and suggest the user enriches it.\n\n"
                f"Question: {question}\n\n"
                f"Wiki pages available (unrelated to this question):\n{context}"
            )
        if system_ctx:
            return prefix + (
                f"Answer the question using the Synthadoc Help documentation and Live Wiki Data below. "
                f"If Live Wiki Data is present, use it to give concrete, specific answers "
                f"(e.g. list the actual page names, show real counts). "
                f"Present every CLI command in a fenced code block, exactly as it appears in the documentation. "
                f"Angle-bracket placeholders like <schedule-id> or <slug> are literal CLI arguments — "
                f"copy them verbatim, do not omit or paraphrase them. "
                f"Keep the answer concise; do not add a verification or troubleshooting section. "
                f"Do not reference or cite wiki pages.\n\n"
                f"Question: {question}\n\nDocumentation:\n{context}"
            )
        if is_live_data:
            return prefix + (
                f"Answer using the Live Wiki Data below. "
                f"The data is fetched directly from Synthadoc's audit log and page state database — "
                f"give specific, concrete answers using the actual page names, dates, and counts shown. "
                f"Do not reference or cite wiki page content.\n\n"
                f"Question: {question}\n\nData:\n{context}"
            )
        gap_instruction = (
            "If the pages do not contain enough information to answer the question, "
            "start your response with exactly '[GAP]' on its own line, then explain what's missing.\n\n"
        ) if gap_sentinel else ""
        return prefix + (
            f"Answer using ONLY these wiki pages. Cite with [[PageTitle]].\n"
            f"Extract and include all specific facts from the pages — dates, years, numbers, and names — "
            f"even when they appear briefly or in passing. Do not claim a fact is absent unless it is "
            f"genuinely missing from every page below.\n\n"
            f"{gap_instruction}"
            f"Question: {question}\n\nPages:\n{context}"
        )

    def _load_purpose_context(self) -> str:
        """Return purpose.md as a pinned preamble for synthesis, or '' if absent."""
        page = self._store.read_page("purpose")
        if not page:
            return ""
        return f"### Wiki Scope (purpose.md)\n{page.content[:12000]}"

    def _expand_aliases(self, question: str) -> str:
        """Replace alias matches in question with canonical slug names."""
        alias_map: dict[str, str] = {}
        for slug in self._store.list_pages():
            page = self._store.read_page(slug)
            if page and page.aliases:
                for alias in page.aliases:
                    alias_map[alias.lower()] = slug
        if not alias_map:
            return question
        q = question
        for alias, slug in sorted(alias_map.items(), key=lambda x: -len(x[0])):
            q = re.sub(re.escape(alias), slug, q, flags=re.IGNORECASE)
        return q

    async def decompose(self, question: str) -> list[str]:
        """Break a question into focused sub-questions for independent retrieval.

        Returns [question] on any failure so callers always get a usable list.
        """
        truncated = question[:_MAX_QUESTION_CHARS]
        try:
            resp = await self._provider.complete(
                messages=[Message(role="user",
                    content=(
                        f"Break this question into focused sub-questions for a knowledge base lookup.\n"
                        f"Simple questions should return a single-element list.\n"
                        f"Return a JSON array of strings only. No explanation.\n\n"
                        f"Question: {truncated}"
                    ))],
                temperature=0.0,
            )
        except Exception as exc:
            logger.warning(
                "decompose failed (%s: %s) — falling back to original question",
                type(exc).__name__, exc,
            )
            return [question]
        filtered = parse_json_string_array(resp.text, _MAX_SUB_QUESTIONS)
        if filtered:
            if len(filtered) == 1:
                logger.info("query is simple — no decomposition (1 sub-question)")
            else:
                logger.info(
                    "query decomposed into %d sub-question(s): %s",
                    len(filtered),
                    " | ".join(f'"{q}"' for q in filtered),
                )
            return filtered
        logger.warning(
            "decompose: response was not a valid JSON array — falling back to original question"
        )
        return [question]

    async def _run_search(self, question: str) -> tuple[list[str], list[SearchResult]]:
        """Decompose question, apply routing scope, run parallel BM25 search.

        Returns (sub_questions, candidates).
        """
        sub_questions = await self.decompose(question)

        scoped_slugs: list[str] | None = None
        if self._routing:
            branches = await self._routing_branch_pick(question)
            if branches:
                scoped_slugs = self._routing.slugs_for_branches(branches)

        async def _search_one(sub_q: str):
            return await self._search.hybrid_search(
                sub_q.lower().split(), top_n=self._top_n, scoped_slugs=scoped_slugs
            )

        results_per_sub = await asyncio.gather(*[_search_one(q) for q in sub_questions])
        best: dict[str, SearchResult] = {}
        for results in results_per_sub:
            for r in results:
                if r.slug not in best or r.score > best[r.slug].score:
                    best[r.slug] = r
        candidates = sorted(best.values(), key=lambda r: r.score, reverse=True)[:self._top_n]
        return sub_questions, candidates

    async def query(self, question: str) -> QueryResult:
        question = self._expand_aliases(question)

        # Action pre-flight: if orchestrator is available and question is an action, dispatch it
        if self._orchestrator is not None:
            _action_agent = ActionAgent(self._provider, self._orchestrator,
                                        self._store._root.parent)
            if _action_agent.detect(question):
                _result = await _action_agent.run(question)
                if _result is not None:
                    return QueryResult(
                        question=question,
                        answer=_result.message,
                        citations=[],
                        knowledge_gap=not _result.success,
                        cacheable=False,
                    )

        sub_questions, candidates = await self._run_search(question)

        _max_score = max((r.score for r in candidates), default=0.0)
        # Use sub-questions for gap detection: decomposition strips request framing
        # ("please provide details of X") so key terms reflect the actual topic, not
        # the phrasing. Falls back to the original question if decomposition returned it.
        _gap_q = " ".join(sub_questions) if sub_questions else question
        _gap, _discriminating_term, _pages_with_overlap, _min_specific_qualifying = \
            self._detect_gap(_gap_q, candidates, _max_score)
        _system_ctx = self._get_relevant_system_pages(question)
        _live_data = await self._fetch_live_wiki_data(question)
        if _system_ctx or _live_data:
            _gap = False
        if _gap and _is_introspective(question):
            _gap = False
        if _gap:
            _suggested = await SearchDecomposeAgent(self._provider).decompose(question)
        else:
            _suggested = []

        citations = [r.slug for r in candidates]
        _purpose_ctx = self._load_purpose_context()
        _pages_ctx = "\n\n".join(
            f"### {p.title}\n{p.content[:1000]}"
            for r in candidates
            if r.slug != "purpose" and (p := self._store.read_page(r.slug))
        ) or "No relevant pages found."
        _ctx_parts = []
        if _purpose_ctx:
            _ctx_parts.append(_purpose_ctx)
        _is_live_data = False
        if _system_ctx:
            # System knowledge matched: answer from help pages only; wiki pages are irrelevant noise
            _ctx_parts.append(f"## Synthadoc Help\n{_system_ctx}")
            citations = []
            if _live_data:
                _ctx_parts.append(f"## Live Wiki Data\n{_live_data}")
                _is_live_data = True
        elif _live_data:
            # Pure live-data query (no system knowledge page matched, but audit/queue data available)
            citations = []
            _ctx_parts.append(f"## Live Wiki Data\n{_live_data}")
            _is_live_data = True
        else:
            _ctx_parts.append(_pages_ctx)
        context = "\n\n".join(_ctx_parts)

        synthesis_prompt = self._build_synthesis_prompt(
            question, context,
            gap=_gap, system_ctx=_system_ctx, is_live_data=_is_live_data,
            gap_sentinel=True,
        )

        resp2 = await self._provider.complete(
            messages=[Message(role="user", content=synthesis_prompt)],
            temperature=0.0,
            max_tokens=self._max_tokens,
        )

        # Post-synthesis gap override: the sentinel [GAP] in the answer means the LLM
        # could not find enough in the wiki pages despite pre-synthesis gap detection
        # saying no gap (Guard B false negative). Strip the marker before displaying.
        answer_text = resp2.text
        if not _gap and resp2.text.startswith("[GAP]"):
            _gap = True
            answer_text = resp2.text[len("[GAP]"):].lstrip("\n")
            _suggested = await SearchDecomposeAgent(self._provider).decompose(question)

        logger.info("query answered — %d page(s) cited, %d tokens",
                    len(citations), resp2.total_tokens)
        return QueryResult(
            question=question,
            answer=answer_text,
            citations=citations,
            tokens_used=resp2.total_tokens,
            input_tokens=resp2.input_tokens,
            output_tokens=resp2.output_tokens,
            knowledge_gap=_gap,
            suggested_searches=_suggested,
            sub_questions_count=len(sub_questions),
            cacheable=not _is_live_data,
        )

    def _detect_gap(
        self, question: str, candidates: list[SearchResult], max_score: float
    ) -> tuple[bool, str, int, int]:
        """Full 5-signal knowledge gap detection.

        Returns (gap, discriminating_term, pages_with_overlap, min_specific_qualifying).
        Called by both run() and run_stream() so they share identical detection logic.
        """
        _any_term_missing = False
        _defining_term_absent = False
        _discriminating_term = ""
        _pages_with_overlap = len(candidates)
        _min_specific_qualifying = len(candidates)

        _contains_cjk = any(
            '぀' <= c <= 'ヿ'
            or '一' <= c <= '鿿'
            or '가' <= c <= '힯'
            for c in question
        )
        _key_terms = set() if _contains_cjk else {
            w.lower().rstrip("s'?!.,").replace("-", " ")
            for w in question.split()
            if len(w) >= 4 and w.lower().rstrip("s'?!.,").replace("-", " ") not in _STOPWORDS
        }

        if _key_terms and candidates:
            _term_doc_freq = {
                t: sum(
                    1 for r in candidates
                    if (p := self._store.read_page(r.slug))
                    and t in p.content.lower().replace("-", " ")
                )
                for t in _key_terms
            }
            _covered = {t: f for t, f in _term_doc_freq.items() if f > 0}
            _n_cands = len(candidates)
            _specific = {t: f for t, f in _covered.items() if f <= _n_cands * 0.8}
            if not _specific:
                _specific = _covered
            elif max(_specific.values(), default=0) <= 1:
                _specific = _covered

            if _specific:
                _discriminating_term = min(_specific, key=lambda t: _specific[t])
            elif _covered:
                _discriminating_term = min(_covered, key=lambda t: _covered[t])
            elif _term_doc_freq:
                _discriminating_term = min(_term_doc_freq, key=lambda t: _term_doc_freq[t])

            _term_qualifying_pages: dict[str, int] = {t: 0 for t in _specific}
            _pages_with_overlap = 0
            for _r in candidates:
                _p = self._store.read_page(_r.slug)
                if not _p:
                    continue
                _content = _p.content.lower().replace("-", " ")
                _page_on_topic = False
                for _t in _specific:
                    if _content.count(_t) >= _MIN_TERM_FREQ:
                        _term_qualifying_pages[_t] += 1
                        _page_on_topic = True
                if _page_on_topic:
                    _pages_with_overlap += 1

            _signal4_active = _pages_with_overlap < _n_cands // 2
            _any_term_missing = (
                _signal4_active
                and bool(_covered)
                and len(_term_doc_freq) >= 2
                and any(f == 0 for f in _term_doc_freq.values())
                and max(_covered.values()) / len(candidates) <= 0.8
            )
            _min_specific_qualifying = (
                min(_term_qualifying_pages.values()) if _term_qualifying_pages else 0
            )
            _signal5_doc_freq_cap = max(2, (_n_cands + 2) // 3)
            _defining_term_absent = (
                bool(_specific)
                and len(_term_doc_freq) >= 2
                and any(
                    _term_qualifying_pages[t] == 0
                    and _specific[t] <= _signal5_doc_freq_cap
                    for t in _term_qualifying_pages
                )
            )

        gap = self._gap_score_threshold > 0 and (
            len(candidates) < 3
            or (bool(_key_terms) and max_score < self._gap_score_threshold)  # skip when no content words
            or _pages_with_overlap < 2
            or _any_term_missing
            or _defining_term_absent
        )
        logger.info(
            "query retrieval — pages=%d, max_score=%.2f, "
            "discriminating_term=%r, on_topic_pages=%d, min_qualifying=%d, gap=%s",
            len(candidates), max_score, _discriminating_term,
            _pages_with_overlap, _min_specific_qualifying, gap,
        )
        return gap, _discriminating_term, _pages_with_overlap, _min_specific_qualifying

    async def run_stream(
        self,
        question: str,
        session_id: str | None = None,
        history: list[dict] | None = None,
        session_mode: SessionMode = "POWER_USER",
    ):
        """Stream query response as an async generator of SSE event dicts.

        Event sequence: status(retrieving) → status(synthesizing) → token* → citations → [gap] → done
        """
        # Action pre-flight: dispatch action requests before entering the query pipeline
        if self._orchestrator is not None:
            _action_agent = ActionAgent(self._provider, self._orchestrator,
                                        self._store._root.parent)
            if _action_agent.detect(question):
                _result = await _action_agent.run(question, history=history or [])
                if _result is not None:
                    if _result.needs_clarification:
                        yield {
                            "event": "clarify",
                            "data": {
                                "prompt": _result.clarify_prompt,
                                "candidates": _result.clarify_candidates,
                                "action": _result.action_type,
                            },
                        }
                        yield {"event": "done", "data": {}}
                        return
                    yield {"event": "status", "data": {"phase": "acting"}}
                    yield {"event": "token", "data": {"text": _result.message}}
                    yield {"event": "citations", "data": {"citations": []}}
                    yield {"event": "done", "data": {
                        "citations": [], "hints": [], "gap": not _result.success,
                        "job_id": _result.job_id,
                        "cacheable": False,
                    }}
                    return

        yield {"event": "status", "data": {"phase": "retrieving"}}

        question = self._expand_aliases(question)

        # Rewrite question for retrieval when history is present
        retrieval_question = question
        if history:
            rewritten = await RewriteAgent(self._provider).rewrite(question, history)
            retrieval_question = rewritten

        sub_questions, candidates = await self._run_search(retrieval_question)

        citations = [r.slug for r in candidates]
        _purpose_ctx = self._load_purpose_context()
        _system_ctx = self._get_relevant_system_pages(question)
        _pages_ctx = "\n\n".join(
            f"### {p.title}\n{p.content[:1000]}"
            for r in candidates
            if r.slug != "purpose" and (p := self._store.read_page(r.slug))
        ) or "No relevant pages found."
        _ctx_parts = []
        if _purpose_ctx:
            _ctx_parts.append(_purpose_ctx)
        _is_live_data = False
        _live_data = await self._fetch_live_wiki_data(question)
        if _system_ctx:
            # System knowledge matched: answer from help pages only; wiki pages are irrelevant noise
            _ctx_parts.append(f"## Synthadoc Help\n{_system_ctx}")
            citations = []
            if _live_data:
                _ctx_parts.append(f"## Live Wiki Data\n{_live_data}")
                _is_live_data = True
        elif _live_data:
            # Pure live-data query (no system knowledge page matched, but audit/queue data available)
            citations = []
            _ctx_parts.append(f"## Live Wiki Data\n{_live_data}")
            _is_live_data = True
        else:
            _ctx_parts.append(_pages_ctx)
        context = "\n\n".join(_ctx_parts)

        _max_score = max((r.score for r in candidates), default=0.0)
        _gap_q = " ".join(sub_questions) if sub_questions else question
        _gap, _discriminating_term, _pages_with_overlap, _min_specific_qualifying = \
            self._detect_gap(_gap_q, candidates, _max_score)

        if _system_ctx or _live_data:
            _gap = False
        if _gap and _is_introspective(question):
            _gap = False

        synthesis_prompt = self._build_synthesis_prompt(
            question, context,
            gap=_gap, system_ctx=_system_ctx, is_live_data=_is_live_data,
            history=history,
        )

        yield {"event": "status", "data": {"phase": "synthesizing", "sources": len(citations)}}

        full_answer = ""
        async for token in self._provider.complete_stream(
            messages=[Message(role="user", content=synthesis_prompt)],
            temperature=0.0,
            max_tokens=self._max_tokens,
        ):
            full_answer += token
            yield {"event": "token", "data": {"text": token}}

        if not full_answer:
            logger.warning("run_stream: LLM returned empty response for question %r", question)
            fallback = "(No response was generated. Please try again.)"
            yield {"event": "token", "data": {"text": fallback}}
            full_answer = fallback

        yield {"event": "citations", "data": {"citations": citations}}

        if _gap:
            try:
                # Use the standalone retrieval_question so gap suggestions are meaningful
                # when the user asked a context-dependent follow-up (e.g. "tell me more
                # about his death" → rewritten to "How did Alan Turing die?").
                _suggested = await SearchDecomposeAgent(self._provider).decompose(retrieval_question)
            except Exception as _exc:
                logger.warning("run_stream: gap decompose failed, falling back to original question: %s", _exc)
                _suggested = [retrieval_question]
            logger.debug("run_stream: yielding gap event (%d searches)", len(_suggested))
            yield {"event": "gap", "data": {"suggested_searches": _suggested}}

        next_hints = HintEngine.after_response(full_answer, session_mode)
        yield {"event": "done", "data": {"next_hints": next_hints, "cacheable": not _is_live_data}}
