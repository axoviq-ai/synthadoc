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

// Display strings for the GapCallout ingest button and inline messages.
// Centralised here so every label has one definition and is easy to update.
export const ENRICH_LABEL = {
    // Button face text per state
    BTN_IDLE_URL:    "Ingest",
    BTN_IDLE_SEARCH: "Enrich",
    BTN_LOADING:     "Ingesting…",    // "Ingesting…"
    BTN_DONE:        "Done ✓",         // "Done ✓"
    BTN_SKIPPED:     "Already indexed",
    BTN_BLOCKED:     "Blocked ✗",      // "Blocked ✗"
    BTN_ERROR:       "Failed",

    // Tooltips
    TIP_LOADING:   "Ingesting in background — polls every 3 s",
    TIP_INDEXING:  "Fetching pages found in search — polls every 3 s",

    // Fallback reason strings (used when the job carries no error message)
    REASON_HASH_SKIP:  "Content hash unchanged — no re-processing needed",
    REASON_INGEST_ERR: "Ingest failed",
    REASON_CANCELLED:  "Cancelled by user",
    REASON_NETWORK:    "Network error — server unreachable",
} as const;
