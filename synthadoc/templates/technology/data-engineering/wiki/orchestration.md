---
title: Orchestration
status: draft
confidence: low
type: concept
sources: []
---

# Orchestration

Data orchestration framework configuration and operational runbook. Populate by ingesting Airflow/Prefect/dbt Cloud configuration and operational guides.

Each orchestration record captures:

- **Framework** — Airflow version, executor (Celery / KubernetesExecutor / LocalExecutor), deployment (managed / self-hosted), worker count, queue configuration
- **DAG standards** — naming convention (`<domain>_<target>_<frequency>`), required metadata (owner, start_date, retries, SLA), default args template, prohibited patterns (no top-level DB calls in DAG files)
- **Failure handling** — retry policy defaults, on-failure callback (Slack / PagerDuty), SLA miss callback, dead-letter queue for tasks
- **Scheduler health** — scheduler heartbeat interval, DAG parse time SLA, executor slot utilization
- **Secrets** — how secrets are injected (Airflow Connections / environment variables / external secret manager), rotation procedure
- **Monitoring** — which metrics are tracked (DAG run duration, task failure rate, slot utilization), alert thresholds, dashboard link
- **Maintenance runbook** — how to clear failed DAG runs, how to add a new DAG, how to deprecate a DAG safely

**How to populate:**

1. Ingest your orchestration README or operational guide:
   ```
   synthadoc ingest airflow/README.md -w <wiki>
   ```

Cross-link to [[pipelines]], [[lineage]], and [[data-quality]].
