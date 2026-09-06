---
title: Getting Started — Data Engineering
status: draft
confidence: low
type: concept
sources: []
---

# Getting Started — Data Engineering

## Recommended first ingests

**Your dbt README**
```
synthadoc ingest dbt/README.md -w <wiki>
```

**Airflow DAG docs**
```
synthadoc ingest airflow/dags/ --batch -w <wiki>
```

## Recommended web searches

- `dbt best practices documentation modular data warehouse` — dbt conventions
- `data catalog comparison Amundsen DataHub OpenMetadata` — catalog tooling
- `Great Expectations data quality framework tutorial` — quality testing
- `data mesh principles federated data ownership` — governance model
- `Apache Kafka schema registry Avro compatibility` — schema management

## First steps checklist

- [ ] Ingest your dbt README or warehouse overview doc
- [ ] Create a pipeline page for your highest-priority data pipeline
- [ ] Document your top 3 most-consumed datasets
- [ ] Ingest your data governance policy
- [ ] Run scaffold to build the index
