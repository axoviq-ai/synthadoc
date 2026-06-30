// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Paul Chen / axoviq.com

import { useState, useCallback, useEffect } from "react";
import { useSession } from "./useSession";
import { useSessions } from "./useSessions";
import { getSessionMessages, getHints } from "./api";
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
    const [graphHints, setGraphHints] = useState<string[]>([]);
    const [hintLockLeft, setHintLockLeft] = useState(0);

    // Displayed hints: graph-sourced (pinned) hints take priority while the lock is active
    const displayHints = hintLockLeft > 0 ? graphHints : hints;

    // Called from ChatWindow after each streamed response
    const handleChatHints = useCallback((newHints: string[]) => {
        setHintLockLeft(prev => {
            const next = Math.max(0, prev - 1);
            if (next === 0) updateHints(newHints);
            return next;
        });
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
        setResetKey((k) => k + 1);
    }, [resumeSession, updateHints]);

    const handleQuerySent = useCallback(() => {
        refreshSessions();
    }, [refreshSessions]);

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
                    />
                )}
                {activeTab === "graph" && (
                    <GraphView
                        onAskQuery={(q, nodeHints) => {
                            setInjectedQuery(q);
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
