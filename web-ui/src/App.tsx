// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Paul Chen / axoviq.com

import { useState, useCallback, useEffect, useRef } from "react";
import { useSession } from "./useSession";
import { useSessions } from "./useSessions";
import { getSessionMessages, getHints, getLifecycleStatus } from "./api";
import { Sidebar } from "./components/Sidebar";
import { ChatWindow } from "./components/ChatWindow";
import { GraphView } from "./components/GraphView";
import type { Message } from "./useQueryStream";
import heroBg from "./assets/hero-bg.png";

// How many chat responses to keep graph-sourced hint chips before replacing them.
const GRAPH_HINT_PIN_TURNS = 3;

export default function App() {
    const { session, hints, updateHints, sessionError, resetSession, resumeSession } = useSession();
    const { sessions, refresh: refreshSessions } = useSessions();
    const [resetKey, setResetKey] = useState(0);
    const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
    const [initialMessages, setInitialMessages] = useState<Message[]>([]);
    const [activeTab, setActiveTab] = useState<"chat" | "graph">("chat");
    const [injectedQuery, setInjectedQuery] = useState<string | null>(null);
    const [pendingPrompt, setPendingPrompt] = useState<string | null>(null);
    const [graphHints, setGraphHints] = useState<string[]>([]);
    const [hintLockLeft, setHintLockLeft] = useState(0);

    // Guard: only auto-fill the Ask field once per page load (not on every session reset).
    const initialPromptSetRef = useRef(false);

    // Displayed hints: graph-sourced (pinned) hints take priority while the lock is active
    const displayHints = hintLockLeft > 0 ? graphHints : hints;

    // On initial session load: fetch lifecycle status and pre-fill the Ask field with
    // the most urgent maintenance action (priority: contradicted > stale > orphan).
    // Mirrors the same priority as _build_pre_prompt in query_agent.py.
    useEffect(() => {
        if (!session?.session_id || initialPromptSetRef.current) return;
        initialPromptSetRef.current = true;
        getLifecycleStatus().then((status) => {
            const contradicted = status.contradicted ?? 0;
            const stale = status.stale ?? 0;
            const orphan = status.orphan ?? 0;
            const broken = status.broken_wikilinks ?? 0;
            if (contradicted > 0) {
                const pageWord = contradicted === 1 ? "page" : "pages";
                setPendingPrompt(
                    `${contradicted} ${pageWord} marked contradicted — run the contradiction resolver to fix them interactively?`
                );
            } else if (stale > 0) {
                const pageWord = stale === 1 ? "page" : "pages";
                setPendingPrompt(`Re-ingest ${stale} stale ${pageWord}`);
            } else if (orphan > 0) {
                const pageWord = orphan === 1 ? "page" : "pages";
                setPendingPrompt(`Run orphan resolver for ${orphan} active orphan ${pageWord}`);
            } else if (broken > 0) {
                const linkWord = broken === 1 ? "broken wikilink" : "broken wikilinks";
                setPendingPrompt(`${broken} ${linkWord} detected — scan and fix them?`);
            }
        }).catch(() => {
            // Silently ignore — pre-fill is optional, not critical
        });
    }, [session?.session_id]);

    // Called from ChatWindow after each streamed response
    const handleChatHints = useCallback((newHints: string[], prePrompt?: string) => {
        setHintLockLeft(prev => {
            const next = Math.max(0, prev - 1);
            if (next === 0) updateHints(newHints);
            return next;
        });
        if (prePrompt) {
            setPendingPrompt(prePrompt);
            setInjectedQuery(null);  // mutually exclusive
        }
    }, [updateHints]);

    // Keep the active highlight in sync with the current session (including the initial session on load)
    useEffect(() => {
        if (session?.session_id) setActiveSessionId(session.session_id);
    }, [session?.session_id]);

    const handleNewRun = useCallback(async () => {
        setResetKey((k) => k + 1);
        setInitialMessages([]);
        setActiveSessionId(null);
        setHintLockLeft(0);
        setActiveTab("chat");
        setPendingPrompt(null);
        await resetSession();
    }, [resetSession]);

    const handleSelectSession = useCallback(async (sessionId: string, mode: string) => {
        resumeSession(sessionId, mode);
        const [msgs, hintsResult] = await Promise.allSettled([
            getSessionMessages(sessionId),
            getHints(mode),
        ]);
        const mapped: Message[] = msgs.status === "fulfilled"
            ? msgs.value.map((m) => ({
                id: crypto.randomUUID(),
                role: m.role as "user" | "assistant",
                text: m.content,
                citations: m.citations.length > 0 ? m.citations : undefined,
                gapSuggestions: m.gap_suggestions.length > 0 ? m.gap_suggestions : undefined,
            }))
            : [];
        setInitialMessages(mapped);
        if (hintsResult.status === "fulfilled") updateHints(hintsResult.value);
        setHintLockLeft(0);
        setActiveSessionId(sessionId);
        setActiveTab("chat");
        setPendingPrompt(null);
        setResetKey((k) => k + 1);
    }, [resumeSession, updateHints]);

    const handleQuerySent = useCallback(() => {
        refreshSessions();
    }, [refreshSessions]);

    const handleConfirmDecision = useCallback(async (sessionId: string, confirmed: boolean) => {
        try {
            await fetch(`/action/confirm`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ session_id: sessionId, confirmed }),
            });
        } catch {
            // fire-and-forget; backend times out gracefully
        }
    }, []);

    return (
        <div className="app-layout">
            <Sidebar
                wikiName={session?.wiki_name ?? ""}
                connected={!!session}
                sessions={sessions}
                activeSessionId={activeSessionId}
                onSelectSession={handleSelectSession}
                onNewRun={handleNewRun}
            />
            <main className="main-panel" style={{ backgroundImage: `url(${heroBg})` }}>
                {sessionError && (
                    <p className="error-banner error-banner-top" role="alert">{sessionError}</p>
                )}
                <div className="tab-nav">
                    <button
                        className={`tab-btn${activeTab === "chat" ? " active" : ""}`}
                        onClick={() => setActiveTab("chat")}
                    >
                        Chat
                    </button>
                    <button
                        className={`tab-btn${activeTab === "graph" ? " active" : ""}`}
                        onClick={() => setActiveTab("graph")}
                    >
                        Graph
                    </button>
                </div>
                {activeTab === "chat" && (
                    <ChatWindow
                        key={resetKey}
                        sessionId={session?.session_id ?? null}
                        mode={session?.mode ?? ""}
                        hints={displayHints}
                        onHints={handleChatHints}
                        wikiName={session?.wiki_name ?? ""}
                        injectedQuery={injectedQuery}
                        onInjected={() => setInjectedQuery(null)}
                        onQuerySent={handleQuerySent}
                        showTip={sessions.length > 0}
                        initialMessages={initialMessages}
                        pendingPrompt={pendingPrompt}
                        onPendingPromptConsumed={() => setPendingPrompt(null)}
                        onConfirmDecision={handleConfirmDecision}
                    />
                )}
                {activeTab === "graph" && (
                    <GraphView
                        onAskQuery={(q, nodeHints) => {
                            setInjectedQuery(q);
                            setPendingPrompt(null);
                            if (nodeHints?.length) {
                                setGraphHints(nodeHints);
                                setHintLockLeft(GRAPH_HINT_PIN_TURNS);
                            }
                            setActiveTab("chat");
                        }}
                    />
                )}
            </main>
        </div>
    );
}
