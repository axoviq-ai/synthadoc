---
title: System Design
status: draft
confidence: low
type: concept
sources: []
---

# System Design

High-level architecture and system design documents. Populate by ingesting architecture docs, design proposals, and sequence diagrams.

Each system design document captures:

- **Design identity** — title, scope (system / subsystem / cross-cutting concern), author, date, status (draft / reviewed / approved / superseded)
- **Problem statement** — the problem being solved and constraints (scale, latency, consistency requirements)
- **Architecture overview** — components, their responsibilities, and how they interact; data flow direction; synchronous vs. asynchronous communication
- **Data model** — key entities, relationships, data stores, and partitioning strategy; read vs. write patterns
- **Scalability and reliability** — horizontal scaling strategy, replication, failure modes and mitigations, traffic patterns and expected load
- **Security** — authentication, authorization, data at rest and in transit encryption, secrets management
- **Trade-offs accepted** — what was prioritized (consistency / availability / partition tolerance), why, and what alternatives were rejected
- **Related ADRs** — decisions that shaped this design (link to [[adrs]])

Cross-link to [[adrs]], [[services]], and [[apis]].
