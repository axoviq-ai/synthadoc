# Experiment: [EXP-NNNN] — [Hypothesis or Short Title]

> **How to use this form**
>
> 1. Copy this file and rename it (e.g. `exp-0042-llm-rag-with-reranker.md`)
> 2. Fill in before the run (hypothesis, config), then complete results after
> 3. Run: `synthadoc ingest raw_sources/experiments/exp-0042-llm-rag-with-reranker.md -w <wiki>`
>
> Your MLflow / W&B run is the source of truth for raw metrics — this form
> captures the narrative context and cross-links for searchability.

---

## Experiment Identity

- **Experiment ID:** EXP-
- **Date:** YYYY-MM-DD
- **Researcher:** 
- **Hypothesis:** *What do you expect to happen and why?*
- **Baseline:** *(Link to previous experiment or model being compared against)*

---

## Configuration

- **Task:** (e.g. text classification / named entity recognition / RAG QA)
- **Model architecture:** 
- **Base model / checkpoint:** 
- **Dataset** (link to [[datasets]])**:** 
- **Dataset split:** train: N / val: N / test: N
- **Training compute:** GPU type, count, hours
- **MLflow / W&B run URL:** 

### Hyperparameters

| Parameter | Value |
|-----------|-------|
| Learning rate | |
| Batch size | |
| Epochs / steps | |
| Optimizer | |
| Warmup steps | |
| Max sequence length | |

---

## Results

### Primary metrics

| Metric | This run | Baseline | Delta |
|--------|----------|----------|-------|
| | | | |

### Secondary metrics (latency, memory, cost)

| Metric | Value |
|--------|-------|
| Inference latency p50 | ms |
| Inference latency p99 | ms |
| GPU memory peak | GB |
| Training cost | $ |

---

## Analysis

- **Did the hypothesis hold?** (yes / no / partially)
- **Key observations:** 
- **Failure modes or errors noted:** 
- **Next experiments to try:** 

---

## Artifacts

- Model checkpoint:
- Evaluation report:
- Confusion matrix / error analysis:
