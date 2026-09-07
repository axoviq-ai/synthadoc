---
title: SLOs — Service Level Objectives
status: draft
confidence: low
type: concept
sources: []
---

# SLOs — Service Level Objectives

SLI and SLO definitions for each service. Populate by ingesting SLO documentation and error budget reports.

Each SLO record captures:

- **Service** — service name (link to [[services]]), team owner, SLO review cadence
- **SLI type** — availability (% of successful requests), latency (p99 < N ms), error rate (% of non-5xx), freshness (data age < N minutes for data services)
- **SLO target** — numerical target (e.g. 99.9% availability over a 30-day rolling window), agreed upon with stakeholders
- **Measurement window** — rolling 30-day / calendar month / trailing 28 days
- **Data source** — metric name in Prometheus / CloudWatch / Datadog; how SLI is calculated (numerator / denominator queries)
- **Error budget** — error budget in minutes/hours per window, burn rate calculation, current status (budget remaining / exhausted)
- **Consequences of burn** — what happens when the error budget is exhausted (feature freeze / incident response escalation / executive notification)
- **Alert rules** — fast-burn and slow-burn alert thresholds (link to [[alerts]])

**How to populate:**

1. Ingest your SLO documentation:
   ```
   synthadoc ingest docs/slos/ --batch -w <wiki>
   ```
2. Ingest the Google SRE workbook chapter on SLOs

Cross-link to [[services]], [[alerts]], [[incidents]], and [[post-mortems]].
