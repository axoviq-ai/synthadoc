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

**How to add an experiment:**

1. Copy `raw_sources/experiments/template-experiment.md` and rename it after the experiment
2. Fill in hypothesis and config before the run; results after
3. Run `synthadoc ingest raw_sources/experiments/<experiment>.md -w <wiki>`

Cross-link to [[datasets]], [[models]], [[benchmarks]], and [[evaluation-methodology]].
