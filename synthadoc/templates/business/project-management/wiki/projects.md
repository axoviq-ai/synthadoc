---
title: Projects
status: draft
confidence: low
type: concept
sources: []
---

# Projects

Active and recently completed project registry. Populate by ingesting project charters and status reports from `raw_sources/charters/`.

Each project record captures:

- **Project identity** — project name, sponsor, project manager, start date, target end date, current status (On Track / At Risk / Off Track / Complete)
- **Objective and scope** — what the project is meant to accomplish; what is in scope and out of scope
- **Budget** — approved budget, spent-to-date, forecast at completion, variance explanation
- **Key milestones** — milestone name, target date, actual date, status (not started / in progress / complete)
- **Top risk** — the single most significant open risk and its mitigation plan (full RAID log: link to [[raid-log]])
- **Stakeholders** — sponsor, project manager, key stakeholders (link to [[stakeholder-map]])
- **Current status narrative** — 2–3 sentence executive summary of where the project stands this week

**How to add a project:**

1. Copy `raw_sources/charters/template-project-charter.md`, fill it in, then:
   ```
   synthadoc ingest raw_sources/charters/<project>.md -w <wiki>
   ```
2. Ingest status reports as the project progresses

Cross-link to [[project-charters]], [[raid-log]], [[project-schedules]], and [[stakeholder-map]].
