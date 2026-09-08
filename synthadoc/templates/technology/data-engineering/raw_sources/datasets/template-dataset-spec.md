# Dataset Spec: [Dataset / Table Name]

> **How to use this form**
>
> This template follows the **W3C DCAT-2 (Data Catalog Vocabulary) + DAMA DMBOK 2nd Ed.** standard --
> the W3C standard for data catalog interoperability, combined with DAMA's data management
> body of knowledge for enterprise data governance.
> If you already have a dataset specification in another format, skip this form and ingest it directly.
>
> Reference: [W3C DCAT-2](https://www.w3.org/TR/vocab-dcat-2/)
>
> 1. Copy this file and rename it (e.g. `orders-fact-table.md`)
> 2. Fill in all sections; keep the schema section in sync with your dbt model YAML
> 3. Run: `synthadoc ingest raw_sources/datasets/<filename>.md -w <wiki>`
>
> Re-ingest whenever the schema, owner, or classification changes.

---

## Dataset Identity

- **Dataset / table name:**
- **Database / schema:**
- **Owner team:**
- **Domain:** (e.g. Commerce / Finance / Customer / Operations)
- **Classification:** (Public / Internal / Confidential / Restricted)
- **DCAT type:** (dcat:Dataset / dcat:DataService / dcat:Catalog)

---

## Description

**What this dataset contains:**
*(What entities or events are represented? What is the grain — one row = one what?)*

**Business purpose:**
*(What business questions does this dataset answer? Who uses it and for what?)*

**Who uses this dataset:**
*(Teams, dashboards, ML models, APIs — be specific.)*

---

## Schema

*Document every column. Mark PII fields with `[PII]` in the description.*

| Column name | Type | Nullable | Description | Example value |
|-------------|------|----------|-------------|---------------|
| | | | | |
| | | | | |

- **Primary key:**
- **Foreign keys:**
- **Partition column(s):**

---

## Source

- **Source system(s):** (e.g. "Postgres orders DB", "Stripe webhooks", "Salesforce")
- **Ingestion method:** (CDC / batch extract / streaming / API pull)
- **Ingestion frequency:** (real-time / hourly / daily / weekly)
- **SLA — data available by:** HH:MM UTC
- **Pipeline(s) that produce this dataset:** (link to [[pipelines]])

---

## Lineage

- **Upstream datasets / tables:** (link to [[lineage]])
- **Downstream consumers:** (dashboards, ML models, APIs, other datasets — list by name)

---

## Partitioning

- **Partition keys:** (column(s) used for partitioning — e.g. `event_date`)
- **Retention period:** (e.g. "90 days rolling" / "7 years" / "indefinite")
- **Approximate storage size:** (GB / TB)

---

## Data Quality Expectations

*List the quality rules this dataset must satisfy on every load.*

| Dimension | Expectation | Measurement method |
|-----------|-------------|--------------------|
| Completeness | % non-null for required fields ≥ N% | dbt not-null test |
| Uniqueness | 0 duplicate rows on primary key | dbt unique test |
| Validity | `status` column in set {active, inactive, pending} | dbt accepted-values test |
| Timeliness | Max `load_timestamp` within N hours of `event_time` | Custom SQL check |
| Accuracy | Referential integrity: `customer_id` exists in customers table | dbt relationship test |
| | | |

---

## Access and Governance

- **Who can access this dataset:** (self-service via data catalog / approval required / restricted)
- **Access request process:** (link to internal access request form or procedure)
- **PII / sensitive fields:** (list all fields tagged as PII or sensitive; note masking approach)
- **Applicable regulations:** (GDPR / CCPA / HIPAA / PCI-DSS — which apply and why)
- **Data steward:** (name / team responsible for governance decisions)

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| | Initial specification | |
| | | |
