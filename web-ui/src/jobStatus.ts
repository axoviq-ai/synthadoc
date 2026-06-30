// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 William Johnason / axoviq.com

// Mirror of JobStatus enum in synthadoc/core/queue.py — keep in sync with that file.
export const JOB = {
    PENDING:    "pending",
    IN_PROGRESS: "in_progress",
    COMPLETED:  "completed",
    SKIPPED:    "skipped",
    FAILED:     "failed",
    DEAD:       "dead",
    CANCELLED:  "cancelled",
} as const;

export type JobStatusValue = typeof JOB[keyof typeof JOB];

// UI-level state machine for a single gap-callout ingest slot.
// Derived from JOB statuses but separate — "error" collapses FAILED/DEAD/CANCELLED,
// and "idle"/"loading" have no backend equivalent.
export const ENRICH = {
    IDLE:    "idle",
    LOADING: "loading",
    DONE:    "done",
    SKIPPED: "skipped",
    ERROR:   "error",
} as const;

export type EnrichState = typeof ENRICH[keyof typeof ENRICH];
