// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
import { describe, it, expect } from "vitest";
import {
    truncateLabel,
    filterAndCap,
    assembleTooltip,
    verletTick,
    computeAutoFit,
    computeLabelPlacement,
} from "./graph-modal";
import type { GNode, GEdge } from "./graph-modal";

// ── helpers ───────────────────────────────────────────────────────────────────

function makeNode(slug: string, type = "concept", cluster_id = 0): GNode {
    return { slug, title: slug.replace(/-/g, " "), type, state: "active", cluster_id,
             x: 0, y: 0, vx: 0, vy: 0, fx: null, fy: null };
}

function makeEdge(from: string, to: string, weight = 1, edge_type = "wikilink"): GEdge {
    return { from, to, weight, edge_type };
}

// ── truncateLabel ─────────────────────────────────────────────────────────────

describe("truncateLabel", () => {
    it("returns the string unchanged when <= 15 chars", () => {
        expect(truncateLabel("Short title")).toBe("Short title");
        expect(truncateLabel("Exactly fifteen")).toBe("Exactly fifteen");
    });
    it("truncates to 14 chars + ellipsis when > 15 chars", () => {
        expect(truncateLabel("A longer title than fifteen")).toBe("A longer title…");
    });
    it("handles empty string", () => {
        expect(truncateLabel("")).toBe("");
    });
});

// ── filterAndCap ──────────────────────────────────────────────────────────────

describe("filterAndCap", () => {
    const nodes = [
        makeNode("a", "concept"), makeNode("b", "person"), makeNode("c", "concept"),
        makeNode("d", "event"),   makeNode("e", "concept"),
    ];
    const edges = [
        makeEdge("a", "b"), makeEdge("b", "c"), makeEdge("a", "c"),
        makeEdge("b", "d"),
    ];

    it("returns all nodes when type is 'all' and count <= cap", () => {
        const r = filterAndCap(nodes, edges, "all", 300);
        expect(r.nodes).toHaveLength(5);
        expect(r.capped).toBe(false);
        expect(r.originalCount).toBe(5);
    });

    it("filters to the given type only", () => {
        const r = filterAndCap(nodes, edges, "concept", 300);
        expect(r.nodes.map(n => n.slug)).toEqual(expect.arrayContaining(["a", "c", "e"]));
        expect(r.nodes).toHaveLength(3);
    });

    it("only returns edges where both endpoints are in the filtered set", () => {
        const r = filterAndCap(nodes, edges, "concept", 300);
        // Only a-c edge is in the concept set
        expect(r.edges).toHaveLength(1);
        expect(r.edges[0]).toMatchObject({ from: "a", to: "c" });
    });

    it("caps to top-N by degree when count exceeds cap", () => {
        // a has degree 3 (b,c; b-a; a-c), b has degree 3, c has degree 2, d has 1, e has 0
        // With cap=3, top 3 by degree: a(3), b(3), c(2)  [d and e excluded]
        const r = filterAndCap(nodes, edges, "all", 3);
        expect(r.capped).toBe(true);
        expect(r.originalCount).toBe(5);
        expect(r.nodes).toHaveLength(3);
        const slugs = r.nodes.map(n => n.slug);
        expect(slugs).toContain("a");
        expect(slugs).toContain("b");
        expect(slugs).toContain("c");
    });

    it("filtered edges after capping only reference nodes in the capped set", () => {
        const r = filterAndCap(nodes, edges, "all", 3);
        for (const e of r.edges) {
            const slugs = r.nodes.map(n => n.slug);
            expect(slugs).toContain(e.from);
            expect(slugs).toContain(e.to);
        }
    });
});

// ── assembleTooltip ───────────────────────────────────────────────────────────

describe("assembleTooltip", () => {
    it("counts all edges where the node is source or target", () => {
        const n = makeNode("alan-turing", "person", 2);
        const edges = [makeEdge("alan-turing", "grace-hopper"), makeEdge("eniac", "alan-turing")];
        const tt = assembleTooltip(n, edges);
        expect(tt.connections).toBe(2);
    });

    it("formats slug as [[slug]]", () => {
        const n = makeNode("alan-turing", "person");
        const tt = assembleTooltip(n, []);
        expect(tt.slug).toBe("[[alan-turing]]");
    });

    it("includes all six fields", () => {
        const n = makeNode("grace-hopper", "person", 1);
        n.state = "stale";
        const tt = assembleTooltip(n, []);
        expect(tt.title).toBe("grace hopper");
        expect(tt.type).toBe("person");
        expect(tt.state).toBe("stale");
        expect(tt.cluster_id).toBe(1);
        expect(tt.connections).toBe(0);
    });

    it("falls back to slug when title is empty", () => {
        const n = makeNode("no-title");
        n.title = "";
        const tt = assembleTooltip(n, []);
        expect(tt.title).toBe("no-title");
    });
});

// ── verletTick ────────────────────────────────────────────────────────────────

