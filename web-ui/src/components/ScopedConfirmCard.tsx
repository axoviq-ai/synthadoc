// SPDX-License-Identifier: AGPL-3.0-or-later
import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ScopedEditBlock } from "../api";
import type { Diagnostic } from "@codemirror/lint";
import type { EditorView as EditorViewType } from "@codemirror/view";

interface Props {
    sessionId: string;
    pageSlug: string;
    currentBody: string;
    accumulatedBody: string;
    blocks: ScopedEditBlock[];
    defaultTab: "blocks" | "page";
    headerMessage: string;
    timeoutSeconds?: number;
    rationale?: string;
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

/**
 * Derive inline MD issue strings for display below the editor.
 * Each entry is formatted as "Line N: <description>".
 */
function getMarkdownIssues(text: string): string[] {
    const lines = text.split("\n");
    const issues: string[] = [];
    let openFences = 0;
    let prevHeadingLevel = 0;

    for (let i = 0; i < lines.length; i++) {
        const ln = lines[i];

        // Unclosed fenced code blocks (``` or ~~~)
        if (/^(`{3,}|~{3,})/.test(ln.trim())) {
            openFences++;
        }

        // Unclosed wikilinks on the same line
        const opens = (ln.match(/\[\[/g) ?? []).length;
        const closes = (ln.match(/\]\]/g) ?? []).length;
        if (opens > closes) {
            issues.push(`Line ${i + 1}: Unclosed wikilink [[ without matching ]]`);
        }

        // Heading level skip (nice-to-have)
        const hMatch = ln.match(/^(#{1,6})\s/);
        if (hMatch) {
            const level = hMatch[1].length;
            if (prevHeadingLevel > 0 && level > prevHeadingLevel + 1) {
                issues.push(`Line ${i + 1}: Heading level skip H${prevHeadingLevel} → H${level}`);
            }
            prevHeadingLevel = level;
        }
    }

    if (openFences % 2 !== 0) {
        issues.push(`Unclosed fenced code block (odd number of fence markers)`);
    }

    return issues;
}

/**
 * CodeMirror linter function — returns Diagnostic[] for in-editor
 * gutter markers and squiggles. Mirrors getMarkdownIssues logic.
 */
function markdownLinterFn(view: EditorViewType): Diagnostic[] {
    const diagnostics: Diagnostic[] = [];
    const text = view.state.doc.toString();
    const lines = text.split("\n");
    let openFences = 0;
    let prevHeadingLevel = 0;

    for (let i = 0; i < lines.length; i++) {
        const ln = lines[i];
        const docLine = view.state.doc.line(i + 1);

        if (/^(`{3,}|~{3,})/.test(ln.trim())) {
            openFences++;
        }

        const opens = (ln.match(/\[\[/g) ?? []).length;
        const closes = (ln.match(/\]\]/g) ?? []).length;
        if (opens > closes) {
            diagnostics.push({
                from: docLine.from,
                to: docLine.to,
                severity: "warning",
                message: "Unclosed wikilink: [[ without matching ]]",
            });
        }

        const hMatch = ln.match(/^(#{1,6})\s/);
        if (hMatch) {
            const level = hMatch[1].length;
            if (prevHeadingLevel > 0 && level > prevHeadingLevel + 1) {
                diagnostics.push({
                    from: docLine.from,
                    to: docLine.to,
                    severity: "warning",
                    message: `Heading level skip: H${prevHeadingLevel} → H${level}`,
                });
            }
            prevHeadingLevel = level;
        }
    }

    if (openFences % 2 !== 0) {
        const docLen = text.length;
        diagnostics.push({
            from: Math.max(0, docLen - 1),
            to: Math.max(0, docLen),
            severity: "error",
            message: "Unclosed fenced code block",
        });
    }

    return diagnostics;
}

export default function ScopedConfirmCard({
    accumulatedBody,
    blocks,
    defaultTab,
    headerMessage,
    rationale,
    onDecide,
}: Props) {
    // pageMode: true = manual page edit mode, false = block review mode
    const [pageMode, setPageMode] = useState(defaultTab === "page");
    const [editSubMode, setEditSubMode] = useState<"edit" | "preview">("edit");
    const [includedIds, setIncludedIds] = useState<Set<string>>(
        () => new Set(blocks.filter(b => b.status === "applied").map(b => b.id))
    );
    const [pageBody, setPageBody] = useState(accumulatedBody);
    const [mdIssues, setMdIssues] = useState<string[]>([]);
    const editorRef = useRef<HTMLDivElement>(null);
    const editorViewRef = useRef<unknown>(null);

    const appliedBlocks = blocks.filter(b => b.status === "applied");
    const allUnchecked = appliedBlocks.length > 0 && appliedBlocks.every(b => !includedIds.has(b.id));
    const approveDisabled = !pageMode && allUnchecked;

    // CodeMirror is initialised once on mount and kept alive for the component
    // lifetime. The editor div is always in the DOM (hidden via display:none when
    // not in page+edit mode) so the ref stays stable and the editor is never
    // re-created when toggling modes.
    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const { EditorView } = await import("@codemirror/view");
                const { EditorState } = await import("@codemirror/state");
                const { markdown } = await import("@codemirror/lang-markdown");
                const { linter, lintGutter } = await import("@codemirror/lint");
                if (cancelled || !editorRef.current) return;
                const view = new EditorView({
                    state: EditorState.create({
                        doc: accumulatedBody,
                        extensions: [
                            markdown(),
                            linter(markdownLinterFn),
                            lintGutter(),
                            EditorView.updateListener.of((update) => {
                                if (update.docChanged) {
                                    const newBody = update.state.doc.toString();
                                    setPageBody(newBody);
                                    setMdIssues(getMarkdownIssues(newBody));
                                }
                            }),
                            EditorView.theme({
                                "&": {
                                    background: "var(--bg-secondary)",
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
            (editorViewRef.current as { destroy?: () => void } | null)?.destroy?.();
            editorViewRef.current = null;
        };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const handleApprove = () => {
        if (pageMode) {
            onDecide({ confirmed: true, mode: "page", includedBlockIds: [], pageBody });
        } else {
            onDecide({ confirmed: true, mode: "blocks", includedBlockIds: [...includedIds], pageBody: null });
        }
    };

    const handleReject = () => {
        onDecide({ confirmed: false, mode: "blocks", includedBlockIds: [], pageBody: null });
    };

    const toggleBlock = (id: string) => {
        setIncludedIds(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    return (
        <div className="confirm-card" style={{
            border: "1px solid var(--border, #ccc)",
            borderRadius: 6, padding: "12px 16px", margin: "8px 0",
            background: "var(--bg-secondary)",
        }}>
            {/* Rationale — shown above header when present */}
            {rationale && (
                <div style={{
                    fontSize: "0.78rem",
                    color: "var(--text-muted, #888)",
                    marginBottom: 6,
                }}>
                    {rationale}
                </div>
            )}

            {/* Header */}
            <div style={{ marginBottom: 10, fontWeight: 500 }}>{headerMessage}</div>

            {/* ── Block view — always in DOM; hidden when in page mode ── */}
            <div style={{ display: !pageMode ? undefined : "none" }}>
                <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: 8 }}>
                    Check to include an edit · uncheck to skip it
                </div>
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
                                        color: "var(--diff-del, #ff7b72)",
                                        fontFamily: "var(--font-mono, monospace)",
                                        fontSize: "0.82rem",
                                        whiteSpace: "pre-wrap",
                                        wordBreak: "break-word",
                                    }}>
                                        {block.old_text}
                                    </div>
                                    <div style={{
                                        color: "var(--diff-add, #7ee787)",
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
                {allUnchecked && (
                    <div style={{
                        fontSize: "0.8rem",
                        color: "var(--text-muted, #888)",
                        marginBottom: 8,
                    }}>
                        No edits selected — Approve will make no changes.
                    </div>
                )}
            </div>

            {/* ── Page mode: Edit/Preview toggle — hidden in block mode ── */}
            <div style={{ display: pageMode ? undefined : "none" }}>
                <div style={{ display: "flex", gap: 4, marginBottom: 8 }}>
                    <button
                        onClick={() => setEditSubMode("edit")}
                        style={{
                            padding: "3px 10px",
                            cursor: "pointer",
                            background: editSubMode === "edit" ? "var(--bg-active, #2a2f3e)" : "transparent",
                            border: "1px solid var(--border, #444)",
                            borderRadius: 3,
                            color: "inherit",
                            fontSize: "0.82rem",
                        }}
                    >
                        Edit
                    </button>
                    <button
                        onClick={() => setEditSubMode("preview")}
                        style={{
                            padding: "3px 10px",
                            cursor: "pointer",
                            background: editSubMode === "preview" ? "var(--bg-active, #2a2f3e)" : "transparent",
                            border: "1px solid var(--border, #444)",
                            borderRadius: 3,
                            color: "inherit",
                            fontSize: "0.82rem",
                        }}
                    >
                        Preview
                    </button>
                </div>
            </div>

            {/* ── CodeMirror editor — always in DOM for ref stability.
                 Visible only in page mode + edit sub-mode. ── */}
            <div style={{ display: pageMode && editSubMode === "edit" ? undefined : "none" }}>
                <div
                    ref={editorRef}
                    style={{
                        border: "1px solid var(--border, #444)",
                        borderRadius: 4,
                        minHeight: "220px",
                        overflow: "auto",
                    }}
                />
                {mdIssues.length > 0 && (
                    <div style={{
                        marginTop: 6,
                        fontSize: "0.78rem",
                        color: "var(--diff-del, #ff7b72)",
                    }}>
                        {mdIssues.map((issue, i) => (
                            <div key={i}>{issue}</div>
                        ))}
                    </div>
                )}
            </div>

            {/* ── Preview — rendered Markdown, shown in page mode + preview sub-mode ── */}
            {pageMode && editSubMode === "preview" && (
                <div
                    className="bubble-md"
                    style={{
                        border: "1px solid var(--border, #444)",
                        borderRadius: 4,
                        minHeight: "220px",
                        padding: "8px 12px",
                        overflow: "auto",
                    }}
                >
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{pageBody}</ReactMarkdown>
                </div>
            )}

            {/* ── Reference — collapsed list of applied edits, page mode only ── */}
            {pageMode && appliedBlocks.length > 0 && (
                <details style={{ marginTop: 10, fontSize: "0.8rem", color: "var(--text-muted, #888)" }}>
                    <summary style={{ cursor: "pointer" }}>Reference (applied edits)</summary>
                    <div style={{ paddingTop: 6 }}>
                        {appliedBlocks.map((block, i) => (
                            <div key={block.id} style={{ marginBottom: 4 }}>
                                Edit {i + 1}: <s>{block.old_text}</s> → {block.new_text}
                            </div>
                        ))}
                    </div>
                </details>
            )}

            {/* ── "Edit full page manually" toggle ── */}
            <label style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                marginTop: 10,
                fontSize: "0.85rem",
                cursor: "pointer",
            }}>
                <input
                    type="checkbox"
                    checked={pageMode}
                    onChange={e => setPageMode(e.target.checked)}
                />
                Edit full page manually
            </label>

            {/* ── Action buttons ── */}
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                <button
                    onClick={handleApprove}
                    disabled={approveDisabled}
                    className="confirm-yes-btn"
                    style={{
                        padding: "6px 16px",
                        cursor: approveDisabled ? "not-allowed" : "pointer",
                        opacity: approveDisabled ? 0.5 : 1,
                    }}
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
