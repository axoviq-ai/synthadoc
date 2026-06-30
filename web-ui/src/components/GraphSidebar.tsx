// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
interface GraphNode {
    slug: string; title: string; type: string; state: string; cluster_id: number;
}
interface Props {
    node: GraphNode | null;
    onAsk: (query: string) => void;
    onClose: () => void;
}
export function GraphSidebar({ node, onAsk, onClose }: Props) {
    if (!node) return null;
    return (
        <div className="graph-sidebar">
            <button className="graph-sidebar-close" onClick={onClose} aria-label="Close">×</button>
            <h3 className="graph-sidebar-title">{node.title}</h3>
            <div className="graph-sidebar-badges">
                <span className={`badge badge-type badge-${node.type}`}>{node.type}</span>
                <span className={`badge badge-state badge-${node.state}`}>{node.state}</span>
            </div>
            <p className="graph-sidebar-cluster">Cluster {node.cluster_id}</p>
            <button
                className="graph-sidebar-ask-btn"
                onClick={() => onAsk(`Tell me about ${node.title}`)}
            >
                Ask about this →
            </button>
        </div>
    );
}
