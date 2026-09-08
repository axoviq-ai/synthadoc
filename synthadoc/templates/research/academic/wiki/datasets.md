---
title: Datasets
status: draft
confidence: low
type: concept
sources: []
---

# Datasets

Research datasets used and produced. Populate by ingesting dataset documentation and data dictionaries.

Each dataset record captures:

- **Dataset identity** — name, version, collection date, PI/owner, storage location, access restrictions
- **Source and collection method** — how data was collected (survey / administrative records / sensor / web scrape / experiment / secondary source), collection period
- **Sample** — population, n, geographic coverage, time period
- **Variables** — variable list with name, type, definition, units, missing value coding; codebook reference
- **Quality notes** — known issues (non-response bias, measurement error, attrition), data cleaning steps applied
- **License and privacy** — access license, IRB number, PII present and how handled, sharing constraints
- **Usage history** — which studies and publications used this dataset (link to [[papers]])

**How to populate:**

1. Ingest your data dictionary or codebook:
   ```
   synthadoc ingest docs/datasets/<dataset>-codebook.pdf -w <wiki>
   ```

Cross-link to [[methodology]], [[findings]], and [[papers]].
