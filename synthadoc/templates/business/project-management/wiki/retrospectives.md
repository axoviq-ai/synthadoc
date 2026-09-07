---
title: Retrospectives
status: draft
confidence: low
type: concept
sources: []
---

# Retrospectives

Sprint, phase, and project retrospective records. Populate by ingesting retrospective notes and action item logs.

Each retrospective record captures:

- **Retrospective identity** — project or team, sprint/phase/milestone, facilitator, date, attendees
- **Format** — retrospective format used (Start / Stop / Continue / 4Ls / Mad-Sad-Glad / Sailboat / other)
- **What went well** — practices, decisions, or behaviors to continue; named specifically enough to repeat
- **What didn't go well** — specific problems, friction points, or failures; named specifically enough to fix
- **Action items** — concrete improvement actions with owner and due date; not vague commitments ("we should communicate better") but specific steps ("add a 15-min sync on Tuesdays by YYYY-MM-DD, owner: PM")
- **Themes** — recurring themes across multiple retrospectives; systemic issues vs. one-off events
- **Action item follow-up** — status of action items from previous retrospective

**How to populate:**

1. Ingest retrospective notes after each sprint or project milestone:
   ```
   synthadoc ingest docs/retrospectives/ --batch -w <wiki>
   ```

Cross-link to [[projects]], [[status-reports]], and [[raid-log]].
