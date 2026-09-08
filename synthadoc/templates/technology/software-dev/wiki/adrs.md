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

Cross-link to [[system-design]], [[services]], and [[tech-debt]].
