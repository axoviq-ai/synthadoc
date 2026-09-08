---
title: Incident Response
status: draft
confidence: low
type: concept
sources: []
---

# Incident Response

Incident response process and severity framework. Populate by ingesting your incident response playbook, post-mortems, and on-call documentation.

Each incident response record captures:

- **Severity definitions** — SEV1 (complete outage, all-hands), SEV2 (significant degradation, key customers affected), SEV3 (minor degradation, workaround available), SEV4 (cosmetic or low-impact); response time targets per severity
- **Roles** — Incident Commander (IC), Communications Lead, Technical Lead, Customer Liaison; who plays each role, how to hand off
- **Detection and declaration** — alert-to-acknowledgment SLA, criteria for declaring an incident vs. handling quietly, escalation triggers
- **Communication** — status page update cadence, internal Slack channel naming convention, executive escalation path, customer communication template
- **Mitigation vs. resolution** — distinction between "service restored" and "root cause fixed"; when to declare mitigation vs. resolution
- **Post-mortem requirements** — which severities require a written post-mortem, timeline (draft within 48 hrs, review within 5 days), blameless culture guidelines (link to [[post-mortems]])

Cross-link to [[runbooks]], [[engineering-practices]], and [[services]].
