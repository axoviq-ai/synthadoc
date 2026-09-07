---
title: Job Frameworks
status: draft
confidence: low
type: concept
sources: []
---

# Job Frameworks

Job family and leveling framework. Populate by ingesting your career ladder or leveling framework documents.

Each job framework record captures:

- **Job family scope** — what work this family covers, which departments it spans, how it differs from adjacent families
- **Career levels** — IC1 through Staff/Principal (or equivalent); Manager / Director / VP / C-level tracks; whether IC and Management tracks are separate or merge
- **Scope and impact at each level** — the size and complexity of problems at each level, independence vs. direction required, team/company scope of impact
- **Competency expectations** — for each level: technical/functional skills with observable behavioral indicators; collaboration, communication, and leadership expectations
- **Typical next roles** — what roles people typically move into from this level/family; lateral moves available
- **Promotion criteria** — evidence required for promotion, calibration process, time-in-level expectations (if any), skip-level promotion policy
- **Compensation alignment** — link to [[compensation]] for salary band information at each level

**How to populate:**

1. Ingest your career ladder documentation:
   ```
   synthadoc ingest docs/career-ladders/ --batch -w <wiki>
   ```
2. Ingest benchmark frameworks (e.g. Radford SWE levels, Levels.fyi data)

Cross-link to [[compensation]], [[performance-management]], and [[succession-planning]].
