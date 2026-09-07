---
title: Evaluation Methodology
status: draft
confidence: low
type: concept
sources: []
---

# Evaluation Methodology

Evaluation standards, anti-contamination practices, and statistical rigor guidelines. Populate by ingesting evaluation guidelines and methodology docs.

Each evaluation methodology record captures:

- **Train/val/test protocol** — how splits are created (time-based / random / stratified), test set lock date, who has access to the test set (minimize to prevent contamination)
- **Anti-contamination checks** — deduplication between train and eval sets, n-gram overlap threshold, memorization detection procedure
- **Statistical significance** — sample size justification, confidence intervals reported, significance test used (McNemar / bootstrap / paired t-test), effect size reporting
- **Human evaluation** — annotation protocol, annotator qualification, inter-annotator agreement metric and threshold, disagreement resolution process
- **Automated metrics critique** — known limitations of primary metric; when automated metrics disagree with human judgment; use of multiple metrics
- **Reproducibility** — random seed policy, model checkpointing convention, compute and runtime reporting standards

**How to populate:**

1. Ingest evaluation methodology docs or papers:
   ```
   synthadoc ingest docs/evaluation-guidelines.md -w <wiki>
   ```

Cross-link to [[benchmarks]], [[datasets]], and [[experiments]].
