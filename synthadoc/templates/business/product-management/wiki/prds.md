---
title: PRDs
status: draft
confidence: low
type: concept
sources: []
---

# Product Requirements Documents

PRD library indexed by feature area. Populate by ingesting PRD documents from `raw_sources/specs/`.

Each PRD captures:

- **Feature identity** — feature name, PM owner, engineering DRI, design owner, target release, status (draft / approved / in dev / shipped)
- **Problem statement** — who has the problem, what happens when they encounter it, size of the problem (users affected, frequency)
- **Goals and success metrics** — measurable metric, baseline, target, how measured; explicit non-goals
- **User stories** — as a [persona], I want to [action], so that [outcome]; acceptance criteria per story
- **Proposed solution** — high-level solution description; Figma link; key user flows
- **Technical considerations** — constraints, dependencies, risks for engineering
- **Rollout plan** — release strategy (GA / gated / feature flag), beta criteria, full rollout criteria, rollback plan
- **Dependencies and open questions** — blocking dependencies, unresolved decisions

**How to add a PRD:**

1. Copy `raw_sources/specs/template-prd.md`, fill it in through the review process, then:
   ```
   synthadoc ingest raw_sources/specs/<feature>.md -w <wiki>
   ```

Cross-link to [[customer-research]], [[roadmap]], and [[product-metrics]].
