// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com

import { useRef, useEffect, useLayoutEffect, useState, useCallback } from "react";
import { MessageBubble } from "./MessageBubble";
import { HintChips } from "./HintChips";
import { Hero } from "./Hero";
import { useQueryStream } from "../useQueryStream";

interface Props {
    sessionId: string | null;
    mode: string;
    hints: string[];
    onHints: (hints: string[]) => void;
    wikiName: string;
    injectedQuery: string | null;
    onInjected: () => void;
    onQuerySent: (question: string) => void;
    showTip: boolean;
}

export function ChatWindow({
    sessionId, mode, hints, onHints, wikiName,
    injectedQuery, onInjected, onQuerySent, showTip,
}: Props) {
    const { messages, streaming, error, send } = useQueryStream(sessionId, onHints);
    const [input, setInput] = useState("");
    const [noCache, setNoCache] = useState(false);
    const messagesRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLTextAreaElement>(null);

    useEffect(() => {
        if (injectedQuery !== null) {
            setInput(injectedQuery);
            onInjected();
            setTimeout(() => inputRef.current?.focus(), 0);
        }
    }, [injectedQuery, onInjected]);

    useLayoutEffect(() => {
        const el = messagesRef.current;
        if (el) el.scrollTop = el.scrollHeight;
    }, [messages]);

    const submit = () => {
        const q = input.trim();
        if (!q) return;
        setInput("");
        send(q, noCache);
        onQuerySent(q);
    };

    const handleChipClick = useCallback((value: string) => {
        send(value, noCache);
        onQuerySent(value);
    }, [send, noCache, onQuerySent]);

    const handleKey = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
    };

    return (
        <div className="chat-window">
            <div className="messages" ref={messagesRef} aria-live="polite">
                {messages.length === 0
                    ? <Hero mode={mode} />
                    : (
                        <div className="messages-list">
                            {messages.map((m) => (
                                <MessageBubble
                                    key={m.id}
                                    msg={m}
                                    wikiName={wikiName}
                                    onChipClick={handleChipClick}
                                />
                            ))}
                        </div>
                    )
                }
                {error && <p className="error-banner" role="alert">{error}</p>}
            </div>
            <div className="input-dock">
                <HintChips hints={hints} onSelect={(h) => setInput(h)} />
                <div className="input-options">
                    <label className="bypass-cache-label">
                        <input
                            type="checkbox"
                            checked={noCache}
                            onChange={(e) => setNoCache(e.target.checked)}
                            disabled={streaming}
                        />
                        Bypass cache
                    </label>
                </div>
                <div className="input-row">
                    <textarea
                        ref={inputRef}
                        className="query-input"
                        aria-label="Ask your wiki"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={handleKey}
                        placeholder="Ask your wiki..."
                        disabled={streaming || !sessionId}
                        rows={2}
                    />
                    <button
                        className="send-btn"
                        aria-label={streaming ? "Sending" : "Ask"}
                        onClick={submit}
                        disabled={streaming || !sessionId || !input.trim()}
                    >
                        {streaming ? "…" : "Ask"}
                    </button>
                </div>
                {showTip && messages.length === 0 && (
                    <p className="input-tip">
                        Tip: Select a recent run from the sidebar to load it into the prompt.
                    </p>
                )}
            </div>
        </div>
    );
}
