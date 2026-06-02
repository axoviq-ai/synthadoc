// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com

import { useState, useCallback } from "react";
import { streamQuery } from "./api";

export interface Message {
    role: "user" | "assistant";
    text: string;
    citations?: string[];
    gapSuggestions?: string[];
}

export function useQueryStream(sessionId: string | null, onHints: (hints: string[]) => void) {
    const [messages, setMessages] = useState<Message[]>([]);
    const [streaming, setStreaming] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const send = useCallback(async (question: string) => {
        if (!sessionId || streaming) return;
        setError(null);
        setStreaming(true);
        setMessages((prev) => [...prev, { role: "user", text: question }]);

        let partial = "";
        let citations: string[] = [];
        let gapSuggestions: string[] = [];

        // Add placeholder for assistant message
        setMessages((prev) => [...prev, { role: "assistant", text: "" }]);

        await streamQuery(question, sessionId, {
            onToken: (text) => {
                partial += text;
                setMessages((prev) => {
                    const next = [...prev];
                    next[next.length - 1] = { role: "assistant", text: partial };
                    return next;
                });
            },
            onCitations: (c) => { citations = c; },
            onGap: (s) => { gapSuggestions = s; },
            onDone: (nextHints) => {
                setMessages((prev) => {
                    const next = [...prev];
                    next[next.length - 1] = {
                        role: "assistant",
                        text: partial,
                        citations,
                        gapSuggestions,
                    };
                    return next;
                });
                onHints(nextHints);
                setStreaming(false);
            },
            onError: (msg) => {
                setError(msg);
                setMessages((prev) => prev.slice(0, -1)); // remove empty assistant message
                setStreaming(false);
            },
        });
    }, [sessionId, streaming, onHints]);

    return { messages, streaming, error, send };
}
