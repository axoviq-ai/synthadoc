# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Peter W. / axoviq.com
"""Views over the knowledge graph for large wikis.

The full graph (every page and link) is too much to draw past a few hundred
pages. These views summarise it per Louvain cluster, and return one
cluster's pages with their strongest links, so the web UI can open on an
overview and drill in.

``enrich_graph`` turns the stored graph into what ``GET /graph`` serves:
nodes ``{slug, title, type, state, cluster_id}`` and edges ``{from, to,
weight, edge_type}``; the views take those.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from synthadoc.storage.wiki import WikiStorage

LABEL_PAGES = 3               # most-connected page titles used to name a cluster
DETAIL_EDGES_PER_NODE = 3     # strongest links kept per page in a cluster view


def enrich_graph(store: "WikiStorage", graph_data: dict) -> tuple[list[dict], list[dict]]:
    """Stored graph rows -> the served nodes and edges.

    Adds each page's current title, type and lifecycle state. Pages deleted
    since the graph was built are left out, with their edges, without forcing
    a rebuild. Reads every page: call it off the event loop.
    """
    nodes = []
    for n in graph_data["nodes"]:
        page = store.read_page(n["slug"])
        if page is None:
            continue
        nodes.append({"slug": n["slug"], "title": page.title, "type": page.type or "concept",
                      "state": page.status, "cluster_id": n["cluster_id"]})
    slugs = {n["slug"] for n in nodes}
    edges = [
        {"from": e["from_slug"], "to": e["to_slug"], "weight": e["weight"],
         "edge_type": e.get("edge_type", "mixed")}
        for e in graph_data["edges"]
        if e["from_slug"] in slugs and e["to_slug"] in slugs
    ]
    return nodes, edges


def _degrees(edges: list[dict]) -> Counter:
    degree: Counter = Counter()
    for e in edges:
        degree[e["from"]] += 1
        degree[e["to"]] += 1
    return degree


def cluster_overview(nodes: list[dict], edges: list[dict]) -> dict:
    """One entry per cluster plus the links between clusters.

    Clusters are ``{id, size, label, top_pages, types}``, largest first; the
    label joins the titles of the cluster's most-connected pages. Links are
    ``{from, to, weight, count}``: the summed weight and number of page links
    between two clusters.
    """
    degree = _degrees(edges)
    members: dict[int, list[dict]] = defaultdict(list)
    for n in nodes:
        members[n["cluster_id"]].append(n)

    clusters = []
    for cid, pages in members.items():
        top = sorted(pages, key=lambda n: (-degree[n["slug"]], n["title"] or n["slug"]))[:LABEL_PAGES]
        clusters.append({
            "id": cid,
            "size": len(pages),
            "label": " · ".join(n["title"] or n["slug"] for n in top),
            "top_pages": [{"slug": n["slug"], "title": n["title"]} for n in top],
            "types": dict(Counter(n["type"] for n in pages).most_common()),
        })
    clusters.sort(key=lambda c: (-c["size"], c["id"]))

    cluster_of = {n["slug"]: n["cluster_id"] for n in nodes}
    between: dict[tuple[int, int], list[float]] = defaultdict(lambda: [0.0, 0])
    for e in edges:
        a, b = cluster_of.get(e["from"]), cluster_of.get(e["to"])
        if a is None or b is None or a == b:
            continue
        key = (a, b) if a < b else (b, a)
        between[key][0] += e["weight"]
        between[key][1] += 1
    links = [{"from": a, "to": b, "weight": w, "count": c} for (a, b), (w, c) in between.items()]
    links.sort(key=lambda x: (-x["weight"], x["from"], x["to"]))
    return {"clusters": clusters, "links": links}


def cluster_detail(nodes: list[dict], edges: list[dict], cluster_id: int,
                   edges_per_node: int = DETAIL_EDGES_PER_NODE) -> dict:
    """The pages of one cluster and the strongest links among them.

    A link is kept when it is among the *edges_per_node* heaviest links of
    either of its pages, so every page keeps its main connections while the
    drawing stays light. Each node gains ``degree``: its link count across the
    whole graph, links to other clusters included.
    """
    degree = _degrees(edges)
    slugs = {n["slug"] for n in nodes if n["cluster_id"] == cluster_id}
    inner = [e for e in edges if e["from"] in slugs and e["to"] in slugs]

    by_page: dict[str, list[int]] = defaultdict(list)
    for i, e in enumerate(inner):
        by_page[e["from"]].append(i)
        by_page[e["to"]].append(i)
    keep: set[int] = set()
    for idxs in by_page.values():
        keep.update(sorted(idxs, key=lambda i: -inner[i]["weight"])[:edges_per_node])

    return {
        "nodes": [{**n, "degree": degree[n["slug"]]} for n in nodes if n["slug"] in slugs],
        "edges": [inner[i] for i in sorted(keep)],
        "edge_total": len(inner),
    }
