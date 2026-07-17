// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
import { App, Modal } from "obsidian";

// ── Constants ──────────────────────────────────────────────────────────────────
const CLUSTER_COLORS = [
    "#4e79a7","#f28e2b","#e15759","#76b7b2","#59a14f",
    "#edc948","#b07aa1","#ff9da7","#9c755f","#bab0ac",
];
export const NODE_CAP = 300;
const LABEL_ALWAYS_SHOW = 50;
const LABEL_ZOOM_THRESHOLD = 1.5;
const LABEL_R = 22;
const NODE_R = 8;
const NODE_R_SEL = 12;
const PAD = 56;

// ── Types ─────────────────────────────────────────────────────────────────────
export interface GNode {
    slug: string;
    title: string;
    type: string;
    state: string;
    cluster_id: number;
    x: number;
    y: number;
    vx: number;
    vy: number;
    fx: number | null;
    fy: number | null;
}

export interface GEdge {
    from: string;
    to: string;
    weight: number;
    edge_type: string;
}

export interface CapResult {
    nodes: GNode[];
    edges: GEdge[];
    capped: boolean;
    originalCount: number;
}

export interface TooltipData {
    title: string;
    slug: string;
    type: string;
    state: string;
    cluster_id: number;
    connections: number;
}

export interface FitTransform {
    scale: number;
    tx: number;
    ty: number;
}

export interface LabelPlacement {
    lx: number;
    ly: number;
    anchor: CanvasTextAlign;
}

// ── Pure helpers (exported for unit testing) ──────────────────────────────────

export function truncateLabel(s: string): string {
    return s.length > 15 ? s.slice(0, 14) + "…" : s;
}

export function filterAndCap(
    allNodes: GNode[], allEdges: GEdge[], type: string, cap: number
): CapResult {
    const filtered = type === "all" ? allNodes : allNodes.filter(n => n.type === type);
    const originalCount = filtered.length;
    const capped = originalCount > cap;

    let nodes: GNode[];
    if (capped) {
        const slugSet = new Set(filtered.map(n => n.slug));
        const degree = new Map<string, number>(filtered.map(n => [n.slug, 0]));
        for (const e of allEdges) {
            if (slugSet.has(e.from) && slugSet.has(e.to)) {
                degree.set(e.from, (degree.get(e.from) || 0) + 1);
                degree.set(e.to, (degree.get(e.to) || 0) + 1);
            }
        }
        nodes = [...filtered]
            .sort((a, b) => (degree.get(b.slug) || 0) - (degree.get(a.slug) || 0))
            .slice(0, cap);
    } else {
        nodes = [...filtered];
    }

    const slugSet = new Set(nodes.map(n => n.slug));
    const edges = allEdges.filter(e => slugSet.has(e.from) && slugSet.has(e.to));
    return { nodes, edges, capped, originalCount };
}

export function assembleTooltip(node: GNode, edges: GEdge[]): TooltipData {
    const connections = edges.filter(e => e.from === node.slug || e.to === node.slug).length;
    return {
        title: node.title || node.slug,
        slug: `[[${node.slug}]]`,
        type: node.type || "—",
        state: node.state || "—",
        cluster_id: node.cluster_id,
        connections,
    };
}

export function verletTick(
    nodes: GNode[], edges: GEdge[], cx: number, cy: number, alpha: number
): void {
    const slugMap = new Map<string, GNode>(nodes.map(n => [n.slug, n]));

    // Spring forces (edges — attractive toward rest length 80px)
    for (const e of edges) {
        const s = slugMap.get(e.from), t = slugMap.get(e.to);
        if (!s || !t) continue;
        const dx = t.x - s.x, dy = t.y - s.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = (dist - 80) * 0.02 * alpha;
        const fx = (dx / dist) * force, fy = (dy / dist) * force;
        if (s.fx === null) { s.vx += fx; s.vy += fy; }
        if (t.fx === null) { t.vx -= fx; t.vy -= fy; }
    }

    // Charge repulsion (O(n²) pairwise — fine for n ≤ 300)
    for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
            const a = nodes[i], b = nodes[j];
            const dx = (b.x - a.x) || 0.1, dy = b.y - a.y;
            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
            const force = (-1500 / (dist * dist)) * alpha;
            const fx = (dx / dist) * force, fy = (dy / dist) * force;
            if (a.fx === null) { a.vx += fx; a.vy += fy; }
            if (b.fx === null) { b.vx -= fx; b.vy -= fy; }
        }
    }

    // Center gravity + integrate (with velocity damping)
    for (const n of nodes) {
        if (n.fx !== null) { n.x = n.fx; n.y = n.fy!; continue; }
        n.vx = (n.vx + (cx - n.x) * 0.06 * alpha) * 0.9;
        n.vy = (n.vy + (cy - n.y) * 0.06 * alpha) * 0.9;
        n.x += n.vx;
        n.y += n.vy;
    }
}

export function computeAutoFit(nodes: GNode[], width: number, height: number): FitTransform {
    if (!nodes.length) return { scale: 1, tx: 0, ty: 0 };
    const allX = nodes.map(n => n.x).sort((a, b) => a - b);
    const allY = nodes.map(n => n.y).sort((a, b) => a - b);
    const clip = allX.length >= 8 ? 1 : 0;
    const x0 = allX[clip], x1 = allX[allX.length - 1 - clip];
    const y0 = allY[clip], y1 = allY[allY.length - 1 - clip];
    const bw = Math.max(x1 - x0, 1), bh = Math.max(y1 - y0, 1);
    const scale = Math.min((width - PAD * 2) / bw, (height - PAD * 2) / bh, 2.0);
    const tx = width / 2 - (x0 + bw / 2) * scale;
    const ty = height / 2 - (y0 + bh / 2) * scale;
    return { scale, tx, ty };
}

export function computeLabelPlacement(node: GNode, neighbors: GNode[]): LabelPlacement {
    if (!neighbors.length) {
        return { lx: node.x, ly: node.y + LABEL_R, anchor: "center" };
    }
    let dx = 0, dy = 0;
    for (const n of neighbors) { dx += (n.x - node.x); dy += (n.y - node.y); }
    dx = -(dx / neighbors.length);
    dy = -(dy / neighbors.length);
    const len = Math.sqrt(dx * dx + dy * dy) || 1;
    const ndx = dx / len, ndy = dy / len;
    const anchor: CanvasTextAlign = ndx < -0.3 ? "right" : ndx > 0.3 ? "left" : "center";
    return { lx: node.x + ndx * LABEL_R, ly: node.y + ndy * LABEL_R, anchor };
}

// ── GraphModal placeholder (implemented in Task 3) ───────────────────────────
export class GraphModal extends Modal {
    constructor(app: App, _serverUrl: string) { super(app); }
    onOpen() {}
    onClose() { this.contentEl.empty(); }
}
