---
title: Architecture Decision Records
status: draft
confidence: low
type: concept
sources: []
---

# Architecture Decision Records

Index of all architectural decisions. ADRs are never deleted — superseded records link to their replacement. Populate by ingesting ADR files from `raw_sources/decisions/`.

Each ADR captures:

- **Identity** — ADR number (zero-padded, sequential), title (the decision made, not the problem), decision date, author
- **Status** — Proposed / Accepted / Deprecated / Superseded; if superseded, links to the ADR that replaces it
- **Context** — the forces at play (technological, political, social, project constraints) that made a decision necessary; value-neutral description of the problem space
- **Decision** — the chosen response stated in full sentences, active voice ("We will…"); specific enough to implement
- **Consequences** — positive outcomes, negative trade-offs, and risks accepted; what becomes easier or harder
- **Alternatives considered** — options evaluated and reason each was rejected

**How to add an ADR:**

1. Copy `raw_sources/decisions/template-adr.md` and name it `adr-<NNNN>-<short-title>.md`
2. Fill in context, decision, and consequences
3. Run `synthadoc ingest raw_sources/decisions/adr-<NNNN>-<short-title>.md -w <wiki>`

Cross-link to [[system-design]], [[services]], and [[tech-debt]].
