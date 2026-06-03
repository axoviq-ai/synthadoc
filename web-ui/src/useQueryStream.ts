// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com

import { useState, useCallback, useEffect, useRef } from "react";
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
    const abortRef = useRef<AbortController | null>(null);
    const streamingRef = useRef(false);

    // Cancel any in-flight stream on unmount
    useEffect(() => {
        return () => { abortRef.current?.abort(); };
    }, []);

    const send = useCallback(async (question: string, noCache = false) => {
        if (!sessionId || streamingRef.current) return;
        setError(null);
        setStreaming(true);
        streamingRef.current = true;

        // Cancel any previous in-flight stream
        abortRef.current?.abort();
        const controller = new AbortController();
        abortRef.current = controller;

        setMessages((prev) => [...prev, { role: "user", text: question }]);
        setMessages((prev) => [...prev, { role: "assistant", text: "" }]);

        let partial = "";
        let citations: string[] = [];
        let gapSuggestions: string[] = [];

        try {
            await streamQuery(question, sessionId, {
                onToken: (text) => {
                    if (controller.signal.aborted) return;
                    partial += text;
                    setMessages((prev) => {
                        const next = [...prev];
                        next[next.length - 1] = { role: "assistant", text: partial };
                        return next;
                    });
                },
                onCitations: (c) => { if (!controller.signal.aborted) citations = c; },
                onGap: (s) => { if (!controller.signal.aborted) gapSuggestions = s; },
                onDone: (nextHints) => {
                    if (controller.signal.aborted) return;
                    setMessages((prev) => {
                        const next = [...prev];
                        next[next.length - 1] = { role: "assistant", text: partial, citations, gapSuggestions };
                        return next;
                    });
                    onHints(nextHints);
                    setStreaming(false);
                    streamingRef.current = false;
                },
                onError: (msg) => {
                    if (controller.signal.aborted) return;
                    setError(msg);
                    setMessages((prev) => prev.slice(0, -1));
                    setStreaming(false);
                    streamingRef.current = false;
                },
            }, controller.signal, noCache);
        } catch {
            if (!controller.signal.aborted) {
                setError("Unexpected error");
                setMessages((prev) => prev.slice(0, -1));
                setStreaming(false);
                streamingRef.current = false;
            }
        }
    }, [sessionId, onHints]);

    return { messages, streaming, error, send };
}
