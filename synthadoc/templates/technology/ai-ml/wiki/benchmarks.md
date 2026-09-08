---
title: Benchmarks
status: draft
confidence: low
type: concept
sources: []
---

# Benchmarks

Benchmark definitions and current results for all evaluated models. Populate by ingesting benchmark papers and evaluation reports.

Each benchmark record captures:

- **Benchmark identity** — benchmark name, task domain (QA / classification / generation / reasoning / retrieval), citation, dataset used, license
- **Metric** — primary metric name, how it is computed (exact match / F1 / BLEU / ROUGE-L / BERTScore / NDCG), metric interpretation (higher is better / lower is better)
- **Evaluation setup** — prompt format, few-shot vs. zero-shot, temperature, context length limit, scoring script
- **Current results table** — model name, score, parameter count, evaluation date

| Model | Score | Params | Eval Date |
|-------|-------|--------|-----------|
| | | | |

- **SOTA reference** — current state-of-the-art score, model name, source paper
- **Notes on contamination** — whether benchmark data may appear in model training; caution flags

Cross-link to [[models]], [[experiments]], and [[evaluation-methodology]].
