---
title: Project Charters
status: draft
confidence: low
type: concept
sources: []
---

# Project Charters

Signed project charters for all authorized projects. Populate by ingesting charter documents from `raw_sources/charters/`.

Each project charter captures:

- **Charter identity** — project name, ID, sponsor, PM, start/end dates, status
- **Problem statement and objective** — the business problem or opportunity, and a measurable, time-bound success statement
- **Scope** — in-scope deliverables and explicitly out-of-scope items
- **Deliverables** — list with description, due date, and acceptance criteria for each deliverable
- **Stakeholders** — name, role, interest level, communication need
- **Budget** — approved total, breakdown (labor / tools / vendors / contingency)
- **Key milestones** — milestone name and target date
- **Top risks** — top 3–5 risks with likelihood, impact, and mitigation
- **Assumptions and constraints** — what the plan assumes, what limits the project
- **Approvals** — sponsor and PM signatures

**How to add a charter:**

1. Copy `raw_sources/charters/template-project-charter.md`, get sponsor approval, then:
   ```
   synthadoc ingest raw_sources/charters/<project>.md -w <wiki>
   ```

Cross-link to [[projects]], [[raid-log]], [[project-schedules]], and [[stakeholder-map]].
