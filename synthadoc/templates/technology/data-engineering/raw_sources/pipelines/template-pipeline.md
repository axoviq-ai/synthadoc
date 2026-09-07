# Data Pipeline: [Pipeline Name]

> **How to use this form**
>
> 1. Copy this file and rename it (e.g. `orders-to-dwh-daily.md`)
> 2. Fill in the pipeline details — use your Airflow/Prefect DAG definition as the source
> 3. Run: `synthadoc ingest raw_sources/pipelines/orders-to-dwh-daily.md -w <wiki>`
>
> Re-ingest whenever the pipeline's SLA, schema, or ownership changes.

---

## Pipeline Identity

- **Pipeline name:** 
- **Owner team:** 
- **Primary contact:** 
- **Date created:** YYYY-MM-DD
- **Last updated:** YYYY-MM-DD
- **Orchestrator:** (Airflow / Prefect / dbt Cloud / custom)
- **DAG ID / job name:** 

---

## Data Flow

- **Source system(s):** (e.g. Postgres orders DB, Stripe webhooks, S3 raw logs)
- **Source tables / paths:** 
- **Destination:** (Snowflake / BigQuery / Redshift / S3 / Kafka topic)
- **Destination tables / paths:** 
- **Transformation logic summary:** 
- **dbt model(s) involved:** (if using dbt)

---

## Schedule & SLA

- **Schedule (cron):** `0 6 * * *` (example: daily at 06:00 UTC)
- **Expected duration:** minutes
- **SLA — data available by:** HH:MM UTC
- **SLA breach escalation:** who is notified, within how many minutes

---

## Quality & Monitoring

- **Row count expectation:** min N rows, max N rows
- **Freshness check:** must run within N hours of last run
- **Schema validation:** (Great Expectations / dbt tests / custom) — which tests run
- **Alert on failure:** (PagerDuty / Slack channel — `#data-alerts`)
- **Retry policy:** N retries with N-minute backoff

---

## Lineage

- **Depends on pipelines:** 
- **Downstream consumers:** (dashboards / models / APIs that consume this pipeline's output)

---

## Known Issues & TODOs

-
