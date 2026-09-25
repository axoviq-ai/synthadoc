// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com

import { useRef, useEffect, useLayoutEffect, useState, useCallback } from "react";
import { MessageBubble } from "./MessageBubble";
import { HintChips } from "./HintChips";
import { Hero } from "./Hero";
import { useQueryStream } from "../useQueryStream";
import type { Message } from "../useQueryStream";
import { SettingsPopover, readTimeoutSetting, readMaxResultsSetting } from "./SettingsPopover";
import ToolProgressBlock from "./ToolProgressBlock";
import ConfirmCard from "./ConfirmCard";
import { CrossWikiToggle } from "./CrossWikiToggle";
import { CrossWikiBar } from "./CrossWikiBar";

const _OPERATION_RE = /\b(run|lint|ingest|resolve|orphan|promote|discard|backup|fix|schedule|archive)\b/i;

interface Props {
    sessionId: string | null;
    mode: string;
    hints: string[];
    onHints: (hints: string[], prePrompt?: string) => void;
    wikiName: string;
    injectedQuery: string | null;
    onInjected: () => void;
    onQuerySent: () => void;
    showTip: boolean;
    initialMessages?: Message[];
    pendingPrompt?: string | null;
    onPendingPromptConsumed?: () => void;
    onConfirmDecision?: (sessionId: string, confirmed: boolean) => void;
    resolvedDark: boolean;
}

