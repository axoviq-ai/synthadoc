// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com

import { memo, useState, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Message } from "../useQueryStream";

interface Props { msg: Message; wikiName?: string; onChipClick?: (value: string) => void; }

type EnrichState = "idle" | "loading" | "done" | "error";

const _IS_URL = /^https?:\/\//i;

function shortUrl(url: string): string {
    try { return new URL(url).hostname.replace(/^www\./, "") + new URL(url).pathname; }
    catch { return url; }
}

function GapCallout({ suggestions, wikiName }: { suggestions: string[]; wikiName?: string }) {
    const [copied, setCopied] = useState(false);
    const [enrichStates, setEnrichStates] = useState<EnrichState[]>(() => suggestions.map(() => "idle"));
    const wikiFlag = wikiName ? ` -w ${wikiName}` : "";
    const commands = suggestions
        .map((s) => _IS_URL.test(s)
            ? `synthadoc ingest "${s}"${wikiFlag}`
            : `synthadoc ingest "search for: ${s}"${wikiFlag}`)
        .join("\n");

    const handleCopy = () => {
        navigator.clipboard.writeText(commands).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }).catch(() => {});
    };

    const handleEnrich = async (s: string, idx: number) => {
        const source = _IS_URL.test(s) ? s : `search for: ${s}`;
        setEnrichStates(prev => { const next = [...prev]; next[idx] = "loading"; return next; });
        try {
            const resp = await fetch("/jobs/ingest", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ source }),
            });
            setEnrichStates(prev => { const next = [...prev]; next[idx] = resp.ok ? "done" : "error"; return next; });
        } catch {
            setEnrichStates(prev => { const next = [...prev]; next[idx] = "error"; return next; });
        }
    };

    return (
        <div className="bubble-gap-callout">
            <p className="gap-title">💡 Knowledge Gap Detected</p>
            <p className="gap-text">
                Your wiki doesn't have enough on this topic yet. Click to ingest:
            </p>
            <ul className="gap-suggestions">
                {suggestions.map((s, i) => {
                    const state = enrichStates[i] ?? "idle";
                    const isUrl = _IS_URL.test(s);
                    return (
                        <li key={i} className="gap-suggestion-row">
                            {isUrl
                                ? <span className="gap-suggestion-type gap-type-url">URL</span>
                                : <span className="gap-suggestion-type gap-type-search">search</span>}
                            <code className="gap-suggestion-cmd" title={s}>
                                {isUrl ? shortUrl(s) : s}
                            </code>
                            <button
                                className={`gap-enrich-btn gap-enrich-${state}`}
                                onClick={() => handleEnrich(s, i)}
                                disabled={state !== "idle"}
                            >
                                {state === "idle" ? (isUrl ? "Ingest" : "Enrich") :
                                 state === "loading" ? "…" :
                                 state === "done" ? "Queued ✓" : "Failed"}
                            </button>
                        </li>
                    );
                })}
            </ul>
            <details className="gap-cli-details">
                <summary className="gap-section">Run from terminal instead</summary>
                <div className="gap-pre-wrap">
                    <pre className="gap-pre"><code>{commands}</code></pre>
                    <button className="gap-copy-btn" onClick={handleCopy}>
                        {copied ? "Copied!" : "Copy"}
                    </button>
                </div>
            </details>
            <p className="gap-footer">After ingesting, re-run your query to get a richer answer.</p>
        </div>
    );
}

// Fenced code block wrapper with a one-click copy button
function PreBlock({ children }: { children?: React.ReactNode }) {
    const [copied, setCopied] = useState(false);
    const preRef = useRef<HTMLPreElement>(null);
    const copy = () => {
        const text = preRef.current?.textContent ?? "";
        navigator.clipboard.writeText(text).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }).catch(() => {});
    };
    return (
        <div className="code-block-wrap">
            <pre ref={preRef}>{children}</pre>
            <button className="code-copy-btn" onClick={copy} title="Copy to clipboard">
                {copied ? "✓" : "Copy"}
            </button>
        </div>
    );
}

// Escape CLI-style placeholders like <schedule-id> or <wiki-name> that appear
// outside code spans. ReactMarkdown v10 drops unknown HTML tags silently, making
// these placeholders invisible. We only target hyphenated names (not <br>, <em>, etc).
// Content inside fenced code blocks (```...```) or inline code (`...`) is left
// verbatim — the <code> element renders angle brackets correctly without escaping.
function escapePlaceholders(text: string): string {
    const PLACEHOLDER = /<([a-z][a-z0-9]*(?:-[a-z0-9]+)+)>/g;
    const CODE_RE = /```[\s\S]*?```|`[^`]*`/g;
    const parts: string[] = [];
    let cursor = 0;
    let m: RegExpExecArray | null;
    while ((m = CODE_RE.exec(text)) !== null) {
        parts.push(text.slice(cursor, m.index).replace(PLACEHOLDER, "&lt;$1&gt;"));
        parts.push(m[0]);
        cursor = m.index + m[0].length;
    }
    parts.push(text.slice(cursor).replace(PLACEHOLDER, "&lt;$1&gt;"));
    return parts.join("");
}

function ClarifyBubble({
    content,
    candidates,
    onChipClick,
}: {
    content: string;
    candidates: string[];
    onChipClick?: (value: string) => void;
}) {
    return (
        <div className="clarify-bubble">
            <p className="clarify-header">{content}</p>
            {candidates.length > 0 && (
                <div className="chip-list">
                    {candidates.map((c, i) => (
                        <button key={c} className="chip" onClick={() => onChipClick?.(c)}>
                            {i + 1}. {c}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}

function NoticeBubble({ content }: { content: string }) {
    return <div className="notice-bubble">{content}</div>;
}

const CLARIFY_ACTION_VERB: Record<string, string> = {
    lifecycle_activate: "Activate",
    lifecycle_archive:  "Archive",
    lifecycle_restore:  "Restore",
};

export const MessageBubble = memo(function MessageBubble({ msg, wikiName, onChipClick }: Props) {
    const isUser = msg.role === "user";

    if (msg.type === "clarify") {
        const verb = CLARIFY_ACTION_VERB[msg.action ?? ""];
        const handleClarifyChip = (slug: string) =>
            onChipClick?.(verb ? `${verb} ${slug}` : slug);
        return <ClarifyBubble content={msg.text} candidates={msg.candidates ?? []} onChipClick={handleClarifyChip} />;
    }
    if (msg.type === "notice") {
        return <NoticeBubble content={msg.text} />;
    }

    return (
        <div className={`bubble ${isUser ? "bubble-user" : "bubble-assistant"}`}>
            {isUser
                ? <p className="bubble-text">{msg.text}</p>
                : !msg.text
                    ? (
                        <div className="bubble-thinking" aria-label="Synthadoc is thinking">
                            <span /><span /><span />
                        </div>
                    )
                    : <div className="bubble-md">
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ pre: PreBlock }}>
                            {escapePlaceholders(msg.text)}
                        </ReactMarkdown>
                      </div>
            }
            {msg.citations && msg.citations.length > 0 && (
                <p className="bubble-citations">
                    Sources: {msg.citations.map((c) => `[[${c}]]`).join(", ")}
                </p>
            )}
            {msg.gapSuggestions && msg.gapSuggestions.length > 0 && (
                <GapCallout suggestions={msg.gapSuggestions} wikiName={wikiName} />
            )}
        </div>
    );
});
