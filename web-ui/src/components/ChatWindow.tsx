// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com

import { useRef, useEffect, useState } from "react";
import { MessageBubble } from "./MessageBubble";
import { HintChips } from "./HintChips";
import { useQueryStream } from "../useQueryStream";

interface Props {
    sessionId: string | null;
    hints: string[];
    onHints: (hints: string[]) => void;
}

export function ChatWindow({ sessionId, hints, onHints }: Props) {
    const { messages, streaming, error, send } = useQueryStream(sessionId, onHints);
    const [input, setInput] = useState("");
    const bottomRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    const submit = () => {
        const q = input.trim();
        if (!q) return;
        setInput("");
        send(q);
    };

    const handleKey = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
    };

    return (
        <div className="chat-window">
            <div className="messages" aria-live="polite">
                {messages.map((m, i) => <MessageBubble key={i} msg={m} />)}
                {error && <p className="error-banner" role="alert">{error}</p>}
                <div ref={bottomRef} />
            </div>
            <HintChips hints={hints} onSelect={(h) => { setInput(h); }} />
            <div className="input-row">
                <textarea
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
        </div>
    );
}
