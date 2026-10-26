# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Peter W. / axoviq.com
from synthadoc.core.graph_views import cluster_detail, cluster_overview


def _node(slug, cluster, title=None, type_="concept"):
    return {"slug": slug, "title": title or slug.title(), "type": type_, "state": "active", "cluster_id": cluster}


def _edge(a, b, weight=1, edge_type="wikilink"):
    return {"from": a, "to": b, "weight": weight, "edge_type": edge_type}


# Cluster 0: hub "a" linked to b, c, d. Cluster 1: e–f. Two links between the clusters.
NODES = [_node("a", 0, "Alpha"), _node("b", 0, "Beta"), _node("c", 0, "Gamma", "person"),
         _node("d", 0, "Delta"), _node("e", 1, "Epsilon"), _node("f", 1, "Zeta")]
EDGES = [_edge("a", "b"), _edge("a", "c", 3), _edge("a", "d"), _edge("e", "f"),
         _edge("d", "e", 2), _edge("b", "f", 5, "co_source")]


def test_overview_has_one_entry_per_cluster_largest_first():
    overview = cluster_overview(NODES, EDGES)
    assert [(c["id"], c["size"]) for c in overview["clusters"]] == [(0, 4), (1, 2)]
    first = overview["clusters"][0]
    assert first["types"] == {"concept": 3, "person": 1}
    assert first["top_pages"][0] == {"slug": "a", "title": "Alpha"}


def test_overview_labels_clusters_by_their_most_connected_pages():
    first = cluster_overview(NODES, EDGES)["clusters"][0]
    # a has 3 links; b and d have 2 (ties broken by title); c has 1.
    assert first["label"] == "Alpha · Beta · Delta"


def test_overview_sums_links_between_clusters_only():
    links = cluster_overview(NODES, EDGES)["links"]
    assert links == [{"from": 0, "to": 1, "weight": 7, "count": 2}]


def test_overview_of_an_empty_graph():
    assert cluster_overview([], []) == {"clusters": [], "links": []}


def test_detail_returns_one_clusters_pages_with_their_full_degree():
    detail = cluster_detail(NODES, EDGES, 0)
    assert sorted(n["slug"] for n in detail["nodes"]) == ["a", "b", "c", "d"]
    degree = {n["slug"]: n["degree"] for n in detail["nodes"]}
    assert degree == {"a": 3, "b": 2, "c": 1, "d": 2}       # b and d also link into cluster 1
    assert {(e["from"], e["to"]) for e in detail["edges"]} == {("a", "b"), ("a", "c"), ("a", "d")}
    assert detail["edge_total"] == 3


def test_detail_keeps_each_pages_strongest_links():
    nodes = [_node("hub", 0)] + [_node(f"p{i}", 0) for i in range(5)]
    edges = [_edge("hub", f"p{i}", weight=i + 1) for i in range(5)] + [_edge("p0", "p1")]
    detail = cluster_detail(nodes, edges, 0, edges_per_node=2)
    kept = {(e["from"], e["to"]) for e in detail["edges"]}
    # The hub keeps its two heaviest links, but every page keeps its own best one too.
    assert ("hub", "p4") in kept and ("hub", "p3") in kept
    assert ("p0", "p1") in kept
    assert all(any(n["slug"] in (a, b) for a, b in kept) for n in detail["nodes"])
    assert detail["edge_total"] == 6


def test_detail_of_an_unknown_cluster_is_empty():
    assert cluster_detail(NODES, EDGES, 99) == {"nodes": [], "edges": [], "edge_total": 0}
