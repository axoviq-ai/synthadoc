// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
import { describe, it, expect } from "vitest";

// We will import the function once it exists; for now the import will fail.
// Add the function export to MessageBubble.tsx before running these tests.
import { obsidianCitationsToGfm, wikilinksToGfm } from "./MessageBubble";

describe("obsidianCitationsToGfm", () => {
    it("transforms a single citation to GFM footnote", () => {
        const input = "Some text.^[source.md:1-3] More text.";
        const out = obsidianCitationsToGfm(input);
        expect(out).toContain("[^1]");
        expect(out).toContain("[^1]: source.md:1-3");
    });

    it("deduplicates repeated same citation", () => {
        const input = "^[f.md:1-3] and again ^[f.md:1-3]";
        const out = obsidianCitationsToGfm(input);
        // Should have exactly one footnote definition
        const defs = out.match(/\[\^1\]:/g);
        expect(defs?.length).toBe(1);
        expect(out.match(/\[\^1\]/g)?.length).toBeGreaterThanOrEqual(2);
    });

    it("assigns sequential numbers to distinct citations", () => {
        const input = "^[a.md:1-2] then ^[b.md:3-4]";
        const out = obsidianCitationsToGfm(input);
        expect(out).toContain("[^1]");
        expect(out).toContain("[^2]");
        expect(out).toContain("[^1]: a.md:1-2");
        expect(out).toContain("[^2]: b.md:3-4");
    });

    it("returns text unchanged when no citations present", () => {
        const input = "plain text with no markers";
        expect(obsidianCitationsToGfm(input)).toBe(input);
    });

    it("handles empty string", () => {
        expect(obsidianCitationsToGfm("")).toBe("");
    });

    it("handles citation at the very start", () => {
        const input = "^[f.md:1-1] text after";
        const out = obsidianCitationsToGfm(input);
        expect(out).toContain("[^1]");
    });

    it("handles citation at the very end", () => {
        const input = "text before ^[f.md:2-5]";
        const out = obsidianCitationsToGfm(input);
        expect(out).toContain("[^1]");
        expect(out).toContain("[^1]: f.md:2-5");
    });
});

describe("wikilinksToGfm", () => {
    it("converts cross-wiki [[wiki::Title]] to bold wiki tag + title", () => {
        const out = wikilinksToGfm("See [[fernway-product::Smart Alerts]] for details.");
        expect(out).toBe("See **[fernway-product]** Smart Alerts for details.");
    });

    it("converts same-wiki [[Title]] to bold title", () => {
        const out = wikilinksToGfm("Read [[Ada Lovelace]] for context.");
        expect(out).toBe("Read **Ada Lovelace** for context.");
    });

    it("handles multiple wikilinks in one string", () => {
        const out = wikilinksToGfm("[[a::B]] and [[C]]");
        expect(out).toContain("**[a]** B");
        expect(out).toContain("**C**");
    });

    it("leaves content inside inline code spans untouched", () => {
        const input = "try `[[wiki::Page]]` literally";
        const out = wikilinksToGfm(input);
        expect(out).toBe(input);
    });

    it("leaves content inside fenced code blocks untouched", () => {
        const input = "```\n[[wiki::Page]]\n```";
        const out = wikilinksToGfm(input);
        expect(out).toBe(input);
    });

    it("returns unchanged text when no wikilinks present", () => {
        const input = "plain answer with no links";
        expect(wikilinksToGfm(input)).toBe(input);
    });

    it("handles empty string", () => {
        expect(wikilinksToGfm("")).toBe("");
    });
});
