---
title: Stakeholder Map
status: draft
confidence: low
type: concept
sources: []
---

# Stakeholder Map

Stakeholder identification, analysis, and engagement plan for all active projects. Populate by ingesting stakeholder analysis documents.

Each stakeholder map entry captures:

- **Stakeholder identity** — name, title, organization/team
- **Power/interest classification** — power (high / low) and interest (high / low) → quadrant: Manage Closely / Keep Satisfied / Keep Informed / Monitor
- **Attitude toward project** — Champion / Supporter / Neutral / Skeptic / Blocker
- **Key interests and concerns** — what this stakeholder cares about; what they fear about the project
- **Engagement strategy** — how often to communicate, what channel (steering committee / 1:1 / email update / town hall), what information they need, who communicates with them
- **Influence relationships** — who this stakeholder can influence or be influenced by; leverage points
- **Status** — engagement status (on-side / needs attention / at risk)

**How to populate:**

1. Ingest your stakeholder analysis document:
   ```
   synthadoc ingest docs/stakeholder-analysis.md -w <wiki>
   ```

Cross-link to [[projects]], [[status-reports]], and [[raid-log]].