export function ChatWindow({
    sessionId, mode, hints, onHints, wikiName,
    injectedQuery, onInjected, onQuerySent, showTip,
    initialMessages = [],
    pendingPrompt, onPendingPromptConsumed, onConfirmDecision,
    resolvedDark,
}: Props) {
    // Cross-wiki state — must be declared before useQueryStream so setters are available
    const [crossWikiEnabled, setCrossWikiEnabled] = useState(() => {
        try { return localStorage.getItem("crossWikiEnabled") === "true"; }
        catch { return false; }
    });
    const [crossWikiToast, setCrossWikiToast] = useState(false);
    const [crossWikiBarState, setCrossWikiBarState] = useState<"idle" | "searching" | "done">("idle");
    const [crossWikiWikis, setCrossWikiWikis] = useState<string[]>([]);
    const [crossWikiResponded, setCrossWikiResponded] = useState<string[]>([]);
    const [crossWikiOffline, setCrossWikiOffline] = useState<string[]>([]);

    const { messages, streaming, error, send, progressLines, pendingConfirm, setPendingConfirm } = useQueryStream(
        sessionId, onHints, initialMessages, onQuerySent,
        {
            onWikisQuerying: (wikis) => { setCrossWikiBarState("searching"); setCrossWikiWikis(wikis); },
            onWikisResult: (responded, offline) => {
                setCrossWikiBarState("done");
                setCrossWikiResponded(responded);
                setCrossWikiOffline(offline);
            },
            onCrossWikiSkipped: () => { setCrossWikiBarState("idle"); },
        },
    );
    const [input, setInput] = useState("");
    const [noCache, setNoCache] = useState(false);
    const [timeoutSeconds, setTimeoutSeconds] = useState(readTimeoutSetting);
    const [maxResults, setMaxResults] = useState(readMaxResultsSetting);
    const [showSettings, setShowSettings] = useState(false);
    const messagesRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLTextAreaElement>(null);

    // Show a brief reminder toast when landing on Chat with cross-wiki already enabled.
    // ChatWindow unmounts/remounts on every tab switch so this fires on each return to Chat.
    useEffect(() => {
        if (crossWikiEnabled) {
            setCrossWikiToast(true);
            const t = setTimeout(() => setCrossWikiToast(false), 5200);
            return () => clearTimeout(t);
        }
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // Focus textarea when the session becomes ready (initial load, new run, session resume)
    useEffect(() => {
        if (sessionId) setTimeout(() => inputRef.current?.focus(), 0);
    }, [sessionId]);

    // Refocus textarea when streaming ends so the user can type the next query immediately
    const prevStreamingRef = useRef(false);
    useEffect(() => {
        if (prevStreamingRef.current && !streaming) {
            setTimeout(() => inputRef.current?.focus(), 0);
        }
        prevStreamingRef.current = streaming;
    }, [streaming]);

    useEffect(() => {
        if (injectedQuery !== null) {
            onInjected();
            send(injectedQuery, noCache, timeoutSeconds);
        }
    }, [injectedQuery, onInjected, send, noCache, timeoutSeconds]);

    useLayoutEffect(() => {
        const el = messagesRef.current;
        if (el) el.scrollTop = el.scrollHeight;
    }, [messages]);

    // Scroll to bottom when the confirm card appears so it's always visible
    useLayoutEffect(() => {
        const el = messagesRef.current;
        if (el && pendingConfirm) el.scrollTop = el.scrollHeight;
    }, [pendingConfirm]);

    // Scroll to bottom as workflow tool_progress lines arrive
    useLayoutEffect(() => {
        const el = messagesRef.current;
        if (el) el.scrollTop = el.scrollHeight;
    }, [progressLines]);

    useEffect(() => {
        if (pendingPrompt != null) {
            setInput(pendingPrompt);
            setTimeout(() => inputRef.current?.focus(), 0);
        }
    }, [pendingPrompt]);

    const submit = () => {
        const q = input.trim();
        if (!q) return;
        setInput("");
        onPendingPromptConsumed?.();
        if (crossWikiEnabled) {
            setCrossWikiBarState("idle");
            setCrossWikiWikis([]);
            setCrossWikiResponded([]);
            setCrossWikiOffline([]);
        }
        send(q, noCache, timeoutSeconds, crossWikiEnabled);
    };

    const handleChipClick = useCallback((value: string) => {
        onPendingPromptConsumed?.();
        send(value, noCache, timeoutSeconds, crossWikiEnabled);
    }, [send, noCache, timeoutSeconds, onPendingPromptConsumed, crossWikiEnabled]);

    const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey) {
            e.preventDefault();
            submit();
        } else if (e.key === "Enter" && e.ctrlKey) {
            e.preventDefault();
            const ta = e.currentTarget;
            const start = ta.selectionStart;
            const end = ta.selectionEnd;
            const next = input.slice(0, start) + "\n" + input.slice(end);
            setInput(next);
            requestAnimationFrame(() => { ta.selectionStart = ta.selectionEnd = start + 1; });
        }
    };

    return (
        <div className="chat-window">
            <CrossWikiBar
                state={crossWikiBarState}
                wikis={crossWikiWikis}
                responded={crossWikiResponded}
                offline={crossWikiOffline}
            />
            <div className="messages" ref={messagesRef} aria-live="polite">
                {messages.length === 0
                    ? <Hero mode={mode} resolvedDark={resolvedDark} />
                    : (
                        <div className="messages-list">
                            {messages.map((m) => (
                                <MessageBubble
                                    key={m.id}
                                    msg={m}
                                    wikiName={wikiName}
                                    maxResults={maxResults}
                                    onChipClick={handleChipClick}
                                />
                            ))}
                        </div>
                    )
                }
                {progressLines.length > 0 && (
                    <ToolProgressBlock lines={progressLines} collapsed={!streaming} />
                )}
                {pendingConfirm && (
                    <ConfirmCard
                        message={pendingConfirm.message}
                        yesLabel={pendingConfirm.yes_label}
                        noLabel={pendingConfirm.no_label}
                        diff={pendingConfirm.diff}
                        timeoutSeconds={pendingConfirm.timeout_seconds}
                        onConfirm={() => {
                            setPendingConfirm(null);
                            onConfirmDecision?.(pendingConfirm.session_id, true);
                        }}
                        onDecline={() => {
                            setPendingConfirm(null);
                            onConfirmDecision?.(pendingConfirm.session_id, false);
                        }}
                    />
                )}
                {error && <p className="error-banner" role="alert">{error}</p>}
            </div>
            <div className="input-dock">
                <HintChips hints={hints} onSelect={(h) => { setInput(h); setTimeout(() => inputRef.current?.focus(), 0); }} />
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
                    <div className="settings-anchor">
                        <button
                            className="settings-gear-btn"
                            aria-label="Settings"
                            aria-expanded={showSettings}
                            onClick={() => setShowSettings((s) => !s)}
                        >
                            ⚙
                        </button>
                        {showSettings && (
                            <SettingsPopover
                                timeoutSeconds={timeoutSeconds}
                                onChangeTimeout={setTimeoutSeconds}
                                maxResults={maxResults}
                                onChangeMaxResults={setMaxResults}
                                onClose={() => setShowSettings(false)}
                            />
                        )}
                    </div>
                </div>
                {crossWikiToast && (
                    <div className="cross-wiki-landing-toast">
                        🌐 Cross-wiki search is ON — your queries will search across all wikis
                    </div>
                )}
                <div className="input-row">
                    <textarea
                        ref={inputRef}
                        className="query-input"
                        aria-label="Ask your wiki"
                        value={input}
                        onChange={(e) => {
                            setInput(e.target.value);
                            if (e.target.value === "" && onPendingPromptConsumed) {
                                onPendingPromptConsumed();
                            }
                        }}
                        onKeyDown={handleKey}
                        placeholder="Ask your wiki..."
                        disabled={streaming || !sessionId}
                        rows={2}
                    />
                    <CrossWikiToggle
                        enabled={crossWikiEnabled}
                        onChange={(val) => {
                            setCrossWikiEnabled(val);
                            try { localStorage.setItem("crossWikiEnabled", String(val)); } catch { /* ignore */ }
                            if (!val) setCrossWikiBarState("idle");
                        }}
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
                {crossWikiEnabled && _OPERATION_RE.test(input) && (
                    <p className="cross-wiki-operation-hint">
                        Note: Operation commands work on the current wiki only.
                    </p>
                )}
                <p className="input-keyboard-hint">
                    Enter or click "Ask" to send · Shift+Enter or Ctrl+Enter for new line
                </p>
                {initialMessages.length > 0 && messages.length === initialMessages.length && (
                    <p className="session-resume-tip">
                        Session restored — type a follow-up to continue this conversation.
                    </p>
                )}
                {showTip && messages.length === 0 && (
                    <p className="input-tip">
                        Tip: Select a recent run from the sidebar to load it into the prompt.
                    </p>
                )}
            </div>
        </div>
    );
}
