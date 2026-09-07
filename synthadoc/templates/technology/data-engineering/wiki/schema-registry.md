---
title: Schema Registry
status: draft
confidence: low
type: concept
sources: []
---

# Schema Registry

Schema definitions and compatibility rules for all data contracts. Populate by ingesting Confluent Schema Registry exports, Avro/Protobuf schemas, and dbt model schemas.

Each schema record captures:

- **Schema identity** — schema name, subject (typically `<topic>-value` for Kafka), format (Avro / Protobuf / JSON Schema / dbt YAML), version, last updated
- **Schema definition** — fields with name, type, nullability, default, documentation string
- **Compatibility mode** — BACKWARD / FORWARD / FULL / NONE; what this means for producers and consumers
- **Breaking change policy** — what constitutes a breaking change for this schema, required migration steps, consumer notification process
- **Version history** — version-to-version diffs, reasons for changes, migration guides for consumers
- **Consumers** — which pipelines and services consume this schema (link to [[pipelines]])

**How to populate:**

1. Ingest schemas from Confluent Schema Registry:
   ```
   synthadoc ingest docs/schemas/ --batch -w <wiki>
   ```
2. Ingest dbt schema YAML files: `synthadoc ingest models/ --batch -w <wiki>`

Cross-link to [[datasets]], [[pipelines]], [[lineage]], and [[data-governance]].
