---
title: Alerts
status: draft
confidence: low
type: concept
sources: []
---

# Alerts

Alert rules and on-call routing for all services. Populate by ingesting your Prometheus alert rules, CloudWatch alarms, or alerting configuration files.

Each alert record captures:

- **Alert identity** — alert name, service (link to [[services]]), SLO it guards (link to [[slos]]), severity (page / ticket / warning)
- **Alert condition** — PromQL / CloudWatch expression, threshold, evaluation window, pending duration before firing
- **Routing** — PagerDuty / OpsGenie team, escalation policy, business hours vs. 24/7
- **Runbook link** — first response runbook (link to [[runbooks]])
- **Tuning history** — false positive rate, last threshold adjustment date, reason for change
- **Error budget impact** — burn rate (fast burn / slow burn), window, how long until the SLO window closes if this burn rate continues

Cross-link to [[slos]], [[runbooks]], [[incidents]], and [[services]].
