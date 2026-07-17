// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
import { useEffect, useRef, useState, useCallback } from "react";
import * as d3 from "d3";
import { GraphSidebar } from "./GraphSidebar";

const CLUSTER_COLORS = [
    "#4e79a7","#f28e2b","#e15759","#76b7b2","#59a14f",
    "#edc948","#b07aa1","#ff9da7","#9c755f","#bab0ac",
];

const LABEL_ALWAYS_SHOW = 50;    // show labels at default zoom for small graphs
const LABEL_ZOOM_THRESHOLD = 1.5; // show labels for larger graphs once zoomed in this much
const LABEL_R = 22; // px from node center to label anchor
const truncateLabel = (s: string) => s.length > 15 ? s.slice(0, 14) + "…" : s;

interface GraphNode { slug: string; title: string; type: string; state: string; cluster_id: number; }
interface GraphEdge { from: string; to: string; weight: number; edge_type: string; }

export function GraphView({ onAskQuery }: { onAskQuery: (q: string, hints: string[]) => void }) {
    const svgRef = useRef<SVGSVGElement>(null);
    const [status, setStatus] = useState<"loading" | "computing" | "ready" | "error">("loading");
    const [nodes, setNodes] = useState<GraphNode[]>([]);
    const [edges, setEdges] = useState<GraphEdge[]>([]);
    const [selected, setSelected] = useState<GraphNode | null>(null);
    const [typeFilter, setTypeFilter] = useState<string>("all");
    const zoomScaleRef = useRef(1);      // current D3 zoom k; read by highlight effect
    const filteredCountRef = useRef(0);  // node count after filter; read by highlight effect

    const fetchGraph = useCallback(async () => {
        try {
            const r = await fetch("/graph", { cache: "no-store" });
            if (!r.ok) { setStatus("error"); return; }
            const data = await r.json();
            if (data.status === "computing") {
                setStatus("computing");
                setTimeout(fetchGraph, 2000);
            } else {
                setNodes(data.nodes);
                setEdges(data.edges);
                setStatus("ready");
            }
        } catch { setStatus("error"); }
    }, []);

    useEffect(() => { fetchGraph(); }, [fetchGraph]);

    useEffect(() => { setSelected(null); }, [typeFilter]);

    // Build the D3 force simulation when graph data changes
    useEffect(() => {
        if (status !== "ready" || !svgRef.current) return;
        const filtered = typeFilter === "all" ? nodes : nodes.filter(n => n.type === typeFilter);
        const filteredSlugs = new Set(filtered.map(n => n.slug));
        const filteredEdges = edges.filter(e => filteredSlugs.has(e.from) && filteredSlugs.has(e.to));

        const svg = d3.select(svgRef.current);
        svg.selectAll("*").remove();
        // getBoundingClientRect gives the true rendered size; clientWidth can be 0 for CSS-sized SVGs
        const { width, height } = svgRef.current.getBoundingClientRect();
        const g = svg.append("g");

        filteredCountRef.current = filtered.length;
        const showLabelsAt = (k: number) => filtered.length <= LABEL_ALWAYS_SHOW || k >= LABEL_ZOOM_THRESHOLD;

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
        filtered.forEach((n: any, i) => {
            n.x = cx + initR * Math.cos((2 * Math.PI * i) / filtered.length);
            n.y = cy + initR * Math.sin((2 * Math.PI * i) / filtered.length);
        });

        const sim = d3.forceSimulation(filtered as d3.SimulationNodeDatum[])
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
            .data(filtered).join("circle")
            .attr("r", 8)
            .attr("fill", (d: any) => CLUSTER_COLORS[d.cluster_id % CLUSTER_COLORS.length])
            .attr("stroke", "#fff").attr("stroke-width", 1.5)
            .style("cursor", "pointer")
            .on("click", (_: any, d: any) => setSelected(prev => prev?.slug === d.slug ? null : d))
            .call(d3.drag<SVGCircleElement, any>()
                .on("start", (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y; })
                .on("drag", (e, d) => { d.fx=e.x; d.fy=e.y; })
                .on("end", (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx=null; d.fy=null; }) as any);

        node.append("title").text((d: any) => d.title || d.slug);

        // Build neighbor map so each label can be placed away from its edges
        const slugToNode = new Map<string, any>(filtered.map((n: any) => [n.slug, n]));
        const neighborMap = new Map<any, any[]>(filtered.map((n: any) => [n, []]));
        for (const e of filteredEdges) {
            const src = slugToNode.get(e.from), tgt = slugToNode.get(e.to);
            if (src && tgt) { neighborMap.get(src)!.push(tgt); neighborMap.get(tgt)!.push(src); }
        }

        label = g.append("g").selectAll<SVGTextElement, GraphNode>("text")
            .data(filtered).join("text")
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

        // Fit all nodes into the viewport. Clips 1 outlier per axis (≥8 nodes) so
        // one stray weakly-connected node can't force the whole graph to zoom out.
        const applyFit = () => {
            const pad = 56;
            const allX = (filtered as any[]).map((d: any) => d.x as number).sort((a, b) => a - b);
            const allY = (filtered as any[]).map((d: any) => d.y as number).sort((a, b) => a - b);
            if (!allX.length) return;
            const clip = allX.length > 8 ? 1 : 0;
            const x0 = allX[clip], x1 = allX[allX.length - 1 - clip];
            const y0 = allY[clip], y1 = allY[allY.length - 1 - clip];
            const bw = Math.max(x1 - x0, 1), bh = Math.max(y1 - y0, 1);
            const scale = Math.min((width - pad * 2) / bw, (height - pad * 2) / bh, 2.0);
            const tx = width / 2 - (x0 + bw / 2) * scale;
            const ty = height / 2 - (y0 + bh / 2) * scale;
            svg.transition().duration(500)
                .call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
        };

        let autoFitted = false;
        sim.on("tick", () => {
            link.attr("x1", (d: any) => d.source.x).attr("y1", (d: any) => d.source.y)
                .attr("x2", (d: any) => d.target.x).attr("y2", (d: any) => d.target.y);
            node.attr("cx", (d: any) => d.x).attr("cy", (d: any) => d.y);
            if (label) {
                // Place each label away from the centroid of its neighbors (into empty space)
                for (const d of filtered as any[]) {
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
    }, [status, nodes, edges, typeFilter]);

    // Highlight selected node without re-running the simulation
    useEffect(() => {
        if (!svgRef.current || status !== "ready") return;
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
    }, [selected, status]);

    const types = ["all", ...Array.from(new Set(nodes.map(n => n.type))).sort()];

    return (
        <div className="graph-view">
            {(status === "loading" || status === "computing") && (
                <div className="graph-computing">
                    <div className="graph-spinner" />
                    <p>Building knowledge graph…</p>
                </div>
            )}
            {status === "error" && (
                <p className="error-banner">Failed to load graph.</p>
            )}
            {status === "ready" && (
                <>
                    <div className="graph-controls">
                        <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)}
                                aria-label="Filter by type">
                            {types.map(t => <option key={t} value={t}>{t === "all" ? "All types" : t}</option>)}
                        </select>
                        <span className="graph-stats">{nodes.length} nodes · {edges.length} edges</span>
                    </div>
                    <div className="graph-canvas-wrap">
                        <svg ref={svgRef} className="graph-canvas" />
                        <GraphSidebar
                            node={selected}
                            clusterColor={selected ? CLUSTER_COLORS[selected.cluster_id % CLUSTER_COLORS.length] : ""}
                            edges={edges}
                            totalNodes={nodes.length}
                            onAsk={(q, hints) => { onAskQuery(q, hints); setSelected(null); }}
                            onClose={() => setSelected(null)}
                        />
                    </div>
                </>
            )}
        </div>
    );
}
