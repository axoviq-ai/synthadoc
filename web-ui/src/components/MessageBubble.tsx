// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com

import type { Message } from "../useQueryStream";

interface Props { msg: Message; }

export function MessageBubble({ msg }: Props) {
    const isUser = msg.role === "user";
    return (
        <div className={`bubble ${isUser ? "bubble-user" : "bubble-assistant"}`}>
            <p className="bubble-text">{msg.text}</p>
            {msg.citations && msg.citations.length > 0 && (
                <p className="bubble-citations">
                    Sources: {msg.citations.map((c) => `[[${c}]]`).join(", ")}
                </p>
            )}
            {msg.gapSuggestions && msg.gapSuggestions.length > 0 && (
                <div className="bubble-gap">
                    <p>Knowledge gap — try ingesting:</p>
                    <ul>
                        {msg.gapSuggestions.map((s) => (
                            <li key={s}><code>{s}</code></li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    );
}
