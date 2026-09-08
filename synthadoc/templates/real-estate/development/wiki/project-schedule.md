---
title: Project Schedule
status: draft
confidence: low
type: concept
sources: []
---

# Project Schedule

Master schedule for all active development projects. Populate by ingesting Gantt charts, CPM schedules, and milestone reports.

Each project schedule record captures:

- **Schedule overview** — project name, total duration, schedule format (CPM / Gantt), last baseline date, current revision number
- **Key milestones** — NTP / groundbreaking, foundations complete, structure topped out, exterior envelope complete, MEP rough-in complete, drywall complete, final finishes, substantial completion, punch list complete, certificate of occupancy
- **Critical path activities** — activities on the critical path, float available on near-critical paths, predecessor/successor relationships for key items
- **Schedule delays** — delay events, responsible party (owner / contractor / weather / AHJ), days lost, recovery plan, adjusted substantial completion date
- **Float consumption** — original float, consumed float by period, remaining float on critical path
- **Look-ahead schedule** — 3-week look-ahead: activities planned this week, next week, and the week after; manpower plan

**How to populate:**

1. Ingest your CPM schedule baseline or Gantt chart export:
   ```
   synthadoc ingest docs/schedule/<project>-schedule.pdf -w <wiki>
   ```
2. Ingest monthly schedule updates or delay notices

Cross-link to [[contractors]], [[permits]], [[inspections]], and [[change-orders]].
