# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import re
from dataclasses import dataclass, field

from synthadoc.providers.base import LLMProvider, Message
from synthadoc.storage.log import AuditDB, LogWriter
from synthadoc.storage.wiki import WikiStorage


@dataclass
class LintReport:
    contradictions_found: int = 0
    contradictions_resolved: int = 0
    orphan_slugs: list[str] = field(default_factory=list)
    tokens_used: int = 0


_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

# Auto-generated / directory pages whose outbound links must NOT count as real
# references.  A page linked only from index/overview/dashboard is still an
# orphan in the content graph — it is not integrated into the knowledge network.
LINT_SKIP_SOURCE_SLUGS: frozenset[str] = frozenset(
    {"index", "overview", "log", "dashboard"}
)

# Pages never reported as orphans (root / auto-generated pages).
LINT_SKIP_SLUGS: frozenset[str] = frozenset(
    {"index", "log", "dashboard", "purpose", "overview"}
)


def find_orphan_slugs(
    page_texts: dict[str, str],
    skip: frozenset[str] = LINT_SKIP_SLUGS,
    skip_source: frozenset[str] = LINT_SKIP_SOURCE_SLUGS,
) -> list[str]:
    """Return slugs with no inbound [[wikilinks]] from other content pages.

    page_texts maps slug → page body text (frontmatter must be stripped by caller).
    Links from skip_source pages (index, overview, dashboard, log) and self-links
    are not counted — only connections between content pages rescue from orphan.
    """
    referenced: set[str] = set()
    for slug, text in page_texts.items():
        if slug in skip_source:
            continue
        for link in _WIKILINK_RE.findall(text):
            slug_part = link.split("|")[0].strip()
            target = slug_part.lower().replace(" ", "-")
            if target != slug:  # self-links don't count as inbound references
                referenced.add(target)
    return [s for s in page_texts if s not in referenced and s not in skip]


class LintAgent:
    def __init__(self, provider: LLMProvider, store: WikiStorage,
                 log_writer: LogWriter, confidence_threshold: float = 0.85,
                 audit_db: AuditDB | None = None) -> None:
        self._provider = provider
        self._store = store
        self._log = log_writer
        self._threshold = confidence_threshold
        self._audit = audit_db

    def _find_orphans(self, slugs: list[str]) -> list[str]:
        page_texts = {}
        for slug in slugs:
            page = self._store.read_page(slug)
            page_texts[slug] = page.content if page else ""
        return find_orphan_slugs(page_texts)

    async def lint(self, scope: str = "all", auto_resolve: bool = False,
                   job_id: str = "system") -> LintReport:
        report = LintReport()
        slugs = self._store.list_pages()

        if scope in ("all", "contradictions"):
            for slug in slugs:
                if slug in LINT_SKIP_SLUGS:
                    continue
                page = self._store.read_page(slug)
                if page and page.status == "contradicted":
                    report.contradictions_found += 1
                    if self._audit:
                        await self._audit.record_audit_event(
                            job_id, "contradiction_found", {"slug": slug})
                    if auto_resolve:
                        resp = await self._provider.complete(
                            messages=[Message(role="user",
                                content=f"Propose resolution:\n{page.content[:500]}")],
                            temperature=0.0,
                        )
                        report.tokens_used += resp.total_tokens
                        page.status = "active"
                        page.content += f"\n\n**Resolution:** {resp.text}"
                        self._store.write_page(slug, page)
                        report.contradictions_resolved += 1
                        if self._audit:
                            await self._audit.record_audit_event(
                                job_id, "auto_resolved", {"slug": slug})

        if scope in ("all", "orphans"):
            report.orphan_slugs = self._find_orphans(slugs)
            orphan_set = set(report.orphan_slugs)
            for slug in slugs:
                page = self._store.read_page(slug)
                if page and page.orphan != (slug in orphan_set):
                    page.orphan = slug in orphan_set
                    self._store.write_page(slug, page)

        self._log.log_lint(resolved=report.contradictions_resolved,
                           flagged=report.contradictions_found - report.contradictions_resolved,
                           orphans=len(report.orphan_slugs))
        return report
