---
title: Getting Started — AI/ML
status: draft
confidence: low
type: concept
sources: []
---

# Getting Started — AI/ML

## Recommended first ingests

**Papers With Code SOTA benchmarks**
```
synthadoc ingest "https://paperswithcode.com/sota" -w <wiki>
```

**Hugging Face model card for your base model**
```
synthadoc ingest "https://huggingface.co/<org>/<model>" -w <wiki>
```

## Recommended web searches

- `"<task name>" state of the art benchmark 2024 arxiv` — SOTA for your task
- `MLflow experiment tracking getting started tutorial` — experiment management
- `model card template responsible AI documentation Google` — model documentation
- `"<model architecture>" training recipe best practices` — training tips
- `ML evaluation train test split data contamination` — evaluation rigor

## First steps checklist

- [ ] Ingest the paper for your current baseline model
- [ ] Create an experiment page for your most recent training run
- [ ] Ingest your dataset documentation
- [ ] Create a benchmark page for your primary evaluation metric
- [ ] Run scaffold to build the index
