---
title: Compliance Monitoring
status: draft
confidence: low
type: concept
sources: []
---

# Compliance Monitoring

Continuous monitoring activities that detect compliance failures between formal audit cycles. Each monitoring activity record captures:

- **Activity identity** — monitoring activity name, ID, owner, and the control(s) or obligation(s) it monitors
- **Monitoring method** — what is measured (transaction sample, system report, data extraction, observation, reconciliation)
- **Data source** — where the monitoring data comes from (system name, report name, data feed)
- **Frequency** — how often the monitoring runs (daily, weekly, monthly, quarterly)
- **Population and sample** — full population size; sample size and selection method (random, risk-based)
- **Threshold / tolerance** — what constitutes an exception or flag; error rate that triggers escalation
- **Results log** — date of most recent run, number of items reviewed, exceptions identified, disposition of exceptions
- **Escalation path** — who is notified when exceptions exceed threshold; how quickly

Cross-link to [[controls]] for the control each activity monitors, [[audit-findings]] if monitoring identifies a finding, and [[risk-register]] for risks that monitoring is designed to detect.
