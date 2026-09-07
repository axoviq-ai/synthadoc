---
title: Technical Debt
status: draft
confidence: low
type: concept
sources: []
---

# Technical Debt

Technical debt register and prioritization. Populate by ingesting your tech debt backlog, architectural audit findings, and legacy system documentation.

Each tech debt item captures:

- **Item identity** — title, service or component affected (link to [[services]]), date identified, identifier, reporter
- **Debt type** — design debt (architectural shortcuts) / code debt (suboptimal implementation) / test debt (missing coverage) / documentation debt / infrastructure debt (outdated platform)
- **Description** — what the debt is and how it was incurred; the original trade-off that created it
- **Impact** — current pain: slower development velocity, higher incident rate, security exposure, onboarding friction, compliance risk; quantify where possible
- **Effort to resolve** — rough estimate (S / M / L / XL), which team owns the work, dependency on other teams
- **Priority** — priority tier (do next sprint / do this quarter / backlog / accept and document), prioritization rationale
- **Status** — open / in progress / resolved; link to the ticket or PR when resolved

**How to populate:**

1. Ingest your tech debt register or architectural audit:
   ```
   synthadoc ingest docs/tech-debt-register.md -w <wiki>
   ```

Cross-link to [[adrs]], [[services]], and [[engineering-practices]].
