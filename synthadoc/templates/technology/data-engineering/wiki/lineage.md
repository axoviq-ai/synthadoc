---
title: Lineage
status: draft
confidence: low
type: concept
sources: []
---

# Lineage

Data lineage map — upstream sources and downstream consumers for all datasets. Populate by ingesting dbt manifest, OpenLineage events, or data catalog lineage exports.

Each lineage record captures:

- **Dataset node** — dataset/table name, owner, domain
- **Upstream sources** — direct parent tables/systems with transformation applied; pipeline or job that produces this dataset (link to [[pipelines]])
- **Downstream consumers** — direct child datasets, dashboards, ML models, APIs, and reports that depend on this dataset; estimated number of users impacted if this dataset breaks
- **Change impact** — when a schema change is proposed, which downstream consumers are affected; notification workflow
- **Column-level lineage** — (where available) per-column source tracing; which columns flow into which downstream columns
- **Lineage freshness** — last time lineage graph was updated; stale lineage flags

Cross-link to [[datasets]], [[pipelines]], [[data-quality]], and [[orchestration]].
