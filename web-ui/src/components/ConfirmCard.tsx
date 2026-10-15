// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
import { useEffect, useRef, useState } from "react";
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

// DiffViewer always renders on the dark --bg-notice (#141826) ground, so we
// use explicit hex values instead of rgba — compositing rgba over a near-black
// background collapses to muddy near-black tones regardless of the alpha.
// Colors chosen to match the Claude Code terminal diff palette:
//   add  #163d24 dark green ground  /  #7ee787 light green text
//   del  #4a1a1c dark red ground    /  #ff7b72 light red text
const LINE_STYLES: Record<DiffLineKind, React.CSSProperties> = {
    add:    { background: "#163d24", color: "#7ee787" },
    del:    { background: "#4a1a1c", color: "#ff7b72" },
    hunk:   { background: "#0d1f38", color: "#58a6ff" },
    header: { background: "transparent", color: "#888" },
    ctx:    { background: "transparent", color: "inherit" },
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

// Countdown becomes visible when this many seconds remain.
const COUNTDOWN_THRESHOLD = 60;

export default function ConfirmCard({
    message, yesLabel, noLabel, onConfirm, onDecline,
    timeoutSeconds = 300, diff,
}: Props) {
    const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const [secsLeft, setSecsLeft] = useState(timeoutSeconds);

    useEffect(() => {
        // Auto-decline timer
        timerRef.current = setTimeout(onDecline, timeoutSeconds * 1000);
        // Countdown ticker — only needs to update when approaching the threshold
        intervalRef.current = setInterval(() => {
            setSecsLeft(s => s - 1);
        }, 1000);
        return () => {
            if (timerRef.current) clearTimeout(timerRef.current);
            if (intervalRef.current) clearInterval(intervalRef.current);
        };
    }, []);

    const dismiss = (confirmed: boolean) => {
        if (timerRef.current) clearTimeout(timerRef.current);
        if (intervalRef.current) clearInterval(intervalRef.current);
        confirmed ? onConfirm() : onDecline();
    };

    const showCountdown = secsLeft > 0 && secsLeft <= COUNTDOWN_THRESHOLD;

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
                    onClick={() => dismiss(true)}
                    className="confirm-yes-btn"
                    style={{ padding: "6px 16px", cursor: "pointer" }}
                >{yesLabel}</button>
                <button
                    onClick={() => dismiss(false)}
                    className="confirm-no-btn"
                    style={{ padding: "6px 16px", cursor: "pointer" }}
                >{noLabel}</button>
            </div>

            {/* Countdown — only visible in the final 60 seconds */}
            {showCountdown && (
                <div style={{
                    fontSize: "0.72rem", color: "var(--text-muted, #888)",
                    marginTop: 6,
                }}>
                    ⏱ Auto-declining in {secsLeft} s
                </div>
            )}
        </div>
    );
}
