---
title: Models
status: draft
confidence: low
type: concept
sources: []
---

# Models

Model registry and documentation for all trained and deployed models. Populate by ingesting model cards, training recipes, and deployment configs.

Each model record captures:

- **Model identity** — model name, version, task, team owner, training date, model card URL
- **Architecture** — base model or family, parameter count, context window, modality (text / vision / audio / multimodal)
- **Training** — dataset(s) used (link to [[datasets]]), training compute (GPU type, count, hours), key hyperparameters, training framework
- **Evaluation** — primary benchmark results (link to [[benchmarks]]), evaluation methodology (link to [[evaluation-methodology]]), held-out test set performance, known failure modes
- **Serving** — serving infrastructure (link to [[serving-infrastructure]]), hardware requirements (GPU type, VRAM), inference latency (p50/p99), throughput (requests/sec), serving cost
- **Limitations and risks** — known biases, out-of-distribution behavior, safety evaluation results, recommended use vs. not-recommended use
- **Lineage** — parent model (fine-tuned from), related experiments (link to [[experiments]])

Cross-link to [[experiments]], [[datasets]], [[benchmarks]], and [[serving-infrastructure]].
