// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
    message: string;
    yesLabel: string;
    noLabel: string;
    onConfirm: () => void;
    onDecline: () => void;
    timeoutSeconds?: number;
    /** Unified diff string — rendered as a syntax-highlighted viewer when present. */
    diff?: string;
}

// ── per-line coloring for unified diff output ─────────────────────────────────

type DiffLineKind = "add" | "del" | "hunk" | "header" | "ctx";

function classifyLine(line: string): DiffLineKind {
    if (line.startsWith("@@")) return "hunk";
    if (line.startsWith("---") || line.startsWith("+++")) return "header";
    if (line.startsWith("+")) return "add";
    if (line.startsWith("-")) return "del";
    return "ctx";
}

const LINE_STYLES: Record<DiffLineKind, React.CSSProperties> = {
    add:    { background: "rgba(63,185,80,0.15)",   color: "var(--diff-add,  #3fb950)" },
    del:    { background: "rgba(248,81,73,0.15)",   color: "var(--diff-del,  #f85149)" },
    hunk:   { background: "rgba(88,166,255,0.10)",  color: "var(--diff-hunk, #58a6ff)" },
    header: { background: "transparent",            color: "var(--diff-header, #888)"  },
    ctx:    { background: "transparent",            color: "inherit"                   },
};

function DiffViewer({ diff }: { diff: string }) {
    const lines = diff.split("\n");
    return (
        <div style={{
            maxHeight: 380,
            overflowY: "auto",
            border: "1px solid var(--border, #444)",
            borderRadius: 4,
            fontFamily: "var(--font-mono, monospace)",
            fontSize: "0.78rem",
            lineHeight: 1.55,
            margin: "10px 0",
            background: "var(--bg-notice, #141826)",
        }}>
            {lines.map((line, i) => (
                <div
                    key={i}
                    style={{
                        ...LINE_STYLES[classifyLine(line)],
                        padding: "0 10px",
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word",
                        minHeight: "1.55em",
                    }}
                >
                    {line || " "}
                </div>
            ))}
        </div>
    );
}

// ── card ──────────────────────────────────────────────────────────────────────

export default function ConfirmCard({
    message, yesLabel, noLabel, onConfirm, onDecline,
    timeoutSeconds = 120, diff,
}: Props) {
    const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    useEffect(() => {
        timerRef.current = setTimeout(onDecline, timeoutSeconds * 1000);
        return () => { if (timerRef.current) clearTimeout(timerRef.current); };
    }, []);

    const handleConfirm = () => {
        if (timerRef.current) clearTimeout(timerRef.current);
        onConfirm();
    };
    const handleDecline = () => {
        if (timerRef.current) clearTimeout(timerRef.current);
        onDecline();
    };

    return (
        <div className="confirm-card" style={{
            border: "1px solid var(--border, #ccc)",
            borderRadius: 6, padding: "12px 16px", margin: "8px 0",
            background: "var(--bg-secondary, #1a1f2e)",
        }}>
            {/* Render message as markdown so **bold**, `code`, etc. display correctly */}
            <div className="bubble-md" style={{ marginBottom: diff ? 0 : 10 }}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{message}</ReactMarkdown>
            </div>

            {/* Syntax-highlighted diff viewer — only shown for diff-review confirms */}
            {diff && <DiffViewer diff={diff} />}

            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <button
                    onClick={handleConfirm}
                    className="confirm-yes-btn"
                    style={{ padding: "6px 16px", cursor: "pointer" }}
                >{yesLabel}</button>
                <button
                    onClick={handleDecline}
                    className="confirm-no-btn"
                    style={{ padding: "6px 16px", cursor: "pointer" }}
                >{noLabel}</button>
            </div>
        </div>
    );
}
