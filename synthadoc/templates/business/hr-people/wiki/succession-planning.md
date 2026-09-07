---
title: Succession Planning
status: draft
confidence: low
type: concept
sources: []
---

# Succession Planning

Succession plans for critical roles and key talent retention strategy. Populate by ingesting succession planning documents and talent review outputs.

Each succession planning record captures:

- **Critical role** — role title, current incumbent, why the role is critical (unique skills, key relationships, regulatory requirement)
- **Succession candidates** — for each candidate: name, current role, readiness assessment (Ready Now / Ready in 1–2 years / Ready in 3+ years), development gaps
- **Development actions** — specific actions for each successor (stretch assignment, mentorship, training, external coaching), owner, timeline
- **Bench strength** — how many ready-now successors exist for each critical role; single points of failure (roles with no successor)
- **Retention risk** — flight risk assessment for key talent, retention levers available (compensation, equity refresh, role expansion)
- **Talent review cadence** — how often succession plans are reviewed, who participates (HR, managers, C-suite), documentation and confidentiality

**How to populate:**

1. Ingest your talent review output or succession planning document:
   ```
   synthadoc ingest docs/succession-planning.pdf -w <wiki>
   ```

Cross-link to [[job-frameworks]], [[performance-management]], and [[org-structure]].
