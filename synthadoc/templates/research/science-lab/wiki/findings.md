---
title: Findings
status: draft
confidence: low
type: concept
sources: []
---

# Findings

Validated experimental findings and their support status. Populate by synthesizing experiment results.

Each finding record captures:

- **Finding statement** — a precise, testable scientific claim (e.g. "Treatment X reduces expression of gene Y by 40% under conditions Z")
- **Supporting experiments** — which experiments provide evidence (link to [[experiments]]); n independent replicates
- **Statistical support** — statistical test, test statistic, p-value, effect size, confidence interval
- **Controls** — positive and negative controls used; their outcomes
- **Replication status** — how many independent replicates confirm the finding; any failures to replicate and possible explanations
- **Interpretation** — biological or scientific meaning of the finding; how it supports or challenges existing knowledge (link to [[literature-review]])
- **Implications** — what follow-up experiments this motivates; what mechanism is implied

**How to populate:**

1. Populate this page after completing and interpreting experiments (link to [[experiments]])
2. Ingest published findings: `synthadoc ingest "https://pubmed.ncbi.nlm.nih.gov/<PMID>/" -w <wiki>`

Cross-link to [[experiments]], [[publications]], [[hypotheses]], and [[raw-data]].
