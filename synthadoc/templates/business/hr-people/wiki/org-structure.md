---
title: Org Structure
status: draft
confidence: low
type: concept
sources: []
---

# Org Structure

Organizational design, reporting relationships, and team structure. Populate by ingesting org chart exports and org design documents.

Each org structure record captures:

- **Organizational layers** — number of management layers (CEO to IC), target spans of control (how many direct reports per manager), and rationale
- **Team structure** — team name, team type (functional / cross-functional / squad / chapter), team mission, size, manager
- **Reporting lines** — who reports to whom; dotted-line vs. solid-line reporting; matrix structure description if applicable
- **Department / function breakdown** — department heads, department size, sub-team breakdown, headcount by function vs. G&A vs. R&D ratio
- **Key roles and responsibilities** — DRI model, role descriptions for critical positions, decision authority matrix (RACI or similar)
- **Recent changes** — reorgs, team mergers, new functions created, and rationale
- **Planned changes** — future org evolution, headcount plan by team, new roles to be created

**How to populate:**

1. Export your org chart and ingest:
   ```
   synthadoc ingest docs/org-chart.pdf -w <wiki>
   ```

Cross-link to [[job-frameworks]], [[succession-planning]], and [[hr-policies]].
