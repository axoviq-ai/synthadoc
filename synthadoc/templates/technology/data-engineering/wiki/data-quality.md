---
title: Data Quality
status: draft
confidence: low
type: concept
sources: []
---

# Data Quality

Data quality check results and data reliability standards. Populate by ingesting Great Expectations suites, dbt test results, and quality dashboards.

Each data quality record captures:

- **Quality dimensions** — completeness (% non-null for required fields), uniqueness (deduplication rate), timeliness (freshness SLA adherence), accuracy (referential integrity pass rate), consistency (cross-system agreement rate)
- **Quality checks** — check name, dataset/column targeted, check type (not-null / unique / range / regex / referential / custom), threshold, last run result (pass/fail/warning), failure rate trend
- **Quality score** — composite quality score per dataset, trend over 30/90 days, owner-facing dashboard link
- **Incident history** — past quality failures, root cause, fix applied, preventive measures added
- **SLA tracking** — which datasets have a data quality SLA, SLA adherence rate over 30 days, breach escalation log

Cross-link to [[datasets]], [[pipelines]], [[data-governance]], and [[lineage]].
