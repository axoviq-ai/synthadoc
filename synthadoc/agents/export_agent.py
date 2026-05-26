# synthadoc/agents/export_agent.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from synthadoc.storage.wiki import WikiStorage, WikiPage, LifecycleState

_SKIP_SLUGS = frozenset({"index", "log", "dashboard", "overview", "purpose"})
EXPORT_FORMATS = frozenset({"llms.txt", "llms-full.txt", "graphml", "json"})
_MAX_FULL_TXT_BYTES = 5 * 1024 * 1024  # 5 MB


@dataclass
class ExportOptions:
    format: str
    status_filter: str = "all"
    context_pack: str | None = None


class ExportAgent:
    def __init__(
        self,
        store: WikiStorage,
        wiki_name: str,
        audit_db_path: Path,
        routing_path: Path,
    ) -> None:
        self._store = store
        self._wiki_name = wiki_name
        self._audit_db_path = Path(audit_db_path)
        self._routing_path = Path(routing_path)

    async def export(self, opts: ExportOptions) -> str:
        if opts.format not in EXPORT_FORMATS:
            raise ValueError(
                f"Unknown format: {opts.format!r}. Valid: {sorted(EXPORT_FORMATS)}"
            )

        slugs = self._store.list_pages()
        pages: dict[str, WikiPage] = {}
        for slug in slugs:
            if slug in _SKIP_SLUGS:
                continue
            page = self._store.read_page(slug)
            if page is None:
                continue
            if opts.status_filter != "all" and page.status != opts.status_filter:
                continue
            pages[slug] = page

        if opts.format == "llms.txt":
            return self._render_llms_txt(pages)
        if opts.format == "llms-full.txt":
            return self._render_llms_full_txt(pages)

        # graphml and json both need routing
        from synthadoc.core.routing import RoutingIndex
        routing = RoutingIndex.parse(self._routing_path)

        if opts.format == "graphml":
            return self._render_graphml(pages, routing)

        # json only
        from synthadoc.storage.log import AuditDB
        audit = AuditDB(self._audit_db_path)
        await audit.init()
        citations = await audit.list_citations(limit=100_000)
        lc_events = await audit.get_lifecycle_events(limit=100_000)
        cost_data = await audit.cost_summary(days=3650)
        return self._render_json(pages, citations, lc_events, cost_data, routing)

    def _render_llms_txt(self, pages: dict[str, WikiPage]) -> str:
        lines = [f"# {self._wiki_name}", f"> Synthadoc wiki: {self._wiki_name}", ""]

        active = {s: p for s, p in pages.items() if p.status == LifecycleState.ACTIVE}
        review = {
            s: p for s, p in pages.items()
            if p.status in (LifecycleState.CONTRADICTED, LifecycleState.STALE)
        }

        if active:
            lines.append("## Pages")
            for slug, page in sorted(active.items()):
                summary = (page.content or "").split("\n")[0][:120].strip()
                lines.append(f"- [{page.title}]({slug}): {summary}")
            lines.append("")

        if review:
            lines.append("## Needs Review")
            for slug, page in sorted(review.items()):
                reason = (
                    "contradicted" if page.status == LifecycleState.CONTRADICTED else "stale"
                )
                note = page.contradiction_note or page.unresolved_note or f"page is {reason}"
                lines.append(f"- [{page.title}]({slug}): {reason} — {note}")
            lines.append("")

        return "\n".join(lines)

    def _render_llms_full_txt(self, pages: dict[str, WikiPage]) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        active_count = sum(
            1 for p in pages.values() if p.status == LifecycleState.ACTIVE
        )
        sections = [f"# {self._wiki_name}\nGenerated: {ts} | Pages: {active_count} active\n"]

        for slug in sorted(pages):
            page = pages[slug]
            section = (
                f"\n---\n\n# {page.title}\n"
                f"Status: {page.status} | Confidence: {page.confidence}"
            )
            if page.tags:
                section += f" | Tags: {', '.join(page.tags)}"
            section += f"\n\n{page.content or ''}\n"
            sections.append(section)

        result = "".join(sections)
        if len(result.encode("utf-8")) > _MAX_FULL_TXT_BYTES:
            result = result[: _MAX_FULL_TXT_BYTES].rsplit("\n", 1)[0]
            result += "\n\n[TRUNCATED — wiki exceeds 5 MB export limit]\n"
        return result

    def _render_graphml(self, pages: dict[str, WikiPage], routing) -> str:
        raise NotImplementedError("implemented in Task 2")

    def _render_json(self, pages, citations, lc_events, cost_data, routing) -> str:
        raise NotImplementedError("implemented in Task 3")
