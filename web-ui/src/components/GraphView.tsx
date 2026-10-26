// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
import { useEffect, useRef, useState, useCallback } from "react";
import * as d3 from "d3";
import { GraphSidebar } from "./GraphSidebar";

const CLUSTER_COLORS = [
    "#4e79a7","#f28e2b","#e15759","#76b7b2","#59a14f",
    "#edc948","#b07aa1","#ff9da7","#9c755f","#bab0ac",
];
const clusterColor = (id: number) => CLUSTER_COLORS[id % CLUSTER_COLORS.length];

const LABEL_ALWAYS_SHOW = 50;    // show labels at default zoom for small graphs
const LABEL_ZOOM_THRESHOLD = 1.5; // show labels for larger graphs once zoomed in this much
const LABEL_R = 22; // px from node center to label anchor
const truncateLabel = (s: string, n = 15) => s.length > n ? s.slice(0, n - 1) + "…" : s;
const CLUSTER_LABEL_CHARS = 22;
const LABEL_CHAR_PX = 6;              // approximate width of one 11px label character
const CLUSTER_LINKS_PER_CLUSTER = 2;  // strongest links drawn per cluster in the overview
const clusterLabel = (c: GraphCluster) => `${truncateLabel(c.label, CLUSTER_LABEL_CHARS)} (${c.size})`;

// Above this many pages the whole graph is too dense to draw or read: open on
// one bubble per cluster and draw a cluster's pages when it is clicked.
export const CLUSTER_VIEW_MIN_NODES = 300;

export interface GraphNode { slug: string; title: string; type: string; state: string; cluster_id: number; degree?: number; }
export interface GraphEdge { from: string; to: string; weight: number; edge_type: string; }
export interface GraphCluster { id: number; size: number; label: string; top_pages: { slug: string; title: string }[]; types: Record<string, number>; }
export interface ClusterLink { from: number; to: number; weight: number; count: number; }

type Status = "loading" | "computing" | "ready" | "error";
// pages: every page (small wikis, or one cluster); clusters: the cluster overview
type Mode = "pages" | "clusters";

type Point = { x?: number; y?: number; r?: number };

/** Zoom so all points (with their radius) fit the viewport. With *clipOutliers*,
 *  1 point per axis is ignored (≥8 points) so one stray weakly-connected node
 *  can't force the whole graph to zoom out. */
function fitToView(
    svg: d3.Selection<SVGSVGElement, unknown, null, undefined>,
    zoom: d3.ZoomBehavior<SVGSVGElement, unknown>,
    points: Point[], width: number, height: number, clipOutliers: boolean,
) {
    const pad = 56;
    const xs = points.flatMap(p => [(p.x ?? 0) - (p.r ?? 0), (p.x ?? 0) + (p.r ?? 0)]).sort((a, b) => a - b);
    const ys = points.flatMap(p => [(p.y ?? 0) - (p.r ?? 0), (p.y ?? 0) + (p.r ?? 0)]).sort((a, b) => a - b);
    if (!xs.length) return;
    const clip = clipOutliers && points.length > 8 ? 2 : 0;   // 2 bounds per point
    const x0 = xs[clip], x1 = xs[xs.length - 1 - clip];
    const y0 = ys[clip], y1 = ys[ys.length - 1 - clip];
    const bw = Math.max(x1 - x0, 1), bh = Math.max(y1 - y0, 1);
    const scale = Math.min((width - pad * 2) / bw, (height - pad * 2) / bh, 2.0);
    const tx = width / 2 - (x0 + bw / 2) * scale;
    const ty = height / 2 - (y0 + bh / 2) * scale;
    svg.transition().duration(500)
        .call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
}

