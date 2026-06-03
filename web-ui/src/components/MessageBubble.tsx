// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Message } from "../useQueryStream";

interface Props { msg: Message; wikiName: string; }

function GapCallout({ suggestions, wikiName }: { suggestions: string[]; wikiName: string }) {
    const [copied, setCopied] = useState(false);
    const wikiFlag = wikiName ? ` -w ${wikiName}` : "";
    const commands = suggestions
        .map((s) => `synthadoc ingest "search for: ${s}"${wikiFlag}`)
        .join("\n");

    const handleCopy = () => {
        navigator.clipboard.writeText(commands).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }).catch(() => {});
    };

    return (
        <div className="bubble-gap-callout">
            <p className="gap-title">💡 Knowledge Gap Detected</p>
            <p className="gap-text">
                Your wiki doesn't have enough on this topic yet. Enrich it with a web search:
            </p>
            <p className="gap-section">
                <strong>From Obsidian:</strong> Open Command Palette (<code>Cmd+P</code> / <code>Ctrl+P</code>)
                {" → "}<strong>Synthadoc: Ingest…</strong>{" → "}Web search tab
            </p>
            <p className="gap-section"><strong>From the terminal:</strong></p>
            <div className="gap-pre-wrap">
                <pre className="gap-pre"><code>{commands}</code></pre>
                <button className="gap-copy-btn" onClick={handleCopy}>
                    {copied ? "Copied!" : "Copy"}
                </button>
            </div>
            <p className="gap-footer">After ingesting, re-run your query to get a richer answer.</p>
        </div>
    );
}

export function MessageBubble({ msg, wikiName }: Props) {
    const isUser = msg.role === "user";
    return (
        <div className={`bubble ${isUser ? "bubble-user" : "bubble-assistant"}`}>
            {isUser
                ? <p className="bubble-text">{msg.text}</p>
                : <div className="bubble-md">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text}</ReactMarkdown>
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
}
