// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
import { useState } from "react";

interface GraphNode { slug: string; title: string; type: string; state: string; cluster_id: number; }
interface GraphEdge { from: string; to: string; weight: number; }

interface Props {
    node: GraphNode | null;
    clusterColor: string;
    edges: GraphEdge[];
    totalNodes: number;
    onAsk: (query: string, hints: string[]) => void;
    onClose: () => void;
}

const TYPE_DESC: Record<string, string> = {
    concept:   "Core idea or theory",
    reference: "External source or citation",
    tutorial:  "Step-by-step guide or how-to",
    event:     "Historical event or milestone",
    person:    "Individual or contributor",
    guide:     "Overview or survey",
    paper:     "Academic or research paper",
};

const STATE_DESC: Record<string, string> = {
    active:      "Current and reviewed",
    draft:       "Not yet reviewed",
    stale:       "May be outdated",
    contradicted:"Conflicts with other pages",
    archived:    "No longer active",
};

function generateHints(node: GraphNode): string[] {
    const t = node.title || node.slug;
    switch (node.type) {
        case "person":
            return [
                `Who is ${t} and what are they known for?`,
                `What is ${t}'s main contribution to the field?`,
                `How did ${t} influence later developments?`,
            ];
        case "event":
        case "milestone":
            return [
                `What was ${t} and why did it matter?`,
                `What led to ${t}?`,
                `What were the long-term impacts of ${t}?`,
            ];
        case "tutorial":
        case "guide":
            return [
                `What does ${t} cover?`,
                `What are the key steps or concepts in ${t}?`,
                `What prerequisites are needed to understand ${t}?`,
            ];
        default:
            return [
                `Summarize ${t}`,
                `What are the key ideas in ${t}?`,
                `How does ${t} connect to related topics in this wiki?`,
            ];
    }
}

export function GraphSidebar({ node, clusterColor, edges, totalNodes, onAsk, onClose }: Props) {
    const [showInfo, setShowInfo] = useState(false);

    if (!node) return null;

    const displayTitle = node.title || node.slug;
    const connections = edges.filter(e => e.from === node.slug || e.to === node.slug).length;
    const density = totalNodes > 1 ? connections / (totalNodes - 1) : 0;
    const connStrength = connections === 0 ? "Isolated"
        : connections < 3 ? "Sparse"
        : density > 0.1 ? "Hub"
        : "Connected";
    const connColor = connections === 0 ? "#ef4444" : connections < 3 ? "#f59e0b" : "#22c55e";

    const hints = generateHints(node);

    return (
        <div className="graph-sidebar">
            <div className="graph-sidebar-header">
                <button className="graph-sidebar-info-btn" onClick={() => setShowInfo(v => !v)} title="About this panel">?</button>
                <button className="graph-sidebar-close" onClick={onClose} aria-label="Close">×</button>
            </div>

            {showInfo && (
                <div className="graph-sidebar-info-box">
                    <p><strong>Node</strong> — a compiled wiki page.</p>
                    <p><strong>Type</strong> — the kind of knowledge (concept, person, event…).</p>
                    <p><strong>State</strong> — lifecycle: active, draft, stale, contradicted, archived.</p>
                    <p><strong>Cluster</strong> — a group of closely related pages detected by the graph algorithm.</p>
                    <p><strong>Connections</strong> — wikilinks to/from this page. Sparse pages may need enrichment.</p>
                    <p className="graph-info-nav"><em>Scroll to zoom · Drag canvas to pan · Drag a node to reposition</em></p>
                </div>
            )}

            <h3 className="graph-sidebar-title" title={node.slug}>{displayTitle}</h3>

            <div className="graph-sidebar-badges">
                <span className={`badge badge-type badge-${node.type}`} title={TYPE_DESC[node.type] || node.type}>{node.type}</span>
                <span className={`badge badge-state badge-${node.state}`} title={STATE_DESC[node.state] || node.state}>{node.state}</span>
            </div>

            <div className="graph-sidebar-meta">
                <div className="graph-meta-row">
                    <span className="graph-meta-label">Cluster</span>
                    <span className="graph-meta-value">
                        <span className="graph-cluster-dot" style={{ background: clusterColor }} />
                        {node.cluster_id}
                    </span>
                </div>
                <div className="graph-meta-row">
                    <span className="graph-meta-label">Connections</span>
                    <span className="graph-meta-value" style={{ color: connColor }}>
                        {connections} <span className="graph-conn-label">({connStrength})</span>
                    </span>
                </div>
            </div>

            {connections < 3 && (
                <p className="graph-sidebar-hint">
                    ⚠ Few connections — this page may need more content or wikilinks.
                </p>
            )}

            <div className="graph-sidebar-hint-list">
                <p className="graph-sidebar-hint-label">Questions to explore:</p>
                {hints.map((h, i) => (
                    <button key={i} className="graph-hint-chip" onClick={() => onAsk(h, hints)}>
                        {h}
                    </button>
                ))}
            </div>

            <button
                className="graph-sidebar-ask-btn"
                onClick={() => onAsk(`Tell me about ${displayTitle}`, hints)}
            >
                Ask about this →
            </button>
        </div>
    );
}
