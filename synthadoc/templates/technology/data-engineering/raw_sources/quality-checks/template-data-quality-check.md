# Data Quality Check: [Check Suite Name]

> **How to use this form**
>
> This template follows the **DAMA DMBOK 2nd Ed., Chapter 13 — Data Quality** standard --
> the Data Management Body of Knowledge framework for defining, measuring, and improving
> data quality across the six standard quality dimensions.
> If you already have quality check documentation in another format, skip this form and ingest it directly.
>
> Reference: [DAMA DMBOK](https://www.dama.org/cpages/body-of-knowledge)
>
> 1. Copy this file and rename it (e.g. `orders-fact-quality-checks.md`)
> 2. Fill in all sections; keep the Rules table in sync with your dbt tests or Great Expectations suite
> 3. Run: `synthadoc ingest raw_sources/quality-checks/<filename>.md -w <wiki>`
>
> Re-ingest after each quarterly quality review or when new rules are added.

---

## Quality Check Identity

- **Check suite name:**
- **Dataset:** (link to [[datasets]])
- **Owner:** (team or individual responsible for quality)
- **Check frequency:** (per pipeline run / daily / weekly)
- **Last reviewed:** YYYY-MM-DD
- **Tool:** (dbt tests / Great Expectations / custom SQL / Monte Carlo)

---

## Quality Dimensions Assessed

*Check all that apply to this dataset and describe what each means in this context.*

- [ ] **Completeness** — required fields are populated; row counts are within expected range
- [ ] **Uniqueness** — no duplicate rows on defined primary key(s)
- [ ] **Validity** — field values conform to defined domain (type, format, allowed values)
- [ ] **Consistency** — values agree across systems or related tables (referential integrity)
- [ ] **Timeliness** — data arrives and is processed within the SLA window
- [ ] **Accuracy** — values correctly represent the real-world entity or event they describe

---

## Rules

*One row per rule. Rule ID format: `DQ-<dataset-short>-NNN`.*

| Rule ID | Dimension | Field(s) | Rule expression | Threshold | Severity |
|---------|-----------|----------|-----------------|-----------|----------|
| DQ-001 | Completeness | `customer_id` | NOT NULL | 100% non-null | Error |
| DQ-002 | Uniqueness | `order_id` | UNIQUE | 0 duplicates | Error |
| DQ-003 | Validity | `status` | IN ('pending','active','closed') | 100% valid | Error |
| DQ-004 | Timeliness | `load_timestamp` | MAX(load_timestamp) within 2h of run time | ≤ 2 hours | Warning |
| | | | | | |

*Severity: **Error** = pipeline fails and alerts on-call; **Warning** = logged, does not block.*

---

## Baseline Metrics

*Measured values before this check suite was introduced, or at the last quarterly review.*

| Rule ID | Baseline value | Measured on | Notes |
|---------|---------------|-------------|-------|
| DQ-001 | 99.97% non-null | YYYY-MM-DD | 120 nulls in legacy data |
| DQ-002 | 0 duplicates | YYYY-MM-DD | |
| | | | |

---

## Findings

*Log every rule failure after this suite goes live.*

| Date | Rule ID | Records failed | % of total | Action taken |
|------|---------|---------------|------------|--------------|
| | | | | |
| | | | | |

---

## Remediation Log

*For each substantive fix applied as a result of a finding — what was done and why.*

| Date | Rule ID | Root cause | Fix applied | Preventive measure added |
|------|---------|-----------|-------------|--------------------------|
| | | | | |
