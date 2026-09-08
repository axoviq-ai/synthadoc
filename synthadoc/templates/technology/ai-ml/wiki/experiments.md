---
title: Experiments
status: draft
confidence: low
type: concept
sources: []
---

# Experiments

Log of all ML experiments. Populate by ingesting experiment records from `raw_sources/experiments/`.

Each experiment record captures:

- **Identity** — experiment ID, date, researcher, hypothesis, baseline being compared against
- **Configuration** — task, model architecture, base model/checkpoint, dataset (link to [[datasets]]), dataset split sizes, compute used, MLflow/W&B run URL
- **Hyperparameters** — learning rate, batch size, epochs/steps, optimizer, warmup steps, max sequence length (or other key parameters for the architecture)
- **Results** — primary metrics (accuracy, F1, BLEU, ROUGE, etc.) with delta vs. baseline; secondary metrics (inference latency p50/p99, GPU memory, training cost)
- **Analysis** — whether the hypothesis held, key observations, failure modes, next experiments to try
- **Artifacts** — model checkpoint path, evaluation report, confusion matrix or error analysis file

Cross-link to [[datasets]], [[models]], [[benchmarks]], and [[evaluation-methodology]].
