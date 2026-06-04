// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com

interface Props {
    hints: string[];
    onSelect: (hint: string) => void;
}

export function HintChips({ hints, onSelect }: Props) {
    if (hints.length === 0) return null;
    return (
        <div className="hint-chips">
            {hints.map((h) => (
                <button key={h} className="hint-chip" onClick={() => onSelect(h)}>
                    {h}
                </button>
            ))}
        </div>
    );
}
