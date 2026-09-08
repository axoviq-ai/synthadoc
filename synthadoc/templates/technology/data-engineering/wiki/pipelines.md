---
title: Pipelines
status: draft
confidence: low
type: concept
sources: []
---

# Pipelines

Catalog of all data pipelines. Populate by ingesting pipeline documentation from `raw_sources/pipelines/`.

Each pipeline record captures:

- **Pipeline identity** — pipeline name, owner team, orchestrator (Airflow / Prefect / dbt Cloud), DAG ID, date created
- **Data flow** — source system(s) and tables/paths, destination and tables/paths, transformation logic summary, dbt models involved
- **Schedule and SLA** — cron schedule, expected duration, data-available-by time, SLA breach escalation path
- **Quality and monitoring** — row count expectations, freshness check, schema validation (Great Expectations / dbt tests), alert routing on failure, retry policy
- **Lineage** — upstream pipeline dependencies (link to [[lineage]]), downstream consumers (dashboards, models, APIs)
- **Known issues** — open bugs, technical debt items, scheduled maintenance windows

Cross-link to [[datasets]], [[orchestration]], [[lineage]], and [[data-quality]].
