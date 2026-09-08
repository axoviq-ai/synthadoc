# Tech Spec: [Title — what this design solves]

> **How to use this form**
>
> This template follows the **Google Design Doc format / RFC 2119** -- the de facto standard for
> writing technical design documents and using requirement keywords (MUST, SHOULD, MAY).
> If you already have a design doc or RFC in another format, skip this form and ingest your document directly.
>
> Reference: [Google Design Doc Template](https://www.industrialempathy.com/posts/design-doc-template/)
>
> 1. Copy this file and rename it (e.g. `search-ranking-redesign.md`)
> 2. Fill in all sections before implementation begins; circulate for review
> 3. Run: `synthadoc ingest raw_sources/specs/<filename>.md -w <wiki>`
>
> Requirement keywords (MUST, SHOULD, MAY) follow RFC 2119 conventions.

---

## Document Identity

- **Title:**
- **Author(s):**
- **Reviewers:**
- **Status:** (Draft / In Review / Approved / Superseded)
- **Created:** YYYY-MM-DD
- **Last updated:** YYYY-MM-DD
- **Related ADRs:** (link to [[adrs]])

---

## Problem Statement

*What problem does this design solve? Who is affected and how severely?
Describe the current state and why it is inadequate. Be concrete — include error rates,
latency numbers, or user complaints that motivate this work.*

---

## Goals

*What must be true when this design is successfully implemented?
Keep goals measurable and verifiable (e.g. "P99 latency < 200 ms under 500 req/s").*

-

---

## Non-goals

*What is explicitly out of scope for this design? Listing non-goals prevents scope creep
and helps reviewers calibrate their feedback.*

-

---

## Background

*What does a reader need to know to understand this design?
Cover prior art, existing systems this design touches, and any constraints
(regulatory, organisational, or contractual) the design must respect.*

---

## Design

*The meat of the document. Describe the proposed solution at a level of detail sufficient
for a senior engineer to implement it without further clarification.
Include: component diagram, data flow, API contracts, data model changes,
concurrency model, and failure modes.*

### Architecture Overview

*(Component diagram or ASCII art showing the system after the change)*

### Data Model

*(New or changed schemas, tables, message formats)*

### API Contract

*(Endpoint signatures, request/response shapes, error codes — OpenAPI snippet or prose)*

### Error Handling and Failure Modes

*(What happens when each dependency fails? How does the system degrade gracefully?)*

### Performance and Scalability

*(Expected load, SLO targets, horizontal scaling strategy, caching approach)*

### Security

*(Authentication, authorisation, data at rest/in-transit encryption, secrets management)*

---

## Key Design Decisions

*Record every significant decision point — alternatives considered and the rationale for the choice made.*

| Decision | Options Considered | Choice | Rationale |
|----------|-------------------|--------|-----------|
| | | | |
| | | | |

---

## Implementation Plan

*Break the design into stages that can be reviewed, merged, and deployed independently.
Include estimated effort (S / M / L) and dependencies between stages.*

| Stage | Description | Effort | Depends on |
|-------|-------------|--------|------------|
| 1 | | | |
| 2 | | | |

---

## Alternatives Considered

*For designs or approaches you evaluated but rejected — explain what they were and why
you chose not to pursue them. This section saves future readers from re-deriving rejected paths.*

| Alternative | Why rejected |
|-------------|-------------|
| | |

---

## Open Questions

*Questions that must be resolved before or during implementation. Assign an owner and
target resolution date for each.*

| Question | Owner | Target date | Resolution |
|----------|-------|-------------|------------|
| | | | |

---

## Appendix

*(Supporting material: benchmarks, proof-of-concept results, external references, related tickets)*

-
