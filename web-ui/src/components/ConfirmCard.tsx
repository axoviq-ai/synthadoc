// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com
import { useEffect, useRef } from "react";

interface Props {
    message: string;
    yesLabel: string;
    noLabel: string;
    onConfirm: () => void;
    onDecline: () => void;
    timeoutSeconds?: number;
}

export default function ConfirmCard({
    message, yesLabel, noLabel, onConfirm, onDecline, timeoutSeconds = 120
}: Props) {
    const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    useEffect(() => {
        timerRef.current = setTimeout(onDecline, timeoutSeconds * 1000);
        return () => { if (timerRef.current) clearTimeout(timerRef.current); };
    }, []);
    const handleConfirm = () => {
        if (timerRef.current) clearTimeout(timerRef.current);
        onConfirm();
    };
    const handleDecline = () => {
        if (timerRef.current) clearTimeout(timerRef.current);
        onDecline();
    };
    return (
        <div className="confirm-card" style={{
            border: "1px solid var(--border, #ccc)",
            borderRadius: 6, padding: "12px 16px", margin: "8px 0",
        }}>
            <p style={{ marginBottom: 10 }}>{message}</p>
            <div style={{ display: "flex", gap: 8 }}>
                <button
                    onClick={handleConfirm}
                    className="confirm-yes-btn"
                    style={{ padding: "6px 12px", cursor: "pointer" }}
                >{yesLabel}</button>
                <button
                    onClick={handleDecline}
                    className="confirm-no-btn"
                    style={{ padding: "6px 12px", cursor: "pointer" }}
                >{noLabel}</button>
            </div>
        </div>
    );
}
