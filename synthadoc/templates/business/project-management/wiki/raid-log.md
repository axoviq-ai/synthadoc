---
title: RAID Log
status: draft
confidence: low
type: concept
sources: []
---

# RAID Log

Risks, Assumptions, Issues, and Dependencies tracker for all active projects. Populate by ingesting RAID log exports.

Each RAID entry captures:

- **Entry identity** — ID, project (link to [[projects]]), entry type (Risk / Assumption / Issue / Dependency), date raised, raised by
- **Description** — what the risk/assumption/issue/dependency is; current state
- **Risk attributes** (for Risks): likelihood (High / Medium / Low), impact (High / Medium / Low), risk score (L×I), risk type (schedule / budget / scope / quality / resource / external)
- **Response/mitigation** — planned response (avoid / mitigate / transfer / accept); specific mitigation actions; owner; target date
- **Status** — Open / Monitoring / Escalated / Closed; resolution description for closed items
- **Dependencies** (for Dependencies): dependent-on team or system, what is needed, by when, consequence if not met

**How to populate:**

1. Ingest your RAID log spreadsheet:
   ```
   synthadoc ingest docs/raid-log.xlsx -w <wiki>
   ```

Cross-link to [[projects]], [[project-charters]], [[stakeholder-map]], and [[status-reports]].
