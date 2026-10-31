// SPDX-License-Identifier: AGPL-3.0-or-later
import { useState, useEffect, useRef } from "react";
import type { ScopedEditBlock } from "../api";

interface Props {
    sessionId: string;
    pageSlug: string;
    currentBody: string;
    accumulatedBody: string;
    blocks: ScopedEditBlock[];
    defaultTab: "blocks" | "page";
    headerMessage: string;
    timeoutSeconds?: number;
    onDecide: (result: {
        confirmed: boolean;
        mode: "blocks" | "page";
        includedBlockIds: string[];
        pageBody: string | null;
    }) => void;
}

const REJECTION_LABELS: Record<string, string> = {
    no_match: "No match",
    conflict: "Conflict",
    heading_mutation: "Heading change",
    sentence_loss: "Sentence loss",
};

export default function ScopedConfirmCard({
    accumulatedBody,
    blocks,
    defaultTab,
    headerMessage,
    onDecide,
}: Props) {
    const [activeTab, setActiveTab] = useState<"blocks" | "page">(defaultTab);
    const [includedIds, setIncludedIds] = useState<Set<string>>(
        () => new Set(blocks.filter(b => b.status === "applied").map(b => b.id))
    );
    const [pageBody, setPageBody] = useState(accumulatedBody);
    const [pageEdited, setPageEdited] = useState(false);
    const editorRef = useRef<HTMLDivElement>(null);
    const editorViewRef = useRef<unknown>(null);

    useEffect(() => {
        if (activeTab !== "page") return;
        // CodeMirror is initialized asynchronously to avoid issues in SSR/test environments.
        let cancelled = false;
        (async () => {
            try {
                const { EditorView } = await import("@codemirror/view");
                const { EditorState } = await import("@codemirror/state");
                const { markdown } = await import("@codemirror/lang-markdown");
                if (cancelled || !editorRef.current) return;
                const view = new EditorView({
                    state: EditorState.create({
                        doc: accumulatedBody,
                        extensions: [
                            markdown(),
                            EditorView.updateListener.of((update) => {
                                if (update.docChanged) {
                                    setPageBody(update.state.doc.toString());
                                    setPageEdited(true);
                                }
                            }),
                            EditorView.theme({
                                "&": {
                                    background: "var(--bg-secondary, #1a1f2e)",
                                    color: "var(--fg, inherit)",
                                    minHeight: "220px",
                                    fontFamily: "var(--font-mono, monospace)",
                                    fontSize: "0.88rem",
                                },
                            }),
                        ],
                    }),
                    parent: editorRef.current,
                });
                editorViewRef.current = view;
            } catch {
                // CodeMirror may fail in test / non-browser environments; skip gracefully.
            }
        })();
        return () => {
            cancelled = true;
            // The view reference may not be set yet if the async init didn't complete.
            (editorViewRef.current as { destroy?: () => void } | null)?.destroy?.();
            editorViewRef.current = null;
        };
    }, [activeTab, accumulatedBody]);

    const handleApprove = () => {
        if (activeTab === "blocks") {
            onDecide({
                confirmed: true,
                mode: "blocks",
                includedBlockIds: [...includedIds],
                pageBody: null,
            });
        } else {
            onDecide({
                confirmed: true,
                mode: "page",
                includedBlockIds: [],
                pageBody,
            });
        }
    };

    const handleReject = () => {
        onDecide({
            confirmed: false,
            mode: "blocks",
            includedBlockIds: [],
            pageBody: null,
        });
    };

    const toggleBlock = (id: string) => {
        setIncludedIds(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    const pageTabLabel = pageEdited ? "Page (edited)" : "Page";

    return (
        <div className="confirm-card" style={{
            border: "1px solid var(--border, #ccc)",
            borderRadius: 6, padding: "12px 16px", margin: "8px 0",
            background: "var(--bg-secondary, #1a1f2e)",
        }}>
            {/* Header */}
            <div style={{ marginBottom: 10, fontWeight: 500 }}>{headerMessage}</div>

            {/* Tab bar */}
            <div style={{ display: "flex", gap: 4, marginBottom: 12, borderBottom: "1px solid var(--border, #444)" }}>
                <button
                    onClick={() => setActiveTab("blocks")}
                    style={{
                        padding: "4px 12px",
                        cursor: "pointer",
                        background: "transparent",
                        border: "none",
                        fontWeight: activeTab === "blocks" ? 600 : undefined,
                        borderBottom: activeTab === "blocks" ? "2px solid var(--fg, currentColor)" : "2px solid transparent",
                        color: "inherit",
                    }}
                >
                    Blocks
                </button>
                <button
                    onClick={() => setActiveTab("page")}
                    style={{
                        padding: "4px 12px",
                        cursor: "pointer",
                        background: "transparent",
                        border: "none",
                        fontWeight: activeTab === "page" ? 600 : undefined,
                        borderBottom: activeTab === "page" ? "2px solid var(--fg, currentColor)" : "2px solid transparent",
                        color: "inherit",
                    }}
                >
                    {pageTabLabel}
                </button>
            </div>

            {/* Block view */}
            {activeTab === "blocks" && (
                <div>
                    {blocks.length === 0 && (
                        <p style={{ color: "var(--text-muted, #888)", fontSize: "0.85rem" }}>
                            No edit blocks to show.
                        </p>
                    )}
                    {blocks.map(block => (
                        <div key={block.id} style={{
                            marginBottom: 8,
                            padding: "6px 10px",
                            border: "1px solid var(--border, #444)",
                            borderRadius: 4,
                            display: "flex",
                            alignItems: "flex-start",
                            gap: 10,
                        }}>
                            {block.status === "applied" ? (
                                <>
                                    <input
                                        type="checkbox"
                                        checked={includedIds.has(block.id)}
                                        onChange={() => toggleBlock(block.id)}
                                        style={{ marginTop: 4, flexShrink: 0 }}
                                        aria-label={`Include block ${block.id}`}
                                    />
                                    <div style={{ flex: 1 }}>
                                        <div style={{
                                            textDecoration: "line-through",
                                            color: "#ff7b72",
                                            fontFamily: "var(--font-mono, monospace)",
                                            fontSize: "0.82rem",
                                            whiteSpace: "pre-wrap",
                                            wordBreak: "break-word",
                                        }}>
                                            {block.old_text}
                                        </div>
                                        <div style={{
                                            color: "#7ee787",
                                            fontFamily: "var(--font-mono, monospace)",
                                            fontSize: "0.82rem",
                                            whiteSpace: "pre-wrap",
                                            wordBreak: "break-word",
                                        }}>
                                            {block.new_text}
                                        </div>
                                    </div>
                                </>
                            ) : (
                                <>
                                    <input type="checkbox" disabled style={{ marginTop: 4, flexShrink: 0 }} />
                                    <div style={{ flex: 1, opacity: 0.5 }}>
                                        <div style={{
                                            fontFamily: "var(--font-mono, monospace)",
                                            fontSize: "0.82rem",
                                            whiteSpace: "pre-wrap",
                                            wordBreak: "break-word",
                                        }}>
                                            {block.old_text}
                                        </div>
                                    </div>
                                    <span style={{
                                        background: "#555",
                                        color: "#ccc",
                                        fontSize: "0.72rem",
                                        padding: "2px 7px",
                                        borderRadius: 3,
                                        whiteSpace: "nowrap",
                                        flexShrink: 0,
                                    }}>
                                        {REJECTION_LABELS[block.rejection_reason ?? ""] ?? block.rejection_reason ?? "Rejected"}
                                    </span>
                                </>
                            )}
                        </div>
                    ))}
                </div>
            )}

            {/* Page view */}
            {activeTab === "page" && (
                <div>
                    <div style={{
                        fontSize: "0.78rem",
                        color: "var(--text-muted, #888)",
                        marginBottom: 8,
                    }}>
                        Pre-filled with all applied blocks. Edit freely.
                    </div>
                    <div
                        ref={editorRef}
                        style={{
                            border: "1px solid var(--border, #444)",
                            borderRadius: 4,
                            minHeight: "220px",
                            overflow: "auto",
                        }}
                    />
                </div>
            )}

            {/* Action buttons */}
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                <button
                    onClick={handleApprove}
                    className="confirm-yes-btn"
                    style={{ padding: "6px 16px", cursor: "pointer" }}
                >
                    Approve
                </button>
                <button
                    onClick={handleReject}
                    className="confirm-no-btn"
                    style={{ padding: "6px 16px", cursor: "pointer" }}
                >
                    Reject
                </button>
            </div>
        </div>
    );
}