describe("verletTick", () => {
    it("spring force moves connected nodes closer when they are far apart", () => {
        const a = makeNode("a"); a.x = -200; a.y = 0;
        const b = makeNode("b"); b.x = 200;  b.y = 0;
        verletTick([a, b], [makeEdge("a", "b")], 0, 0, 1);
        // a should move right, b should move left
        expect(a.x).toBeGreaterThan(-200);
        expect(b.x).toBeLessThan(200);
    });

    it("charge repulsion pushes nodes apart when they are very close", () => {
        const a = makeNode("a"); a.x = 0; a.y = 0;
        const b = makeNode("b"); b.x = 5; b.y = 0;
        verletTick([a, b], [], 0, 0, 1);
        // a should move left, b should move right
        expect(a.x).toBeLessThan(0);
        expect(b.x).toBeGreaterThan(5);
    });

    it("center gravity pulls nodes toward (cx, cy)", () => {
        const n = makeNode("a"); n.x = 500; n.y = 500;
        verletTick([n], [], 0, 0, 1);
        // Should move toward (0, 0)
        expect(n.x).toBeLessThan(500);
        expect(n.y).toBeLessThan(500);
    });

    it("pinned nodes (fx/fy set) do not move", () => {
        const n = makeNode("a"); n.x = 100; n.y = 100; n.fx = 100; n.fy = 100;
        verletTick([n], [], 0, 0, 1);
        expect(n.x).toBe(100);
        expect(n.y).toBe(100);
    });

    it("alpha=0 produces no movement (forces scale with alpha)", () => {
        const a = makeNode("a"); a.x = 300; a.y = 0;
        const b = makeNode("b"); b.x = -300; b.y = 0;
        const axBefore = a.x;
        verletTick([a, b], [makeEdge("a", "b")], 0, 0, 0);
        // alpha=0 means no force contribution beyond what's already in velocity
        // velocity starts at 0 so position should be unchanged (within damping)
        expect(Math.abs(a.x - axBefore)).toBeLessThan(1);
    });
});

// ── computeAutoFit ────────────────────────────────────────────────────────────

describe("computeAutoFit", () => {
    it("returns identity-like transform for a single node at center", () => {
        const n = makeNode("a"); n.x = 400; n.y = 300;
        const fit = computeAutoFit([n], 800, 600);
        expect(fit.scale).toBeGreaterThan(0);
        expect(fit.scale).toBeLessThanOrEqual(2.0);
    });

    it("scale <= 2.0 (never zooms in beyond the cap)", () => {
        const nodes = [makeNode("a"), makeNode("b")];
        nodes[0].x = 0; nodes[0].y = 0;
        nodes[1].x = 10; nodes[1].y = 10; // very close together
        const fit = computeAutoFit(nodes, 800, 600);
        expect(fit.scale).toBeLessThanOrEqual(2.0);
    });

    it("clips 1 outlier per axis when n >= 8", () => {
        const nodes = Array.from({ length: 9 }, (_, i) => {
            const n = makeNode(`n${i}`);
            n.x = i * 10; n.y = i * 10;
            return n;
        });
        nodes[8].x = 10000; nodes[8].y = 10000; // extreme outlier
        const fitWithClip = computeAutoFit(nodes, 800, 600);
        // Outlier clipped: scale should be much larger than if outlier forced zoom-out
        expect(fitWithClip.scale).toBeGreaterThan(0.1);
    });

    it("clips outlier at exactly n=8 boundary", () => {
        const nodes = Array.from({ length: 8 }, (_, i) => ({
            slug: `n${i}`, title: `N${i}`, type: "concept", state: "active", cluster_id: 0,
            x: i * 100, y: i * 100, vx: 0, vy: 0, fx: null, fy: null,
        }));
        // With clip=1: uses indices [1..6] for x and y
        const result = computeAutoFit(nodes, 1600, 1200);
        expect(result.scale).toBeGreaterThan(0);
        // Clipped bounding box: x0=100, x1=600 (width 500); y0=100, y1=600 (height 500)
        // Unclipped bounding box: x0=0, x1=700 (width 700); y0=0, y1=700 (height 700)
        const clippedBW = 500;
        const clippedBH = 500;
        const unclippedBW = 700;
        const unclippedBH = 700;
        const clippedScale = Math.min((1600 - 56*2) / clippedBW, (1200 - 56*2) / clippedBH, 2.0);
        const unclippedScale = Math.min((1600 - 56*2) / unclippedBW, (1200 - 56*2) / unclippedBH, 2.0);
        expect(result.scale).toBeCloseTo(clippedScale, 1);
        expect(result.scale).not.toBeCloseTo(unclippedScale, 1);
    });

    it("returns { scale:1, tx:0, ty:0 } for empty array", () => {
        const fit = computeAutoFit([], 800, 600);
        expect(fit).toEqual({ scale: 1, tx: 0, ty: 0 });
    });
});

// ── computeLabelPlacement ─────────────────────────────────────────────────────

describe("computeLabelPlacement", () => {
    it("places label below center when node has no neighbors", () => {
        const n = makeNode("a"); n.x = 100; n.y = 100;
        const lp = computeLabelPlacement(n, []);
        expect(lp.lx).toBe(100);
        expect(lp.ly).toBeGreaterThan(100); // below
        expect(lp.anchor).toBe("center");
    });

    it("places label away from the neighbor centroid", () => {
        const n = makeNode("a"); n.x = 0; n.y = 0;
        const neighbor = makeNode("b"); neighbor.x = 100; neighbor.y = 0; // neighbor to the right
        const lp = computeLabelPlacement(n, [neighbor]);
        // Label should be placed to the LEFT of node (opposite neighbor)
        expect(lp.lx).toBeLessThan(0);
    });

    it("sets anchor to 'right' when label is placed to the left", () => {
        const n = makeNode("a"); n.x = 0; n.y = 0;
        const neighbor = makeNode("b"); neighbor.x = 200; neighbor.y = 0;
        const lp = computeLabelPlacement(n, [neighbor]);
        expect(lp.anchor).toBe("right");
    });

    it("sets anchor to 'left' when label is placed to the right", () => {
        const n = makeNode("a"); n.x = 0; n.y = 0;
        const neighbor = makeNode("b"); neighbor.x = -200; neighbor.y = 0;
        const lp = computeLabelPlacement(n, [neighbor]);
        expect(lp.anchor).toBe("left");
    });
});
