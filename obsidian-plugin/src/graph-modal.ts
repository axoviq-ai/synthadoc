// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
import { App, Modal } from "obsidian";
import { api } from "./api";

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

// ── GraphModal ────────────────────────────────────────────────────────────────
export class GraphModal extends Modal {
    private _raf: number | null = null;
    private _closed = false;
    private _abort: AbortController | null = null;
    private _xClose = false;

    constructor(app: App, _serverUrl: string) {
        super(app);
    }

    // Block Escape-key and outside-click; only allow close via the × button.
    // Also allow Obsidian's programmatic close (vault/workspace teardown) through
    // when the modal container is no longer attached to the document.
    close() {
        if (this._xClose || !document.contains(this.containerEl)) {
            this._xClose = false;
            super.close();
        }
    }

    private _dismiss() { this._xClose = true; this.close(); }

    onOpen() {
        this._closed = false;
        this._abort = new AbortController();
        const sig = this._abort.signal;
        const { contentEl, modalEl } = this;
        contentEl.empty();
        contentEl.style.cssText = "display:flex;flex-direction:column;height:100%;overflow:hidden;padding:0;";
        modalEl.style.width = "clamp(800px, 80vw, 1400px)";
        modalEl.style.height = "clamp(600px, 80vh, 1000px)";

        // Switch to fixed positioning so the panel can be dragged freely.
        // Done in the next animation frame after Obsidian has laid it out.
        requestAnimationFrame(() => {
            if (this._closed) return;
            const r = modalEl.getBoundingClientRect();
            modalEl.style.cssText += ";position:fixed;left:" + r.left + "px;top:" + r.top + "px;margin:0;transform:none;";
        });

        // ── Header (drag handle) ─────────────────────────────────────────────
        const header = contentEl.createDiv();
        header.style.cssText = "display:flex;align-items:center;gap:10px;padding:8px 14px;flex-shrink:0;border-bottom:1px solid rgba(255,255,255,0.08);cursor:move;user-select:none;";
        header.createEl("span", { text: "Knowledge Graph" })
              .style.cssText = "font-weight:600;font-size:14px;";

        const typeSelect = header.createEl("select") as HTMLSelectElement;
        typeSelect.style.cssText = "background:var(--background-secondary);color:var(--text-normal);border:1px solid var(--background-modifier-border);border-radius:4px;padding:2px 6px;font-size:12px;cursor:default;";

        const statsEl = header.createEl("span");
        statsEl.style.cssText = "margin-left:auto;opacity:0.55;font-size:12px;";

        // ── Canvas area ─────────────────────────────────────────────────────
        const canvasWrap = contentEl.createDiv();
        canvasWrap.style.cssText = "flex:1;position:relative;overflow:hidden;background:var(--background-primary);";

        const canvas = canvasWrap.createEl("canvas") as HTMLCanvasElement;
        canvas.style.cssText = "position:absolute;inset:0;width:100%;height:100%;cursor:grab;";

        // Node-cap banner
        const bannerEl = canvasWrap.createEl("div");
        bannerEl.style.cssText = [
            "position:absolute;top:10px;left:50%;transform:translateX(-50%);",
            "background:rgba(253,230,138,0.15);border:1px solid rgba(253,230,138,0.45);",
            "border-radius:6px;padding:4px 14px;font-size:12px;color:#fde68a;",
            "display:none;white-space:nowrap;",
        ].join("");

        // Hover tooltip
        const tooltipEl = canvasWrap.createEl("div");
        tooltipEl.style.cssText = [
            "position:absolute;background:var(--background-secondary);",
            "border:1px solid var(--background-modifier-border);border-radius:6px;",
            "padding:8px 12px;font-size:12px;pointer-events:none;display:none;min-width:160px;",
        ].join("");

        // Loading message
        const loadingEl = canvasWrap.createEl("p", { text: "Loading knowledge graph…" });
        loadingEl.style.cssText = "position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);opacity:0.55;margin:0;";

        // ── Footer — cluster legend ──────────────────────────────────────────
        const footer = contentEl.createDiv();
        footer.style.cssText = "display:flex;flex-wrap:wrap;gap:8px;padding:6px 14px;flex-shrink:0;border-top:1px solid rgba(255,255,255,0.08);font-size:11px;min-height:30px;";

        // ── Simulation state ─────────────────────────────────────────────────
        let allNodes: GNode[] = [];
        let allEdges: GEdge[] = [];
        let currentNodes: GNode[] = [];
        let currentEdges: GEdge[] = [];
        let neighborMap: Map<string, GNode[]> = new Map();
        let selectedSlug: string | null = null;
        let hoverSlug: string | null = null;
        let alpha = 1;
        let scale = 1, offsetX = 0, offsetY = 0;

        // ── Canvas sizing ────────────────────────────────────────────────────
        const canvasSize = (): { w: number; h: number } => {
            const r = canvas.getBoundingClientRect();
            return { w: r.width || 800, h: r.height || 600 };
        };

        let _lastCanvasW = 0, _lastCanvasH = 0;
        const resizeCanvas = () => {
            const { w, h } = canvasSize();
            const dpr = window.devicePixelRatio || 1;
            const pw = Math.round(w * dpr), ph = Math.round(h * dpr);
            if (pw !== _lastCanvasW || ph !== _lastCanvasH) {
                canvas.width = pw; canvas.height = ph;
                _lastCanvasW = pw; _lastCanvasH = ph;
            }
        };

        // ── Draw ─────────────────────────────────────────────────────────────
        const draw = () => {
            resizeCanvas();
            const { w, h } = canvasSize();
            const dpr = window.devicePixelRatio || 1;
            const ctx = canvas.getContext("2d");
            if (!ctx) return;
            ctx.save();
            ctx.scale(dpr, dpr);
            ctx.clearRect(0, 0, w, h);
            ctx.save();
            ctx.translate(offsetX, offsetY);
            ctx.scale(scale, scale);

            // Edges
            const slugMap = new Map(currentNodes.map(n => [n.slug, n]));
            for (const e of currentEdges) {
                const s = slugMap.get(e.from), t = slugMap.get(e.to);
                if (!s || !t) continue;
                ctx.beginPath();
                ctx.moveTo(s.x, s.y);
                ctx.lineTo(t.x, t.y);
                ctx.strokeStyle = "rgba(160,170,220,0.35)";
                ctx.lineWidth = Math.min(4, Math.max(1, Math.sqrt(e.weight)));
                ctx.setLineDash(e.edge_type === "co_source" ? [5, 3] : []);
                ctx.stroke();
            }
            ctx.setLineDash([]);

            const showLabels = currentNodes.length <= LABEL_ALWAYS_SHOW || scale >= LABEL_ZOOM_THRESHOLD;

            // Nodes + labels
            for (const n of currentNodes) {
                const isSel = n.slug === selectedSlug;
                const isHov = n.slug === hoverSlug;
                const dim = selectedSlug !== null && !isSel;
                const r = isSel ? NODE_R_SEL : NODE_R;
                const color = CLUSTER_COLORS[n.cluster_id % CLUSTER_COLORS.length];

                ctx.globalAlpha = dim ? 0.45 : 1;
                ctx.beginPath();
                ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
                ctx.fillStyle = color;
                ctx.fill();
                ctx.strokeStyle = isSel ? "#facc15" : "#fff";
                ctx.lineWidth = isSel ? 3 : 1.5;
                ctx.stroke();

                if (isSel || isHov || showLabels) {
                    const lp = computeLabelPlacement(n, neighborMap.get(n.slug) || []);
                    const label = truncateLabel(n.title || n.slug);
                    ctx.font = "10px sans-serif";
                    ctx.textAlign = lp.anchor;
                    ctx.textBaseline = "middle";
                    ctx.lineWidth = 3;
                    ctx.lineJoin = "round";
                    ctx.strokeStyle = "rgba(5,6,14,0.85)";
                    ctx.globalAlpha = selectedSlug ? (isSel ? 1 : 0.2) : 0.85;
                    ctx.strokeText(label, lp.lx, lp.ly);
                    ctx.fillStyle = "#94a3b8";
                    ctx.fillText(label, lp.lx, lp.ly);
                }
                ctx.globalAlpha = 1;
            }
            ctx.restore();
            ctx.restore();
        };

        // ── Animation loop ───────────────────────────────────────────────────
        const loop = () => {
            if (this._closed) return;
            if (alpha > 0.01) {
                const { w, h } = canvasSize();
                verletTick(currentNodes, currentEdges, w / 2, h / 2, alpha);
                alpha *= 0.95;
                draw();
                this._raf = requestAnimationFrame(loop);
            } else {
                draw();
                this._raf = null; // settled — stop the loop
            }
        };
        const startLoop = () => {
            if (this._raf === null && !this._closed) {
                this._raf = requestAnimationFrame(loop);
            }
        };

        // ── Helpers ──────────────────────────────────────────────────────────
        const buildNeighborMap = () => {
            neighborMap = new Map(currentNodes.map(n => [n.slug, []]));
            const sm = new Map(currentNodes.map(n => [n.slug, n]));
            for (const e of currentEdges) {
                const s = sm.get(e.from), t = sm.get(e.to);
                if (s && t) { neighborMap.get(e.from)!.push(t); neighborMap.get(e.to)!.push(s); }
            }
        };

        const applyFilter = (type: string) => {
            const result = filterAndCap(allNodes, allEdges, type, NODE_CAP);
            currentNodes = result.nodes;
            currentEdges = result.edges;
            selectedSlug = null;
            hoverSlug = null;

            // Seed positions in circle
            const { w, h } = canvasSize();
            const cx = w / 2, cy = h / 2;
            const initR = Math.min(w, h) * 0.35;
            currentNodes.forEach((n, i) => {
                n.x = cx + initR * Math.cos((2 * Math.PI * i) / (currentNodes.length || 1));
                n.y = cy + initR * Math.sin((2 * Math.PI * i) / (currentNodes.length || 1));
                n.vx = 0; n.vy = 0; n.fx = null; n.fy = null;
            });

            buildNeighborMap();

            // 200 offline ticks before first paint
            for (let i = 0; i < 200; i++) {
                verletTick(currentNodes, currentEdges, cx, cy, 1 - i / 200);
            }

            // Auto-fit
            const fit = computeAutoFit(currentNodes, w, h);
            scale = fit.scale; offsetX = fit.tx; offsetY = fit.ty;

            alpha = 0.3; // restart live animation gently

            // Banner
            if (result.capped) {
                const hidden = result.originalCount - NODE_CAP;
                bannerEl.textContent = type === "all"
                    ? `Your wiki has ${result.originalCount} pages — showing the ${NODE_CAP} most connected (${hidden} not displayed). Use the type filter to narrow the view.`
                    : `Filtered to '${type}': ${result.originalCount} pages — showing the ${NODE_CAP} most connected (${hidden} not displayed).`;
                bannerEl.style.display = "block";
            } else {
                bannerEl.style.display = "none";
            }

            statsEl.empty();
            statsEl.appendText(`${currentNodes.length} nodes · ${currentEdges.length} edges`);
            const noteEl = statsEl.createEl("span");
            noteEl.textContent = " (excludes draft and archived nodes)";
            noteEl.style.cssText = "font-size:11px;opacity:0.7;";

            // Cluster legend
            footer.empty();
            const clusters = [...new Set(currentNodes.map(n => n.cluster_id))].sort((a, b) => a - b);
            for (const cid of clusters) {
                const item = footer.createDiv();
                item.style.cssText = "display:flex;align-items:center;gap:4px;opacity:0.7;";
                const dot = item.createEl("span");
                dot.style.cssText = `width:9px;height:9px;border-radius:50%;background:${CLUSTER_COLORS[cid % CLUSTER_COLORS.length]};flex-shrink:0;`;
                item.createEl("span", { text: `Cluster ${cid}` });
            }
        };

        // ── Hit test ─────────────────────────────────────────────────────────
        const hitNode = (clientX: number, clientY: number): GNode | null => {
            const rect = canvas.getBoundingClientRect();
            const cx = (clientX - rect.left - offsetX) / scale;
            const cy = (clientY - rect.top  - offsetY) / scale;
            const hitR = 12 / scale;
            let best: GNode | null = null, bestD = hitR;
            for (const n of currentNodes) {
                const d = Math.sqrt((n.x - cx) ** 2 + (n.y - cy) ** 2);
                if (d < bestD) { bestD = d; best = n; }
            }
            return best;
        };

        // ── Tooltip ──────────────────────────────────────────────────────────
        const showTooltip = (node: GNode, clientX: number, clientY: number) => {
            const tt = assembleTooltip(node, currentEdges);
            tooltipEl.empty();
            const titleEl = tooltipEl.createDiv();
            titleEl.style.cssText = "font-weight:600;margin-bottom:4px;white-space:nowrap;";
            titleEl.textContent = tt.title;
            const slugEl = tooltipEl.createDiv();
            slugEl.style.cssText = "opacity:0.6;font-size:11px;margin-bottom:6px;";
            slugEl.textContent = tt.slug;
            const tbl = tooltipEl.createEl("table");
            tbl.style.cssText = "border-collapse:collapse;width:100%;";
            const rows: [string, string | number][] = [
                ["Type", tt.type], ["State", tt.state],
                ["Cluster", tt.cluster_id], ["Connections", tt.connections],
            ];
            for (const [label, val] of rows) {
                const tr = tbl.createEl("tr");
                const th = tr.createEl("td"); th.style.cssText = "opacity:0.65;padding-right:12px;";
                th.textContent = label;
                const td = tr.createEl("td"); td.textContent = String(val);
            }
            const rect = canvas.getBoundingClientRect();
            tooltipEl.style.display = "block";
            let tx = clientX - rect.left + 14;
            let ty = clientY - rect.top - 10;
            const tw = tooltipEl.offsetWidth || 180, th = tooltipEl.offsetHeight || 100;
            if (tx + tw > rect.width - 6) tx = clientX - rect.left - tw - 14;
            if (ty + th > rect.height - 6) ty = rect.height - th - 6;
            tooltipEl.style.left = `${tx}px`;
            tooltipEl.style.top  = `${ty}px`;
        };

        // ── Pointer / scroll events ──────────────────────────────────────────

        // Wire Obsidian's native close button (added to modalEl before onOpen) to _dismiss()
        // so it can bypass our close() override that blocks Escape and outside-click.
        const nativeClose = modalEl.querySelector(".modal-close-button") as HTMLElement | null;
        if (nativeClose) {
            nativeClose.addEventListener("click", (e) => { e.stopPropagation(); this._dismiss(); }, { signal: sig });
        }

        // Header drag — move the whole panel.
        let panelDrag: { x0: number; y0: number; l0: number; t0: number } | null = null;
        header.addEventListener("mousedown", (e) => {
            if ((e.target as HTMLElement).closest("select,button")) return;
            const r = modalEl.getBoundingClientRect();
            panelDrag = { x0: e.clientX, y0: e.clientY, l0: r.left, t0: r.top };
            e.preventDefault();
        }, { signal: sig });
        document.addEventListener("mousemove", (e) => {
            if (!panelDrag) return;
            const newLeft = panelDrag.l0 + e.clientX - panelDrag.x0;
            const newTop  = panelDrag.t0 + e.clientY - panelDrag.y0;
            // Keep at least 60 px (≈ header height) visible so the panel stays grabbable.
            const margin = 60;
            const w = modalEl.offsetWidth, h = modalEl.offsetHeight;
            modalEl.style.left = Math.max(margin - w, Math.min(window.innerWidth - margin, newLeft)) + "px";
            modalEl.style.top  = Math.max(0, Math.min(window.innerHeight - margin, newTop)) + "px";
        }, { signal: sig });
        document.addEventListener("mouseup", () => { panelDrag = null; }, { signal: sig });

        canvas.addEventListener("wheel", (e) => {
            e.preventDefault();
            const rect = canvas.getBoundingClientRect();
            const mx = e.clientX - rect.left, my = e.clientY - rect.top;
            const prev = scale;
            scale = Math.max(0.2, Math.min(4.0, scale * (e.deltaY < 0 ? 1.1 : 0.9)));
            const ratio = scale / prev;
            offsetX = mx - ratio * (mx - offsetX);
            offsetY = my - ratio * (my - offsetY);
            startLoop();
        }, { passive: false, signal: sig });

        let dragState: {
            type: "pan" | "node";
            startClientX: number; startClientY: number;
            node?: GNode;
        } | null = null;

        canvas.addEventListener("pointerdown", (e) => {
            const node = hitNode(e.clientX, e.clientY);
            if (node) {
                dragState = { type: "node", startClientX: e.clientX, startClientY: e.clientY, node };
                node.fx = node.x; node.fy = node.y;
                alpha = Math.max(alpha, 0.3);
                canvas.style.cursor = "grabbing";
            } else {
                dragState = { type: "pan", startClientX: e.clientX, startClientY: e.clientY };
                canvas.style.cursor = "grabbing";
            }
            canvas.setPointerCapture(e.pointerId);
            startLoop();
        }, { signal: sig });

        canvas.addEventListener("pointermove", (e) => {
            // Hover tooltip
            const hov = hitNode(e.clientX, e.clientY);
            hoverSlug = hov?.slug ?? null;
            if (hov) {
                showTooltip(hov, e.clientX, e.clientY);
                canvas.style.cursor = dragState ? "grabbing" : "pointer";
            } else {
                tooltipEl.style.display = "none";
                canvas.style.cursor = dragState?.type === "pan" ? "grabbing" : "grab";
            }

            if (!dragState) return;
            if (dragState.type === "pan") {
                offsetX += e.clientX - dragState.startClientX;
                offsetY += e.clientY - dragState.startClientY;
                dragState.startClientX = e.clientX;
                dragState.startClientY = e.clientY;
            } else if (dragState.node) {
                const rect = canvas.getBoundingClientRect();
                dragState.node.fx = (e.clientX - rect.left - offsetX) / scale;
                dragState.node.fy = (e.clientY - rect.top  - offsetY) / scale;
                alpha = Math.max(alpha, 0.1);
            }
        }, { signal: sig });

        canvas.addEventListener("pointerup", (e) => {
            if (dragState?.type === "node" && dragState.node) {
                const dx = e.clientX - dragState.startClientX;
                const dy = e.clientY - dragState.startClientY;
                if (Math.sqrt(dx * dx + dy * dy) < 5) {
                    // Click — select/deselect and open page
                    const slug = dragState.node.slug;
                    if (slug === selectedSlug) {
                        selectedSlug = null;
                    } else {
                        selectedSlug = slug;
                        this.app.workspace.openLinkText(slug, "");
                    }
                }
                dragState.node.fx = null;
                dragState.node.fy = null;
            }
            canvas.style.cursor = "grab";
            dragState = null;
        }, { signal: sig });

        canvas.addEventListener("pointercancel", () => {
            if (dragState?.node) { dragState.node.fx = null; dragState.node.fy = null; }
            dragState = null;
        }, { signal: sig });

        // ── Type filter ──────────────────────────────────────────────────────
        typeSelect.addEventListener("change", () => { applyFilter(typeSelect.value); startLoop(); }, { signal: sig });

        // ── Fetch and init ────────────────────────────────────────────────────
        api.graph().then((data: any) => {
            if (this._closed) return;
            loadingEl.remove();

            if (data.status === "computing") {
                const msg = canvasWrap.createEl("p", { text: "Graph is still being computed — open this panel again in a moment." });
                msg.style.cssText = "position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);opacity:0.55;margin:0;text-align:center;";
                return;
            }

            allNodes = (data.nodes as any[]).map((n: any): GNode => ({
                slug: n.slug, title: n.title || n.slug, type: n.type || "concept",
                state: n.state || "active", cluster_id: n.cluster_id ?? 0,
                x: 0, y: 0, vx: 0, vy: 0, fx: null, fy: null,
            }));
            allEdges = (data.edges as any[]).map((e: any): GEdge => ({
                from: e.from, to: e.to, weight: e.weight ?? 1, edge_type: e.edge_type || "wikilink",
            }));

            // Build type dropdown
            const types = ["all", ...Array.from(new Set(allNodes.map(n => n.type))).sort()];
            for (const t of types) {
                const opt = typeSelect.createEl("option", { value: t });
                opt.text = t === "all" ? "All types" : t;
                if (t === "all") opt.selected = true;
            }

            applyFilter("all");
            loop();
        }).catch(() => {
            if (!this._closed) {
                loadingEl.textContent = "Could not load graph — is the server running?";
            }
        });
    }

    onClose() {
        this._closed = true;
        if (this._raf !== null) { cancelAnimationFrame(this._raf); this._raf = null; }
        this._abort?.abort();
        this._abort = null;
        this.contentEl.empty();
    }
}
