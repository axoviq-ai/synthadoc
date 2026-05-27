# synthadoc/agents/export_agent.py
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from synthadoc.storage.wiki import WikiStorage, WikiPage, LifecycleState

_SKIP_SLUGS = frozenset({"index", "log", "dashboard", "overview", "purpose"})
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
EXPORT_FORMATS = frozenset({"llms.txt", "llms-full.txt", "graphml", "json"})


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
        ingest_records = await audit.list_ingests(limit=100_000)
        return self._render_json(pages, citations, lc_events, cost_data, ingest_records, routing)

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

        return "".join(sections)

    def _render_graphml(self, pages: dict[str, WikiPage], routing) -> str:
        import xml.etree.ElementTree as ET

        all_links: dict[str, list[str]] = {}
        for slug, page in pages.items():
            targets = []
            for m in _WIKILINK_RE.finditer(page.content or ""):
                target = m.group(1).strip().split("|")[0].strip()
                if target in pages and target != slug:
                    targets.append(target)
            all_links[slug] = targets

        inbound_count: dict[str, int] = {s: 0 for s in pages}
        for targets in all_links.values():
            for t in targets:
                if t in inbound_count:
                    inbound_count[t] += 1

        slug_to_branch: dict[str, str] = {}
        for branch, slugs in routing.branches.items():
            for s in slugs:
                slug_to_branch[s] = branch

        NS = "http://graphml.graphdrawing.org/graphml"
        YNS = "http://www.yworks.com/xml/graphml"
        XSI = "http://www.w3.org/2001/XMLSchema-instance"
        ET.register_namespace("y", YNS)
        root_el = ET.Element("graphml", {
            "xmlns": NS,
            "xmlns:xsi": XSI,
            "xsi:schemaLocation": f"{NS} {NS}/1.1/graphml.xsd",
        })

        def _key(kid, for_, name, typ):
            ET.SubElement(root_el, "key", {"id": kid, "for": for_,
                                           "attr.name": name, "attr.type": typ})

        _key("label",               "node", "label",               "string")
        _key("title",               "node", "title",               "string")
        _key("status",              "node", "status",              "string")
        _key("confidence",          "node", "confidence",          "string")
        _key("orphan",              "node", "orphan",              "boolean")
        _key("citation_count",      "node", "citation_count",      "int")
        _key("inbound_link_count",  "node", "inbound_link_count",  "int")
        _key("routing_branch",      "node", "routing_branch",      "string")
        _key("edge_type",           "edge", "edge_type",           "string")
        # yEd reads node labels from its own namespace key, not the standard label attribute
        ET.SubElement(root_el, "key", {"id": "yed_node", "for": "node",
                                       "yfiles.type": "nodegraphics"})

        graph_el = ET.SubElement(root_el, "graph",
                                  {"id": "wiki", "edgedefault": "directed"})

        for slug in sorted(pages):
            page = pages[slug]
            node_el = ET.SubElement(graph_el, "node", {"id": slug})

            def _data(key, val, _node=node_el):
                d = ET.SubElement(_node, "data", {"key": key})
                d.text = str(val)

            _data("label", page.title)
            _data("title", page.title)
            _data("status", page.status)
            _data("confidence", page.confidence or "")
            _data("orphan", "true" if page.orphan else "false")
            _data("citation_count", "0")
            _data("inbound_link_count", str(inbound_count.get(slug, 0)))
            _data("routing_branch", slug_to_branch.get(slug, ""))
            yed_data = ET.SubElement(node_el, "data", {"key": "yed_node"})
            sn = ET.SubElement(yed_data, f"{{{YNS}}}ShapeNode")
            ET.SubElement(sn, f"{{{YNS}}}NodeLabel").text = page.title

        edge_id = 0
        for slug in sorted(all_links):
            seen: set[str] = set()
            for target in all_links[slug]:
                if target not in seen:
                    edge_el = ET.SubElement(graph_el, "edge", {
                        "id": f"e{edge_id}", "source": slug, "target": target,
                    })
                    d = ET.SubElement(edge_el, "data", {"key": "edge_type"})
                    d.text = "wikilink"
                    edge_id += 1
                    seen.add(target)

        ET.indent(root_el, space="  ")
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
            root_el, encoding="unicode"
        )

    def _render_json(
        self,
        pages: dict[str, WikiPage],
        citations: list[dict],
        lc_events: list[dict],
        cost_data: dict,
        ingest_records: list[dict],
        routing,
    ) -> str:
        import json as _json

        citations_by_slug: dict[str, list[dict]] = {}
        for c in citations:
            citations_by_slug.setdefault(c["page_slug"], []).append({
                "source_file": c["source_file"],
                "source_lines": [c["line_start"], c["line_end"]],
                "claim_excerpt": c.get("claim_excerpt", ""),
            })

        ingest_cost_by_slug: dict[str, float] = {}
        ingest_tokens_by_slug: dict[str, int] = {}
        for r in ingest_records:
            slug = r["wiki_page"]
            ingest_cost_by_slug[slug] = ingest_cost_by_slug.get(slug, 0.0) + (r["cost_usd"] or 0.0)
            ingest_tokens_by_slug[slug] = ingest_tokens_by_slug.get(slug, 0) + (r["tokens"] or 0)

        events_by_slug: dict[str, list[dict]] = {}
        for e in lc_events:
            events_by_slug.setdefault(e["slug"], []).append({
                "from": e.get("from_state"),
                "to": e["to_state"],
                "ts": e.get("timestamp", ""),
                "triggered_by": e.get("triggered_by", ""),
                "reason": e.get("reason", ""),
            })

        branch_memberships = []
        for branch, slugs in routing.branches.items():
            for slug in slugs:
                if slug in pages:
                    branch_memberships.append({"slug": slug, "branch": branch})

        output: dict = {
            "wiki": self._wiki_name,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "total_compilation_cost_usd": cost_data.get("total_cost_usd", 0.0),
            "page_count": len(pages),
            "routing": {"branch_memberships": branch_memberships},
            "pages": [],
        }

        for slug in sorted(pages):
            page = pages[slug]
            output["pages"].append({
                "slug": slug,
                "title": page.title,
                "status": page.status,
                "confidence": page.confidence,
                "tags": page.tags or [],
                "categories": page.categories or [],
                "aliases": page.aliases or [],
                "orphan": page.orphan,
                "created": str(page.created) if page.created is not None else None,
                "sources": [
                    {
                        "file": s.file, "hash": s.hash,
                        "size": s.size,
                        "ingested": str(s.ingested) if s.ingested is not None else None,
                    }
                    for s in (page.sources or [])
                ],
                "content": page.content or "",
                "claims": citations_by_slug.get(slug, []),
                "lifecycle_history": events_by_slug.get(slug, []),
                "lint_warnings": page.lint_warnings or [],
                "ingest_cost_usd": round(ingest_cost_by_slug.get(slug, 0.0), 6),
                "ingest_tokens": ingest_tokens_by_slug.get(slug, 0),
            })

        return _json.dumps(output, ensure_ascii=False, indent=2)