/** Draws pages and links as a force layout. Returns a cleanup function. */
function drawPages(
    svgEl: SVGSVGElement, nodes: GraphNode[], edges: GraphEdge[],
    onSelect: (d: GraphNode) => void, zoomScaleRef: { current: number },
): () => void {
    const filteredSlugs = new Set(nodes.map(n => n.slug));
    const filteredEdges = edges.filter(e => filteredSlugs.has(e.from) && filteredSlugs.has(e.to));

    const svg = d3.select(svgEl);
    svg.selectAll("*").remove();
    // getBoundingClientRect gives the true rendered size; clientWidth can be 0 for CSS-sized SVGs
    const { width, height } = svgEl.getBoundingClientRect();
    const g = svg.append("g");

    const showLabelsAt = (k: number) => nodes.length <= LABEL_ALWAYS_SHOW || k >= LABEL_ZOOM_THRESHOLD;

    // label is declared here so the zoom closure can toggle its visibility
    let label: d3.Selection<SVGTextElement, GraphNode, SVGGElement, unknown> | null = null;
    const zoom = d3.zoom<SVGSVGElement, unknown>().on("zoom", e => {
        g.attr("transform", e.transform);
        zoomScaleRef.current = e.transform.k;
        if (label) label.attr("visibility", showLabelsAt(e.transform.k) ? "visible" : "hidden");
    });
    svg.call(zoom);

    // D3 forceLink requires {source, target} — our API uses {from, to}
    const d3Links = filteredEdges.map(e => ({ source: e.from, target: e.to, weight: e.weight, edge_type: e.edge_type }));

    // Seed positions in a circle so the simulation starts spread across the viewport
    const cx = width / 2, cy = height / 2;
    const initR = Math.min(width, height) * 0.35;
    nodes.forEach((n: any, i) => {
        n.x = cx + initR * Math.cos((2 * Math.PI * i) / nodes.length);
        n.y = cy + initR * Math.sin((2 * Math.PI * i) / nodes.length);
    });

    const sim = d3.forceSimulation(nodes as d3.SimulationNodeDatum[])
        .force("link", d3.forceLink(d3Links).id((d: any) => d.slug).distance(80))
        .force("charge", d3.forceManyBody().strength(-120))
        .force("center", d3.forceCenter(cx, cy))
        // Gentle gravity prevents weakly-connected nodes from drifting off-screen
        .force("x", d3.forceX(cx).strength(0.06))
        .force("y", d3.forceY(cy).strength(0.06))
        .alphaDecay(0.05);

    const link = g.append("g").selectAll("line")
        .data(d3Links).join("line")
        .attr("stroke", "rgba(160,170,220,0.35)")
        .attr("stroke-width", (d: any) => Math.min(4, Math.max(1, Math.sqrt(d.weight))))
        .attr("stroke-dasharray", (d: any) => d.edge_type === "co_source" ? "5,3" : null);

    const node = g.append("g").selectAll("circle")
        .data(nodes).join("circle")
        .attr("r", 8)
        .attr("fill", (d: any) => clusterColor(d.cluster_id))
        .attr("stroke", "#fff").attr("stroke-width", 1.5)
        .style("cursor", "pointer")
        .on("click", (_: any, d: any) => onSelect(d))
        .call(d3.drag<SVGCircleElement, any>()
            .on("start", (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y; })
            .on("drag", (e, d) => { d.fx=e.x; d.fy=e.y; })
            .on("end", (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx=null; d.fy=null; }) as any);

    node.append("title").text((d: any) => d.title || d.slug);

    // Build neighbor map so each label can be placed away from its edges
    const slugToNode = new Map<string, any>(nodes.map((n: any) => [n.slug, n]));
    const neighborMap = new Map<any, any[]>(nodes.map((n: any) => [n, []]));
    for (const e of filteredEdges) {
        const src = slugToNode.get(e.from), tgt = slugToNode.get(e.to);
        if (src && tgt) { neighborMap.get(src)!.push(tgt); neighborMap.get(tgt)!.push(src); }
    }

    label = g.append("g").selectAll<SVGTextElement, GraphNode>("text")
        .data(nodes).join("text")
        .attr("class", "node-label")
        .text((d: any) => truncateLabel(d.title || d.slug))
        .attr("font-size", "10px")
        .attr("fill", "#94a3b8")
        .attr("dominant-baseline", "middle")
        // Dark halo so labels remain legible when sitting over edge lines
        .style("paint-order", "stroke fill")
        .attr("stroke", "rgba(5,6,14,0.85)")
        .attr("stroke-width", "3")
        .attr("stroke-linejoin", "round")
        .attr("pointer-events", "none")
        .attr("visibility", showLabelsAt(1) ? "visible" : "hidden");

    const applyFit = () => fitToView(svg, zoom, nodes as Point[], width, height, true);

    let autoFitted = false;
    sim.on("tick", () => {
        link.attr("x1", (d: any) => d.source.x).attr("y1", (d: any) => d.source.y)
            .attr("x2", (d: any) => d.target.x).attr("y2", (d: any) => d.target.y);
        node.attr("cx", (d: any) => d.x).attr("cy", (d: any) => d.y);
        if (label) {
            // Place each label away from the centroid of its neighbors (into empty space)
            for (const d of nodes as any[]) {
                const ns = neighborMap.get(d) || [];
                if (!ns.length) { d._lx = d.x; d._ly = d.y + LABEL_R; d._la = "middle"; continue; }
                let dx = 0, dy = 0;
                for (const n of ns) { dx += (n.x - d.x); dy += (n.y - d.y); }
                dx = -(dx / ns.length); dy = -(dy / ns.length); // flip: away from neighbors
                const len = Math.sqrt(dx * dx + dy * dy) || 1;
                d._lx = d.x + (dx / len) * LABEL_R;
                d._ly = d.y + (dy / len) * LABEL_R;
                d._la = (dx / len) < -0.3 ? "end" : (dx / len) > 0.3 ? "start" : "middle";
            }
            label.attr("x", (d: any) => d._lx).attr("y", (d: any) => d._ly)
                 .attr("text-anchor", (d: any) => d._la);
        }
        // Fire fit when visually settled (~1s with alphaDecay 0.05), don't wait for full cooldown
        if (!autoFitted && sim.alpha() < 0.05) { autoFitted = true; applyFit(); }
    });

    sim.on("end", () => { if (!autoFitted) { autoFitted = true; applyFit(); } });
    return () => { sim.stop(); };
}

