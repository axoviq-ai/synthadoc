// @vitest-environment happy-dom
// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, waitFor, fireEvent } from "@testing-library/react";
import { GraphView, CLUSTER_VIEW_MIN_NODES } from "./GraphView";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const node = (slug: string, cluster_id = 0) => ({ slug, title: slug.toUpperCase(), type: "concept", state: "active", cluster_id });

function overview(nodeCount: number) {
    return {
        status: "ready", node_count: nodeCount, edge_count: 3, cluster_count: 2,
        clusters: [
            { id: 0, size: nodeCount - 1, label: "Alpha · Beta", top_pages: [], types: { concept: nodeCount - 1 } },
            { id: 1, size: 1, label: "Gamma", top_pages: [], types: { concept: 1 } },
        ],
        links: [{ from: 0, to: 1, weight: 2, count: 1 }],
    };
}

/** Stub fetch with a response per URL; records the URLs requested. */
function stubFetch(responses: Record<string, unknown>) {
    const urls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
        urls.push(url);
        return { ok: true, json: async () => responses[url] } as Response;
    }));
    return urls;
}

describe("GraphView", () => {
    it("draws every page for a small wiki", async () => {
        const urls = stubFetch({
            "/graph?view=clusters": overview(3),
            "/graph": { status: "ready", nodes: [node("a"), node("b"), node("c", 1)], edges: [] },
        });
        render(<GraphView onAskQuery={vi.fn()} />);
        await waitFor(() => expect(screen.getByText(/3 nodes · 0 edges/)).toBeDefined());
        expect(urls).toEqual(["/graph?view=clusters", "/graph"]);
        // The legend names clusters after their main pages, like the overview does.
        expect(screen.getByText("Alpha · Beta")).toBeDefined();
        expect(screen.getByText("Gamma")).toBeDefined();
        expect(screen.queryByText("Cluster 1")).toBeNull();
        expect(screen.queryByText("← All clusters")).toBeNull();
    });

    it("opens a large wiki on the cluster overview without loading every page", async () => {
        const urls = stubFetch({ "/graph?view=clusters": overview(CLUSTER_VIEW_MIN_NODES + 1) });
        render(<GraphView onAskQuery={vi.fn()} />);
        await waitFor(() => expect(screen.getByText(/2 clusters — click a cluster to explore it/)).toBeDefined());
        expect(urls).toEqual(["/graph?view=clusters"]);
        expect(document.querySelectorAll("circle.graph-cluster").length).toBe(2);
        expect(screen.queryByLabelText("Filter by type")).toBeNull();
    });

    it("drills into a cluster and back", async () => {
        const urls = stubFetch({
            "/graph?view=clusters": overview(CLUSTER_VIEW_MIN_NODES + 1),
            "/graph?cluster=0": { status: "ready", cluster_id: 0,
                                  nodes: [{ ...node("a"), degree: 5 }, { ...node("b"), degree: 1 }],
                                  edges: [{ from: "a", to: "b", weight: 1, edge_type: "wikilink" }] },
        });
        render(<GraphView onAskQuery={vi.fn()} />);
        await waitFor(() => expect(document.querySelectorAll("circle.graph-cluster").length).toBe(2));

        fireEvent.click(document.querySelectorAll("circle.graph-cluster")[0]);
        await waitFor(() => expect(screen.getByText(/Alpha · Beta — 2 pages · 1 strongest links/)).toBeDefined());
        expect(urls).toContain("/graph?cluster=0");

        fireEvent.click(screen.getByText("← All clusters"));
        await waitFor(() => expect(screen.getByText(/click a cluster to explore it/)).toBeDefined());
    });

    it("lists clusters by name under the overview, and opens one from the list", async () => {
        const urls = stubFetch({
            "/graph?view=clusters": overview(CLUSTER_VIEW_MIN_NODES + 1),
            "/graph?cluster=1": { status: "ready", cluster_id: 1, nodes: [{ ...node("g", 1), degree: 0 }], edges: [] },
        });
        render(<GraphView onAskQuery={vi.fn()} />);
        const list = await screen.findByLabelText("Clusters");
        expect(list.textContent).toBe(`Alpha · Beta${CLUSTER_VIEW_MIN_NODES}Gamma1`);   // largest first, with sizes
        expect(screen.queryByText("Cluster 0")).toBeNull();

        fireEvent.click(screen.getByTitle("Gamma — 1 pages"));
        await waitFor(() => expect(screen.getByText(/Gamma — 1 pages · 0 strongest links/)).toBeDefined());
        expect(urls).toContain("/graph?cluster=1");
        expect(screen.queryByLabelText("Clusters")).toBeNull();
    });

    it("keeps polling while the graph is being built", async () => {
        vi.useFakeTimers({ shouldAdvanceTime: true });
        let calls = 0;
        vi.stubGlobal("fetch", vi.fn(async () => {
            calls += 1;
            return { ok: true, json: async () => (calls === 1 ? { status: "computing" } : overview(CLUSTER_VIEW_MIN_NODES + 1)) } as Response;
        }));
        render(<GraphView onAskQuery={vi.fn()} />);
        await waitFor(() => expect(screen.getByText("Building knowledge graph…")).toBeDefined());
        await vi.advanceTimersByTimeAsync(2100);
        await waitFor(() => expect(screen.getByText(/click a cluster to explore it/)).toBeDefined());
        vi.useRealTimers();
    });

    it("falls back to cluster numbers when the summary has no names", async () => {
        stubFetch({
            "/graph?view=clusters": { ...overview(2), clusters: [] },
            "/graph": { status: "ready", nodes: [node("a"), node("b", 1)], edges: [] },
        });
        render(<GraphView onAskQuery={vi.fn()} />);
        await waitFor(() => expect(screen.getByText("Cluster 1")).toBeDefined());
        expect(screen.getByText("Cluster 0")).toBeDefined();
    });

    it("names the selected page's cluster in the side panel", async () => {
        stubFetch({
            "/graph?view=clusters": overview(3),
            "/graph": { status: "ready", nodes: [node("a"), node("b"), node("c", 1)], edges: [] },
        });
        render(<GraphView onAskQuery={vi.fn()} />);
        await waitFor(() => expect(document.querySelectorAll("svg circle").length).toBe(3));
        fireEvent.click(document.querySelectorAll("svg circle")[2]);     // page "c", cluster 1
        await waitFor(() => expect(document.querySelector(".graph-meta-cluster-name")?.textContent).toBe("Gamma"));
    });
});
