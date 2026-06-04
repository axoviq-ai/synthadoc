# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from synthadoc.agents._utils import parse_json_string_array
from synthadoc.agents.hint_engine import HintEngine, SessionMode
from synthadoc.agents.search_decompose_agent import SearchDecomposeAgent
from synthadoc.providers.base import LLMProvider, Message
from synthadoc.storage.log import AuditDB
from synthadoc.storage.search import HybridSearch, SearchResult
from synthadoc.storage.wiki import WikiStorage

logger = logging.getLogger(__name__)

_MAX_SUB_QUESTIONS = 4

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
    "adversarial", "adversarial warning", "flagged", "overstated", "claim concern",
    "lint warning", "warnings",
    "job", "jobs", "job id", "job status", "ingest job", "queue",
    "pending jobs", "failed job", "dead job",
})

_RECENT_CHANGE_TRIGGERS: frozenset[str] = frozenset({
    "changed", "this week", "recently", "recent changes", "what's new",
    "whats new", "updated", "new pages", "added", "last week", "past week",
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


class QueryAgent:
    def __init__(self, provider: LLMProvider, store: WikiStorage,
                 search: HybridSearch, top_n: int = 8,
                 gap_score_threshold: float = 2.0,
                 routing_path: Path | None = None,
                 orchestrator: object | None = None) -> None:
        self._provider = provider
        self._store = store
        self._search = search
        self._top_n = top_n
        self._gap_score_threshold = gap_score_threshold
        self._orchestrator = orchestrator
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
            if any(kw in q_lower for kw in page.keywords):
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
                _HINTS = {
                    "draft":       "← run `synthadoc lint run` to promote",
                    "stale":       "← re-ingest needed",
                    "contradicted": "← review required",
                }
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
                recent = await audit.list_ingests_since(days=7)
                if recent:
                    lines.append("\n### Pages ingested or updated in the last 7 days")
                    seen: set[str] = set()
                    for r in recent:
                        slug = r.get("wiki_page") or ""
                        src = r.get("source_path") or ""
                        date = (r.get("ingested_at") or "")[:10]
                        if slug and slug not in seen:
                            seen.add(slug)
                            lines.append(f"  - [[{slug}]]  (from {src}, {date})" if src else f"  - [[{slug}]]  ({date})")
                else:
                    lines.append("\n### Pages ingested or updated in the last 7 days\n  (none)")

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

    async def query(self, question: str) -> QueryResult:
        question = self._expand_aliases(question)

        # Action pre-flight: if orchestrator is available and question is an action, dispatch it
        if self._orchestrator is not None:
            from synthadoc.agents.action_agent import ActionAgent
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

        # ── Knowledge gap detection ────────────────────────────────────────────
        # Three independent signals; any one triggers the gap:
        #
        #   1. Page count < 3  — wiki has almost nothing on the topic.
        #
        #   2. Max BM25 score < gap_score_threshold  — pages exist but their
        #      keyword overlap with the query is weak (tunable via
        #      [query] gap_score_threshold in synthadoc.toml; default 2.0).
        #
        #   3. Content overlap < 2  — BM25 scores are corpus-relative and can
        #      be inflated by shared vocabulary even when pages are off-topic
        #      (e.g. spring-flower pages match a vegetables query because both
        #      use words like "spring", "planting", "Canada").  This check
        #      counts how many retrieved pages actually contain at least one
        #      key noun from the question.  Key terms = question words longer
        #      than 4 chars that are not in _STOPWORDS, with trailing
        #      plural/punctuation stripped for basic suffix matching.
        #      If fewer than 2 pages pass this test, the wiki lacks on-topic
        #      content regardless of BM25 scores.
        #
        # Set gap_score_threshold = 0 to disable gap detection entirely.
        _max_score = max((r.score for r in candidates), default=0.0)

        # Extract meaningful content words from the question for the overlap check.
        # Strip trailing plural-s, possessive-apostrophe, and punctuation so that
        # "Moore's" → "moore", "vegetables" → "vegetable", "indoors" → "indoor".
        # Stripping 2 chars was too aggressive — it turned "Canadian" into "canadi",
        # which still matched every page in a Canada-focused wiki and made the check
        # useless as a discriminator.  Including "'" in the strip set is safe: it
        # handles possessives ("Moore's" → "moore") and plural-possessives
        # ("computers'" → "computer") without over-stripping ordinary words.
        # Hyphens are normalised to spaces so that compound terms like "open-source"
        # match wiki pages that write "open source" (and vice-versa).  The same
        # normalisation is applied to page content during the overlap check.
        #
        # CJK scripts (Chinese, Japanese, Korean) do not use whitespace word
        # boundaries, so split() either yields the whole sentence as one token
        # (doc_freq=0 in any page → spurious signal 4 gap) or tiny 1-2 char
        # fragments that all fail the len>4 guard.  Skip key-term extraction
        # entirely for CJK input; signals 1 and 2 remain active and are
        # language-agnostic.
        _contains_cjk = any(
            '぀' <= c <= 'ヿ'    # Japanese kana (hiragana + katakana)
            or '一' <= c <= '鿿' # CJK Unified Ideographs (Chinese/Japanese/Korean)
            or '가' <= c <= '힯' # Korean Hangul syllables
            for c in question
        )
        _key_terms = set() if _contains_cjk else {
            w.lower().rstrip("s'?!.,").replace("-", " ")  # normalize compound terms
            for w in question.split()
            if len(w) > 4 and w.lower().rstrip("s'?!.,").replace("-", " ") not in _STOPWORDS
        }

        # Signal 3: check whether retrieved pages contain dedicated coverage of the
        # query's specific topic words.
        #
        # Generic corpus terms ("canadian", "spring", "plant") appear in nearly
        # every page and would make every page look on-topic.  We filter them out
        # by excluding terms whose document frequency exceeds 60% of the candidates.
        # From the remaining "specific" terms we check whether at least 2 candidates
        # contain ANY of them with meaningful frequency (≥ 2 occurrences).
        #
        # Using ANY rather than a single rarest term handles multi-aspect queries
        # correctly: a page about "full shade" plants is on-topic for a query about
        # "sun, partial shade, and full shade" even if it lacks the word "partial".
        #
        # Zero-freq terms (synonyms like "backyard" vs "garden") are excluded;
        # they reflect vocabulary mismatch, not missing content.
        _MIN_TERM_FREQ = 2
        _any_term_missing = False   # signal 4 default
        _defining_term_absent = False  # signal 5 default
        if _key_terms and candidates:
            # Count how many candidates contain each key term (doc frequency).
            # Content is hyphen-normalised to match both "open-source" and "open source".
            _term_doc_freq = {
                t: sum(
                    1 for r in candidates
                    if (p := self._store.read_page(r.slug))
                    and t in p.content.lower().replace("-", " ")
                )
                for t in _key_terms
            }
            _covered = {t: f for t, f in _term_doc_freq.items() if f > 0}

            # Drop hyper-generic terms that appear in >80% of candidates.
            # Using 80% (not 60%) so moderately-common topic words like "partial"
            # (present in ~60-70% of pages in a shade-focused wiki) are kept as
            # discriminators rather than being wrongly discarded as generic.
            _n_cands = len(candidates)
            _specific = {t: f for t, f in _covered.items() if f <= _n_cands * 0.8}
            if not _specific:
                _specific = _covered  # all terms are corpus-generic; use full covered set
            # If every term in _specific appears in only one page it is too rare to
            # discriminate topic coverage — expand to include all covered terms.
            elif max(_specific.values(), default=0) <= 1:
                _specific = _covered

            # Log the rarest specific term as a representative discriminator.
            if _specific:
                _discriminating_term = min(_specific, key=lambda t: _specific[t])
            elif _covered:
                _discriminating_term = min(_covered, key=lambda t: _covered[t])
            else:
                _discriminating_term = min(_term_doc_freq, key=lambda t: _term_doc_freq[t])

            # Single pass: compute both signal 3 (any specific term ≥ freq) and
            # per-term qualifying page counts (needed for signals 4 and 5).
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

            # Signal 4 guard: if ≥ half the candidates have dedicated on-topic
            # coverage, a term with doc_freq=0 is almost certainly a synonym
            # mismatch ("backyard" absent when the wiki says "garden") rather than
            # a genuine absence.  Signal 4 needs this guard; signal 5 does not —
            # signal 5 only fires for terms with doc_freq > 0 and relies on
            # guard B (doc_freq cap) as the sole discriminator.
            _signal4_active = _pages_with_overlap < _n_cands // 2

            # Signal 4: a defining concept word is entirely absent from the wiki.
            # When a query has ≥ 2 key terms and at least one appears in zero
            # retrieved pages, the topic's core vocabulary is missing — not a
            # synonym/vocabulary mismatch.  E.g. "quantum error correction" in a
            # history-of-computing wiki: "error" and "correction" hit Bombe pages
            # (high BM25 score, signal 3 passes), but "quantum" has zero coverage,
            # definitively flagging the topic as absent.
            #
            # Coverage guard: if non-zero terms appear in >80% of candidates they
            # are generic corpus words, not topic discriminators — the zero-freq term
            # is a synonym mismatch, not a true gap.
            #
            # On-topic guard: if coverage is already good (≥ n_cands//2 pages),
            # a doc_freq=0 term is likely a synonym mismatch, not a genuine absence.
            _any_term_missing = (
                _signal4_active
                and bool(_covered)
                and len(_term_doc_freq) >= 2
                and any(f == 0 for f in _term_doc_freq.values())
                and max(_covered.values()) / len(candidates) <= 0.8
            )

            # Signal 5: a specific topic term exists in the wiki but never appears
            # with meaningful frequency (≥ MIN_TERM_FREQ) in any single candidate
            # page — i.e. only passing references, not dedicated coverage.
            #
            # Guard B — doc_freq cap: a term appearing in ≥ ⌈n_cands/3⌉ candidates
            # is a reference term (present in the domain), not an absent concept.
            # Low doc_freq + qualifying_pages=0 is the fingerprint of a genuine gap.
            # Guard B alone is sufficient; guard A is intentionally omitted here.
            #
            # Why no guard A: when on_topic_pages = n_cands//2 exactly, guard A
            # would block signal 5 even when min_qualifying=0 for the discriminating
            # term — this is the bug where half the pages share vocabulary (e.g.
            # "agent", "judge") while the specific concept ("methodologies") has
            # zero dedicated coverage.  Guard B catches that case: if the term's
            # doc_freq is below the threshold it is genuinely absent, not just
            # phrased differently.
            #
            # "quantum error correction" (gap): "quantum" doc_freq=2 < threshold(3),
            # qualifying=0 → gap=True ✓
            #
            # "Moore's Law" (no gap): "moore" doc_freq=4 ≥ threshold(3) → guard B
            # blocks → gap=False ✓
            #
            # "agent-as-a-judge methodologies" (gap fixed): on_topic_pages=4/8 (was
            # blocking guard A), "methodologie" doc_freq=1–2 < threshold(3),
            # qualifying=0 → gap=True ✓
            _min_specific_qualifying = (
                min(_term_qualifying_pages.values())
                if _term_qualifying_pages else 0
            )
            _signal5_doc_freq_cap = max(2, (_n_cands + 2) // 3)
            _defining_term_absent = (
                bool(_specific)
                and len(_term_doc_freq) >= 2
                and any(
                    _term_qualifying_pages[t] == 0
                    and _specific[t] < _signal5_doc_freq_cap      # guard B
                    for t in _term_qualifying_pages
                )
            )
        else:
            _discriminating_term = ""
            _pages_with_overlap = len(candidates)   # no key terms → skip check
            _min_specific_qualifying = len(candidates)

        _gap = self._gap_score_threshold > 0 and (
            len(candidates) < 3                                              # signal 1: too few pages
            or (bool(_key_terms) and _max_score < self._gap_score_threshold) # signal 2: skip when query has no content words
            or _pages_with_overlap < 2                                       # signal 3: no dedicated coverage
            or _any_term_missing                                             # signal 4: defining concept absent
            or _defining_term_absent                     # signal 5: defining term barely present
        )

        # Always log retrieval quality so operators can tune gap_score_threshold.
        logger.info(
            "query retrieval — pages=%d, max_score=%.2f, "
            "discriminating_term=%r, on_topic_pages=%d, min_qualifying=%d, gap=%s",
            len(candidates), _max_score, _discriminating_term,
            _pages_with_overlap, _min_specific_qualifying, _gap,
        )
        _system_ctx = self._get_relevant_system_pages(question)
        if _system_ctx:
            _gap = False
        _q_lower = question.lower()
        if _gap and (
            any(kw in _q_lower for kw in _WIKI_INTROSPECTIVE_TRIGGERS)
            or any(cmd in _q_lower for cmd in _SYNTHADOC_CLI_SUBCOMMANDS)
        ):
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
            _live_data = await self._fetch_live_wiki_data(question)
            if _live_data:
                _ctx_parts.append(f"## Live Wiki Data\n{_live_data}")
                _is_live_data = True
        else:
            _ctx_parts.append(_pages_ctx)
        context = "\n\n".join(_ctx_parts)

        if _gap:
            synthesis_prompt = (
                f"The wiki does not yet have a page on this topic. "
                f"Answer the question using your general knowledge, then note in one sentence "
                f"that the wiki does not currently cover this topic and suggest the user enriches it.\n\n"
                f"Question: {question}\n\n"
                f"Wiki pages available (unrelated to this question):\n{context}"
            )
        elif _system_ctx:
            synthesis_prompt = (
                f"Answer the question using the Synthadoc Help documentation and Live Wiki Data below. "
                f"If Live Wiki Data is present, use it to give concrete, specific answers "
                f"(e.g. list the actual page names, show real counts). "
                f"After answering, include a short 'To verify or investigate further' section "
                f"with the relevant CLI commands copied VERBATIM from the code blocks in the documentation — "
                f"do not rephrase or generate command names from memory. "
                f"Do not reference or cite wiki pages.\n\n"
                f"Question: {question}\n\nDocumentation:\n{context}"
            )
        else:
            synthesis_prompt = (
                f"Answer using ONLY these wiki pages. Cite with [[PageTitle]].\n\n"
                f"If the pages do not contain enough information to answer the question, "
                f"start your response with exactly '[GAP]' on its own line, then explain what's missing.\n\n"
                f"Question: {question}\n\nPages:\n{context}"
            )

        resp2 = await self._provider.complete(
            messages=[Message(role="user", content=synthesis_prompt)],
            temperature=0.0,
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
        _MIN_TERM_FREQ = 2
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
            if len(w) > 4 and w.lower().rstrip("s'?!.,").replace("-", " ") not in _STOPWORDS
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
                    and _specific[t] < _signal5_doc_freq_cap
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
        return gap, _discriminating_term, _pages_with_overlap, _min_specific_qualifying

    async def run_stream(
        self, question: str, session_id: str | None = None,  # reserved for future session history
        session_mode: SessionMode = "POWER_USER",
    ):
        """Stream query response as an async generator of SSE event dicts.

        Event sequence: status(retrieving) → status(synthesizing) → token* → citations → [gap] → done
        """
        # Action pre-flight: dispatch action requests before entering the query pipeline
        if self._orchestrator is not None:
            from synthadoc.agents.action_agent import ActionAgent
            _action_agent = ActionAgent(self._provider, self._orchestrator,
                                        self._store._root.parent)
            if _action_agent.detect(question):
                _result = await _action_agent.run(question)
                if _result is not None:
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
        if _system_ctx:
            # System knowledge matched: answer from help pages only; wiki pages are irrelevant noise
            _ctx_parts.append(f"## Synthadoc Help\n{_system_ctx}")
            citations = []
            _live_data = await self._fetch_live_wiki_data(question)
            if _live_data:
                _ctx_parts.append(f"## Live Wiki Data\n{_live_data}")
                _is_live_data = True
        else:
            _ctx_parts.append(_pages_ctx)
        context = "\n\n".join(_ctx_parts)

        _max_score = max((r.score for r in candidates), default=0.0)
        _gap, _discriminating_term, _pages_with_overlap, _min_specific_qualifying = \
            self._detect_gap(question, candidates, _max_score)

        logger.info(
            "query retrieval — pages=%d, max_score=%.2f, "
            "discriminating_term=%r, on_topic_pages=%d, min_qualifying=%d, gap=%s",
            len(candidates), _max_score, _discriminating_term,
            _pages_with_overlap, _min_specific_qualifying, _gap,
        )

        if _system_ctx:
            _gap = False
        _q_lower_s = question.lower()
        if _gap and (
            any(kw in _q_lower_s for kw in _WIKI_INTROSPECTIVE_TRIGGERS)
            or any(cmd in _q_lower_s for cmd in _SYNTHADOC_CLI_SUBCOMMANDS)
        ):
            _gap = False

        if _gap:
            synthesis_prompt = (
                f"The wiki does not yet have a page on this topic. "
                f"Answer the question using your general knowledge, then note in one sentence "
                f"that the wiki does not currently cover this topic and suggest the user enriches it.\n\n"
                f"Question: {question}\n\n"
                f"Wiki pages available (unrelated to this question):\n{context}"
            )
        elif _system_ctx:
            synthesis_prompt = (
                f"Answer the question using the Synthadoc Help documentation and Live Wiki Data below. "
                f"If Live Wiki Data is present, use it to give concrete, specific answers "
                f"(e.g. list the actual page names, show real counts). "
                f"After answering, include a short 'To verify or investigate further' section "
                f"with the relevant CLI commands copied VERBATIM from the code blocks in the documentation — "
                f"do not rephrase or generate command names from memory. "
                f"Do not reference or cite wiki pages.\n\n"
                f"Question: {question}\n\nDocumentation:\n{context}"
            )
        else:
            synthesis_prompt = (
                f"Answer using ONLY these wiki pages. Cite with [[PageTitle]].\n\n"
                f"Question: {question}\n\nPages:\n{context}"
            )

        yield {"event": "status", "data": {"phase": "synthesizing", "sources": len(citations)}}

        full_answer = ""
        async for token in self._provider.complete_stream(
            messages=[Message(role="user", content=synthesis_prompt)],
            temperature=0.0,
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
            _suggested = await SearchDecomposeAgent(self._provider).decompose(question)
            yield {"event": "gap", "data": {"suggested_searches": _suggested}}

        next_hints = HintEngine.after_response(full_answer, session_mode)
        yield {"event": "done", "data": {"next_hints": next_hints, "cacheable": not _is_live_data}}