type Bubble = GraphCluster & d3.SimulationNodeDatum & { r: number; space: number };
type BubbleLink = d3.SimulationLinkDatum<Bubble> & { source: Bubble; target: Bubble; weight: number };

/** Draws one bubble per cluster (area ∝ pages) and the links between clusters. */
function drawClusters(
    svgEl: SVGSVGElement, clusters: GraphCluster[], links: ClusterLink[],
    onOpen: (c: GraphCluster) => void,
): () => void {
    const svg = d3.select(svgEl);
    svg.selectAll("*").remove();
    const { width, height } = svgEl.getBoundingClientRect();
    const g = svg.append("g");
    const zoom = d3.zoom<SVGSVGElement, unknown>().on("zoom", e => g.attr("transform", e.transform));
    svg.call(zoom);

    const maxSize = d3.max(clusters, c => c.size) || 1;
    const radius = d3.scaleSqrt().domain([1, maxSize]).range([12, 46]);
    // space: room each bubble needs, including its label below (≈6px per character)
    const bubbles: Bubble[] = clusters.map(c => {
        const r = radius(c.size);
        return { ...c, r, space: Math.max(r, clusterLabel(c).length * LABEL_CHAR_PX / 2) + 10 };
    });
    const byId = new Map(bubbles.map(b => [b.id, b]));
    // Only links that are among a cluster's strongest, so the overview shows
    // structure rather than every faint connection.
    const keep = new Set<ClusterLink>();
    for (const b of bubbles) {
        links.filter(l => l.from === b.id || l.to === b.id)
             .sort((x, y) => y.weight - x.weight).slice(0, CLUSTER_LINKS_PER_CLUSTER).forEach(l => keep.add(l));
    }
    const bubbleLinks: BubbleLink[] = [...keep].map(l => ({ source: byId.get(l.from)!, target: byId.get(l.to)!, weight: l.weight }));
    const maxW = d3.max(bubbleLinks, l => l.weight) || 1;

    const sim = d3.forceSimulation<Bubble>(bubbles)
        .force("link", d3.forceLink<Bubble, BubbleLink>(bubbleLinks).distance(l => l.source.space + l.target.space).strength(0.2))
        .force("charge", d3.forceManyBody<Bubble>().strength(-300))
        .force("collide", d3.forceCollide<Bubble>().radius(b => b.space).iterations(3))
        // Pull harder along the short side so the layout takes the viewport's shape
        .force("x", d3.forceX<Bubble>(width / 2).strength(0.05 * Math.min(1, height / width)))
        .force("y", d3.forceY<Bubble>(height / 2).strength(0.05 * Math.min(1, width / height)));

    const link = g.append("g").selectAll<SVGLineElement, BubbleLink>("line").data(bubbleLinks).join("line")
        .attr("stroke", "rgba(160,170,220,0.35)")
        .attr("stroke-width", l => 1 + 5 * (l.weight / maxW));

    const bubble = g.append("g").selectAll<SVGCircleElement, Bubble>("circle").data(bubbles).join("circle")
        .attr("class", "graph-cluster")
        .attr("r", b => b.r)
        .attr("fill", b => clusterColor(b.id))
        .attr("stroke", "#fff").attr("stroke-width", 1.5)
        .style("cursor", "pointer")
        .on("click", (_, b) => onOpen(b));
    bubble.append("title").text(b => `${b.label}\n${b.size} pages — click to explore`);
    // Labels in their own layer above every bubble, so no bubble covers another's label.
    const label = g.append("g").selectAll<SVGTextElement, Bubble>("text").data(bubbles).join("text")
        .attr("class", "node-label cluster-label")
        .attr("text-anchor", "middle")
        .attr("font-size", "11px")
        .style("paint-order", "stroke fill")
        .attr("stroke-width", "3").attr("stroke-linejoin", "round")
        .attr("pointer-events", "none")
        .text(b => clusterLabel(b));

    // Fit bubbles and their labels (centre shifted down, label width as radius)
    const fitPoints = (): Point[] => bubbles.map(b => ({ x: b.x, y: (b.y ?? 0) + 8, r: b.space }));
    let fitted = false;
    sim.on("tick", () => {
        link.attr("x1", l => l.source.x ?? 0).attr("y1", l => l.source.y ?? 0)
            .attr("x2", l => l.target.x ?? 0).attr("y2", l => l.target.y ?? 0);
        bubble.attr("cx", b => b.x ?? 0).attr("cy", b => b.y ?? 0);
        label.attr("x", b => b.x ?? 0).attr("y", b => (b.y ?? 0) + b.r + 14);
        if (!fitted && sim.alpha() < 0.05) { fitted = true; fitToView(svg, zoom, fitPoints(), width, height, false); }
    });
    sim.on("end", () => { if (!fitted) { fitted = true; fitToView(svg, zoom, fitPoints(), width, height, false); } });
    return () => { sim.stop(); };
}

