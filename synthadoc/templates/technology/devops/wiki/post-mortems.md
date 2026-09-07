---
title: Post Mortems
status: draft
confidence: low
type: concept
sources: []
---

# Post Mortems

Blameless post-mortem library. Populate by ingesting post-mortem documents from your docs folder.

Each post-mortem captures:

- **Identity** — post-mortem ID (matches incident ID), incident title, severity, author, date written, review date
- **Executive summary** — one paragraph: what happened, how long it lasted, what was affected, what was done to fix it
- **Timeline** — detailed chronology with timestamps; what was known and what was done at each step
- **Root cause analysis** — the 5-why chain leading to the deepest causal factor; distinguish contributing factors from the root cause
- **Contributing factors** — all factors that made the incident worse or harder to detect/recover from (monitoring gaps, missing runbooks, pager fatigue, deployment process)
- **What went well** — detection speed, escalation, communication — things worth repeating
- **What went poorly** — gaps in on-call process, tooling, or documentation
- **Action items** — concrete, assignable improvements with owner and target date; track status
- **Lessons learned** — what the team will do differently

**How to populate:**

1. Ingest post-mortem documents:
   ```
   synthadoc ingest docs/post-mortems/ --batch -w <wiki>
   ```

Cross-link to [[incidents]], [[alerts]], [[runbooks]], and [[slos]].
