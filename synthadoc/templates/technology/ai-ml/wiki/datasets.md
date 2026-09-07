---
title: Datasets
status: draft
confidence: low
type: concept
sources: []
---

# Datasets

Dataset catalog for all training, validation, and evaluation datasets. Populate by ingesting dataset documentation and data cards.

Each dataset record captures:

- **Dataset identity** — name, version, task domain, creation date, owner team, storage location
- **Source and collection** — data source (web scrape / annotation / synthetic / licensed), collection method, annotation process, inter-annotator agreement (if labeled)
- **Size and splits** — total examples, train/val/test split sizes, sampling strategy
- **Features** — schema (input format, label format), feature distributions, class balance
- **Quality** — data cleaning steps, deduplication method, known contamination risks (train/test leakage), quality metrics (annotation accuracy, noise rate)
- **License and privacy** — license (CC-BY / research-only / proprietary), PII present (yes/no — what PII, how mitigated), geographic/demographic representation
- **Usage history** — which models have been trained on this dataset (link to [[models]]), which experiments used it (link to [[experiments]])

**How to populate:**

1. Ingest dataset data cards:
   ```
   synthadoc ingest "https://huggingface.co/datasets/<dataset>" -w <wiki>
   ```
2. Ingest internal dataset documentation

Cross-link to [[experiments]], [[models]], and [[evaluation-methodology]].