export function GraphView({ onAskQuery }: { onAskQuery: (q: string, hints: string[]) => void }) {
    const svgRef = useRef<SVGSVGElement>(null);
    const [status, setStatus] = useState<Status>("loading");
    const [mode, setMode] = useState<Mode>("pages");
    const [totalNodes, setTotalNodes] = useState(0);
    const [totalEdges, setTotalEdges] = useState(0);
    const [clusters, setClusters] = useState<GraphCluster[]>([]);
    const [clusterLinks, setClusterLinks] = useState<ClusterLink[]>([]);
    const [openCluster, setOpenCluster] = useState<GraphCluster | null>(null);
    const [nodes, setNodes] = useState<GraphNode[]>([]);
    const [edges, setEdges] = useState<GraphEdge[]>([]);
    const [selected, setSelected] = useState<GraphNode | null>(null);
    const [typeFilter, setTypeFilter] = useState<string>("all");
    const zoomScaleRef = useRef(1);      // current D3 zoom k; read by highlight effect
    const filteredCountRef = useRef(0);  // node count after filter; read by highlight effect

    const loadPages = useCallback(async (url: string) => {
        const r = await fetch(url, { cache: "no-store" });
        if (!r.ok) { setStatus("error"); return; }
        const data = await r.json();
        setNodes(data.nodes);
        setEdges(data.edges);
        setMode("pages");
        setStatus("ready");
    }, []);

    // Start from the cluster summary: small wikis then load every page,
    // large ones open on the cluster overview.
    const fetchGraph = useCallback(async () => {
        try {
            const r = await fetch("/graph?view=clusters", { cache: "no-store" });
            if (!r.ok) { setStatus("error"); return; }
            const data = await r.json();
            if (data.status === "computing") {
                setStatus("computing");
                setTimeout(fetchGraph, 2000);
                return;
            }
            setTotalNodes(data.node_count);
            setTotalEdges(data.edge_count);
            setClusters(data.clusters);
            setClusterLinks(data.links);
            if (data.node_count <= CLUSTER_VIEW_MIN_NODES) {
                await loadPages("/graph");
            } else {
                setMode("clusters");
                setStatus("ready");
            }
        } catch { setStatus("error"); }
    }, [loadPages]);

    useEffect(() => { fetchGraph(); }, [fetchGraph]);

    useEffect(() => { setSelected(null); }, [typeFilter, openCluster]);

    const openClusterPages = useCallback(async (c: GraphCluster) => {
        setOpenCluster(c);
        setTypeFilter("all");
        setStatus("loading");
        try { await loadPages(`/graph?cluster=${c.id}`); } catch { setStatus("error"); }
    }, [loadPages]);

    const backToClusters = useCallback(() => {
        setOpenCluster(null);
        setNodes([]);
        setEdges([]);
        setMode("clusters");
    }, []);

    // Draw whenever the data or view changes
    useEffect(() => {
        if (status !== "ready" || !svgRef.current) return;
        if (mode === "clusters") {
            return drawClusters(svgRef.current, clusters, clusterLinks, openClusterPages);
        }
        const filtered = typeFilter === "all" ? nodes : nodes.filter(n => n.type === typeFilter);
        filteredCountRef.current = filtered.length;
        return drawPages(svgRef.current, filtered, edges,
                         d => setSelected(prev => prev?.slug === d.slug ? null : d), zoomScaleRef);
    }, [status, mode, nodes, edges, typeFilter, clusters, clusterLinks, openClusterPages]);

    // Highlight selected node without re-running the simulation
    useEffect(() => {
        if (!svgRef.current || status !== "ready" || mode !== "pages") return;
        d3.select(svgRef.current)
            .selectAll<SVGCircleElement, GraphNode>("circle")
            .attr("r", (d) => d.slug === selected?.slug ? 12 : 8)
            .attr("stroke", (d) => d.slug === selected?.slug ? "#facc15" : "#fff")
            .attr("stroke-width", (d) => d.slug === selected?.slug ? 3 : 1.5)
            .attr("opacity", selected ? (d) => d.slug === selected.slug ? 1 : 0.45 : 1);
        const labelsShown = filteredCountRef.current <= LABEL_ALWAYS_SHOW || zoomScaleRef.current >= LABEL_ZOOM_THRESHOLD;
        d3.select(svgRef.current)
            .selectAll<SVGTextElement, GraphNode>("text.node-label")
            // Always show the selected node's label even when labels are zoom-hidden
            .attr("visibility", (d) => selected?.slug === d.slug ? "visible" : (labelsShown ? "visible" : "hidden"))
            .attr("opacity", selected ? (d) => d.slug === selected.slug ? 1 : 0.2 : 0.85);
    }, [selected, status, mode]);

    const types = ["all", ...Array.from(new Set(nodes.map(n => n.type))).sort()];
    const filteredNodes = typeFilter === "all" ? nodes : nodes.filter(n => n.type === typeFilter);
    const clusterIds = [...new Set(filteredNodes.map(n => n.cluster_id))].sort((a, b) => a - b);
    // Clusters are named after their most-connected pages (from the cluster summary).
    const clusterById = new Map(clusters.map(c => [c.id, c]));
    const clusterName = (cid: number) => clusterById.get(cid)?.label || `Cluster ${cid}`;

    return (
        <div className="graph-view">
            {(status === "loading" || status === "computing") && (
                <div className="graph-computing">
                    <div className="graph-spinner" />
                    <p>{status === "computing" ? "Building knowledge graph…" : "Loading graph…"}</p>
                </div>
            )}
            {status === "error" && (
                <p className="error-banner">Failed to load graph.</p>
            )}
            {status === "ready" && (
                <>
                    <div className="graph-controls">
                        {openCluster && (
                            <button className="graph-back-btn" onClick={backToClusters}>← All clusters</button>
                        )}
                        {mode === "pages" && (
                            <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)}
                                    aria-label="Filter by type">
                                {types.map(t => <option key={t} value={t}>{t === "all" ? "All types" : t}</option>)}
                            </select>
                        )}
                        <span className="graph-stats">
                            {mode === "clusters"
                                ? <>{totalNodes} nodes · {totalEdges} edges · {clusters.length} clusters — click a cluster to explore it</>
                                : openCluster
                                    ? <>{openCluster.label} — {nodes.length} pages · {edges.length} strongest links</>
                                    : <>{nodes.length} nodes · {edges.length} edges</>}
                            <span className="graph-stats-note"> (excludes draft and archived nodes)</span>
                        </span>
                    </div>
                    <div className="graph-canvas-wrap">
                        <svg ref={svgRef} className="graph-canvas" />
                        {mode === "pages" && (
                            <GraphSidebar
                                node={selected}
                                clusterColor={selected ? clusterColor(selected.cluster_id) : ""}
                                clusterName={selected ? clusterName(selected.cluster_id) : ""}
                                edges={edges}
                                totalNodes={totalNodes || nodes.length}
                                onAsk={(q, hints) => { onAskQuery(q, hints); setSelected(null); }}
                                onClose={() => setSelected(null)}
                            />
                        )}
                    </div>
                    {mode === "clusters" && (
                        <div className="graph-legend graph-legend--clusters" aria-label="Clusters">
                            {clusters.map(c => (
                                <button key={c.id} className="graph-legend-item graph-legend-btn"
                                        title={`${c.label} — ${c.size} pages`} onClick={() => openClusterPages(c)}>
                                    <span className="graph-cluster-dot" style={{ background: clusterColor(c.id) }} />
                                    <span className="graph-legend-label">{c.label}</span>
                                    <span className="graph-legend-size">{c.size}</span>
                                </button>
                            ))}
                        </div>
                    )}
                    {mode === "pages" && !openCluster && (
                        <div className="graph-legend">
                            {clusterIds.map(cid => (
                                <div key={cid} className="graph-legend-item" title={clusterName(cid)}>
                                    <span className="graph-cluster-dot" style={{ background: clusterColor(cid) }} />
                                    <span className="graph-legend-label">{clusterName(cid)}</span>
                                    {clusterById.has(cid) && (
                                        <span className="graph-legend-size">{clusterById.get(cid)!.size}</span>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </>
            )}
        </div>
    );
}
