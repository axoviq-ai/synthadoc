---
title: Status Reports
status: draft
confidence: low
type: concept
sources: []
---

# Status Reports

Weekly and milestone status reports for all active projects. Populate by ingesting status report documents.

Each status report captures:

- **Report identity** — project (link to [[projects]]), reporting period, author, distribution list
- **Overall status** — RAG status (Red / Amber / Green) for: schedule, budget, scope, quality; one-sentence explanation for any non-Green status
- **Accomplishments this period** — bullet list of what was completed since the last report
- **Planned for next period** — what will be worked on in the coming period
- **Issues and decisions needed** — escalations or decisions required from the audience
- **RAID highlights** — top open risks and issues (link to [[raid-log]])
- **Budget update** — approved budget, spent-to-date, EAC, variance
- **Milestone status** — next 2–3 milestones with baseline and forecast dates

**How to populate:**

1. Ingest status reports as they are produced:
   ```
   synthadoc ingest docs/status-reports/ --batch -w <wiki>
   ```

Cross-link to [[projects]], [[raid-log]], [[project-schedules]], and [[stakeholder-map]].
