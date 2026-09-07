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

**How to add a pipeline:**

1. Copy `raw_sources/pipelines/template-pipeline.md` and rename it after the pipeline
2. Fill in source, destination, schedule, and quality checks
3. Run `synthadoc ingest raw_sources/pipelines/<pipeline>.md -w <wiki>`

Cross-link to [[datasets]], [[orchestration]], [[lineage]], and [[data-quality]].
