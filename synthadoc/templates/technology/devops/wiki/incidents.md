---
title: Incidents
status: draft
confidence: low
type: concept
sources: []
---

# Incidents

Incident log for all production services. Populate by ingesting incident reports from `raw_sources/incidents/`.

Each incident record captures:

- **Incident identity** — incident ID, title, severity (SEV1–SEV4), service(s) affected, incident commander, status
- **Customer impact** — what users experienced, how many requests or users affected, duration of impact
- **Timeline** — alert fire time, IC assigned, root cause identified, mitigation applied, service restored, incident resolved (all in UTC)
- **Root cause** — the underlying cause, not just the proximate symptom
- **Impact quantification** — error rate at peak, duration in minutes/hours, estimated revenue impact
- **Mitigation** — what was done to restore service
- **Action items** — follow-up tasks, owners, priority, due dates
- **Post-mortem** — whether a post-mortem is required; link to [[post-mortems]] when written

Cross-link to [[post-mortems]], [[alerts]], [[slos]], and [[services]].
