// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
import { useEffect, useRef, useState, useCallback } from "react";
import * as d3 from "d3";
import { GraphSidebar } from "./GraphSidebar";

const CLUSTER_COLORS = [
    "#4e79a7","#f28e2b","#e15759","#76b7b2","#59a14f",
    "#edc948","#b07aa1","#ff9da7","#9c755f","#bab0ac",
];

interface GraphNode { slug: string; title: string; type: string; state: string; cluster_id: number; }
interface GraphEdge { from: string; to: string; weight: number; }

export function GraphView({ onAskQuery }: { onAskQuery: (q: string, hints: string[]) => void }) {
    const svgRef = useRef<SVGSVGElement>(null);
    const [status, setStatus] = useState<"loading" | "computing" | "ready" | "error">("loading");
    const [nodes, setNodes] = useState<GraphNode[]>([]);
    const [edges, setEdges] = useState<GraphEdge[]>([]);
    const [selected, setSelected] = useState<GraphNode | null>(null);
    const [typeFilter, setTypeFilter] = useState<string>("all");

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
        const width = svgRef.current.clientWidth;
        const height = svgRef.current.clientHeight;
        const g = svg.append("g");

        svg.call(d3.zoom<SVGSVGElement, unknown>().on("zoom", e => g.attr("transform", e.transform)));

        // D3 forceLink requires {source, target} — our API uses {from, to}
        const d3Links = filteredEdges.map(e => ({ source: e.from, target: e.to, weight: e.weight }));

        const sim = d3.forceSimulation(filtered as d3.SimulationNodeDatum[])
            .force("link", d3.forceLink(d3Links).id((d: any) => d.slug).distance(80))
            .force("charge", d3.forceManyBody().strength(-120))
            .force("center", d3.forceCenter(width / 2, height / 2));

        const link = g.append("g").selectAll("line")
            .data(d3Links).join("line")
            .attr("stroke", "rgba(160,170,220,0.35)").attr("stroke-width", (d: any) => Math.sqrt(d.weight));

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

        sim.on("tick", () => {
            link.attr("x1", (d: any) => d.source.x).attr("y1", (d: any) => d.source.y)
                .attr("x2", (d: any) => d.target.x).attr("y2", (d: any) => d.target.y);
            node.attr("cx", (d: any) => d.x).attr("cy", (d: any) => d.y);
        });
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
