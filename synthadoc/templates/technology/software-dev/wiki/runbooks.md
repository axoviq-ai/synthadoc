---
title: Runbooks
status: draft
confidence: low
type: concept
sources: []
---

# Runbooks

Operational procedures for routine and emergency tasks. Populate by ingesting runbook documents from your ops wiki or docs folder.

Each runbook captures:

- **Runbook identity** — title, service (link to [[services]]), severity/use case (routine / escalation / disaster recovery), last reviewed date, owner
- **Preconditions** — required access (AWS IAM role, VPN, database credentials), tools needed, environment constraints
- **Steps** — numbered, concrete steps with exact commands, expected outputs, and decision branches; no ambiguous "check if…" steps
- **Escalation path** — when to escalate, who to contact, what information to provide; pager rotation and backup contact
- **Rollback procedure** — how to reverse the action if something goes wrong; rollback success criteria
- **Known issues** — past incidents where this runbook helped or failed; link to [[incidents]] or [[post-mortems]]

Cross-link to [[services]], [[incidents]], [[slos]], and [[alerts]].
