// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com

import { useRef, useEffect, useLayoutEffect, useState, useCallback } from "react";
import { MessageBubble } from "./MessageBubble";
import { HintChips } from "./HintChips";
import { Hero } from "./Hero";
import { useQueryStream } from "../useQueryStream";
import type { Message } from "../useQueryStream";
import { SettingsPopover, readTimeoutSetting } from "./SettingsPopover";

interface Props {
    sessionId: string | null;
    mode: string;
    hints: string[];
    onHints: (hints: string[]) => void;
    wikiName: string;
    injectedQuery: string | null;
    onInjected: () => void;
    onQuerySent: () => void;
    showTip: boolean;
    initialMessages?: Message[];
}

export function ChatWindow({
    sessionId, mode, hints, onHints, wikiName,
    injectedQuery, onInjected, onQuerySent, showTip,
    initialMessages = [],
}: Props) {
    const { messages, streaming, error, send } = useQueryStream(sessionId, onHints, initialMessages, onQuerySent);
    const [input, setInput] = useState("");
    const [noCache, setNoCache] = useState(false);
    const [timeoutSeconds, setTimeoutSeconds] = useState(readTimeoutSetting);
    const [showSettings, setShowSettings] = useState(false);
    const messagesRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLTextAreaElement>(null);

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
        send(q, noCache, timeoutSeconds);
    };

    const handleChipClick = useCallback((value: string) => {
        send(value, noCache, timeoutSeconds);
    }, [send, noCache, timeoutSeconds]);

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
                                onClose={() => setShowSettings(false)}
                            />
                        )}
                    </div>
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
