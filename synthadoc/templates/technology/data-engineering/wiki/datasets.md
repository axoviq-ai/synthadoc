---
title: Datasets
status: draft
confidence: low
type: concept
sources: []
---

# Datasets

Data catalog for all managed datasets, tables, and data products. Populate by ingesting data catalog exports and dbt documentation.

Each dataset record captures:

- **Dataset identity** — dataset/table name, database, schema, data product owner, domain, classification (raw / staged / mart / aggregate)
- **Description** — what this dataset represents, primary use cases, business definition of key columns
- **Schema** — column names, data types, nullability, descriptions; primary key and foreign key relationships; partition column and strategy
- **Freshness** — update schedule, SLA (data available by what time), last successful run, freshness check result
- **Row counts and volume** — current row count, growth rate, storage size, retention policy
- **Lineage** — upstream source tables/systems, downstream consumers (dashboards, ML models, APIs) — link to [[lineage]]
- **Data quality** — active quality checks, last run results, known data issues or quirks

**How to populate:**

1. Ingest your dbt docs build:
   ```
   synthadoc ingest target/catalog.json -w <wiki>
   ```
2. Ingest your data catalog tool export (DataHub / Amundsen / OpenMetadata)

Cross-link to [[pipelines]], [[lineage]], [[data-quality]], and [[schema-registry]].
