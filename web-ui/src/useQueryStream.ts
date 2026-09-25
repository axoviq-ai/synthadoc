// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com

import { useState, useCallback, useEffect, useRef } from "react";
import { streamQuery, streamCrossWikiQuery, type ConfirmRequestData, type CrossWikiCallbacks } from "./api";

export interface CrossWikiMetaCallbacks {
    onWikisQuerying?: (wikis: string[]) => void;
    onWikisResult?: (responded: string[], offline: string[]) => void;
    onCrossWikiSkipped?: (reason: string) => void;
}

export interface Message {
    id: string;
    role: "user" | "assistant";
    text: string;
    citations?: string[];
    gapSuggestions?: string[];
    type?: "clarify" | "notice";
    candidates?: string[];
    action?: string;
}

export function useQueryStream(
    sessionId: string | null,
    onHints: (hints: string[], prePrompt?: string) => void,
    initialMessages: Message[] = [],
    onComplete?: () => void,
    crossWikiMeta?: CrossWikiMetaCallbacks,
) {
    const [messages, setMessages] = useState<Message[]>(initialMessages);
    const [streaming, setStreaming] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [progressLines, setProgressLines] = useState<string[]>([]);
    const [pendingConfirm, setPendingConfirm] = useState<ConfirmRequestData | null>(null);
    const abortRef = useRef<AbortController | null>(null);
    const streamingRef = useRef(false);
    // RAF handle and accumulated text ref — kept outside send() so they survive re-renders
    const rafRef = useRef<number | null>(null);
    const partialRef = useRef("");
    // Always-current ref for cross-wiki meta callbacks
    const crossWikiMetaRef = useRef<CrossWikiMetaCallbacks | undefined>(undefined);
    crossWikiMetaRef.current = crossWikiMeta;
    // Always-current ref for onComplete so the effect below never has a stale closure
    const onCompleteRef = useRef(onComplete);
    onCompleteRef.current = onComplete;
    // Safety net: fire onComplete whenever streaming transitions true→false,
    // in case the onDone path misses it (e.g. stale useCallback closure).
    const prevStreamingRef = useRef(false);
    useEffect(() => {
        if (prevStreamingRef.current && !streaming) {
            onCompleteRef.current?.();
        }
        prevStreamingRef.current = streaming;
    }, [streaming]);

    // Cancel any in-flight stream and pending RAF flush on unmount
    useEffect(() => {
        return () => {
            abortRef.current?.abort();
            if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
        };
    }, []);

    const send = useCallback(async (question: string, noCache = false, timeoutSeconds?: number, useCrossWiki = false) => {
        if (!sessionId || streamingRef.current) return;
        setError(null);
        setProgressLines([]);
        setStreaming(true);
        streamingRef.current = true;

        // Cancel any pending RAF flush from a previous stream
        if (rafRef.current !== null) { cancelAnimationFrame(rafRef.current); rafRef.current = null; }

        // Cancel any previous in-flight stream
        abortRef.current?.abort();
        const controller = new AbortController();
        abortRef.current = controller;

        setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "user", text: question }]);
        setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "assistant", text: "" }]);

        let partial = "";
        partialRef.current = "";
        let citations: string[] = [];
        let gapSuggestions: string[] = [];
        let crossWikiSkipReason: string | null = null;

        // Strip [GAP] sentinel the LLM may prepend when guard B fires (post-synthesis gap).
        // Also strip outer <answer>...</answer> wrapper emitted by some providers (e.g. MiniMax).
        const stripGap = (s: string) => {
            if (s.startsWith("[GAP]")) s = s.slice(5).replace(/^\n/, "");
            return s.replace(/^\s*<answer>\s*/i, "").replace(/\s*<\/answer>\s*$/i, "");
        };

        // Coalesce rapid token callbacks into one React state update per animation frame.
        // Without this, every token triggers setMessages → full re-render + layout flush.
        const scheduleFlush = () => {
            if (rafRef.current !== null) return; // already scheduled for this frame
            rafRef.current = requestAnimationFrame(() => {
                rafRef.current = null;
                setMessages((prev) => {
                    const next = [...prev];
                    next[next.length - 1] = { ...next[next.length - 1], text: stripGap(partialRef.current) };
                    return next;
                });
            });
        };

        const cancelFlush = () => {
            if (rafRef.current !== null) { cancelAnimationFrame(rafRef.current); rafRef.current = null; }
        };

        // Build common callbacks shared by both stream paths
        const baseCallbacks = {
            onToken: (text: string) => {
                if (controller.signal.aborted) return;
                partial += text;
                partialRef.current = partial;
                scheduleFlush();
            },
            onCitations: (c: string[]) => { if (!controller.signal.aborted) citations = c; },
            onGap: (s: string[]) => { if (!controller.signal.aborted) gapSuggestions = s; },
            onDone: (nextHints: string[], prePrompt?: string) => {
                if (controller.signal.aborted) return;
                cancelFlush(); // final update carries citations + gap, skip the pending token flush
                setMessages((prev) => {
                    const next = [...prev];
                    const last = next[next.length - 1];
                    // Don't overwrite a clarify/notice message — it was already finalised by its handler
                    if (last.type !== "clarify" && last.type !== "notice") {
                        let text = stripGap(partial);
                        if (crossWikiSkipReason !== null) {
                            text += `\n\n*Cross-wiki search skipped: ${crossWikiSkipReason}*`;
                        }
                        next[next.length - 1] = { ...last, text, citations, gapSuggestions };
                    }
                    return next;
                });
                setProgressLines([]);
                onHints(nextHints, prePrompt);
                setStreaming(false);
                streamingRef.current = false;
                onComplete?.();
            },
            onError: (msg: string) => {
                if (controller.signal.aborted) return;
                cancelFlush();
                const displayMsg = msg.toLowerCase().includes("timed out")
                    ? `${msg} Increase the timeout in Settings (⚙).`
                    : msg;
                setError(displayMsg);
                setMessages((prev) => prev.slice(0, -1));
                setStreaming(false);
                streamingRef.current = false;
            },
            onClarify: (data: { prompt: string; candidates: string[]; action: string }) => {
                if (controller.signal.aborted) return;
                cancelFlush();
                // Replace the placeholder assistant message with the clarify message
                setMessages((prev) => {
                    const next = [...prev];
                    next[next.length - 1] = {
                        ...next[next.length - 1],
                        text: data.prompt,
                        type: "clarify" as const,
                        candidates: data.candidates,
                        action: data.action,
                    };
                    return next;
                });
                setStreaming(false);
                streamingRef.current = false;
            },
            onNotice: (text: string) => {
                if (controller.signal.aborted) return;
                // Insert a notice message before the current placeholder
                setMessages((prev) => {
                    const placeholder = prev[prev.length - 1];
                    return [
                        ...prev.slice(0, -1),
                        { id: crypto.randomUUID(), role: "assistant" as const, text, type: "notice" as const },
                        placeholder,
                    ];
                });
            },
            onToolProgress: (data: { tool: string; job_id?: string; message: string }) => {
                if (controller.signal.aborted) return;
                setProgressLines(prev => [...prev, data.message]);
            },
            onConfirmRequest: (data: ConfirmRequestData) => {
                if (controller.signal.aborted) return;
                setPendingConfirm(data);
            },
        };

        try {
            if (useCrossWiki) {
                const cwCallbacks: CrossWikiCallbacks = {
                    ...baseCallbacks,
                    onWikisQuerying: (wikis) => {
                        if (!controller.signal.aborted) crossWikiMetaRef.current?.onWikisQuerying?.(wikis);
                    },
                    onWikisResult: (responded, offline) => {
                        if (!controller.signal.aborted) crossWikiMetaRef.current?.onWikisResult?.(responded, offline);
                    },
                    onCrossWikiSkipped: (reason) => {
                        if (!controller.signal.aborted) {
                            crossWikiSkipReason = reason;
                            crossWikiMetaRef.current?.onCrossWikiSkipped?.(reason);
                        }
                    },
                };
                await streamCrossWikiQuery(question, sessionId, cwCallbacks, controller.signal, timeoutSeconds);
            } else {
                await streamQuery(question, sessionId, baseCallbacks, controller.signal, noCache, timeoutSeconds);
            }
        } catch {
            if (!controller.signal.aborted) {
                cancelFlush();
                setError("Unexpected error");
                setMessages((prev) => prev.slice(0, -1));
                setStreaming(false);
                streamingRef.current = false;
            }
        }
    }, [sessionId, onHints]);

    return { messages, streaming, error, send, progressLines, pendingConfirm, setPendingConfirm };
}
